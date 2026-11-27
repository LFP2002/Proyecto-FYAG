"""AUD-025: fresh fyag_aud025_tty only; run inside operaciones_seguridad.

The lab overlay connects this one-off container to the proxy's edge network
and disables its Docker log driver. The Linux PTY is not a transcript: only
fixed outcomes are printed, and credentials are used in memory over HTTPS.
"""
import errno
import json
import os
import pty
import re
import select
import signal
import socket
import ssl
import sys
from http.client import HTTPSConnection
from http.cookies import SimpleCookie
from pathlib import Path
from secrets import token_urlsafe
from time import monotonic
from urllib.parse import urlencode, urlsplit

import django
from django.conf import settings
from django.db import connection

OPERATOR, REFERENCE, REASON = 'operador-aud025', 'LAB-AUD025-DOBLE-APROBACION', 'Ensayo sintetico autorizado'
EMAIL = 'ti-aud025@worker025.test'
REFRESH = 'fyag_refresh'


class Terminal:
    def __enter__(self):
        return self

    def __init__(self, command, *args):
        connection.close()
        self.pid, self.fd = pty.fork()
        if self.pid == 0:
            try:
                with open('/dev/tty') as tty:
                    assert all(os.isatty(fd) for fd in (0, 1, 2))
                    assert os.tcgetpgrp(tty.fileno()) == os.getpgrp()
                os.execv(sys.executable, [sys.executable, '-m', 'config.security_cli', command, *args])
            finally:
                os._exit(125)
        self.buffer = b''
        self.deadline = monotonic() + 25
        self.eof = False

    def read(self):
        if self.eof:
            return False
        remaining = self.deadline - monotonic()
        if remaining <= 0 or not select.select([self.fd], [], [], remaining)[0]:
            raise TimeoutError
        try:
            chunk = os.read(self.fd, 4096)
        except OSError as exc:
            if exc.errno != errno.EIO:
                raise
            chunk = b''
        self.eof = not chunk
        self.buffer += chunk
        assert len(self.buffer) <= 16384
        return not self.eof

    def answer(self, prompt, value):
        while prompt not in self.buffer:
            assert self.read()
        self.buffer = self.buffer.split(prompt, 1)[1]
        os.write(self.fd, value.encode() + b'\n')

    def finish(self, code):
        while self.read():
            pass
        _, status = os.waitpid(self.pid, 0)
        self.pid = None
        assert os.waitstatus_to_exitcode(status) == code
        return self.buffer

    def __exit__(self, *_):
        self.buffer = b''
        os.close(self.fd)
        if self.pid is not None:
            try:
                os.kill(self.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            os.waitpid(self.pid, 0)


class Client:
    def __init__(self):
        self.cookies = {}
        self.origin = urlsplit(settings.FYAG_PUBLIC_BASE_URL)
        self.tls = ssl.create_default_context(cafile='/run/secrets/redis_ca')

    def request(self, path, status, *, payload=None, access=None, csrf=None):
        headers = {'Host': self.origin.netloc, 'Cookie': '; '.join(f'{k}={v}' for k, v in self.cookies.items())}
        if access:
            headers['Authorization'] = f'Bearer {access}'
        if payload is not None:
            headers.update({'Origin': self.origin.geturl(), 'X-CSRFToken': csrf, 'Content-Type': 'application/json'})
        conn = HTTPSConnection(self.origin.hostname, context=self.tls, timeout=8)
        conn._create_connection = lambda _addr, *args: socket.create_connection(('proxy', 8443), *args)
        try:
            conn.request('POST' if payload is not None else 'GET', path,
                         json.dumps(payload) if payload is not None else None, headers)
            response = conn.getresponse()
            assert response.status == status, f'{path.split("?")[0]}: HTTP {response.status}, esperado {status}'
            for name, value in response.getheaders():
                if name.lower() == 'set-cookie':
                    for key, cookie in SimpleCookie(value).items():
                        if cookie['max-age'] == '0':
                            self.cookies.pop(key, None)
                        else:
                            self.cookies[key] = cookie.value
            return json.loads(response.read())
        finally:
            conn.close()

    def post(self, action, payload, status):
        csrf = self.request('/api/auth/csrf/', 200)['csrfToken']
        return self.request(f'/api/auth/{action}/', status, payload=payload, csrf=csrf)

    def login(self, password, status=200):
        return self.post('login', {'email': EMAIL, 'password': password}, status)


def install(code):
    with Terminal('emitir_clave_instalacion', '--operador', OPERATOR, '--referencia', REFERENCE) as terminal:
        output = terminal.finish(code)
        match = re.search(rb'Clave de instalaci[^\r\n]+: ([A-Za-z0-9_-]{43})\r?\n', output)
        assert bool(match) == (code == 0)
        if match:
            assert b'Vence:' in output
            return match[1].decode()
        assert b'Error:' in output


def recovery(pk, reference, confirmation, code):
    with Terminal('recuperar_acceso_ti') as terminal:
        terminal.answer(b'cuenta TI: ', str(pk))
        terminal.answer(b'operador: ', OPERATOR)
        terminal.answer(b'dos personas: ', reference)
        terminal.answer(b'incluya secretos): ', REASON)
        if confirmation is not None:
            terminal.answer(f'escriba RECUPERAR {pk}: '.encode(), confirmation)
        output = terminal.finish(code)
        match = re.search(rb'Credencial temporal \(se muestra una vez\): ([A-Za-z0-9_-]{43})\r?\n', output)
        assert bool(match) == (code == 0)
        if match:
            assert b'Requiere cambio al ingresar.' in output
            return match[1].decode()
        assert (b'cancelada' if confirmation else b'no realizada') in output


def main():
    assert settings.DATABASES['default']['NAME'] == 'fyag_aud025_tty'
    assert settings.FYAG_PRODUCTION_ROLE == 'security'
    assert {p.name for p in Path('/run/secrets').glob('postgres*')} == {'postgres_security_password'}
    django.setup()
    from apps.usuarios.models import EventoInstalacionFYAG, RecuperacionTIEvento, SeguridadCredencial, Usuario

    with connection.cursor() as cursor:
        cursor.execute('''SELECT current_user, session_user, rolsuper OR rolcreatedb OR rolcreaterole,
            EXISTS (SELECT FROM pg_auth_members WHERE member=r.oid), has_schema_privilege('public','CREATE')
            FROM pg_roles r WHERE rolname=current_user AND current_database()='fyag_aud025_tty' ''')
        assert cursor.fetchone() == ('fyag_sql_security', 'fyag_sql_security', False, False, False)
    print('OK: identidad SQL operativa verificada; sin secretos SQL de administración o migraciones.', flush=True)

    client = Client()
    assert client.request('/api/auth/setup/estado/', 200) == {'pendiente': True}
    key = install(0)
    assert EventoInstalacionFYAG.objects.filter(tipo='EMISION', operador=OPERATOR, referencia=REFERENCE).count() == 1
    password, new_password = [f'Aa9!{token_urlsafe(24)}' for _ in range(2)]
    payload = dict(first_name='Prueba', last_name='AUD', username='ti_aud025', email=EMAIL,
                   password=password, password_confirm=password, clave_instalacion=key)
    client.post('setup', payload, 201)
    assert REFRESH not in client.cookies
    assert client.request('/api/auth/setup/estado/', 200) == {'pendiente': False}
    client.post('setup', payload, 409)
    install(1)
    assert EventoInstalacionFYAG.objects.count() == 2
    print('OK: emisión en TTY, uso único vía HTTPS y rechazo de nueva emisión tras el alta.', flush=True)

    access = client.login(password)['access']
    client.post('refresh', {}, 200)
    refresh = client.cookies[REFRESH]
    pk = client.request('/api/auth/me/', 200, access=access)['id']
    before = Usuario.objects.values('password', 'sesion_version').get(pk=pk)
    recovery(pk, '', None, 1)
    recovery(pk, REFERENCE, 'NO', 1)
    assert Usuario.objects.values('password', 'sesion_version').get(pk=pk) == before
    assert SeguridadCredencial.objects.get(usuario_id=pk).estado == 'PERSONAL'
    assert not RecuperacionTIEvento.objects.exists()
    client.request('/api/auth/me/', 200, access=access)
    print('OK: referencia ausente y confirmación cancelada no modifican cuenta, sesión ni auditoría.', flush=True)

    temporary = recovery(pk, REFERENCE, f'RECUPERAR {pk}', 0)
    assert Usuario.objects.get(pk=pk).sesion_version == before['sesion_version'] + 1
    client.request('/api/auth/me/', 401, access=access)
    client.cookies[REFRESH] = refresh
    client.post('refresh', {}, 401)
    login = client.login(temporary)
    assert login['estado'] == 'CAMBIO_OBLIGATORIO' and 'access' not in login and REFRESH not in client.cookies
    change = client.post('primer-cambio-clave', {'desafio': login['desafio'], 'nueva_clave': new_password}, 200)
    assert change == {'estado': 'CLAVE_PERSONAL_CONFIRMADA', 'login_requerido': True}
    assert REFRESH not in client.cookies
    client.login(temporary, 401)
    access_new = client.login(new_password)['access']
    client.request('/api/auth/me/', 200, access=access_new)
    assert REFRESH in client.cookies
    print('OK: temporal emitida, access y refresh revocados, primer cambio obligatorio y nuevo login.', flush=True)

    event = RecuperacionTIEvento.objects.get(usuario_id=pk)
    assert (event.operador, event.referencia, event.motivo) == (OPERATOR, REFERENCE, REASON)
    filters = urlencode(dict(fuente=event.FUENTE, tipo=event.TIPO, recurso_tipo='USUARIO', recurso_id=pk))
    audit, = client.request(f'/api/auditoria/eventos/?{filters}', 200, access=access_new)['results']
    assert audit['id'] == f'{event.FUENTE}:{event.pk}' and audit['actor'] is None
    assert audit['actor_identidad_origen'] == 'INFRAESTRUCTURA'
    assert audit['datos_nuevos'] == {'operador': OPERATOR, 'referencia': REFERENCE}
    for secret in (key, password, new_password, temporary, refresh, access, access_new, login['desafio']):
        assert secret not in json.dumps(audit)
    print('OK: evento SQL único y proyección de auditoría TI sin secretos.', flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        # No mostrar excepciones de drivers, respuestas ni buffers de terminal.
        site = exc.__traceback__
        while site.tb_next:
            site = site.tb_next
        sys.exit(f'FALLO: {type(exc).__name__} en {site.tb_frame.f_code.co_name}:{site.tb_lineno}')
