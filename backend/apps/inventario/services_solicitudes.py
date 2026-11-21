"""019C-1: UUID C1 (1903) → UUID autorización B (1900) → raíces → solicitud/
participante → artículo → núcleo 019B. Ningún lock asesor nuevo tras las raíces.
"""
import hashlib
import json
import re
import unicodedata
from decimal import Decimal
from uuid import UUID, uuid4

from django.db import connection, transaction, IntegrityError
from rest_framework.exceptions import NotFound, ValidationError

from apps.obras import services as obras
from apps.obras.exceptions import RecursoNoEncontrado, EstadoIncompatible
from apps.obras.models import ObraParticipante
from apps.usuarios.models import Usuario
from .models import SolicitudMaterialObra as Solicitud, SolicitudMaterialEvento as Evento, ArticuloInventario, OperacionMaterial, MovimientoInventario
from .permissions_solicitudes import revalidar
from .services import cantidad, identificador, texto, contrato, ConflictoInventario
from . import services_materiales as bodega


def conflicto(code='estado_incompatible'):
    raise ConflictoInventario(code, 'La solicitud no es compatible con su estado u origen actual.')


def _clave(value):
    if type(value) is not str or not re.fullmatch(r'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}', value):
        raise ValidationError({'clave_idempotencia': ['UUID canónico requerido.']})
    return UUID(value)


def _texto(value, campo, maximo=2000):
    if isinstance(value, str) and any(unicodedata.category(c) == 'Cc' for c in value):
        raise ValidationError({campo: ['Texto sin caracteres de control requerido.']})
    return texto(value, campo, maximo)


def _huella(accion, data, actor):
    normal = {k: str(v) if isinstance(v, Decimal) else v for k, v in data.items()}
    return hashlib.sha256(json.dumps({'accion': accion, 'actor': actor.pk, **normal}, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _bloquear_uuid(key, namespace):
    digest = int.from_bytes(hashlib.sha256(key.bytes).digest()[:4], 'big', signed=True)
    with connection.cursor() as cursor:
        cursor.execute('SELECT pg_advisory_xact_lock(%s, %s)', [namespace, digest])


def _replay(key, huella):
    evento = Evento.objects.select_related('solicitud').filter(clave_idempotencia=key).first()
    if evento is not None and evento.huella != huella:
        conflicto('idempotencia_conflictiva')
    return evento


def _obra(pk, actor, accion):
    try:
        obra = obras._obra_bloqueada(pk)
    except RecursoNoEncontrado:
        raise NotFound('Obra no disponible.') from None
    except EstadoIncompatible:
        conflicto()
    revalidar(actor, accion)
    if obra.estado not in {'EN_PROCESO', 'SUSPENDIDA'}:
        conflicto()
    return obra


def _articulo(pk):
    articulo = ArticuloInventario.objects.select_for_update().filter(pk=pk).first()
    if articulo is None:
        raise NotFound('Artículo no disponible.')
    return articulo


def _integridad(exc):
    name = getattr(getattr(exc.__cause__, 'diag', None), 'constraint_name', '')
    if name in {'inv_sol_integridad', 'inv_019b_integridad'}:
        conflicto()
    raise exc


def crear_solicitud(payload, actor):
    revalidar(actor, 'crear')
    campos = {'obra', 'articulo', 'cantidad', 'justificacion', 'clave_idempotencia'}
    contrato(payload, campos, campos)
    key = _clave(payload['clave_idempotencia'])
    data = {'obra': identificador(payload['obra']), 'articulo': identificador(payload['articulo']),
            'cantidad': cantidad(payload['cantidad']), 'justificacion': _texto(payload['justificacion'], 'justificacion')}
    huella = _huella('crear', data, actor)
    try:
        with transaction.atomic():
            _bloquear_uuid(key, 1903)
            actual = revalidar(actor, 'crear')
            previo = _replay(key, huella)
            if previo is not None:
                return previo.solicitud, False
            # No revelar una Obra ajena. Se vuelve a comprobar bajo su raíz.
            if not ObraParticipante.objects.filter(obra_id=data['obra'], tecnico=actual, activo=True).exists():
                raise NotFound('Obra no disponible.')
            obra = _obra(data['obra'], actor, 'crear')
            participante = ObraParticipante.objects.select_for_update().filter(obra=obra, tecnico=actual, activo=True).first()
            if participante is None:
                raise NotFound('Obra no disponible.')
            articulo = _articulo(data['articulo'])
            actual = revalidar(actor, 'crear')
            if not articulo.activo:
                conflicto()
            solicitud = Solicitud.objects.create(obra=obra, articulo=articulo, unidad=articulo.unidad,
                solicitante=actual, cantidad_solicitada=data['cantidad'], justificacion=data['justificacion'],
                clave_idempotencia=key, huella=huella)
            Evento.objects.create(solicitud=solicitud, tipo='CREACION', actor=actual, motivo=solicitud.justificacion,
                clave_idempotencia=key, huella=huella, creado_en=solicitud.creado_en)
            revalidar(actor, 'crear')
            return solicitud, True
    except IntegrityError as exc:
        _integridad(exc)


def decidir_solicitud(pk, payload, actor):
    revalidar(actor, 'decidir')
    identificador(pk)
    contrato(payload, {'decision', 'cantidad_aprobada', 'motivo', 'clave_idempotencia'}, {'decision', 'motivo', 'clave_idempotencia'})
    decision = payload['decision']
    if decision not in ('APROBAR', 'RECHAZAR'):
        raise ValidationError({'decision': ['Use APROBAR o RECHAZAR.']})
    if (decision == 'APROBAR') != ('cantidad_aprobada' in payload):
        raise ValidationError({'cantidad_aprobada': ['Obligatoria únicamente al aprobar.']})
    q = cantidad(payload['cantidad_aprobada']) if decision == 'APROBAR' else None
    data = {'solicitud': pk, 'decision': decision, 'cantidad_aprobada': q, 'motivo': _texto(payload['motivo'], 'motivo')}
    key = _clave(payload['clave_idempotencia'])
    huella = _huella('decidir', data, actor)
    try:
        with transaction.atomic():
            _bloquear_uuid(key, 1903)
            revalidar(actor, 'decidir')
            previo = _replay(key, huella)
            if previo is not None:
                return previo.solicitud, False
            referencia = Solicitud.objects.filter(pk=pk).first()
            if referencia is None:
                raise NotFound('Solicitud no encontrada.')
            clave_autorizacion = None
            if decision == 'APROBAR':
                clave_autorizacion = uuid4()
                while clave_autorizacion in {key, referencia.clave_idempotencia}:
                    clave_autorizacion = uuid4()
                _bloquear_uuid(clave_autorizacion, 1900)  # Antes de cualquier raíz.
                if OperacionMaterial.objects.filter(clave_idempotencia=clave_autorizacion).exists() or MovimientoInventario.objects.filter(clave_idempotencia=clave_autorizacion).exists():
                    conflicto('idempotencia_conflictiva')
            obra = _obra(referencia.obra_id, actor, 'decidir')
            solicitud = Solicitud.objects.select_for_update().get(pk=pk)
            participante = ObraParticipante.objects.select_for_update().filter(obra=obra, tecnico_id=solicitud.solicitante_id, activo=True).first()
            articulo = _articulo(solicitud.articulo_id)
            actual = revalidar(actor, 'decidir')
            if solicitud.estado != 'PENDIENTE':
                conflicto('solicitud_ya_decidida')
            autorizacion = None
            if decision == 'APROBAR':
                if (participante is None or not articulo.activo or articulo.unidad != solicitud.unidad
                    or not Usuario.objects.filter(pk=solicitud.solicitante_id, is_active=True, rol='TECNICO').exists()):
                    conflicto()
                if q > solicitud.cantidad_solicitada:
                    conflicto('cantidad_aprobada_excesiva')
                datos_b = {'obra': obra.pk, 'articulo': articulo.pk, 'cantidad': q,
                    'referencia': f'Solicitud de materiales {solicitud.pk}', 'motivo': data['motivo']}
                autorizacion = bodega._autorizar_entrega_bloqueada(obra, articulo, q, actor, clave_autorizacion,
                    bodega._huella('AUTORIZACION_ENTREGA', datos_b, actual), datos_b['referencia'], data['motivo'], solicitud=solicitud)
            Evento.objects.create(solicitud=solicitud, tipo='APROBACION' if decision == 'APROBAR' else 'RECHAZO',
                actor=actual, motivo=data['motivo'], cantidad_aprobada=q, autorizacion=autorizacion,
                clave_idempotencia=key, huella=huella)
            solicitud.refresh_from_db()  # Proyección aplicada por el evento SQL.
            revalidar(actor, 'decidir')
            return solicitud, True
    except IntegrityError as exc:
        _integridad(exc)
