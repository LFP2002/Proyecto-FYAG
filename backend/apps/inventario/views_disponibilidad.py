"""Consulta de planificación del Supervisor. Sin escrituras ni importes."""
import re

from django.db.models import Count, Q
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from .models import ArticuloInventario, OperacionMaterial
from .permissions import PuedeOperarInventario
from .views import InventarioPaginacion, query
from .views_bodega import ROOT, articulo, operaciones, operacion
from .views_materiales import CabecerasMateriales


def pendientes(actor, tipo):
    return operaciones(actor, tipo).filter(pendiente__gt=0, obra__estado__in=ROOT)


def seguimiento(o):
    # Lista explícita: no exponer costos, claves de idempotencia ni capacidad de ejecución.
    r = operacion(o)
    keys = ('id', 'articulo', 'codigo', 'nombre', 'unidad', 'tipo', 'obra',
            'cantidad', 'referencia', 'motivo', 'creado_en', 'origen')
    result = {k: r[k] for k in keys}
    if o.tipo.startswith('AUTORIZACION'):
        result.update({k: r[k] for k in ('ejecutada', 'pendiente', 'saldo', 'bloqueo')})
    return result


class DisponibilidadSupervisorView(CabecerasMateriales, APIView):
    permission_classes = [IsAuthenticated, PuedeOperarInventario]
    http_method_names = ['get', 'head', 'options']

    def get(self, request):
        actor = request.user
        if actor.rol != 'SUPERVISOR_OBRAS':
            raise PermissionDenied('Consulta exclusiva de Supervisión de Obras.')
        p = request.query_params
        section = p.get('seccion', 'disponibilidad')
        if section not in {'disponibilidad', 'pendientes', 'historial'}:
            raise ValidationError({'seccion': ['Sección no permitida.']})
        query(p, {'seccion', 'buscar'} | ({'stock'} if section == 'disponibilidad' else
              {'vista'} if section == 'historial' else set()))
        term = p.get('buscar', '').strip()
        if 'buscar' in p and (not term or len(term) > 150 or any(ord(c) < 32 for c in term)):
            raise ValidationError({'buscar': ['Búsqueda inválida.']})
        catalogo = ArticuloInventario.objects.filter(activo=True).select_related('existencia').order_by('nombre', 'id')
        despachos = pendientes(actor, 'AUTORIZACION_ENTREGA')
        summary = catalogo.aggregate(disponibles=Count('pk', filter=Q(existencia__saldo__gt=0)),
                                     sin_stock=Count('pk', filter=Q(existencia__saldo=0)))
        summary['despachos_pendientes'] = despachos.count()
        if section == 'disponibilidad':
            stock = p.get('stock')
            if stock not in (None, 'con_stock', 'sin_stock'):
                raise ValidationError({'stock': ['Filtro no permitido.']})
            qs = catalogo
            if stock:
                qs = qs.filter(existencia__saldo__gt=0) if stock == 'con_stock' else qs.filter(existencia__saldo=0)
            if term:
                qs = qs.filter(Q(nombre__icontains=term) | Q(codigo__icontains=term))
            project = articulo
        else:
            if section == 'pendientes':
                qs = despachos
            else:
                vista = p.get('vista')
                if vista not in (None, 'entregas', 'devoluciones', 'por_recibir'):
                    raise ValidationError({'vista': ['Vista no permitida.']})
                if vista == 'por_recibir':
                    qs = pendientes(actor, 'AUTORIZACION_DEVOLUCION')
                else:
                    tipos = {'entregas': ['ENTREGA'], 'devoluciones': ['DEVOLUCION']}.get(vista, ['ENTREGA', 'DEVOLUCION'])
                    qs = OperacionMaterial.objects.filter(tipo__in=tipos).select_related(
                        'articulo', 'obra', 'actor', 'autorizacion', 'entrega__autorizacion').order_by('-creado_en', '-id')
            if term:
                criteria = Q(articulo__nombre__icontains=term) | Q(articulo__codigo__icontains=term) | Q(referencia__icontains=term)
                match = re.fullmatch(r'OB-([0-9]{1,18})', term.upper())
                if match and int(match[1]) <= 9223372036854775807:
                    criteria |= Q(obra_id=int(match[1]))
                qs = qs.filter(criteria)
            project = seguimiento
        paginator = InventarioPaginacion()
        response = paginator.get_paginated_response([project(row) for row in paginator.paginate_queryset(qs, request, view=self)])
        response.data['resumen'] = summary
        return response
