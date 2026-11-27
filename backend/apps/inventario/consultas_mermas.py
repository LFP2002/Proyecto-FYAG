from decimal import Decimal, localcontext

from django.db.models import Count, Q
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from .models import Merma, TIPOS_MB, TIPOS_MO
from .permissions_mermas import revalidar
from .consultas_solicitudes import validar_query
from .views import articulo_filtro
from .services_mermas import importe
from .services_solicitudes import _texto


def scope(actor, ambito):
    actual = revalidar(actor, ambito)
    qs = Merma.objects.filter(ambito=ambito).select_related('operacion', 'entrega').order_by('id')
    return qs.filter(informado_por=actual) if actual.rol == 'TECNICO' else qs


def vista_finanzas(actor, ambito, params):
    if 'vista' not in params:
        return False
    if ambito != 'BODEGA' or actor.rol != 'ADMINISTRATIVO_FINANZAS':
        raise PermissionDenied('Vista exclusiva de Finanzas.')
    if params['vista'] != 'finanzas':
        raise ValidationError({'vista': 'Vista no válida.'})
    return True


def resumen_finanzas(actor):
    qs = scope(actor, 'BODEGA')
    counts = qs.aggregate(pendientes=Count('pk', filter=Q(estado='PENDIENTE')),
                          aprobadas=Count('pk', filter=Q(estado='APROBADA')),
                          rechazadas=Count('pk', filter=Q(estado='RECHAZADA')))
    with localcontext() as ctx:
        ctx.prec = 60
        total = sum((importe(q, c, estricto=False) for q, c in qs.filter(
            estado='APROBADA').values_list('cantidad', 'operacion__costo_unitario_neto').iterator()), Decimal('0.00'))
    return {**counts, 'perdida_neta': format(total, '.2f')}


def listado(actor, ambito, params):
    qs = scope(actor, ambito)
    ids = {'articulo'} | ({'obra', 'entrega'} if ambito == 'OBRA' else set())
    financiera = vista_finanzas(actor, ambito, params)
    validar_query(params, ids | {'estado', 'tipo'} | ({'vista', 'buscar'} if financiera else set()), paginada=True)
    if financiera:
        qs = qs.select_related('articulo', 'informado_por', 'decidido_por').order_by('-creado_en', '-pk')
        if 'buscar' in params:
            term = _texto(params['buscar'], 'buscar', 150)
            qs = qs.filter(Q(articulo__nombre__icontains=term) | Q(articulo__codigo__icontains=term))
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
    financiera = vista_finanzas(actor, ambito, params)
    validar_query(params, {'vista'} if financiera else set())
    if financiera:
        qs = qs.select_related('articulo', 'informado_por', 'decidido_por')
    merma = qs.prefetch_related('eventos').filter(pk=pk).first()
    if merma is None:
        raise NotFound('Merma no disponible.')
    return merma
