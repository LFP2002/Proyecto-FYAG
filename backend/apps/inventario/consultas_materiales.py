from .models import OperacionMaterial, EstadoValoracion
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
    return qs


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
