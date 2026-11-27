"""Servicio exclusivo de la CLI de infraestructura; no es autorización HTTP."""
import re

from django.db import connection, transaction
from django.views.decorators.debug import sensitive_variables
from rest_framework.exceptions import ValidationError

from .autenticacion_c2 import exigir_respaldo_para_temporal_qa
from .configuracion_c2 import habilitado
from .credenciales import estado_coherente, guardar_temporal
from .models import DesafioCorreo, DesafioRecuperacionCorreo, RecuperacionTIEvento, SeguridadCredencial, Usuario
from .recuperacion_c2 import bloquear_estado_recuperacion, normalizar_acceso
from .services_usuarios import ADMIN_MUTEX, ConflictoUsuario, _id, _text


def metadatos(operador, referencia, motivo):
    operador = _text(operador, 'operador', maximum=120)
    referencia = _text(referencia, 'referencia', maximum=120)
    motivo = _text(motivo, 'motivo', maximum=500)
    for nombre, campo in (('operador', operador), ('referencia', referencia)):
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._@:/-]*', campo):
            raise ValidationError({nombre: 'Identificador de auditoría inválido.'})
    if not motivo.isprintable():
        raise ValidationError({'motivo': 'Se requiere texto imprimible en una sola línea.'})
    return operador, referencia, motivo


def cuenta_elegible(qs, pk):
    cuenta = qs.filter(pk=_id(pk), rol=Usuario.Rol.ADMINISTRADOR_TI, is_active=True).first()
    if cuenta is None:
        raise ConflictoUsuario('cuenta_no_elegible', 'Se requiere una cuenta TI existente y activa.')
    return cuenta


@sensitive_variables()
@transaction.atomic(durable=True)
def recuperar(pk, version_confirmada, *, operador, referencia, motivo):
    operador, referencia, motivo = metadatos(operador, referencia, motivo)
    with connection.cursor() as cursor:
        cursor.execute('SELECT pg_advisory_xact_lock(%s)', [ADMIN_MUTEX])
    user = cuenta_elegible(Usuario.objects.select_for_update(), pk)
    if user.sesion_version != version_confirmada:
        raise ConflictoUsuario('cuenta_cambio', 'La cuenta cambió; vuelva a verificar y confirmar.')
    state = SeguridadCredencial.objects.select_for_update().filter(usuario=user).first()
    if not estado_coherente(state):
        raise ConflictoUsuario('seguridad_no_disponible', 'Estado de credencial no disponible; no se modificó la cuenta.')
    access = None
    if habilitado():
        access = bloquear_estado_recuperacion(user)
        exigir_respaldo_para_temporal_qa(user)
    emitida = guardar_temporal(user, state)
    DesafioRecuperacionCorreo.objects.filter(usuario=user).delete()
    DesafioCorreo.objects.filter(usuario=user, proposito=DesafioCorreo.Proposito.CAMBIO).delete()
    anterior, version = '', None
    if access is not None:
        anterior, _ = normalizar_acceso(access)
        version = access.version
    RecuperacionTIEvento.objects.create(usuario=user, acceso_anterior=anterior, acceso_version_nueva=version,
                                        operador=operador, referencia=referencia, motivo=motivo)
    return emitida
