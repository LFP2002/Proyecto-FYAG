from datetime import timedelta
from hashlib import sha256
from secrets import token_urlsafe
from time import time

from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone
from django.views.decorators.debug import sensitive_variables
from redis.exceptions import RedisError
from rest_framework.exceptions import ValidationError

from .correo import avisar_cambio_despues_commit, enviar_desafio_despues_commit
from .models import DesafioCorreo, SeguridadCredencial, Usuario, UsuarioEvento
from .services_usuarios import ADMIN_MUTEX, _event, _version, operacion
from .throttles import LimitesNoDisponibles, _client

TITULARIDAD = DesafioCorreo.Proposito.TITULARIDAD
CAMBIO = DesafioCorreo.Proposito.CAMBIO
_ENQUEUE = """
if redis.call('LLEN', KEYS[1]) >= 250 then return 0 end
redis.call('RPUSH', KEYS[1], ARGV[1])
redis.call('EXPIRE', KEYS[1], 300)
return 1
"""


def _queue(suffix):
    url = settings.FYAG_SECURITY_REDIS_URL
    if not url.startswith(('redis://', 'rediss://')):
        raise LimitesNoDisponibles()
    return _client(url), f'{settings.FYAG_SECURITY_REDIS_PREFIX}:{suffix}:solicitudes'


def encolar_reenvio(email, *, cola='verificacion'):
    # Mismo trabajo y respuesta para toda dirección: aquí no se consulta Usuario.
    if settings.FYAG_EMAIL_PROFILE == 'deshabilitado':
        return
    try:
        redis, key = _queue(cola)
        if redis.eval(_ENQUEUE, 1, key, f'{int(time())}:{email}') != 1:
            raise LimitesNoDisponibles()
    except (RedisError, ValueError, OSError):
        raise LimitesNoDisponibles() from None


def consumir_solicitud(cola, procesar):
    try:
        redis, key = _queue(cola)
        raw = redis.lpop(key)
    except (RedisError, ValueError, OSError):
        raise LimitesNoDisponibles() from None
    if raw is None:
        return False
    try:
        timestamp, email = raw.decode().split(':', 1)
        fresco = 0 <= int(time()) - int(timestamp) < 300
    except (UnicodeError, ValueError):
        return True
    if fresco:
        procesar(email)
    return True


@transaction.atomic
def _reenviar(email):
    user = Usuario.objects.select_for_update().filter(email=email).first()
    if user:
        emitir(user, TITULARIDAD)


def procesar_reenvio():
    return consumir_solicitud('verificacion', _reenviar)


@sensitive_variables()
def emitir(user, purpose):
    """El caller mantiene el lock de Usuario o lo acaba de insertar."""
    email = user.email if purpose == TITULARIDAD else user.correo_pendiente
    profile = settings.FYAG_EMAIL_PROFILE
    if (not email or profile == 'deshabilitado' or (profile == 'mailpit' and not email.endswith('.test'))
            or (purpose == TITULARIDAD and user.correo_verificado_en is not None)):
        return
    now = timezone.now()
    challenges = DesafioCorreo.objects.filter(usuario=user, proposito=purpose)
    version = user.sesion_version if purpose == CAMBIO else None
    if purpose == CAMBIO:
        challenges.exclude(sesion_version=version).delete()
    challenges.filter(vence_en__lte=now).delete()
    if challenges.filter(emitido_en__gt=now - timedelta(minutes=10)).exists() or challenges.count() >= 3:
        return
    token = token_urlsafe(32)
    minutes = settings.FYAG_VERIFICACION_MINUTOS
    DesafioCorreo.objects.create(usuario=user, email=email, proposito=purpose, digest=sha256(token.encode()).hexdigest(),
                                 emitido_en=now, vence_en=now + timedelta(minutes=minutes), sesion_version=version)
    enviar_desafio_despues_commit('verificacion', email, token, minutes)


def proponer(user, actor, email):
    if user.correo_pendiente != email:
        # Otra propuesta invalida solo los desafíos de cambio anteriores.
        DesafioCorreo.objects.filter(usuario=user, proposito=CAMBIO).delete()
        user.correo_pendiente = email
        user.save(update_fields=['correo_pendiente'])
        _event(user, actor, UsuarioEvento.Tipo.CORREO_SOLICITADO, after={'email': email})
    emitir(user, CAMBIO)


def _invalido():
    return ValidationError({'detail': 'El enlace de verificación no es válido o ha vencido.'})


@sensitive_variables()
@operacion
def confirmar(token):
    digest = sha256(token.encode()).hexdigest()
    candidate = DesafioCorreo.objects.filter(digest=digest).values('usuario_id', 'proposito').first()
    if candidate is None:
        raise _invalido()
    if candidate['proposito'] == CAMBIO:
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_advisory_xact_lock(%s)', [ADMIN_MUTEX])
    user = Usuario.objects.select_for_update().filter(pk=candidate['usuario_id']).first()
    if user is None:
        raise _invalido()
    challenge = DesafioCorreo.objects.filter(digest=digest, usuario=user).first()
    now = timezone.now()
    if challenge is None or challenge.vence_en <= now:
        raise _invalido()
    if challenge.proposito == TITULARIDAD:
        if challenge.email != user.email:
            raise _invalido()
        user.correo_verificado_en = now
        user.save(update_fields=['correo_verificado_en'])
        DesafioCorreo.objects.filter(usuario=user, proposito=TITULARIDAD).delete()
        _event(user, user, UsuarioEvento.Tipo.CORREO_VERIFICADO, 'Confirmado mediante titularidad del buzón; no autenticó sesión.')
        return
    if (challenge.sesion_version != user.sesion_version or challenge.email != user.correo_pendiente
            or Usuario.objects.exclude(pk=user.pk).filter(email=challenge.email).exists()):
        raise _invalido()
    anterior = user.email
    user.email, user.correo_pendiente, user.correo_verificado_en = challenge.email, '', now
    _version(user)
    user.save(update_fields=['email', 'correo_pendiente', 'correo_verificado_en', 'sesion_version'])
    SeguridadCredencial.objects.filter(usuario=user).update(desafio_digest=None, desafio_vence_en=None, desafio_version=None)
    DesafioCorreo.objects.filter(usuario=user).delete()
    _event(user, user, UsuarioEvento.Tipo.CORREO_CAMBIADO, 'Confirmado mediante titularidad del nuevo buzón.',
           before={'email': anterior}, after={'email': user.email})
    avisar_cambio_despues_commit(anterior)
