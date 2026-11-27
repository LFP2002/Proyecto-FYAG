"""Directed lab-only smoke. Resolves via loopback without modifying OS DNS or trust."""
import argparse
from http.client import HTTPConnection, HTTPSConnection
from http.cookies import SimpleCookie
import json
import re
import socket
import ssl

from websockets.exceptions import InvalidStatus
from websockets.sync.client import connect


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('host')
    parser.add_argument('http', type=int)
    parser.add_argument('https', type=int)
    parser.add_argument('ca')
    parser.add_argument('--email', required=True)
    parser.add_argument('--password', required=True, help='Synthetic laboratory password only')
    args = parser.parse_args()
    assert args.host.endswith('.test') and args.email.endswith('.test')
    context = ssl.create_default_context(cafile=args.ca)
    origin = f'https://{args.host}:{args.https}'
    ws_uri = origin.replace('https:', 'wss:') + '/ws/chat/'

    def fetch(path, method='GET', body=None, headers=None, *, tls=context, host=args.host):
        con = (HTTPSConnection(host, args.https, timeout=8, context=tls) if tls is not False
               else HTTPConnection(host, args.http, timeout=8))
        con._create_connection = lambda address, *a: socket.create_connection(('127.0.0.1', address[1]), *a)
        try:
            con.request(method, path, body, headers or {})
            reply = con.getresponse()
            return reply.status, reply.headers, reply.read()
        finally:
            con.close()

    status, headers, _ = fetch('/ruta?x=1', tls=False)
    assert status == 308 and headers['Location'] == origin + '/ruta?x=1'
    assert fetch('/', tls=False, host='incorrecto.test')[0] == 421
    for options in ({'tls': ssl.create_default_context()}, {'host': 'incorrecto.test'}):
        try:
            fetch('/', **options)
        except ssl.SSLError:
            pass
        else:
            raise AssertionError('HTTPS aceptó una CA no confiable o un SNI incorrecto')
    status, headers, html = fetch('/')
    assert status == 200 and headers['Strict-Transport-Security'].startswith('max-age=')
    assert headers['X-Frame-Options'] == 'DENY' and 'frame-ancestors' in headers['Content-Security-Policy']
    assert fetch('/ruta-react')[2] == html
    asset = re.search(rb'src="(/assets/[^\"]+\.js)"', html)[1].decode()
    assert fetch(asset)[0] == 200 and fetch('/assets/inexistente.js')[0] == 404
    assert all(fetch(path)[0] == 404 for path in ('/health/ready/', '/admin/', '/media/x'))
    status, headers, payload = fetch('/api/auth/csrf/')
    assert status == 200
    csrf = json.loads(payload)['csrfToken']
    cookie = SimpleCookie(headers['Set-Cookie'])['csrftoken']
    assert cookie['secure'] and cookie['httponly'] and cookie['samesite'] == 'Strict'
    login = json.dumps({'email': args.email, 'password': args.password})
    auth = {'Content-Type': 'application/json', 'Origin': origin}
    assert fetch('/api/auth/login/', 'POST', login, auth)[0] == 403
    auth.update({'Cookie': f'csrftoken={cookie.value}', 'X-CSRFToken': csrf})
    foreign = {**auth, 'Origin': 'https://incorrecto.test'}
    status, headers, _ = fetch('/api/auth/login/', 'POST', login, foreign)
    assert status == 403 and 'Access-Control-Allow-Origin' not in headers
    status, headers, payload = fetch('/api/auth/login/', 'POST', login, auth)
    assert status == 200, status
    refresh = SimpleCookie('\r\n'.join(headers.get_all('Set-Cookie')))['fyag_refresh']
    assert refresh['secure'] and refresh['httponly'] and refresh['samesite'] == 'Strict'
    token = json.loads(payload)['access']
    status, _, payload = fetch('/api/chat/conexion/', 'POST', '{}', {
        'Authorization': f'Bearer {token}', 'Content-Type': 'application/json', 'Origin': origin,
    })
    assert status == 201, status
    ticket = json.loads(payload)['ticket']

    def ws(tls, source):
        return connect(ws_uri, sock=socket.create_connection(('127.0.0.1', args.https), timeout=3),
                       ssl=tls, proxy=None, origin=source, open_timeout=5)

    try:
        ws(ssl.create_default_context(), origin)
    except ssl.SSLCertVerificationError:
        pass
    else:
        raise AssertionError('WSS aceptó una CA no confiable')
    try:
        ws(context, 'https://incorrecto.test')
    except InvalidStatus as exc:
        assert exc.response.status_code == 403
    else:
        raise AssertionError('WSS aceptó un origen ajeno')
    with ws(context, origin) as channel:
        channel.send(json.dumps({'tipo': 'autenticar', 'ticket': ticket}))
        assert json.loads(channel.recv(timeout=5)) == {'tipo': 'chat.conectado'}
        channel.send('{"tipo":"ping"}')
        assert json.loads(channel.recv(timeout=5)) == {'tipo': 'pong'}
    print('OK: HTTPS/WSS, CA/SNI, SPA, cabeceras, cookies, CSRF/CORS y ticket.')


if __name__ == '__main__':
    main()
