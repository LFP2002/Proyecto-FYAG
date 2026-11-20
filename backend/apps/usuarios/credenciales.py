"""SPEC-018 A: locks Usuario -> Seguridad; el reset adquiere antes el mutex TI.

Los ausentes (creaciones internas/usuarios históricos) equivalen a PERSONAL.
Solo alta HTTP y reset TI emiten credenciales temporales. No hay lockouts.
"""
import hashlib
import secrets
from dataclasses import dataclass, field
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from django.views.decorators.debug import sensitive_variables
from rest_framework.exceptions import AuthenticationFailed, ValidationError

from .models import SeguridadCredencial, Usuario, UsuarioEvento
from . import services_usuarios as services
from .services_usuarios import _admin, _contract, _not_self, _password, _text, _version, operacion


@dataclass
class CredencialEmitida:
    usuario: Usuario
    credencial_temporal: str = field(repr=False)
    vence_en: object = field(repr=False)


def estado_credencial(user):
    relation = Usuario._meta.get_field("seguridad_credencial")
    if relation.is_cached(user):
        state = relation.get_cached_value(user)
        return state.estado if state is not None else "PERSONAL"
    return SeguridadCredencial.objects.filter(usuario_id=user.pk).values_list("estado", flat=True).first() or "PERSONAL"


def es_personal(user):
    return estado_credencial(user) == SeguridadCredencial.Estado.PERSONAL


def limpiar_desafio(state):
    state.desafio_digest = state.desafio_vence_en = state.desafio_version = None


@sensitive_variables()
def emitir_temporal(user, actor, *, inicial=False, motivo=""):
    """Dentro de transacción y lock usuario (o alta aún no visible)."""
    credential = secrets.token_urlsafe(32)  # 256 bits; no depende de identidad/reloj.
    now = timezone.now()
    state, _ = SeguridadCredencial.objects.get_or_create(usuario=user)
    state.estado = SeguridadCredencial.Estado.INICIAL if inicial else SeguridadCredencial.Estado.RECUPERACION
    state.emitida_en = now
    state.vence_en = now + timedelta(seconds=settings.CREDENCIAL_TEMPORAL_TTL_SECONDS)
    limpiar_desafio(state)
    user.set_password(credential)
    if not inicial:
        _version(user)
    user.save(update_fields=["password", "sesion_version"])
    state.save()
    services._event(user, actor, UsuarioEvento.Tipo.CREACION_CREDENCIAL_TEMPORAL if inicial else UsuarioEvento.Tipo.REEMISION, motivo)
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
    if state is None or state.estado == "PERSONAL" or state.vence_en <= now:
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
    now = timezone.now()
    if (not user or not user.is_active or state is None or state.estado == "PERSONAL"
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
    state.emitida_en = state.vence_en = None
    limpiar_desafio(state)
    state.save()
    services._event(user, user, UsuarioEvento.Tipo.CAMBIO_INICIAL)
