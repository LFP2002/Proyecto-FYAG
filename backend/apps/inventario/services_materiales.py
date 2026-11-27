"""019B: UUID → Presupuesto → Obra → padres → artículo → saldo/valor → gasto/control.

SQL revalida enlaces y aplica proyecciones. No hay locks de Obras tras artículo.
Las seis clases de actos comparten un libro append-only y UUID global inventario.
"""
import hashlib
import json
import re
from decimal import Decimal, ROUND_HALF_UP, localcontext
from uuid import UUID

from django.db import connection, transaction, IntegrityError
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from apps.obras import services as obras, services_gastos as gastos
from apps.obras.models import GastoObra, CierreCostosObra
from apps.obras.exceptions import RecursoNoEncontrado, EstadoIncompatible
from .models import ArticuloInventario, ExistenciaInventario, EstadoValoracion, OperacionMaterial as Op, MovimientoInventario, MAXIMO
from .permissions_materiales import revalidar
from .services import contrato, texto, cantidad, identificador, ConflictoInventario

CENTAVO = Decimal('0.01')
PRECIO_MAXIMO = Decimal('9999999999999.99')
CAMPOS = {
    'AUTORIZACION_ENTREGA': {'obra', 'articulo', 'cantidad'}, 'ENTREGA': {'autorizacion', 'cantidad'},
    'AUTORIZACION_DEVOLUCION': {'entrega', 'cantidad'}, 'DEVOLUCION': {'autorizacion', 'cantidad'},
    'VALORIZACION': {'ingreso', 'costo_unitario_neto', 'referencia'},
    'REGULARIZACION': {'articulo', 'costo_unitario_neto', 'referencia', 'motivo'},
}


def conflicto(code='estado_incompatible'):
    raise ConflictoInventario(code, 'La operación de materiales no es compatible con su origen o estado actual.')


def precio(value):
    if type(value) is not str or not re.fullmatch(r'[0-9]{1,13}(?:\.[0-9]{1,2})?', value):
        raise ValidationError({'costo_unitario_neto': ['String decimal neto con hasta 13 enteros y 2 decimales requerido.']})
    return Decimal(value).quantize(CENTAVO)


def normalizar(tipo, data):
    requeridos = CAMPOS[tipo] | {'clave_idempotencia'}
    contrato(data, requeridos | {'referencia', 'motivo'}, requeridos)
    resultado = {}
    for campo in requeridos - {'clave_idempotencia'}:
        valor = data[campo]
        if campo == 'cantidad':
            resultado[campo] = cantidad(valor)
        elif campo == 'costo_unitario_neto':
            resultado[campo] = precio(valor)
        elif campo not in {'referencia', 'motivo'}:
            resultado[campo] = identificador(valor)
    resultado['referencia'] = texto(data.get('referencia', 'Registro BODEGA_019B'), 'referencia', 150)
    resultado['motivo'] = texto(data.get('motivo', 'Operación de materiales autorizada'), 'motivo', 2000)
    key = data['clave_idempotencia']
    if type(key) is not str or not re.fullmatch(r'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}', key):
        raise ValidationError({'clave_idempotencia': ['UUID canónico requerido.']})
    return resultado, UUID(key)


def _huella(tipo, data, actor):
    canonical = {k: str(v) if isinstance(v, Decimal) else v for k, v in data.items()}
    return hashlib.sha256(json.dumps({'tipo': tipo, 'actor': actor.pk, **canonical}, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def operar(tipo, payload, actor):
    revalidar(actor, tipo, escritura=True)
    data, key = normalizar(tipo, payload)
    huella = _huella(tipo, data, actor)
    try:
        with transaction.atomic():
            return _operar(tipo, data, key, huella, actor)
    except IntegrityError as exc:
        if getattr(getattr(exc.__cause__, 'diag', None), 'constraint_name', '') in {'inv_019b_integridad', 'inv_merma_integridad'}:
            conflicto()
        raise


def _obtener(model, pk):
    manager = model.objects if hasattr(model, 'objects') else model
    obj = manager.filter(pk=pk).first()
    if obj is None:
        raise NotFound('Referencia de materiales no disponible.')
    return obj


def _autorizar_entrega_bloqueada(obra, articulo, q, actor, key, huella, referencia, motivo, *,
                                solicitud=None, item_presupuesto=None):
    """Núcleo compartido 019B/019C-1, sin locks asesores nuevos.

    Caller posee transacción, Presupuesto/Obra y artículo, en ese orden.
    Las operaciones públicas adquieren el lock UUID antes de las raíces;
    019F usa UUID interno nuevo y la unicidad persistente del ítem.
    019C-1 bloquea además solicitud/participante antes del artículo. El trigger
    019B conserva sus verificaciones de origen, unidad, rol y estado.
    """
    if not connection.in_atomic_block:
        raise RuntimeError('La autorización requiere una transacción y sus raíces bloqueadas.')
    actual = revalidar(actor, 'AUTORIZACION_ENTREGA', escritura=True)
    if obra.estado not in {'EN_PROCESO', 'SUSPENDIDA'} or not articulo.activo:
        conflicto()
    op = Op.objects.create(tipo='AUTORIZACION_ENTREGA', obra=obra, articulo=articulo, cantidad=q,
        unidad=articulo.unidad, actor=actual, clave_idempotencia=key, huella=huella,
        referencia=referencia, motivo=motivo, solicitud_material=solicitud, item_presupuesto=item_presupuesto)
    revalidar(actor, 'AUTORIZACION_ENTREGA', escritura=True)
    return op


def _operar(tipo, data, key, huella, actor):
    lock = int.from_bytes(hashlib.sha256(key.bytes).digest()[:4], 'big', signed=True)
    with connection.cursor() as cursor:
        cursor.execute('SELECT pg_advisory_xact_lock(1900, %s)', [lock])
    actual = revalidar(actor, tipo, escritura=True)
    anterior = Op.objects.filter(clave_idempotencia=key).first()
    if anterior:
        if anterior.huella != huella:
            conflicto('idempotencia_conflictiva')
        return anterior, False
    if MovimientoInventario.objects.filter(clave_idempotencia=key).exists():
        conflicto('idempotencia_conflictiva')
    campos = dict(tipo=tipo, clave_idempotencia=key, huella=huella, actor=actual,
                  referencia=data['referencia'], motivo=data['motivo'])
    padre = original = ingreso = None
    obra_id = data.get('obra')
    articulo_id = data.get('articulo')
    q = data.get('cantidad')
    if tipo in {'ENTREGA', 'DEVOLUCION'}:
        padre = _obtener(Op, data['autorizacion'])
        esperado = 'AUTORIZACION_ENTREGA' if tipo == 'ENTREGA' else 'AUTORIZACION_DEVOLUCION'
        if padre.tipo != esperado:
            conflicto()
        obra_id, articulo_id = padre.obra_id, padre.articulo_id
        campos['autorizacion'] = padre
        if tipo == 'DEVOLUCION':
            original = _obtener(Op, padre.entrega_id)
    elif tipo == 'AUTORIZACION_DEVOLUCION':
        original = _obtener(Op, data['entrega'])
        if original.tipo != 'ENTREGA':
            conflicto()
        obra_id, articulo_id = original.obra_id, original.articulo_id
    elif tipo == 'VALORIZACION':
        ingreso = _obtener(MovimientoInventario, data['ingreso'])
        articulo_id, q = ingreso.articulo_id, ingreso.cantidad
        campos['ingreso'] = ingreso
    obra = None
    if obra_id:
        try:
            obra = obras._obra_bloqueada(obra_id)
        except RecursoNoEncontrado:
            raise NotFound('Obra no disponible.') from None
        except EstadoIncompatible:
            conflicto()
        if obra.estado not in {'EN_PROCESO', 'SUSPENDIDA'}:
            conflicto()
        campos['obra'] = obra
    padres = [x.pk for x in (padre, original) if x is not None]
    list(Op.objects.select_for_update().filter(pk__in=padres).order_by('pk'))
    # C2: la entrega original es la raíz común con clasificación MO. Revalidar
    # tras esperar antes de revelar un conflicto o generar cualquier efecto.
    revalidar(actor, tipo, escritura=True)
    if tipo in {'AUTORIZACION_DEVOLUCION', 'DEVOLUCION'}:
        from .services_mermas import aprobada
        from django.db.models import Sum
        total = Op.objects.filter(entrega=original, tipo=tipo).aggregate(q=Sum('cantidad'))['q'] or Decimal('0.000')
        if aprobada(original.pk) + total + q > original.cantidad:
            conflicto('remanente_insuficiente')
    articulo = _obtener(ArticuloInventario.objects.select_for_update(), articulo_id)
    stock = _obtener(ExistenciaInventario.objects.select_for_update(), articulo_id)
    valor = _obtener(EstadoValoracion.objects.select_for_update(), articulo_id)
    actual = revalidar(actor, tipo, escritura=True)
    campos.update(actor=actual, articulo=articulo, unidad=articulo.unidad)
    if not articulo.activo and tipo not in {'DEVOLUCION', 'VALORIZACION', 'REGULARIZACION'}:
        conflicto()
    if original:
        campos['entrega'] = original
    from django.db.models import Sum
    def acumulada(**filtros):
        return Op.objects.filter(**filtros).aggregate(q=Sum('cantidad'))['q'] or Decimal('0.000')
    if padre and acumulada(autorizacion=padre, tipo=tipo) + q > padre.cantidad:
        conflicto('remanente_insuficiente')
    if tipo == 'AUTORIZACION_DEVOLUCION' and acumulada(entrega=original, tipo=tipo) + q > original.cantidad:
        conflicto('remanente_insuficiente')
    if tipo == 'REGULARIZACION':
        q = valor.saldo_historico
        if q <= 0 or Op.objects.filter(articulo=articulo, tipo__in=['REGULARIZACION', 'VALORIZACION']).exists():
            conflicto()
    if tipo == 'VALORIZACION':
        if ingreso.tipo != 'INGRESO' or ingreso.pk <= (valor.ultimo_movimiento_historico or 0) or Op.objects.filter(ingreso=ingreso).exists():
            conflicto()
        if valor.saldo_historico > 0 and not Op.objects.filter(articulo=articulo, tipo='REGULARIZACION').exists():
            conflicto('valoracion_pendiente')
        if MovimientoInventario.objects.filter(articulo=articulo, tipo='INGRESO', id__gt=valor.ultimo_movimiento_historico or 0,
            id__lt=ingreso.pk, valoracion__isnull=True).exists():
            conflicto('orden_valoracion')
    campos['cantidad'] = q
    if tipo == 'AUTORIZACION_ENTREGA':
        return _autorizar_entrega_bloqueada(obra, articulo, q, actor, key, huella, data['referencia'], data['motivo']), True
    economica = tipo not in {'AUTORIZACION_ENTREGA', 'AUTORIZACION_DEVOLUCION'}
    costo = None
    if economica:
        costo = valor.promedio if tipo == 'ENTREGA' else original.costo_unitario_neto if tipo == 'DEVOLUCION' else data['costo_unitario_neto']
        if tipo == 'ENTREGA' and (valor.saldo_valorado != stock.saldo or costo is None):
            conflicto('valoracion_pendiente')
        if tipo == 'ENTREGA' and q > stock.saldo:
            conflicto('existencia_insuficiente')
        if tipo == 'DEVOLUCION' and stock.saldo + q > MAXIMO:
            conflicto('saldo_fuera_rango')
        with localcontext() as ctx:
            ctx.prec = 60
            subtotal = (q * costo).quantize(CENTAVO, rounding=ROUND_HALF_UP)
            nuevo_saldo = valor.saldo_valorado - q if tipo == 'ENTREGA' else valor.saldo_valorado + q
            if tipo == 'ENTREGA':
                promedio = valor.promedio if nuevo_saldo else None
            else:
                numerador = valor.saldo_valorado * (valor.promedio or Decimal(0)) + q * costo
                promedio = (numerador / nuevo_saldo).quantize(CENTAVO, rounding=ROUND_HALF_UP)
                if numerador > 0 and promedio == 0:
                    conflicto('importe_fuera_rango' if tipo in {'VALORIZACION', 'REGULARIZACION'} else 'estado_incompatible')
            if costo > 0 and subtotal == 0 or subtotal > CierreCostosObra.LIMITE_IMPORTE or promedio is not None and promedio > PRECIO_MAXIMO:
                conflicto('importe_fuera_rango' if tipo in {'VALORIZACION', 'REGULARIZACION'} else 'estado_incompatible')
        campos.update(costo_unitario_neto=costo, saldo_valorado_anterior=valor.saldo_valorado,
            saldo_valorado_posterior=nuevo_saldo, promedio_anterior=valor.promedio, promedio_posterior=promedio)
    gasto = None
    if tipo == 'ENTREGA':
        gasto = GastoObra.objects.create(obra=obra, tipo='MATERIAL', origen='BODEGA_019B', descripcion=articulo.nombre,
            unidad=articulo.unidad, cantidad=q, costo_unitario_neto=costo, fecha_gasto=timezone.localdate(),
            referencia_respaldo=data['referencia'], registrado_por=actual)
        campos['gasto'] = gasto
    op = Op.objects.create(**campos)
    if tipo in {'ENTREGA', 'DEVOLUCION'}:
        MovimientoInventario.objects.create(articulo=articulo, tipo='SALIDA' if tipo == 'ENTREGA' else 'DEVOLUCION',
            clave_idempotencia=key, cantidad=q, saldo_anterior=stock.saldo,
            saldo_posterior=stock.saldo-q if tipo == 'ENTREGA' else stock.saldo+q, actor=actual,
            referencia=data['referencia'], motivo=data['motivo'], operacion=op)
        antes = {}
        extras = {'origen': 'BODEGA_019B', 'operacion_material': op.pk}
        if tipo == 'DEVOLUCION':
            gasto = GastoObra.objects.select_for_update().get(pk=original.gasto_id)
            antes = gastos._snapshot(gasto)
            gasto.cantidad_devuelta += q
            gasto.save(update_fields=['cantidad_devuelta', 'actualizado_en'])
            extras['devolucion'] = {'cantidad': format(q, '.3f'), 'fecha': timezone.localdate().isoformat()}
        gastos._evento(gasto, 'ALTA' if tipo == 'ENTREGA' else 'DEVOLUCION', actual, data['motivo'], antes, **extras)
    revalidar(actor, tipo, escritura=True)
    return op, True
