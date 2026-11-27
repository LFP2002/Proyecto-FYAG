from decimal import Decimal

from django.db.models import OuterRef, Subquery, Sum, Value, F, DecimalField
from django.db.models.functions import Coalesce, Greatest, Least

from .models import OperacionMaterial, EstadoValoracion, Merma
from .permissions_materiales import revalidar
from .permissions import revalidar as lector_inventario
from .views import query, articulo_filtro


def listado(actor, tipo, params):
    revalidar(actor, tipo)
    permitidos = {'articulo'} | ({'obra', 'autorizacion', 'entrega'} if tipo not in {'VALORIZACION', 'REGULARIZACION'} else set())
    query(params, permitidos)
    qs = OperacionMaterial.objects.filter(tipo=tipo).order_by('id')
    for campo in permitidos & set(params):
        qs = qs.filter(**{campo + '_id': articulo_filtro({'articulo': params[campo]})})
    return con_recibible(qs) if tipo == 'AUTORIZACION_DEVOLUCION' else qs


def con_recibible(qs):
    decimal = DecimalField(max_digits=12, decimal_places=3)
    cero = Value(Decimal('0.000'), output_field=decimal)

    def suma(model, grupo, **filtros):
        sub = model.objects.filter(**filtros).order_by().values(grupo).annotate(q=Sum('cantidad')).values('q')
        return Coalesce(Subquery(sub, output_field=decimal), cero)

    return qs.annotate(
        _recibida=suma(OperacionMaterial, 'autorizacion_id', autorizacion_id=OuterRef('pk'), tipo='DEVOLUCION'),
        _total_recibida=suma(OperacionMaterial, 'entrega_id', entrega_id=OuterRef('entrega_id'), tipo='DEVOLUCION'),
        _mermada=suma(Merma, 'entrega_id', entrega_id=OuterRef('entrega_id'), ambito='OBRA', estado='APROBADA'),
    ).annotate(cantidad_recibible_efectiva=Greatest(cero, Least(F('cantidad')-F('_recibida'),
        F('entrega__cantidad')-F('_total_recibida')-F('_mermada')), output_field=decimal))


def estados(actor, params):
    lector_inventario(actor)
    query(params, {'articulo'})
    qs = EstadoValoracion.objects.select_related('articulo__existencia').order_by('articulo_id')
    if 'articulo' in params:
        qs = qs.filter(articulo_id=articulo_filtro(params))
    return qs


def estado_publico(valor):
    # Sin precios ni cantidades valoradas: las cantidades físicas permanecen
    # en existencias/; no inferir un importe a través de filtros económicos.
    saldo = valor.articulo.existencia.saldo
    return {'articulo': valor.articulo_id, 'estado': 'DISPONIBLE' if saldo == valor.saldo_valorado else 'PENDIENTE_VALORIZACION'}
