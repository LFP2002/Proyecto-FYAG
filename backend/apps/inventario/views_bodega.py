"""Proyección operativa exclusiva de Bodega. No expone costos ni datos comerciales."""
import re
from datetime import date
from decimal import Decimal
from uuid import UUID

from django.db.models import Q, OuterRef, Subquery, Sum, Value, F, DecimalField
from django.db.models.functions import Coalesce, Greatest
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import consultas_materiales, consultas_mermas
from .models import ArticuloInventario, ExistenciaInventario, MovimientoInventario, OperacionMaterial, Merma, TIPOS_MB, MAXIMO
from .permissions import revalidar
from .views import InventarioPaginacion, query, articulo_filtro
from .views_materiales import CabecerasMateriales

ROOT = 'EN_PROCESO', 'SUSPENDIDA'
DECIMAL = DecimalField(max_digits=12, decimal_places=3)
ZERO = Value(Decimal('0.000'), output_field=DECIMAL)


def cantidad(value):
    return format(value, '.3f') if value is not None else None


def material(a):
    return {'articulo': a.pk, 'codigo': a.codigo, 'nombre': a.nombre, 'unidad': a.unidad}


def saldo(a):
    return getattr(getattr(a, 'existencia', None), 'saldo', None)


def articulo(a):
    return {**material(a), 'id': a.pk, 'activo': a.activo, 'descripcion': a.descripcion,
            'saldo': cantidad(saldo(a))}


def actor_label(a):
    return a.get_full_name().strip() or a.username


def movimiento(m):
    return {**material(m.articulo), 'id': m.pk, 'tipo': m.tipo,
            'cantidad': cantidad(m.cantidad), 'saldo_anterior': cantidad(m.saldo_anterior),
            'saldo_posterior': cantidad(m.saldo_posterior), 'referencia': m.referencia,
            'motivo': m.motivo, 'actor': actor_label(m.actor), 'creado_en': m.creado_en.isoformat()}


def operaciones(actor, tipo):
    qs = consultas_materiales.listado(actor, tipo, {}).select_related(
        'articulo__existencia', 'articulo__estadovaloracion', 'obra', 'actor',
        'autorizacion', 'entrega__autorizacion')
    if tipo in ('AUTORIZACION_ENTREGA', 'AUTORIZACION_DEVOLUCION'):
        ejecucion = 'ENTREGA' if tipo == 'AUTORIZACION_ENTREGA' else 'DEVOLUCION'
        sub = OperacionMaterial.objects.filter(autorizacion_id=OuterRef('pk'), tipo=ejecucion).order_by().values(
            'autorizacion_id').annotate(total=Sum('cantidad')).values('total')
        qs = qs.annotate(ejecutada=Coalesce(Subquery(sub, output_field=DECIMAL), ZERO))
        if tipo == 'AUTORIZACION_ENTREGA':
            qs = qs.annotate(pendiente=Greatest(ZERO, F('cantidad') - F('ejecutada'), output_field=DECIMAL))
        else:
            qs = qs.annotate(pendiente=F('cantidad_recibible_efectiva'))
    return qs.order_by('-id')


def operacion(o):
    row = {**material(o.articulo), 'id': o.pk, 'tipo': o.tipo, 'obra': o.obra.codigo if o.obra else None,
           'autorizacion': o.autorizacion_id, 'entrega': o.entrega_id, 'cantidad': cantidad(o.cantidad),
           'referencia': o.referencia, 'motivo': o.motivo, 'actor': actor_label(o.actor),
           'creado_en': o.creado_en.isoformat()}
    raiz = o if o.tipo == 'AUTORIZACION_ENTREGA' else (
        o.autorizacion if o.tipo == 'ENTREGA' else o.entrega.autorizacion)
    row['origen'] = ('PRESUPUESTO' if raiz.item_presupuesto_id else
                     'SOLICITUD' if raiz.solicitud_material_id else 'SIN_VINCULO_PRESUPUESTARIO')
    if o.tipo.startswith('AUTORIZACION'):
        stock = saldo(o.articulo)
        limit = o.pendiente
        reason = None
        if o.pendiente <= 0:
            reason = 'Sin cantidad pendiente'
        elif o.obra and o.obra.estado in {'FINALIZADA', 'CANCELADA'}:
            reason = 'Inhabilitada por cierre de obra'
        elif not o.obra or o.obra.estado not in ROOT:
            reason = 'Obra no operativa'
        elif stock is None:
            reason = 'Existencia no disponible'
        elif o.tipo == 'AUTORIZACION_ENTREGA':
            valuation = getattr(o.articulo, 'estadovaloracion', None)
            if not o.articulo.activo:
                reason = 'Material inactivo'
            elif not stock:
                reason = 'Sin existencias'
            elif not valuation or valuation.saldo_valorado != stock or valuation.promedio is None:
                reason = 'Pendiente de valoración por Finanzas'
            else:
                limit = min(limit, stock)
        else:
            limit = min(limit, MAXIMO - stock)
            if limit <= 0:
                reason = 'Capacidad de stock agotada'
        row.update(ejecutada=cantidad(o.ejecutada), pendiente=cantidad(o.pendiente),
                   saldo=cantidad(stock), maximo=cantidad(Decimal(0) if reason else limit), bloqueo=reason,
                   inhabilitada=bool(o.pendiente and o.obra and o.obra.estado in {'FINALIZADA', 'CANCELADA'}))
    return row


def merma_row(m, detalle=False):
    row = {**material(m.articulo), 'id': m.pk, 'unidad': m.unidad,
           'cantidad': cantidad(m.cantidad), 'tipo': m.tipo, 'estado': m.estado,
           'creado_en': m.creado_en.isoformat(), 'motivo': m.motivo,
           'referencia': m.referencia, 'actor': actor_label(m.informado_por),
           'decidido_por': actor_label(m.decidido_por) if m.decidido_por else None,
           'decidido_en': m.decidido_en.isoformat() if m.decidido_en else None,
           'motivo_decision': m.motivo_decision}
    if detalle:
        row['historial'] = [{'id': e.pk, 'tipo': e.tipo, 'actor': actor_label(e.actor),
                             'motivo': e.motivo, 'creado_en': e.creado_en.isoformat()}
                            for e in m.eventos.select_related('actor').order_by('id')]
    return row


class BodegaOperativaView(CabecerasMateriales, APIView):
    permission_classes = [IsAuthenticated]
    http_method_names = ['get', 'head', 'options']

    def get(self, request):
        actor = revalidar(request.user)
        if actor.rol != 'BODEGUERO':
            raise PermissionDenied('Consulta operativa exclusiva de Bodega.')
        p = request.query_params
        section = p.get('seccion', 'resumen')
        if section == 'confirmacion':
            query(p, {'seccion', 'clave', 'tipo'})
            try:
                key = UUID(p.get('clave', ''))
                if str(key) != p.get('clave'):
                    raise ValueError()
            except (ValueError, AttributeError):
                raise ValidationError({'clave': ['UUID canónico requerido.']}) from None
            kind = p.get('tipo')
            if kind == 'INGRESO':
                qs = MovimientoInventario.objects.filter(tipo=kind, clave_idempotencia=key, actor=actor)
            elif kind in ('ENTREGA', 'DEVOLUCION'):
                qs = OperacionMaterial.objects.filter(tipo=kind, clave_idempotencia=key, actor=actor)
            elif kind == 'MERMA':
                qs = consultas_mermas.scope(actor, 'BODEGA').filter(clave_idempotencia=key, informado_por=actor)
            else:
                raise ValidationError({'tipo': ['Operación no permitida.']})
            return Response({'id': qs.values_list('pk', flat=True).first()})
        catalog = ArticuloInventario.objects.select_related('existencia').order_by('nombre', 'id')
        if section == 'resumen':
            query(p, {'seccion'})
            zero = catalog.filter(activo=True, existencia__saldo=0)
            deliveries = operaciones(actor, 'AUTORIZACION_ENTREGA').filter(pendiente__gt=0, obra__estado__in=ROOT)
            returns = operaciones(actor, 'AUTORIZACION_DEVOLUCION').filter(pendiente__gt=0, obra__estado__in=ROOT)
            return Response({'materiales': catalog.count(), 'sin_stock': zero.count(),
                             'entregas': deliveries.count(), 'devoluciones': returns.count(),
                             'faltantes': [articulo(a) for a in zero[:5]],
                             'pendientes': [operacion(o) for o in deliveries[:5]],
                             'retornos': [operacion(o) for o in returns[:5]]})
        if section == 'merma_detalle':
            query(p, {'seccion', 'merma'})
            if 'merma' not in p or 'page' in p:
                raise ValidationError({'merma': ['Identificador requerido; sin página.']})
            pk = articulo_filtro({'articulo': p['merma']})
            m = consultas_mermas.scope(actor, 'BODEGA').select_related(
                'articulo', 'informado_por', 'decidido_por').filter(pk=pk).first()
            if m is None:
                raise NotFound('Merma no disponible.')
            return Response(merma_row(m, detalle=True))
        allowed = {'seccion', 'buscar'}
        if section == 'inventario':
            allowed |= {'estado', 'stock'}
            qs, render = catalog, articulo
        elif section == 'mermas':
            allowed |= {'estado', 'tipo'}
            qs = consultas_mermas.scope(actor, 'BODEGA').select_related(
                'articulo', 'informado_por', 'decidido_por').order_by('-creado_en', '-id')
            render = merma_row
        elif section == 'movimientos':
            allowed |= {'articulo', 'tipo', 'desde', 'hasta'}
            qs = MovimientoInventario.objects.select_related('articulo', 'actor').order_by('-creado_en', '-id')
            render = movimiento
        elif section in ('entregas', 'devoluciones'):
            allowed |= {'vista'}
            view = p.get('vista', 'pendientes')
            if view not in ('pendientes', 'historial', 'autorizaciones'):
                raise ValidationError({'vista': ['Vista no permitida.']})
            kind = 'ENTREGA' if section == 'entregas' else 'DEVOLUCION'
            auth_kind = 'AUTORIZACION_ENTREGA' if section == 'entregas' else 'AUTORIZACION_DEVOLUCION'
            qs = operaciones(actor, kind if view == 'historial' else auth_kind)
            if view == 'pendientes':
                qs = qs.filter(pendiente__gt=0, obra__estado__in=ROOT)
            render = operacion
        else:
            raise ValidationError({'seccion': ['Sección no permitida.']})
        query(p, allowed)
        if 'buscar' in p:
            term = p['buscar'].strip()
            if not term or len(term) > 150 or any(ord(c) < 32 for c in term):
                raise ValidationError({'buscar': ['Búsqueda no válida.']})
            prefix = '' if section == 'inventario' else 'articulo__'
            criteria = Q(**{prefix + 'nombre__icontains': term}) | Q(**{prefix + 'codigo__icontains': term})
            if section in ('entregas', 'devoluciones'):
                match = re.fullmatch(r'OB-([0-9]{1,18})', term.upper())
                if match and int(match[1]) <= 9223372036854775807:
                    criteria |= Q(obra_id=int(match[1]))
                criteria |= Q(referencia__icontains=term)
            qs = qs.filter(criteria)
        if section == 'inventario':
            if 'estado' in p:
                if p['estado'] not in ('activo', 'inactivo'):
                    raise ValidationError({'estado': ['Estado no permitido.']})
                qs = qs.filter(activo=p['estado'] == 'activo')
            if 'stock' in p:
                if p['stock'] not in ('con_stock', 'sin_stock'):
                    raise ValidationError({'stock': ['Filtro no permitido.']})
                qs = qs.filter(existencia__saldo__gt=0) if p['stock'] == 'con_stock' else qs.filter(existencia__saldo=0)
        if section == 'mermas':
            for key, choices in (('estado', ('PENDIENTE', 'APROBADA', 'RECHAZADA')), ('tipo', TIPOS_MB)):
                if key in p:
                    if p[key] not in choices:
                        raise ValidationError({key: ['Valor no permitido.']})
                    qs = qs.filter(**{key: p[key]})
        if section == 'movimientos':
            if 'articulo' in p:
                qs = qs.filter(articulo_id=articulo_filtro(p))
            if 'tipo' in p:
                if p['tipo'] not in MovimientoInventario.Tipo.values:
                    raise ValidationError({'tipo': ['Tipo no permitido.']})
                qs = qs.filter(tipo=p['tipo'])
            dates = {}
            for key in ('desde', 'hasta'):
                if key in p:
                    try:
                        dates[key] = date.fromisoformat(p[key])
                        if dates[key].isoformat() != p[key]:
                            raise ValueError()
                    except ValueError:
                        raise ValidationError({key: ['Fecha civil inválida.']}) from None
            if len(dates) == 2 and dates['desde'] > dates['hasta']:
                raise ValidationError({'hasta': ['Rango invertido.']})
            for key, lookup in (('desde', 'gte'), ('hasta', 'lte')):
                if key in dates:
                    qs = qs.filter(**{'creado_en__date__' + lookup: dates[key]})
        paginator = InventarioPaginacion()
        return paginator.get_paginated_response([render(row) for row in paginator.paginate_queryset(qs, request, view=self)])
