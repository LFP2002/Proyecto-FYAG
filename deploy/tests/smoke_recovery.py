"""OBS-007: real HTTPS, Redis, worker and SMTP, exclusively in the disposable OBS-007 lab."""
import argparse
from http.client import HTTPSConnection
from http.cookies import SimpleCookie
import json
import re
import socket
import ssl
import subprocess
from time import monotonic, sleep
from urllib.request import urlopen

HOST = 'fyag-obs007.example.org'  # Reserved example domain; always connect by loopback.
OLD = 'Sintetica-Inicial-OBS007!92'
NEW = 'Sintetica-Renovada-OBS007!84'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('env_file')
    parser.add_argument('lab_override')
    parser.add_argument('ca')
    args = parser.parse_args()
    compose = ['docker', 'compose', '-p', 'fyag-obs007-lab', '--env-file', args.env_file,
               '-f', 'compose.production.yaml', '-f', 'deploy/compose.production.smtp.yaml', '-f', args.lab_override]
    origin = f'https://{HOST}:18497'
    tls = ssl.create_default_context(cafile=args.ca)

    def docker(*command):
        subprocess.run([*compose, *command], check=True)

    def call(method, path, body=None, headers=None):
        con = HTTPSConnection(HOST, 18497, timeout=8, context=tls)
        con._create_connection = lambda address, *options: socket.create_connection(('127.0.0.1', address[1]), *options)
        try:
            con.request(method, path, body, headers or {})
            res = con.getresponse()
            return res.status, res.headers, res.read()
        finally:
            con.close()

    def post(path, data):
        status, headers, body = call('GET', '/api/auth/csrf/')
        assert status == 200, status
        cookie = SimpleCookie(headers['Set-Cookie'])['csrftoken']
        return call('POST', '/api/auth/' + path, json.dumps(data), {
            'Origin': origin, 'Content-Type': 'application/json', 'X-CSRFToken': json.loads(body)['csrfToken'],
            'Cookie': f'csrftoken={cookie.value}',
        })

    def mail(path):
        with urlopen(f'http://127.0.0.1:18098/api/v1/{path}', timeout=4) as response:
            return json.load(response)

    def receive(email, previous):
        deadline = monotonic() + 35
        while monotonic() < deadline:
            for item in mail('messages')['messages']:
                if item['ID'] not in previous and any(t['Address'] == email for t in item['To']):
                    text = mail(f'message/{item["ID"]}')['Text']
                    match = re.search(re.escape(origin) + r'(/restablecer-clave)#token=([\w-]{43})(?![\w-])', text, re.ASCII)
                    if match:
                        return match.groups()
            sleep(0.5)
        raise AssertionError('No llegó el enlace a Mailpit')

    def login(email, password):
        return post('login/', {'email': email, 'password': password})

    normal, locked = (f'{handle}@{HOST}' for handle in ('normal', 'locked'))
    assert login(normal, OLD)[0] == 200
    for _ in range(5):
        assert login(locked, 'Incorrecta-Sintetica!')[0] == 401
    docker('exec', '-T', 'backend', 'python', 'manage.py', 'shell', '-c',
           "from django.conf import settings; from apps.usuarios.models import EstadoAcceso; "
           "assert settings.DATABASES['default']['NAME']=='fyag_obs007_lab'; "
           "assert settings.FYAG_BLOQUEOS_PERFIL=='produccion'; "
           f"assert EstadoAcceso.objects.get(usuario__email='{locked}').estado=='BLOQUEO_TEMPORAL'")

    for email in (normal, locked):
        previous = {item['ID'] for item in mail('messages')['messages']}
        if email == normal:
            docker('stop', 'verificacion_correo')
        assert post('recuperacion/solicitar/', {'email': email})[0] == 202
        if email == normal:
            docker('start', 'verificacion_correo')
        page, token = receive(email, previous)
        if email == normal:
            docker('restart', 'verificacion_correo')
        assert call('GET', page)[0] == 200
        payload = {'token': token, 'nueva_clave': NEW, 'confirmacion': NEW}
        status, headers, _ = post('recuperacion/confirmar/', payload)
        assert status == 204 and not headers.get_all('Set-Cookie'), status
        assert post('recuperacion/confirmar/', payload)[0] == 400
        status, headers, body = login(email, NEW)
        if status == 429 and email == locked:
            retry = int(headers['Retry-After'])
            assert 0 < retry <= 61
            sleep(retry + 1)  # Respetar el límite real; no borrar contadores de Redis.
            status, headers, body = login(email, NEW)
        assert status == 200 and 'fyag_refresh' in SimpleCookie(headers['Set-Cookie']), status
        assert login(email, OLD)[0] == 401
        print('OK: enlace por SMTP, confirmación, login nuevo y rechazo de reutilización', flush=True)

    docker('exec', '-T', 'backend', 'python', 'manage.py', 'shell', '-c',
           "from apps.usuarios.models import EstadoAcceso, RecuperacionCorreoEvento; "
           f"assert EstadoAcceso.objects.get(usuario__email='{locked}').estado=='NORMAL'; "
           f"assert RecuperacionCorreoEvento.objects.filter(usuario__email='{locked}', acceso_anterior='BLOQUEO_TEMPORAL').count()==1")
    print('OK: cola procesada tras reinicio y cuenta bloqueada recuperada bajo perfil productivo aislado.')


if __name__ == '__main__':
    main()
