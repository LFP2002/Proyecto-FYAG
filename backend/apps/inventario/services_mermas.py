"""C2 UUID1904 → [MB UUID1900 → artículo/stock/valor | MO raíces/entrega] → merma.

MO nunca adquiere locks explícitos de artículo, gasto o control de costos.
SQL valida origen y proyecta cada decisión; no se actualizan proyecciones ORM.
"""
from decimal import Decimal, ROUND_HALF_UP, localcontext
from uuid import uuid4

from django.db import transaction, IntegrityError
from django.db.models import Sum
from rest_framework.exceptions import NotFound, ValidationError

from apps.obras import services as obras
from apps.obras.exceptions import RecursoNoEncontrado, EstadoIncompatible
from apps.obras.models import ObraParticipante, GastoObra
from apps.usuarios.models import Usuario
from .models import Merma, MermaEvento as Evento, ArticuloInventario, ExistenciaInventario, EstadoValoracion, OperacionMaterial as Op, MovimientoInventario as Movimiento, TIPOS_MB, TIPOS_MO
from .permissions_mermas import revalidar
from .services import contrato, cantidad, identificador, ConflictoInventario
from .services_solicitudes import _clave, _texto, _huella, _bloquear_uuid

CENTAVO = Decimal('0.01')


def conflicto(code='estado_incompatible'):
    raise ConflictoInventario(code, 'La merma no es compatible con su estado u origen actual.')


def importe(q, costo, *, estricto=True):
    with localcontext() as ctx:
        ctx.prec = 60
        total = (q*costo).quantize(CENTAVO, rounding=ROUND_HALF_UP)
        if estricto and costo > 0 and total == 0:
            conflicto('importe_fuera_rango')
        return total


def aprobada(entrega):
    return Merma.objects.filter(ambito='OBRA', entrega_id=entrega, estado='APROBADA').aggregate(q=Sum('cantidad'))['q'] or Decimal('0.000')


def _integridad(exc):
    if getattr(getattr(exc.__cause__, 'diag', None), 'constraint_name', '') == 'inv_merma_integridad':
        conflicto()
    raise exc


def normalizar(ambito, payload):
    requeridos = {'cantidad', 'tipo', 'motivo', 'clave_idempotencia'} | ({'articulo', 'referencia_respaldo'} if ambito == 'BODEGA' else {'entrega', 'actividad'})
    contrato(payload, requeridos | ({'referencia'} if ambito == 'OBRA' else set()), requeridos)
    key = _clave(payload['clave_idempotencia'])
    tipos = TIPOS_MB if ambito == 'BODEGA' else TIPOS_MO
    if type(payload['tipo']) is not str or payload['tipo'] not in tipos:
        raise ValidationError({'tipo': ['Tipo de merma no permitido.']})
    data = {'cantidad': cantidad(payload['cantidad']), 'tipo': payload['tipo'], 'motivo': _texto(payload['motivo'], 'motivo')}
    if ambito == 'BODEGA':
        data.update(articulo=identificador(payload['articulo']), referencia=_texto(payload['referencia_respaldo'], 'referencia_respaldo', 150), actividad='')
    else:
        referencia = payload.get('referencia', '')
        if referencia != '':
            referencia = _texto(referencia, 'referencia', 150)
        data.update(entrega=identificador(payload['entrega']), actividad=_texto(payload['actividad'], 'actividad'), referencia=referencia)
    return data, key


def _replay(key, huella):
    previo = Evento.objects.select_related('merma').filter(clave_idempotencia=key).first()
    if previo and previo.huella != huella:
        conflicto('idempotencia_conflictiva')
    return previo


def _stock(pk):
    articulo = ArticuloInventario.objects.select_for_update().filter(pk=pk).first()
    if articulo is None:
        raise NotFound('Artículo no disponible.')
    stock = ExistenciaInventario.objects.select_for_update().get(pk=pk)
    valor = EstadoValoracion.objects.select_for_update().get(pk=pk)
    return articulo, stock, valor


def _entrega(pk, actor, accion):
    entrega = Op.objects.filter(pk=pk, tipo='ENTREGA').first()
    if entrega is None:
        raise NotFound('Entrega no disponible.')
    # Pre-scope para no revelar Obras ajenas, revalidado bajo raíz.
    if accion == 'crear' and not ObraParticipante.objects.filter(obra_id=entrega.obra_id, tecnico_id=actor.pk, activo=True).exists():
        raise NotFound('Entrega no disponible.')
    try:
        obra = obras._obra_bloqueada(entrega.obra_id)
    except RecursoNoEncontrado:
        raise NotFound('Entrega no disponible.') from None
    except EstadoIncompatible:
        conflicto()
    revalidar(actor, 'OBRA', accion)
    if obra.estado not in {'EN_PROCESO', 'SUSPENDIDA'}:
        conflicto()
    return Op.objects.select_for_update().get(pk=pk)


def crear(ambito, payload, actor):
    revalidar(actor, ambito, 'crear')
    data, key = normalizar(ambito, payload)
    huella = _huella('crear_merma_'+ambito, data, actor)
    try:
        with transaction.atomic():
            _bloquear_uuid(key, 1904)
            actual = revalidar(actor, ambito, 'crear')
            previo = _replay(key, huella)
            if previo:
                return previo.merma, False
            campos = dict(data)
            if ambito == 'BODEGA':
                articulo, _, _ = _stock(data['articulo'])
                actual = revalidar(actor, ambito, 'crear')
                if not articulo.activo:
                    conflicto()
                campos.update(articulo=articulo, unidad=articulo.unidad, corte_movimiento=Movimiento.objects.filter(articulo=articulo).order_by('-pk').first())
            else:
                entrega = _entrega(data['entrega'], actor, 'crear')
                participante = ObraParticipante.objects.select_for_update().filter(obra_id=entrega.obra_id, tecnico=actual, activo=True).first()
                actual = revalidar(actor, ambito, 'crear')
                if participante is None:
                    raise NotFound('Entrega no disponible.')
                if data['cantidad'] > entrega.cantidad:
                    conflicto('remanente_insuficiente')
                campos.update(entrega=entrega, obra_id=entrega.obra_id, articulo_id=entrega.articulo_id, unidad=entrega.unidad)
            merma = Merma.objects.create(ambito=ambito, informado_por=actual, clave_idempotencia=key, huella=huella, **campos)
            Evento.objects.create(merma=merma, tipo='CREACION', actor=actual, motivo=merma.motivo, clave_idempotencia=key, huella=huella, creado_en=merma.creado_en)
            revalidar(actor, ambito, 'crear')
            return merma, True
    except IntegrityError as exc:
        _integridad(exc)


def decidir(ambito, pk, payload, actor):
    revalidar(actor, ambito, 'decidir')
    identificador(pk)
    contrato(payload, {'decision', 'motivo', 'clave_idempotencia'}, {'decision', 'motivo', 'clave_idempotencia'})
    if payload['decision'] not in ('APROBAR', 'RECHAZAR'):
        raise ValidationError({'decision': ['Use APROBAR o RECHAZAR.']})
    data = {'merma': pk, 'decision': payload['decision'], 'motivo': _texto(payload['motivo'], 'motivo')}
    key = _clave(payload['clave_idempotencia'])
    huella = _huella('decidir_merma_'+ambito, data, actor)
    try:
        with transaction.atomic():
            _bloquear_uuid(key, 1904)
            revalidar(actor, ambito, 'decidir')
            previo = _replay(key, huella)
            if previo:
                return previo.merma, False
            referencia = Merma.objects.filter(pk=pk, ambito=ambito).first()
            if referencia is None:
                raise NotFound('Merma no disponible.')
            aprobar = data['decision'] == 'APROBAR'
            fisica = None
            if ambito == 'BODEGA':
                if aprobar:
                    fisica = uuid4()
                    while fisica in {key, referencia.clave_idempotencia}:
                        fisica = uuid4()
                    _bloquear_uuid(fisica, 1900)
                    if Op.objects.filter(clave_idempotencia=fisica).exists() or Movimiento.objects.filter(clave_idempotencia=fisica).exists():
                        conflicto('idempotencia_conflictiva')
                articulo, stock, valor = _stock(referencia.articulo_id)
            else:
                entrega = _entrega(referencia.entrega_id, actor, 'decidir')
            merma = Merma.objects.select_for_update().get(pk=pk)
            actual = revalidar(actor, ambito, 'decidir')
            if merma.estado != 'PENDIENTE':
                conflicto('merma_ya_decidida')
            op = None
            if aprobar and ambito == 'BODEGA':
                ultimo = Movimiento.objects.filter(articulo=articulo).order_by('-pk').values_list('pk', flat=True).first()
                if merma.corte_movimiento_id != ultimo:
                    conflicto('corte_desactualizado')
                if not articulo.activo or articulo.unidad != merma.unidad:
                    conflicto()
                if stock.saldo < merma.cantidad:
                    conflicto('existencia_insuficiente')
                if stock.saldo != valor.saldo_valorado or valor.promedio is None:
                    conflicto('valoracion_pendiente')
                importe(merma.cantidad, valor.promedio)
                posterior = valor.saldo_valorado-merma.cantidad
                observacion = f'Merma de Bodega {merma.pk}; informante {merma.informado_por_id}'
                op = Op.objects.create(tipo='MERMA', merma_bodega=merma, articulo=articulo, cantidad=merma.cantidad, unidad=merma.unidad,
                    actor=actual, clave_idempotencia=fisica, huella=huella, referencia=merma.referencia, motivo=observacion,
                    costo_unitario_neto=valor.promedio, saldo_valorado_anterior=valor.saldo_valorado, saldo_valorado_posterior=posterior,
                    promedio_anterior=valor.promedio, promedio_posterior=valor.promedio if posterior else None)
                Movimiento.objects.create(tipo='MERMA', operacion=op, articulo=articulo, cantidad=merma.cantidad,
                    actor=actual, clave_idempotencia=fisica, referencia=merma.referencia, motivo=observacion,
                    saldo_anterior=stock.saldo, saldo_posterior=stock.saldo-merma.cantidad)
            elif aprobar:
                participante = ObraParticipante.objects.select_for_update().filter(obra_id=merma.obra_id, tecnico_id=merma.informado_por_id, activo=True).first()
                actual = revalidar(actor, ambito, 'decidir')
                if (participante is None or not Usuario.objects.filter(pk=merma.informado_por_id, is_active=True, rol='TECNICO').exists()
                    or not GastoObra.objects.filter(pk=entrega.gasto_id, obra_id=merma.obra_id, vigente=True, origen='BODEGA_019B').exists()):
                    conflicto()
                recibidas = Op.objects.filter(entrega=entrega, tipo='DEVOLUCION').aggregate(q=Sum('cantidad'))['q'] or Decimal(0)
                if aprobada(entrega.pk)+recibidas+merma.cantidad > entrega.cantidad:
                    conflicto('remanente_insuficiente')
            Evento.objects.create(merma=merma, tipo='APROBACION' if aprobar else 'RECHAZO', actor=actual, motivo=data['motivo'],
                operacion=op, clave_idempotencia=key, huella=huella)
            merma.refresh_from_db()
            revalidar(actor, ambito, 'decidir')
            return merma, True
    except IntegrityError as exc:
        _integridad(exc)
