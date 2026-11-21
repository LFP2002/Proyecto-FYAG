from rest_framework.exceptions import NotFound, ValidationError

from .models import Merma, TIPOS_MB, TIPOS_MO
from .permissions_mermas import revalidar
from .consultas_solicitudes import validar_query
from .views import articulo_filtro


def scope(actor, ambito):
    actual = revalidar(actor, ambito)
    qs = Merma.objects.filter(ambito=ambito).select_related('operacion', 'entrega').order_by('id')
    return qs.filter(informado_por=actual) if actual.rol == 'TECNICO' else qs


def listado(actor, ambito, params):
    qs = scope(actor, ambito)
    ids = {'articulo'} | ({'obra', 'entrega'} if ambito == 'OBRA' else set())
    validar_query(params, ids | {'estado', 'tipo'}, paginada=True)
    for campo in ids & set(params):
        qs = qs.filter(**{campo+'_id': articulo_filtro({'articulo': params[campo]})})
    for campo, valores in [('estado', ['PENDIENTE', 'APROBADA', 'RECHAZADA']), ('tipo', TIPOS_MB if ambito == 'BODEGA' else TIPOS_MO)]:
        if campo in params:
            if params[campo] not in valores:
                raise ValidationError({campo: ['Valor no permitido.']})
            qs = qs.filter(**{campo: params[campo]})
    return qs


def obtener(actor, ambito, pk, params):
    qs = scope(actor, ambito)
    validar_query(params)
    merma = qs.prefetch_related('eventos').filter(pk=pk).first()
    if merma is None:
        raise NotFound('Merma no disponible.')
    return merma
