from unittest import IsolatedAsyncioTestCase

from config.unix_proxy import UnixProxy


class UnixProxyTests(IsolatedAsyncioTestCase):
    async def dispatch(self, **fields):
        observed, messages = [], []

        async def app(scope, receive, send):
            observed.append(scope)

        async def send(message):
            messages.append(message)

        scope = {'type': 'http', 'client': None, 'server': None, 'headers': [], **fields}
        await UnixProxy(app)(scope, None, send)
        return observed, messages

    async def test_unix_normalizes_http_and_websocket_without_forwarding_client_headers(self):
        for kind, scheme in [('http', 'https'), ('websocket', 'wss')]:
            with self.subTest(kind=kind):
                headers = [(b'x-fyag-client-ip', b'::ffff:192.0.2.8'), (b'x-forwarded-for', b'192.0.2.9'),
                           (b'x-forwarded-proto', b'http'), (b'forwarded', b'for=192.0.2.9'), (b'host', b'fyag.test')]
                observed, messages = await self.dispatch(type=kind, headers=headers)
                self.assertEqual(observed[0]['client'], ('192.0.2.8', 0))
                self.assertEqual(observed[0]['scheme'], scheme)
                self.assertEqual(observed[0]['headers'], [(b'host', b'fyag.test')])
                self.assertFalse(messages)

    async def test_rejects_tcp_missing_duplicate_and_malformed(self):
        valid = (b'x-fyag-client-ip', b'192.0.2.8')
        for fields in ({'client': ('192.0.2.9', 1), 'headers': [valid]},
                       {'server': ('127.0.0.1', 8000), 'headers': [valid]}, {}, {'headers': [valid, valid]},
                       {'headers': [(valid[0], b'fe80::1%eth0')]}, {'headers': [(valid[0], b'192.0.2.8, 192.0.2.9')]},
                       {'root_path': '/untrusted', 'headers': [valid]}):
            with self.subTest(fields=fields):
                observed, messages = await self.dispatch(**fields)
                self.assertFalse(observed)
                self.assertEqual(messages[0]['status'], 400)

    async def test_websocket_denies_before_accept(self):
        observed, messages = await self.dispatch(type='websocket')
        self.assertFalse(observed)
        self.assertEqual(messages, [{'type': 'websocket.close', 'code': 1008}])
