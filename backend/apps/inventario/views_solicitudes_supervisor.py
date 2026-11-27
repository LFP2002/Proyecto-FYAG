"""Proyección de lectura para decidir solicitudes, sin modificar el contrato 019C-1."""
import re

from django.db.models import Count, Q, Prefetch
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response

from . import consultas_solicitudes as consultas
from .models import SolicitudMaterialEvento
from .views import InventarioPaginacion, articulo_filtro
from .views_solicitudes import SolicitudesAPIView


def etiqueta(usuario):
    return usuario.get_full_name().strip() or usuario.username


def scope(request):
    if request.user.rol != 'SUPERVISOR_OBRAS':
        raise PermissionDenied('Consulta exclusiva del Supervisor de Obras.')
    return consultas.listado(request.user, {}).select_related(
        'obra', 'articulo__existencia', 'solicitante', 'decidido_por')


def proyectar(s, detalle=False):
    stock = getattr(s.articulo, 'existencia', None)
    saldo = stock.saldo if stock is not None and s.articulo.unidad == s.unidad else None
    row = {
        'id': s.pk, 'obra': s.obra.codigo, 'obra_estado': s.obra.estado,
        'material': s.articulo.nombre, 'codigo': s.articulo.codigo, 'unidad': s.unidad,
        'solicitante': etiqueta(s.solicitante), 'estado': s.estado,
        'cantidad_solicitada': format(s.cantidad_solicitada, '.3f'),
        'cantidad_aprobada': format(s.cantidad_aprobada, '.3f') if s.cantidad_aprobada is not None else None,
        'saldo': format(saldo, '.3f') if saldo is not None else None,
        'justificacion': s.justificacion, 'motivo_decision': s.motivo_decision,
        'decidido_por': etiqueta(s.decidido_por) if s.decidido_por else None,
        'decidido_en': s.decidido_en.isoformat() if s.decidido_en else None,
        'creado_en': s.creado_en.isoformat(), 'autorizacion': s.autorizacion_id,
    }
    if detalle:
        row['historial'] = [
            {'id': e.pk, 'tipo': e.tipo, 'actor': etiqueta(e.actor), 'motivo': e.motivo,
             'creado_en': e.creado_en.isoformat()}
            for e in s.eventos.all()
        ]
    return row


class SolicitudesSupervisorView(SolicitudesAPIView):
    def get(self, request):
        qs = scope(request)
        p = request.query_params
        consultas.validar_query(p, {'estado', 'buscar'}, paginada=True)
        estado = p.get('estado')
        if estado not in (None, 'PENDIENTE', 'APROBADA', 'RECHAZADA'):
            raise ValidationError({'estado': ['Estado no permitido.']})
        summary = qs.aggregate(pendientes=Count('pk', filter=Q(estado='PENDIENTE')),
                               aprobadas=Count('pk', filter=Q(estado='APROBADA')),
                               rechazadas=Count('pk', filter=Q(estado='RECHAZADA')))
        if estado:
            qs = qs.filter(estado=estado)
        if 'buscar' in p:
            term = p['buscar'].strip()
            if not term or len(term) > 150 or any(ord(c) < 32 for c in term):
                raise ValidationError({'buscar': ['Búsqueda inválida.']})
            condition = (Q(articulo__nombre__icontains=term) | Q(articulo__codigo__icontains=term) |
                         Q(solicitante__username__icontains=term) | Q(solicitante__first_name__icontains=term) |
                         Q(solicitante__last_name__icontains=term))
            match = re.fullmatch(r'OB-([0-9]{1,18})', term.upper())
            if match and int(match[1]) <= 9223372036854775807:
                condition |= Q(obra_id=int(match[1]))
            qs = qs.filter(condition)
        paginator = InventarioPaginacion()
        response = paginator.get_paginated_response([
            proyectar(s) for s in paginator.paginate_queryset(qs.order_by('-creado_en', '-pk'), request, view=self)])
        response.data['resumen'] = summary
        return response


class SolicitudSupervisorDetalleView(SolicitudesAPIView):
    def get(self, request, solicitud_id):
        qs = scope(request)
        consultas.validar_query(request.query_params)
        pk = articulo_filtro({'articulo': solicitud_id})
        row = qs.prefetch_related(Prefetch('eventos', queryset=SolicitudMaterialEvento.objects.select_related(
            'actor').order_by('id'))).filter(pk=pk).first()
        if row is None:
            raise NotFound('Solicitud no encontrada.')
        return Response(proyectar(row, detalle=True))
