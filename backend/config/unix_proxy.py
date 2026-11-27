"""Trust the edge only over the private Unix socket (Daphne, no proxy flags)."""
from ipaddress import ip_address

CLIENT_IP = b'x-fyag-client-ip'


class UnixProxy:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] not in {'http', 'websocket'}:
            return await self.app(scope, receive, send)
        ips, headers = [], []
        for name, value in scope['headers']:
            if name == CLIENT_IP:
                ips.append(value)
            elif name not in {b'forwarded', b'x-real-ip'} and not name.startswith(b'x-forwarded-'):
                headers.append((name, value))
        try:
            if (scope.get('client') is not None or scope.get('server') is not None or len(ips) != 1
                    or b'%' in ips[0] or scope.get('root_path')):
                raise ValueError
            ip = ip_address(ips[0].decode('ascii'))
        except (ValueError, UnicodeError):
            if scope['type'] == 'http':
                await send({'type': 'http.response.start', 'status': 400, 'headers': []})
                await send({'type': 'http.response.body', 'body': b''})
            else:
                await send({'type': 'websocket.close', 'code': 1008})
            return
        return await self.app({**scope, 'headers': headers, 'client': (str(getattr(ip, 'ipv4_mapped', None) or ip), 0),
                               'scheme': 'https' if scope['type'] == 'http' else 'wss'}, receive, send)
