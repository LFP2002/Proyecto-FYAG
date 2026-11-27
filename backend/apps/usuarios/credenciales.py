"""SPEC-018 A: locks Usuario -> Seguridad; el reset adquiere antes el mutex TI.

Ausencia o incoherencia de estado implica denegación, nunca PERSONAL implícito.
La emisión temporal comparte el cambio de credencial entre alta y recuperaciones autorizadas.
"""
import hashlib
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import re

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from django.views.decorators.debug import sensitive_variables
from rest_framework.exceptions import AuthenticationFailed, ValidationError

from .models import SeguridadCredencial, Usuario, UsuarioEvento
from . import services_usuarios as services
from .services_usuarios import ConflictoUsuario, _admin, _contract, _not_self, _password, _text, _version, operacion


@dataclass
class CredencialEmitida:
    usuario: Usuario
    credencial_temporal: str = field(repr=False)
    vence_en: object = field(repr=False)


ESTADO_NO_DISPONIBLE = "NO_DISPONIBLE"  # Proyección de inconsistencia, no estado SQL.


def estado_coherente(state):
    """Defensa en profundidad, sin confiar solo en enum ni en constraints SQL."""
    if state is None:
        return False
    temporal = (state.emitida_en, state.vence_en)
    challenge = (state.desafio_digest, state.desafio_vence_en, state.desafio_version)
    if state.estado == "PERSONAL":
        return all(value is None for value in temporal + challenge)
    if state.estado not in {"INICIAL", "RECUPERACION"}:
        return False
    if not all(isinstance(value, datetime) and timezone.is_aware(value) for value in temporal):
        return False
    if state.vence_en <= state.emitida_en:
        return False
    if all(value is None for value in challenge):
        return True
    return (isinstance(state.desafio_digest, str)
            and re.fullmatch(r"[0-9a-f]{64}", state.desafio_digest) is not None
            and isinstance(state.desafio_vence_en, datetime) and timezone.is_aware(state.desafio_vence_en)
            and state.emitida_en < state.desafio_vence_en <= state.vence_en
            and type(state.desafio_version) is int and 1 <= state.desafio_version <= 9223372036854775807)


def estado_credencial(user):
    relation = Usuario._meta.get_field("seguridad_credencial")
    if relation.is_cached(user):
        state = relation.get_cached_value(user)
    else:
        state = SeguridadCredencial.objects.filter(usuario_id=user.pk).first()
    if not estado_coherente(state) or state.usuario_id != user.pk:
        return ESTADO_NO_DISPONIBLE
    return state.estado


def es_personal(user):
    return estado_credencial(user) == SeguridadCredencial.Estado.PERSONAL


def limpiar_desafio(state):
    state.desafio_digest = state.desafio_vence_en = state.desafio_version = None


@sensitive_variables()
def emitir_temporal(user, actor, *, inicial=False, motivo=""):
    """Dentro de transacción y lock usuario (o alta aún no visible)."""
    state = SeguridadCredencial.objects.select_for_update().filter(usuario=user).first()
    if not estado_coherente(state):
        raise ConflictoUsuario("seguridad_no_disponible", "Estado de seguridad no disponible; requiere revisión autorizada.")
    from .configuracion_c2 import habilitado
    access = None
    if not inicial and habilitado():
        from .autenticacion_c2 import recuperadoras_qa
        from .recuperacion_c2 import bloquear_estado_recuperacion
        disponibles = recuperadoras_qa()
        if (user.pk in settings.BLOQUEOS_C2_TI_QA_IDS
            and not any(ti.pk != user.pk for ti in disponibles)):
            raise ConflictoUsuario("recuperacion_qa_protegida", "Debe permanecer otra recuperadora QA personal disponible.")
        access = bloquear_estado_recuperacion(user)
    emitida = guardar_temporal(user, state, inicial=inicial)
    event = services._event(user, actor, UsuarioEvento.Tipo.CREACION_CREDENCIAL_TEMPORAL if inicial else UsuarioEvento.Tipo.REEMISION, motivo)
    if access is not None:
        from .recuperacion_c2 import confirmar_recuperacion
        confirmar_recuperacion(user, actor, access, event)
    return emitida


@sensitive_variables()
def guardar_temporal(user, state, *, inicial=False):
    """Solo callers autorizados con locks de usuario y credencial y estado validado."""
    credential = secrets.token_urlsafe(32)  # 256 bits; no depende de identidad/reloj.
    now = timezone.now()
    state.personal_previa = not inicial and (state.estado == 'PERSONAL' or state.personal_previa)
    state.estado = SeguridadCredencial.Estado.INICIAL if inicial else SeguridadCredencial.Estado.RECUPERACION
    state.emitida_en = now
    state.vence_en = now + timedelta(seconds=settings.CREDENCIAL_TEMPORAL_TTL_SECONDS)
    limpiar_desafio(state)
    user.set_password(credential)
    if not inicial:
        _version(user)
    user.save(update_fields=["password", "sesion_version"])
    state.save()
    return CredencialEmitida(user, credential, state.vence_en)


@sensitive_variables()
@operacion
def restablecer_clave(target, data, actor):
    actor, user = _admin(actor, target)
    _not_self(actor, user)
    _contract(data, {"motivo"}, {"motivo"})
    return emitir_temporal(user, actor, motivo=_text(data["motivo"], "motivo"))


@sensitive_variables()
def iniciar_cambio(user):
    """Invocado por login con Usuario bloqueado y password ya comprobado."""
    state = SeguridadCredencial.objects.select_for_update().filter(usuario=user).first()
    now = timezone.now()
    if not estado_coherente(state) or state.estado == "PERSONAL" or state.vence_en <= now:
        raise AuthenticationFailed("Credenciales inválidas.")
    challenge = secrets.token_urlsafe(32)
    state.desafio_digest = hashlib.sha256(challenge.encode()).hexdigest()
    state.desafio_vence_en = min(state.vence_en, now + timedelta(seconds=settings.PRIMER_CAMBIO_TTL_SECONDS))
    state.desafio_version = user.sesion_version
    state.save(update_fields=["desafio_digest", "desafio_vence_en", "desafio_version"])
    return {"estado": "CAMBIO_OBLIGATORIO", "desafio": challenge, "desafio_vence_en": state.desafio_vence_en.isoformat()}


@sensitive_variables()
@transaction.atomic
def primer_cambio(data):
    _contract(data, {"desafio", "nueva_clave"}, {"desafio", "nueva_clave"})
    challenge = data["desafio"]
    if not isinstance(challenge, str) or len(challenge) != 43 or not challenge.isascii():
        raise AuthenticationFailed("Desafío no disponible.")
    digest = hashlib.sha256(challenge.encode()).hexdigest()
    identifier = SeguridadCredencial.objects.filter(desafio_digest=digest).values_list("usuario_id", flat=True).first()
    user = Usuario.objects.select_for_update().filter(pk=identifier).first()
    state = SeguridadCredencial.objects.select_for_update().filter(usuario_id=identifier).first() if user else None
    from .configuracion_c2 import habilitado
    if user and habilitado():
        from .models import EstadoAcceso
        from .acceso import acceso_permitido
        access = EstadoAcceso.objects.select_for_update().filter(usuario=user).first()
        Usuario._meta.get_field("estado_acceso").set_cached_value(user, access)
        if not acceso_permitido(user):
            raise AuthenticationFailed("Desafío no disponible.")
    now = timezone.now()
    if (not user or not user.is_active or not estado_coherente(state) or state.estado == "PERSONAL"
        or not constant_time_compare(state.desafio_digest or "", digest)
        or state.desafio_version != user.sesion_version or state.vence_en <= now
        or state.desafio_vence_en is None or state.desafio_vence_en <= now):
        raise AuthenticationFailed("Desafío no disponible.")
    _password(data["nueva_clave"], user, "nueva_clave")
    if user.check_password(data["nueva_clave"]):
        raise ValidationError({"nueva_clave": ["Debe elegir una contraseña diferente de la temporal."]})
    user.set_password(data["nueva_clave"])
    _version(user)
    user.save(update_fields=["password", "sesion_version"])
    state.estado = SeguridadCredencial.Estado.PERSONAL
    state.personal_previa = False
    state.emitida_en = state.vence_en = None
    limpiar_desafio(state)
    state.save()
    services._event(user, user, UsuarioEvento.Tipo.CAMBIO_INICIAL)
