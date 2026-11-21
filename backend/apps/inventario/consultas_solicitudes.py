from django.db.models import Q
from django.http import QueryDict
from rest_framework.exceptions import NotFound, ValidationError

from .models import ArticuloInventario, SolicitudMaterialObra
from .permissions_solicitudes import revalidar
from .services import identificador
from .services_solicitudes import _texto
from .views import query, articulo_filtro


def validar_query(params, permitidos=(), *, paginada=False):
    if not hasattr(params, 'getlist'):
        copia = QueryDict(mutable=True)
        copia.update(params)
        params = copia
    query(params, permitidos)
    if not paginada and 'page' in params:
        raise ValidationError({'query': ['Parámetro no permitido.']})


def catalogo(actor, params):
    revalidar(actor)
    validar_query(params, {'buscar'}, paginada=True)
    qs = ArticuloInventario.objects.filter(activo=True).order_by('id')
    if 'buscar' in params:
        buscar = _texto(params['buscar'], 'buscar', 150)
        qs = qs.filter(Q(codigo__icontains=buscar) | Q(nombre__icontains=buscar))
    return qs


def _scope(actor):
    actual = revalidar(actor)
    qs = SolicitudMaterialObra.objects.order_by('id')
    return qs.filter(solicitante=actual) if actual.rol == 'TECNICO' else qs


def listado(actor, params):
    qs = _scope(actor)
    validar_query(params, {'obra', 'articulo', 'estado'}, paginada=True)
    for campo in ('obra', 'articulo'):
        if campo in params:
            qs = qs.filter(**{campo+'_id': articulo_filtro({'articulo': params[campo]})})
    if 'estado' in params:
        if params['estado'] not in {'PENDIENTE', 'APROBADA', 'RECHAZADA'}:
            raise ValidationError({'estado': ['Estado no permitido.']})
        qs = qs.filter(estado=params['estado'])
    return qs


def obtener(actor, pk, params):
    qs = _scope(actor)
    validar_query(params)
    solicitud = qs.prefetch_related('eventos').filter(pk=identificador(pk)).first()
    if solicitud is None:
        raise NotFound('Solicitud no encontrada.')
    return solicitud
