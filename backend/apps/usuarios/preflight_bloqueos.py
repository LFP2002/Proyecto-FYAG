"""Validación estática por perfil y preflight de entrada a tráfico, no una autorización HTTP."""
import re
from urllib.parse import urlsplit
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.core.mail import get_connection
from django.core.validators import validate_email
from django.db import DatabaseError, connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone
from django.views.decorators.debug import sensitive_variables
from redis.exceptions import RedisError


@sensitive_variables()
def validar_configuracion_productiva():
    if (settings.DEBUG or not settings.SECURE_SSL_REDIRECT or not settings.SESSION_COOKIE_SECURE
            or not settings.CSRF_COOKIE_SECURE or not settings.JWT_REFRESH_COOKIE_SECURE
            or settings.DATABASES['default']['ENGINE'] != 'django.db.backends.postgresql'
            or settings.DATABASES['default'].get('ATOMIC_REQUESTS')):
        raise ImproperlyConfigured('Bloqueos: se requiere HTTPS, cookies seguras, PostgreSQL sin ATOMIC_REQUESTS y DEBUG desactivado.')
    try:
        url = urlsplit(settings.FYAG_SECURITY_REDIS_URL)
        chat = settings.CHANNEL_LAYERS['default']['CONFIG']['hosts']
        if (url.scheme != 'rediss' or not url.hostname or not url.port or not url.password
                or url.query or url.fragment or url.path not in ('', '/', '/0')
                or any(url.hostname == host['host'].lower() and url.port == int(host['port']) for host in chat)):
            raise ValueError
    except (KeyError, TypeError, ValueError):
        raise ImproperlyConfigured('Bloqueos: se requiere Redis dedicado con TLS verificado y autenticación.') from None
    dominio = settings.FYAG_BLOQUEOS_DOMINIO
    base = urlsplit(settings.FYAG_PUBLIC_BASE_URL)
    try:
        if not re.fullmatch(r'[a-z0-9-]+(?:\.[a-z0-9-]+)+', dominio) or dominio.endswith(('.test', '.example', '.invalid', '.localhost')):
            raise ValueError
        for email in (settings.FYAG_BLOQUEOS_CORREO_TI, settings.DEFAULT_FROM_EMAIL):
            validate_email(email)
            if not email.endswith('@' + dominio):
                raise ValueError
        if (settings.FYAG_EMAIL_PROFILE != 'smtp' or not settings.EMAIL_HOST or settings.EMAIL_HOST == 'mailpit'
                or not settings.EMAIL_HOST_USER or not settings.EMAIL_HOST_PASSWORD
                or not (settings.EMAIL_USE_TLS ^ settings.EMAIL_USE_SSL)
                or settings.EMAIL_BACKEND != 'django.core.mail.backends.smtp.EmailBackend'
                or base.scheme != 'https' or not base.hostname):
            raise ValueError
    except (ValidationError, ValueError):
        raise ImproperlyConfigured('Bloqueos: se requiere SMTP institucional autenticado con TLS y un origen HTTPS.') from None
    for referencia in (settings.FYAG_BLOQUEOS_AUTORIZACION, settings.FYAG_BLOQUEOS_ENTREGA_SMTP):
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:/-]{2,119}', referencia):
            raise ImproperlyConfigured('Bloqueos: faltan referencias de autorización y entrega SMTP comprobada fuera de banda.')


@sensitive_variables()
def preflight_si_productivo():
    from .configuracion_c2 import perfil_bloqueos
    if perfil_bloqueos() != 'produccion':
        return False
    from .acceso import estado_acceso
    from .autenticacion_c2 import hash_utilizable
    from .credenciales import estado_coherente
    from .models import Usuario
    from .throttles import _LIMIT, _client

    try:
        executor = MigrationExecutor(connection)
        if executor.migration_plan(executor.loader.graph.leaf_nodes()):
            raise ImproperlyConfigured('Bloqueos: el esquema tiene migraciones pendientes.')
        ti = Usuario.objects.select_related('seguridad_credencial', 'estado_acceso').filter(
            email=settings.FYAG_BLOQUEOS_CORREO_TI, rol=Usuario.Rol.ADMINISTRADOR_TI,
            is_active=True, correo_verificado_en__isnull=False).first()
        credencial = getattr(ti, 'seguridad_credencial', None)
        recuperable = estado_coherente(credencial) and (
            credencial.estado == 'PERSONAL' or (credencial.estado == 'RECUPERACION'
                and credencial.personal_previa and credencial.vence_en > timezone.now()))
        if not recuperable or not hash_utilizable(ti) or estado_acceso(ti) != 'NORMAL':
            raise ImproperlyConfigured('Bloqueos: la TI institucional de referencia no está operativa y recuperable.')
    except DatabaseError:
        raise ImproperlyConfigured('Bloqueos: no se pudo comprobar el esquema y la TI de referencia.') from None
    try:
        redis = _client(settings.FYAG_SECURITY_REDIS_URL)
        if redis.eval(_LIMIT, 1, f'{settings.FYAG_SECURITY_REDIS_PREFIX}:preflight:{uuid4().hex}', 1, 5) != 0:
            raise ValueError
    except (RedisError, OSError, ValueError):
        raise ImproperlyConfigured('Bloqueos: Redis dedicado no está disponible para límites atómicos.') from None
    try:
        with get_connection():  # Comprueba transporte/autenticación sin enviar mensajes.
            pass
    except (OSError, ValueError):
        raise ImproperlyConfigured('Bloqueos: no se pudo conectar al SMTP institucional.') from None
    return True
