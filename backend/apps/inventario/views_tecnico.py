"""Lecturas operativas del técnico, sin modificar los servicios de escritura 019C."""
import re
from decimal import Decimal
from uuid import UUID

from django.db.models import DecimalField, F, OuterRef, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce, Greatest
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.obras.models import Obra, ObraParticipante
from . import consultas_mermas, consultas_solicitudes
from .models import ArticuloInventario, Merma, OperacionMaterial, TIPOS_MO
from .permissions_solicitudes import revalidar
from .services_solicitudes import _texto
from .views import InventarioPaginacion, articulo_filtro
from .views_materiales import CabecerasMateriales

ESTADOS = ('PENDIENTE', 'APROBADA', 'RECHAZADA')
OPERATIVAS = ('EN_PROCESO', 'SUSPENDIDA')
DECIMAL = DecimalField(max_digits=24, decimal_places=3)
ZERO = Value(Decimal('0.000'), output_field=DECIMAL)


def q(value):
    return format(value, '.3f') if value is not None else None


def identity(user):
    return (user.get_full_name().strip() or user.username) if user else None


def work(o):
    return {'id': o.pk, 'codigo': o.codigo, 'cliente': o.presupuesto.cliente.nombre_legal,
            'categoria': o.categoria_servicio.nombre, 'estado': o.estado}


def material(a):
    return {'id': a.pk, 'codigo': a.codigo, 'nombre': a.nombre, 'unidad': a.unidad}


def project(row, loss, detail=False):
    result = {'id': row.pk, 'obra': work(row.obra), 'material': material(row.articulo),
              'unidad': row.unidad, 'estado': row.estado, 'creado_en': row.creado_en.isoformat(),
              'motivo_decision': row.motivo_decision, 'decidido_por': identity(row.decidido_por),
              'decidido_en': row.decidido_en.isoformat() if row.decidido_en else None}
    if loss:
        result.update(cantidad=q(row.cantidad), tipo=row.tipo, entrega=row.entrega_id,
                      motivo=row.motivo, actividad=row.actividad, referencia=row.referencia)
    else:
        result.update(cantidad=q(row.cantidad_solicitada), cantidad_aprobada=q(row.cantidad_aprobada),
                      justificacion=row.justificacion, autorizacion=row.autorizacion_id)
    if detail:
        result['historial'] = [{'id': e.pk, 'tipo': e.tipo, 'actor': identity(e.actor),
                                'motivo': e.motivo, 'creado_en': e.creado_en.isoformat()}
                               for e in row.eventos.select_related('actor').order_by('id')]
    return result


def delivery(row):
    return {'id': row.pk, 'obra': work(row.obra), 'material': material(row.articulo),
            'unidad': row.unidad, 'cantidad': q(row.cantidad), 'devuelta': q(row.devuelta),
            'mermas_aprobadas': q(row.mermas_aprobadas), 'remanente': q(row.remanente),
            'creado_en': row.creado_en.isoformat()}


def search(qs, term, section):
    if section == 'catalogo':
        return qs.filter(Q(nombre__icontains=term) | Q(codigo__icontains=term))
    prefix = '' if section == 'obras' else 'obra__'
    criteria = Q(**{prefix+'presupuesto__cliente__nombre_legal__icontains': term}) | Q(**{prefix+'categoria_servicio__nombre__icontains': term})
    match = re.fullmatch(r'OB-([0-9]{1,19})', term.upper())
    if match and 0 < int(match[1]) <= 9223372036854775807:
        criteria |= Q(**{prefix+'pk': int(match[1])})
    if section != 'obras':
        criteria |= Q(articulo__nombre__icontains=term) | Q(articulo__codigo__icontains=term)
    return qs.filter(criteria)


class TecnicoMaterialesView(CabecerasMateriales, APIView):
    permission_classes = [IsAuthenticated]
    http_method_names = ['get', 'head', 'options']

    def get(self, request):
        actor = revalidar(request.user, 'crear')
        if actor.rol != 'TECNICO':
            raise PermissionDenied('Consulta exclusiva del técnico.')
        p = request.query_params
        section = p.get('seccion')
        works = Obra.objects.filter(pk__in=ObraParticipante.objects.filter(tecnico=actor, activo=True).values('obra_id'),
                                    estado__in=OPERATIVAS).select_related('presupuesto__cliente', 'categoria_servicio')
        if section == 'confirmacion':
            consultas_solicitudes.validar_query(p, {'seccion', 'tipo', 'clave'})
            try:
                key = UUID(p.get('clave', ''))
                if str(key) != p.get('clave'):
                    raise ValueError()
            except (ValueError, AttributeError):
                raise ValidationError({'clave': ['UUID canónico requerido.']}) from None
            if p.get('tipo') == 'MERMA':
                qs = consultas_mermas.scope(actor, 'OBRA')
            elif p.get('tipo') == 'SOLICITUD':
                qs = consultas_solicitudes._scope(actor)
            else:
                raise ValidationError({'tipo': ['Tipo no permitido.']})
            return Response({'id': qs.filter(clave_idempotencia=key).values_list('pk', flat=True).first()})
        if section in ('merma_detalle', 'solicitud_detalle'):
            consultas_solicitudes.validar_query(p, {'seccion', 'id'})
            pk = articulo_filtro({'articulo': p.get('id', '')})
            loss = section == 'merma_detalle'
            qs = consultas_mermas.scope(actor, 'OBRA') if loss else consultas_solicitudes._scope(actor)
            row = qs.select_related('obra__presupuesto__cliente', 'obra__categoria_servicio', 'articulo', 'decidido_por').filter(pk=pk).first()
            if row is None:
                raise NotFound('Registro no disponible.')
            return Response(project(row, loss, detail=True))
        allowed = {'seccion', 'buscar'}
        if section == 'obras':
            qs, render = works.order_by('-creado_en', '-id'), work
        elif section == 'catalogo':
            qs, render = ArticuloInventario.objects.filter(activo=True).order_by('nombre', 'id'), material
        elif section == 'entregas':
            allowed.add('obra')
            pk = articulo_filtro({'articulo': p.get('obra', '')})
            if not works.filter(pk=pk).exists():
                raise NotFound('Obra no disponible.')
            returned = OperacionMaterial.objects.filter(tipo='DEVOLUCION', entrega_id=OuterRef('pk')).order_by().values('entrega_id').annotate(total=Sum('cantidad')).values('total')
            losses = Merma.objects.filter(ambito='OBRA', estado='APROBADA', entrega_id=OuterRef('pk')).order_by().values('entrega_id').annotate(total=Sum('cantidad')).values('total')
            qs = OperacionMaterial.objects.filter(tipo='ENTREGA', obra_id=pk, obra_id__in=works.values('pk')).select_related('obra__presupuesto__cliente', 'obra__categoria_servicio', 'articulo').annotate(
                devuelta=Coalesce(Subquery(returned, output_field=DECIMAL), ZERO),
                mermas_aprobadas=Coalesce(Subquery(losses, output_field=DECIMAL), ZERO),
            ).annotate(remanente=Greatest(ZERO, F('cantidad')-F('devuelta')-F('mermas_aprobadas'), output_field=DECIMAL)).order_by('-creado_en', '-id')
            render = delivery
        elif section in ('mermas', 'solicitudes'):
            loss = section == 'mermas'
            allowed.add('estado')
            if loss:
                allowed.add('tipo')
            qs = (consultas_mermas.scope(actor, 'OBRA') if loss else consultas_solicitudes._scope(actor)).select_related(
                'obra__presupuesto__cliente', 'obra__categoria_servicio', 'articulo', 'decidido_por').order_by('-creado_en', '-id')
            if 'estado' in p:
                if p['estado'] not in ESTADOS:
                    raise ValidationError({'estado': ['Estado no permitido.']})
                qs = qs.filter(estado=p['estado'])
            if loss and 'tipo' in p:
                if p['tipo'] not in TIPOS_MO:
                    raise ValidationError({'tipo': ['Tipo no permitido.']})
                qs = qs.filter(tipo=p['tipo'])
            render = lambda row: project(row, loss)
        else:
            raise ValidationError({'seccion': ['Sección no permitida.']})
        consultas_solicitudes.validar_query(p, allowed, paginada=True)
        if 'buscar' in p:
            qs = search(qs, _texto(p['buscar'], 'buscar', 150), section)
        paginator = InventarioPaginacion()
        rows = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response([render(r) for r in rows])
