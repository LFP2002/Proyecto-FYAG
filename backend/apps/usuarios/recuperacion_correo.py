from datetime import timedelta
from hashlib import sha256
from secrets import token_urlsafe

from django.conf import settings
from django.contrib.auth.hashers import check_password
from django.db import connection, transaction
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac
from django.views.decorators.debug import sensitive_variables
from rest_framework.exceptions import ValidationError

from .configuracion_c2 import habilitado
from .correo import avisar_recuperacion_despues_commit, enviar_desafio_despues_commit
from .credenciales import estado_coherente, limpiar_desafio
from .models import DesafioCorreo, DesafioRecuperacionCorreo, RecuperacionCorreoEvento, SeguridadCredencial, Usuario
from .recuperacion_c2 import bloquear_estado_recuperacion, normalizar_acceso
from .services_usuarios import ADMIN_MUTEX, ConflictoUsuario, _password, _version, operacion
from .verificacion import consumir_solicitud, encolar_reenvio

COLA = 'recuperacion-correo'


def solicitar(email):
    encolar_reenvio(email, cola=COLA)


def procesar_recuperacion():
    return consumir_solicitud(COLA, emitir)


@sensitive_variables()
def _digest(token):
    return sha256(b'FYAG:recuperacion-correo\0' + token.encode()).hexdigest()


@sensitive_variables()
def _vinculo(user, credencial):
    datos = (user.pk, user.email, user.correo_verificado_en.isoformat(), user.sesion_version,
             user.rol, user.password, credencial.estado, credencial.personal_previa)
    return salted_hmac('fyag.027.recuperacion.v1', repr(datos), algorithm='sha256').hexdigest()


def _credencial_elegible(user):
    if not user or not user.is_active or not user.correo_verificado_en:
        return None
    state = SeguridadCredencial.objects.select_for_update().filter(usuario=user).first()
    if not estado_coherente(state):
        return None
    if state.estado == 'PERSONAL' or (state.estado == 'RECUPERACION' and state.personal_previa):
        return state
    return None


@sensitive_variables()
@transaction.atomic
def emitir(email):
    if settings.FYAG_EMAIL_PROFILE == 'deshabilitado' or (
            settings.FYAG_EMAIL_PROFILE == 'mailpit' and not email.endswith('.test')):
        return
    user = Usuario.objects.select_for_update().filter(email=email).first()
    credencial = _credencial_elegible(user)
    if credencial is None:
        return
    now = timezone.now()
    vinculo = _vinculo(user, credencial)
    vigente = DesafioRecuperacionCorreo.objects.filter(usuario=user, vence_en__gt=now, vinculo=vinculo)
    if vigente.exists():
        return  # No reemplazar, reenviar ni prolongar un enlace válido.
    token = token_urlsafe(32)
    minutos = settings.FYAG_RECUPERACION_MINUTOS
    DesafioRecuperacionCorreo.objects.update_or_create(usuario=user, defaults={
        'digest': _digest(token), 'vinculo': vinculo, 'vence_en': now + timedelta(minutes=minutos)})
    enviar_desafio_despues_commit('recuperacion', email, token, minutos)


def _invalido():
    return ValidationError({'detail': 'El enlace de recuperación no es válido o ha vencido.'})


@sensitive_variables()
@operacion
def confirmar(token, nueva_clave):
    digest = _digest(token)
    pk = DesafioRecuperacionCorreo.objects.filter(digest=digest).values_list('usuario_id', flat=True).first()
    if pk is None:
        raise _invalido()
    with connection.cursor() as cursor:
        cursor.execute('SELECT pg_advisory_xact_lock(%s)', [ADMIN_MUTEX])
    user = Usuario.objects.select_for_update().filter(pk=pk).first()
    credencial = _credencial_elegible(user)
    if credencial is None:
        raise _invalido()
    acceso = None
    if habilitado():
        try:
            acceso = bloquear_estado_recuperacion(user)
        except ConflictoUsuario:
            raise _invalido() from None
    desafio = DesafioRecuperacionCorreo.objects.select_for_update().filter(usuario=user, digest=digest).first()
    if (desafio is None or desafio.vence_en <= timezone.now()
            or not constant_time_compare(desafio.vinculo, _vinculo(user, credencial))):
        raise _invalido()
    _password(nueva_clave, user, 'nueva_clave')
    if check_password(nueva_clave, user.password):
        raise ValidationError({'nueva_clave': ['Elija una contraseña distinta.']})

    user.set_password(nueva_clave)
    _version(user)
    user.save(update_fields=['password', 'sesion_version'])
    credencial.estado = 'PERSONAL'
    credencial.personal_previa = False
    credencial.emitida_en = credencial.vence_en = None
    limpiar_desafio(credencial)
    credencial.save()
    DesafioCorreo.objects.filter(usuario=user, proposito=DesafioCorreo.Proposito.CAMBIO).delete()
    desafio.delete()
    anterior, version = ('', None)
    if acceso is not None:
        anterior, _ = normalizar_acceso(acceso)
        version = acceso.version
    RecuperacionCorreoEvento.objects.create(usuario=user, acceso_anterior=anterior, acceso_version_nueva=version)
    avisar_recuperacion_despues_commit(user.email)
