import hashlib
import hmac
from functools import lru_cache
from ipaddress import ip_address

from django.conf import settings
from django.views.decorators.debug import sensitive_variables
from redis import Redis
from redis.exceptions import RedisError
from rest_framework.exceptions import APIException
from rest_framework.throttling import AnonRateThrottle, BaseThrottle


_LIMIT = """
local wait = 0
for i, key in ipairs(KEYS) do
    local hits = tonumber(redis.call('GET', key) or '0')
    if hits >= tonumber(ARGV[2*i-1]) then
        local ttl = redis.call('TTL', key)
        if ttl < 0 then return -1 end
        wait = math.max(wait, ttl + 1)
    end
end
if wait > 0 then return wait end
for i, key in ipairs(KEYS) do
    if redis.call('EXISTS', key) == 0 then
        redis.call('SET', key, 1, 'EX', ARGV[2*i])
    else
        redis.call('INCR', key)
    end
end
return 0
"""


class LimitesNoDisponibles(APIException):
    status_code = 503
    default_detail = 'Servicio de autenticación temporalmente no disponible.'


@lru_cache(maxsize=4)
def _client(url):
    tls = {'ssl_cert_reqs': 'required', 'ssl_check_hostname': True} if url.startswith('rediss://') else {}
    if tls and (ca := getattr(settings, 'FYAG_SECURITY_REDIS_CA', None)):
        tls['ssl_ca_certs'] = ca
    return Redis.from_url(url, socket_connect_timeout=1, socket_timeout=1, retry_on_timeout=False, **tls)


def _digest(value):
    return hmac.new(settings.SECRET_KEY.encode(), value.encode(), hashlib.sha256).hexdigest()


def _remote(request):
    # No aceptar cabeceras del cliente: producción normaliza el peer en ASGI.
    try:
        ip = ip_address(request.META.get('REMOTE_ADDR', ''))
        return str(getattr(ip, 'ipv4_mapped', None) or ip)
    except ValueError:
        return 'desconocida'


class SecurityRateThrottle(BaseThrottle):
    operation = ''
    ip_limit = (20, 60)
    identity_limit = (5, 60)
    identity_field = 'email'

    @sensitive_variables()
    def allow_request(self, request, view):
        prefix = f'{settings.FYAG_SECURITY_REDIS_PREFIX}:{self.operation}'
        keys = [f'{prefix}:ip:{_digest(_remote(request))}']
        args = list(self.ip_limit)
        if self.identity_field and isinstance(request.data, dict):
            value = request.data.get(self.identity_field)
            if isinstance(value, str) and 0 < len(value) <= 1024 and value.strip():
                keys.append(f'{prefix}:identidad:{_digest(value.strip().lower())}')
                args.extend(self.identity_limit)
        try:
            url = settings.FYAG_SECURITY_REDIS_URL
            if not url.startswith(('redis://', 'rediss://')):
                raise LimitesNoDisponibles()
            wait = _client(url).eval(_LIMIT, len(keys), *keys, *args)
        except (RedisError, ValueError, OSError):
            raise LimitesNoDisponibles() from None
        if type(wait) is not int or wait < 0:
            raise LimitesNoDisponibles()
        self.seconds = wait
        return wait == 0

    def wait(self):
        return self.seconds


class LoginIPRateThrottle(SecurityRateThrottle):
    """Nombre histórico: IP y correo se limitan juntos."""
    operation = 'login'


class RefreshIPRateThrottle(SecurityRateThrottle, AnonRateThrottle):
    # Conservar el presupuesto común que tenían ambos endpoints (mismo scope).
    scope = 'refresh_ip'
    operation = 'refresh-primer-cambio'
    identity_field = None

    @property
    def ip_limit(self):
        return self.num_requests, self.duration
