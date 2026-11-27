"""Standalone Compose profile. No .env development fallback or test configuration."""
import os
import re
from pathlib import Path
from urllib.parse import quote

from django.core.exceptions import ImproperlyConfigured


def secret(name, *, minimum=1):
    try:
        value = (Path('/run/secrets') / name).read_text(encoding='utf-8').rstrip('\r\n')
        if len(value) < minimum or any(ord(c) < 32 for c in value):
            raise ValueError
        return value
    except (OSError, ValueError):
        raise ImproperlyConfigured(f'Secreto productivo no disponible o inválido: {name}.') from None


role = os.environ.get('FYAG_PROD_ROLE')
if role not in {'web', 'migration', 'security', 'alerts', 'documents', 'attachments', 'chat', 'mail'}:
    raise ImproperlyConfigured('Rol de proceso FYAG no válido.')
host = os.environ.get('FYAG_PUBLIC_HOST', '')
label = r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?'
port = os.environ.get('FYAG_HTTPS_PORT', '443')
if (len(host) > 253 or not re.fullmatch(rf'{label}(?:\.{label})+', host)
        or not re.fullmatch(r'[1-9][0-9]{0,4}', port) or int(port) > 65535):
    raise ImproperlyConfigured('Dominio DNS o puerto HTTPS productivo inválido.')
origin = f'https://{host}' + (f':{port}' if port != '443' else '')
os.environ.update(DJANGO_DEBUG='False', DJANGO_ALLOWED_HOSTS=host, FYAG_PUBLIC_BASE_URL=origin,
                  FYAG_CHAT_WS_ALLOWED_ORIGINS=origin, DJANGO_CSRF_TRUSTED_ORIGINS=origin,
                  DJANGO_CORS_ALLOWED_ORIGINS='', FYAG_BLOQUEOS_C2='', POSTGRES_USER=f'fyag_sql_{role}',
                  POSTGRES_PASSWORD=secret(f'postgres_{role}_password', minimum=64))
if role == 'web':
    os.environ['DJANGO_SECRET_KEY'] = secret('django_secret', minimum=50)
    os.environ['JWT_SIGNING_KEY'] = secret('jwt_signing_key', minimum=50)
    if os.environ['DJANGO_SECRET_KEY'] == os.environ['JWT_SIGNING_KEY']:
        raise ImproperlyConfigured('Django y JWT requieren claves independientes.')
else:
    # Los comandos de mantenimiento no emiten ni validan sesiones. Nunca cargar ASGI con este rol.
    from secrets import token_urlsafe
    os.environ.update(DJANGO_SECRET_KEY=secret('django_secret', minimum=50) if role == 'security' else token_urlsafe(64),
                      JWT_SIGNING_KEY=token_urlsafe(64))
    if role != 'security':
        os.environ['FYAG_BLOQUEOS_PERFIL'] = 'deshabilitado'

if role in {'web', 'documents', 'attachments'}:
    os.environ['FYAG_MONGO_PASSWORD'] = secret('mongo_app_password')
if role == 'web':
    os.environ['FYAG_CHAT_REDIS_PASSWORD'] = secret('redis_chat_password', minimum=32)
recovery_key = None
if role in {'web', 'mail', 'security'}:
    password = quote(secret('redis_security_password', minimum=32), safe='')
    os.environ['FYAG_SECURITY_REDIS_URL'] = f'rediss://:{password}@redis-seguridad:6379/0'
    FYAG_SECURITY_REDIS_CA = '/run/secrets/redis_ca'
    if not os.access(FYAG_SECURITY_REDIS_CA, os.R_OK):
        raise ImproperlyConfigured('CA de Redis de seguridad no disponible.')
    profile = os.environ.get('FYAG_EMAIL_PROFILE', 'deshabilitado')
    if profile == 'smtp':
        os.environ['EMAIL_HOST_PASSWORD'] = secret('smtp_password')
        if role != 'security':
            recovery_key = secret('recovery_hmac_key')
        if recovery_key is not None and (not re.fullmatch(r'[0-9a-f]{64}', recovery_key)
                or recovery_key in {os.environ['DJANGO_SECRET_KEY'], os.environ['JWT_SIGNING_KEY']}):
            raise ImproperlyConfigured('La clave HMAC de recuperación debe ser independiente y tener 64 caracteres hexadecimales minúsculos.')
    elif profile != 'deshabilitado' or role == 'mail':
        raise ImproperlyConfigured('Producción solo admite correo deshabilitado o SMTP autenticado.')

from .settings import *  # noqa: E402,F403

FYAG_RECUPERACION_HMAC_KEY = recovery_key
del recovery_key
FYAG_PRODUCTION_ROLE = role
FYAG_ACTIVACION_SQL_USER = 'fyag_sql_web'  # La constancia autoriza el usuario ASGI, no el operador que la registra.
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_SAMESITE = 'Strict'
SECURE_PROXY_SSL_HEADER = None  # El esquema se establece exclusivamente en la frontera ASGI Unix.
X_FRAME_OPTIONS = 'DENY'
