from urllib.parse import urlsplit
import re

from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.core.validators import validate_email


def configurar_vigencia_recuperacion(env):
    valor = env.get('FYAG_RECUPERACION_MINUTOS', '15')
    if isinstance(valor, str) and re.fullmatch(r'[0-9]{1,2}', valor) and 5 <= int(valor) <= 30:
        return int(valor)
    raise ImproperlyConfigured('FYAG_RECUPERACION_MINUTOS debe ser un entero entre 5 y 30.')


def configurar_correo(env):
    def boolean(name):
        value = env.get(name, 'false').lower()
        if value not in {'true', 'false'}:
            raise ImproperlyConfigured(f'{name} debe ser True o False.')
        return value == 'true'

    profile = env.get('FYAG_EMAIL_PROFILE', 'deshabilitado')
    backend = env.get('EMAIL_BACKEND') or 'django.core.mail.backends.dummy.EmailBackend'
    host = env.get('EMAIL_HOST', '')
    base = (env.get('FYAG_PUBLIC_BASE_URL') or '').rstrip('/')
    sender = env.get('DEFAULT_FROM_EMAIL', '')
    user, password = env.get('EMAIL_HOST_USER', ''), env.get('EMAIL_HOST_PASSWORD', '')
    tls, ssl = boolean('EMAIL_USE_TLS'), boolean('EMAIL_USE_SSL')
    try:
        port, timeout = int(env.get('EMAIL_PORT', '587')), int(env.get('EMAIL_TIMEOUT', '10'))
        url = urlsplit(base)
        _ = url.port  # Rechaza puertos no numéricos o fuera de rango.
        if base and (url.scheme not in {'http', 'https'} or not url.hostname or url.username is not None
                     or url.path or url.query or url.fragment or any(c.isspace() or c == '\\' for c in base)):
            raise ValueError
        if sender:
            validate_email(sender)
        if not 1 <= port <= 65535 or not 1 <= timeout <= 30 or tls and ssl:
            raise ValueError
    except (ValueError, ValidationError):
        raise ImproperlyConfigured('Configuración de correo no válida.') from None

    smtp = 'django.core.mail.backends.smtp.EmailBackend'
    dummy = 'django.core.mail.backends.dummy.EmailBackend'
    if profile == 'deshabilitado':
        valid = backend == dummy
    elif profile == 'mailpit':
        valid = (backend == smtp and host == 'mailpit' and port == 1025 and not (tls or ssl or user or password)
                 and sender.lower().endswith('.test') and bool(base))
    elif profile == 'smtp':
        valid = (backend == smtp and host and host != 'mailpit' and sender and user and password
                 and (tls or ssl) and url.scheme == 'https')
    else:
        valid = False
    if not valid:
        raise ImproperlyConfigured('Perfil de correo incompatible con la configuración SMTP o URL pública.')
    return {
        'FYAG_EMAIL_PROFILE': profile, 'FYAG_PUBLIC_BASE_URL': base, 'EMAIL_BACKEND': backend,
        'EMAIL_HOST': host, 'EMAIL_HOST_USER': user, 'EMAIL_HOST_PASSWORD': password,
        'EMAIL_PORT': port, 'EMAIL_TIMEOUT': timeout, 'EMAIL_USE_TLS': tls, 'EMAIL_USE_SSL': ssl,
        'DEFAULT_FROM_EMAIL': sender,
    }
