"""SPEC-019F: previsión comercial congelada y conciliación física 019B/C."""
from decimal import Decimal
from uuid import uuid4

from django.db.models import DecimalField, F, OuterRef, Subquery, Sum, Value
from django.db.models.functions import Coalesce

from apps.comercial.models import PresupuestoItem
from apps.inventario.models import ArticuloInventario, OperacionMaterial as Op
from apps.inventario.services_materiales import _autorizar_entrega_bloqueada, _huella

from .exceptions import DatosInvalidos


DECIMAL = DecimalField(max_digits=24, decimal_places=3)
ZERO = Value(Decimal('0.000'), output_field=DECIMAL)


def previstos(obra):
    return PresupuestoItem.objects.filter(presupuesto_id=obra.presupuesto_id, articulo__isnull=False)


def autorizar_prevision(obra, usuario, motivo, *, token=None):
    """Solo en el inicio; el caller posee los locks Presupuesto → Obra → técnico."""
    items = list(previstos(obra).order_by('articulo_id', 'id'))
    articulos = {a.pk: a for a in ArticuloInventario.objects.select_for_update().filter(
        pk__in={i.articulo_id for i in items}).order_by('pk')}
    from .services import _actor_019f
    _actor_019f(usuario, token)
    errores = []
    for item in items:
        articulo = articulos[item.articulo_id]
        if not articulo.activo:
            errores.append(f'{item.codigo_articulo}: material inactivo. Solicite a Bodega regularizar el catálogo.')
        elif articulo.unidad != item.unidad:
            errores.append(f'{item.codigo_articulo}: unidad incompatible con la prevista ({item.unidad}). '
                           'Solicite a Bodega revisar el catálogo antes de iniciar.')
    if errores:
        raise DatosInvalidos({'materiales': errores})
    for item in items:
        referencia = f'Previsión {obra.codigo} · {item.codigo_articulo}'
        tipo = 'AUTORIZACION_ENTREGA'
        huella = _huella(tipo, {'item_presupuesto': item.pk, 'obra': obra.pk, 'articulo': item.articulo_id,
                                'cantidad': item.cantidad, 'referencia': referencia, 'motivo': motivo}, usuario)
        _autorizar_entrega_bloqueada(obra, articulos[item.articulo_id], item.cantidad, usuario,
                                    uuid4(), huella, referencia, motivo, item_presupuesto=item)


def _suma(tipo, grupo, **filtros):
    qs = Op.objects.filter(tipo=tipo, **filtros).order_by().values(grupo)
    return Coalesce(Subquery(qs.annotate(total=Sum('cantidad')).values('total'), output_field=DECIMAL), ZERO)


def autorizaciones(obra):
    return Op.objects.filter(obra=obra, tipo='AUTORIZACION_ENTREGA')


def conciliacion(obra, origen):
    if origen == 'PRESUPUESTO':
        return previstos(obra).annotate(
            autorizacion_id=F('autorizacion_prevista__pk'),
            autorizado=Coalesce(F('autorizacion_prevista__cantidad'), ZERO, output_field=DECIMAL),
            despachado=_suma('ENTREGA', 'autorizacion__item_presupuesto_id',
                             autorizacion__item_presupuesto_id=OuterRef('pk')),
            devuelto=_suma('DEVOLUCION', 'entrega__autorizacion__item_presupuesto_id',
                           entrega__autorizacion__item_presupuesto_id=OuterRef('pk')),
        )
    return autorizaciones(obra).filter(item_presupuesto__isnull=True).select_related('articulo').annotate(
        autorizado=F('cantidad'),
        despachado=_suma('ENTREGA', 'autorizacion_id', autorizacion_id=OuterRef('pk')),
        devuelto=_suma('DEVOLUCION', 'entrega__autorizacion_id', entrega__autorizacion_id=OuterRef('pk')),
    ).order_by('pk')


def fila(obj, obra, previsto):
    autorizacion = obj.autorizacion_id if previsto else obj.pk
    pendiente = obj.autorizado - obj.despachado
    return {
        'id': obj.pk, 'articulo': obj.articulo_id,
        'origen': 'PRESUPUESTO' if previsto else ('SOLICITUD' if obj.solicitud_material_id else 'SIN_VINCULO_PRESUPUESTARIO'),
        'codigo': obj.codigo_articulo if previsto else obj.articulo.codigo,
        'nombre': obj.descripcion if previsto else obj.articulo.nombre,
        'unidad': obj.unidad,
        'presupuestado': format(obj.cantidad, '.3f') if previsto else None,
        'autorizado': format(obj.autorizado, '.3f'), 'despachado': format(obj.despachado, '.3f'),
        'devuelto': format(obj.devuelto, '.3f'),
        'neto_imputado': format(obj.despachado - obj.devuelto, '.3f'),
        'pendiente_despacho': format(pendiente, '.3f'),
        'estado': ('SIN_AUTORIZACION' if autorizacion is None else 'COMPLETADO' if not pendiente
                   else 'INHABILITADO' if obra.estado in {'FINALIZADA', 'CANCELADA'}
                   else 'PARCIAL' if obj.despachado else 'PENDIENTE'),
    }
