from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

from django.test import SimpleTestCase, override_settings

from apps.usuarios.throttles import LimitesNoDisponibles, LoginIPRateThrottle


def request(email='qa@example.test', ip='192.0.2.10', forwarded='192.0.2.50'):
    return SimpleNamespace(data={'email': email}, META={'REMOTE_ADDR': ip, 'HTTP_X_FORWARDED_FOR': forwarded})


class SecurityRedisTests(SimpleTestCase):
    def test_concurrent_workers_share_atomic_identity_limit(self):
        def attempt(i):
            return LoginIPRateThrottle().allow_request(request(' QA@EXAMPLE.test ', f'192.0.2.{i + 1}'), None)

        with ThreadPoolExecutor(max_workers=12) as pool:
            self.assertEqual(sum(pool.map(attempt, range(24))), 5)

    def test_forwarded_header_does_not_change_the_ip_limit(self):
        for i in range(20):
            self.assertTrue(LoginIPRateThrottle().allow_request(request(f'qa{i}@example.test'), None))
        throttle = LoginIPRateThrottle()
        self.assertFalse(throttle.allow_request(request('otra@example.test', forwarded='203.0.113.5'), None))
        self.assertGreater(throttle.wait(), 0)

    @override_settings(FYAG_SECURITY_REDIS_URL='redis://127.0.0.1:1/0')
    def test_unavailable_storage_denies_instead_of_falling_back(self):
        with self.assertRaises(LimitesNoDisponibles):
            LoginIPRateThrottle().allow_request(request(), None)
