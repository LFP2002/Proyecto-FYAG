"""Activación explícita y arranque de tráfico separados; no es autorización HTTP."""
import json
import re
from urllib.parse import urlsplit
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.core.mail import get_connection
from django.core.validators import validate_email
from django.db import DatabaseError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac
from django.views.decorators.debug import sensitive_variables
from redis.exceptions import RedisError

_CONFIG_AUTORIZADA = (
    'FYAG_BLOQUEOS_PERFIL', 'FYAG_BLOQUEOS_DOMINIO', 'FYAG_BLOQUEOS_CORREO_TI',
    'FYAG_BLOQUEOS_AUTORIZACION', 'FYAG_BLOQUEOS_ENTREGA_SMTP', 'FYAG_BLOQUEOS_AUTORIZACION_REMITENTE',
    'FYAG_PUBLIC_BASE_URL', 'ALLOWED_HOSTS', 'SECURE_SSL_REDIRECT', 'SECURE_PROXY_SSL_HEADER',
    'SESSION_COOKIE_SECURE', 'CSRF_COOKIE_SECURE', 'JWT_REFRESH_COOKIE_SECURE', 'DEBUG',
    'FYAG_SECURITY_REDIS_URL', 'FYAG_SECURITY_REDIS_PREFIX', 'FYAG_EMAIL_PROFILE', 'EMAIL_BACKEND',
    'EMAIL_HOST', 'EMAIL_PORT', 'EMAIL_TIMEOUT', 'EMAIL_HOST_USER', 'EMAIL_HOST_PASSWORD',
    'EMAIL_USE_TLS', 'EMAIL_USE_SSL', 'EMAIL_SSL_CERTFILE', 'EMAIL_SSL_KEYFILE', 'DEFAULT_FROM_EMAIL',
)
_ACTIVACION_MUTEX = 0x465941470027005


@sensitive_variables()
def _huella_configuracion():
    datos = {clave: getattr(settings, clave) for clave in _CONFIG_AUTORIZADA}
    db = settings.DATABASES['default']
    datos['postgres'] = {clave: db.get(clave) for clave in ('ENGINE', 'NAME', 'HOST', 'PORT', 'USER', 'OPTIONS')}
    datos['postgres']['USER'] = getattr(settings, 'FYAG_ACTIVACION_SQL_USER', db.get('USER'))
    return salted_hmac('fyag.spec027.activacion.v1', json.dumps(datos, sort_keys=True), algorithm='sha256').hexdigest()


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
        if (not settings.FYAG_SECURITY_REDIS_URL.startswith('rediss://') or not url.hostname or not url.port or not url.password
                or url.query or url.fragment or url.path not in ('', '/', '/0')
                or any(url.hostname == host['host'].lower() and url.port == int(host['port']) for host in chat)):
            raise ValueError
    except (KeyError, TypeError, ValueError):
        raise ImproperlyConfigured('Bloqueos: se requiere Redis dedicado con TLS verificado y autenticación.') from None
    dominio = settings.FYAG_BLOQUEOS_DOMINIO
    try:
        base = urlsplit(settings.FYAG_PUBLIC_BASE_URL)
        if not re.fullmatch(r'[a-z0-9-]+(?:\.[a-z0-9-]+)+', dominio) or dominio.endswith(('.test', '.example', '.invalid', '.localhost')):
            raise ValueError
        for email in (settings.FYAG_BLOQUEOS_CORREO_TI, settings.DEFAULT_FROM_EMAIL):
            validate_email(email)
        if not settings.FYAG_BLOQUEOS_CORREO_TI.endswith('@' + dominio):
            raise ValueError
        if (settings.FYAG_EMAIL_PROFILE != 'smtp' or not settings.EMAIL_HOST or settings.EMAIL_HOST == 'mailpit'
                or not settings.EMAIL_HOST_USER or not settings.EMAIL_HOST_PASSWORD
                or not (settings.EMAIL_USE_TLS ^ settings.EMAIL_USE_SSL)
                or settings.EMAIL_BACKEND != 'django.core.mail.backends.smtp.EmailBackend'
                or base.scheme != 'https' or not base.hostname):
            raise ValueError
    except (ValidationError, ValueError):
        raise ImproperlyConfigured('Bloqueos: se requiere SMTP institucional autenticado con TLS y un origen HTTPS.') from None
    for referencia in (settings.FYAG_BLOQUEOS_AUTORIZACION, settings.FYAG_BLOQUEOS_ENTREGA_SMTP,
                       settings.FYAG_BLOQUEOS_AUTORIZACION_REMITENTE):
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._:/-]{2,119}', referencia):
            raise ImproperlyConfigured('Bloqueos: faltan referencias de autorización operativa, del remitente o de entrega SMTP.')


def _productivo():
    from .configuracion_c2 import perfil_bloqueos
    return perfil_bloqueos() == 'produccion'


def _validar_esquema():
    try:
        executor = MigrationExecutor(connection)
        if executor.migration_plan(executor.loader.graph.leaf_nodes()):
            raise ImproperlyConfigured('Bloqueos: el esquema tiene migraciones pendientes.')
    except DatabaseError:
        raise ImproperlyConfigured('Bloqueos: no se pudo comprobar el esquema.') from None


def _constancia_vigente():
    from .models import ActivacionBloqueos
    return ActivacionBloqueos.objects.order_by('-id').first()


def _coincide(constancia, huella):
    return (constancia is not None and constancia.autorizacion == settings.FYAG_BLOQUEOS_AUTORIZACION
            and constancia.entrega_smtp == settings.FYAG_BLOQUEOS_ENTREGA_SMTP
            and constancia.autorizacion_remitente == settings.FYAG_BLOQUEOS_AUTORIZACION_REMITENTE
            and constant_time_compare(constancia.huella_configuracion, huella))


def validar_arranque_si_productivo():
    if not _productivo():
        return False
    _validar_esquema()
    try:
        if not _coincide(_constancia_vigente(), _huella_configuracion()):
            raise ImproperlyConfigured('Bloqueos: no hay constancia vigente para la configuración autorizada.')
    except DatabaseError:
        raise ImproperlyConfigured('Bloqueos: no se pudo consultar la constancia de activación.') from None
    return True


@sensitive_variables()
def preflight_activacion():
    if not _productivo():
        raise ImproperlyConfigured('El perfil productivo no está seleccionado.')
    _validar_esquema()
    from .acceso import estado_acceso
    from .autenticacion_c2 import hash_utilizable
    from .credenciales import estado_coherente
    from .models import Usuario
    from .throttles import _LIMIT, _client

    try:
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
        raise ImproperlyConfigured('Bloqueos: no se pudo comprobar la TI de referencia.') from None
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


def registrar_activacion():
    """Solo por CLI, con evidencias explícitas y sin enviar correo ni cambiar cuentas."""
    from .models import ActivacionBloqueos
    preflight_activacion()
    huella = _huella_configuracion()
    try:
        with transaction.atomic(durable=True), connection.cursor() as cursor:
            cursor.execute('SELECT pg_advisory_xact_lock(%s)', [_ACTIVACION_MUTEX])
            vigente = _constancia_vigente()
            if _coincide(vigente, huella):
                return vigente
            if ActivacionBloqueos.objects.filter(autorizacion=settings.FYAG_BLOQUEOS_AUTORIZACION).exists():
                raise ImproperlyConfigured('Bloqueos: se requiere una nueva referencia de autorización para esta configuración.')
            return ActivacionBloqueos.objects.create(
                autorizacion=settings.FYAG_BLOQUEOS_AUTORIZACION, entrega_smtp=settings.FYAG_BLOQUEOS_ENTREGA_SMTP,
                autorizacion_remitente=settings.FYAG_BLOQUEOS_AUTORIZACION_REMITENTE, huella_configuracion=huella,
            )
    except DatabaseError:
        raise ImproperlyConfigured('Bloqueos: no se pudo registrar la constancia de activación.') from None
