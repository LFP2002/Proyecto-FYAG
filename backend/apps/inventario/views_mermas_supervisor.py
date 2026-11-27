"""Bandeja de mermas de obra, exclusivamente de lectura para Supervisión."""
import re
from decimal import Decimal

from django.db.models import Count, Prefetch, Q, Sum
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response

from . import consultas_mermas as consultas
from .consultas_solicitudes import validar_query
from .models import MermaEvento, OperacionMaterial, TIPOS_MO
from .services_mermas import aprobada, importe
from .views import InventarioPaginacion, articulo_filtro
from .views_mermas import MermasAPIView
from .views_solicitudes_supervisor import etiqueta


def scope(request):
    if request.user.rol != 'SUPERVISOR_OBRAS':
        raise PermissionDenied('Consulta exclusiva del Supervisor de Obras.')
    return consultas.scope(request.user, 'OBRA').select_related(
        'obra', 'articulo', 'informado_por', 'decidido_por')


def project(m, detail=False):
    row = {
        'id': m.pk, 'obra': m.obra.codigo, 'obra_estado': m.obra.estado,
        'material': m.articulo.nombre, 'codigo': m.articulo.codigo, 'unidad': m.unidad,
        'informado_por': etiqueta(m.informado_por), 'estado': m.estado,
        'cantidad': format(m.cantidad, '.3f'), 'tipo': m.tipo, 'motivo': m.motivo,
        'actividad': m.actividad, 'referencia': m.referencia, 'entrega': m.entrega_id,
        'motivo_decision': m.motivo_decision,
        'decidido_por': etiqueta(m.decidido_por) if m.decidido_por else None,
        'decidido_en': m.decidido_en.isoformat() if m.decidido_en else None,
        'creado_en': m.creado_en.isoformat(),
    }
    if detail:
        returned = OperacionMaterial.objects.filter(entrega_id=m.entrega_id, tipo='DEVOLUCION').aggregate(
            total=Sum('cantidad'))['total'] or Decimal('0.000')
        accepted = aprobada(m.entrega_id)
        cost = m.entrega.costo_unitario_neto
        row.update(entregado=format(m.entrega.cantidad, '.3f'), devuelto=format(returned, '.3f'),
                   mermas_aprobadas=format(accepted, '.3f'),
                   remanente=format(m.entrega.cantidad-returned-accepted, '.3f'),
                   importe_informativo_no_aditivo=format(importe(m.cantidad, cost, estricto=False), '.2f') if cost is not None else None,
                   historial=[{'id': e.pk, 'tipo': e.tipo, 'actor': etiqueta(e.actor),
                               'motivo': e.motivo, 'creado_en': e.creado_en.isoformat()} for e in m.eventos.all()])
    return row


class MermasSupervisorView(MermasAPIView):
    ambito = 'OBRA'

    def get(self, request):
        qs = scope(request)
        p = request.query_params
        validar_query(p, {'estado', 'tipo', 'buscar'}, paginada=True)
        summary = qs.aggregate(pendientes=Count('pk', filter=Q(estado='PENDIENTE')),
                               aprobadas=Count('pk', filter=Q(estado='APROBADA')),
                               rechazadas=Count('pk', filter=Q(estado='RECHAZADA')))
        for key, allowed in [('estado', ('PENDIENTE', 'APROBADA', 'RECHAZADA')), ('tipo', TIPOS_MO)]:
            if key in p:
                if p[key] not in allowed:
                    raise ValidationError({key: ['Valor no permitido.']})
                qs = qs.filter(**{key: p[key]})
        if 'buscar' in p:
            term = p['buscar'].strip()
            if not term or len(term) > 150 or any(ord(c) < 32 for c in term):
                raise ValidationError({'buscar': ['Búsqueda inválida.']})
            criteria = (Q(articulo__nombre__icontains=term) | Q(articulo__codigo__icontains=term) |
                        Q(informado_por__username__icontains=term) | Q(informado_por__first_name__icontains=term) |
                        Q(informado_por__last_name__icontains=term))
            match = re.fullmatch(r'OB-([0-9]{1,18})', term.upper())
            if match and int(match[1]) <= 9223372036854775807:
                criteria |= Q(obra_id=int(match[1]))
            qs = qs.filter(criteria)
        paginator = InventarioPaginacion()
        response = paginator.get_paginated_response([
            project(m) for m in paginator.paginate_queryset(qs.order_by('-creado_en', '-pk'), request, view=self)])
        response.data['resumen'] = summary
        return response


class MermaSupervisorDetalleView(MermasAPIView):
    ambito = 'OBRA'

    def get(self, request, merma_id):
        qs = scope(request)
        validar_query(request.query_params)
        pk = articulo_filtro({'articulo': merma_id})
        row = qs.prefetch_related(Prefetch('eventos', queryset=MermaEvento.objects.select_related(
            'actor').order_by('id'))).filter(pk=pk).first()
        if row is None:
            raise NotFound('Merma no disponible.')
        return Response(project(row, detail=True))
