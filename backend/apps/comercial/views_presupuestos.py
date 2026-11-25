from django.db.models import Prefetch, Q
from django.shortcuts import get_object_or_404
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import APIException, NotFound, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.inventario.models import ArticuloInventario

from . import services_presupuestos as servicios
from .services_seguimiento import seguimiento_comercial
from .exceptions import (
    ClienteInactivo,
    DatosInvalidos,
    EstadoIncompatible,
    MotivoObligatorio,
    OrdenDuplicado,
    RecursoNoEncontrado,
    PresupuestoUtilizado,
)
from .models import Cliente, Presupuesto, PresupuestoItem
from .permissions import PuedeOperarPresupuestos
from .permissions_presupuestos import presupuestos_visibles, revalidar_presupuestos
from .serializers_presupuestos import (
    ClienteElegibleSerializer,
    MaterialElegibleSerializer,
    PresupuestoAccionSerializer,
    PresupuestoDetalleSerializer,
    PresupuestoEscrituraSerializer,
    PresupuestoEventoSerializer,
    PresupuestoItemEscrituraSerializer,
    PresupuestoItemSerializer,
    PresupuestoListadoSerializer,
    PresupuestoMotivoObligatorioSerializer,
    PresupuestoRevisionSerializer,
)


class ConflictoPresupuesto(APIException):
    status_code = status.HTTP_409_CONFLICT

    def __init__(self, error):
        super().__init__({"detail": str(error), "code": error.codigo})


def traducir_error_presupuesto(error):
    """Traduce errores conocidos sin ocultar fallos internos."""
    if isinstance(error, (EstadoIncompatible, PresupuestoUtilizado)):
        return ConflictoPresupuesto(error)
    if isinstance(error, RecursoNoEncontrado):
        return NotFound(str(error))
    if isinstance(error, DatosInvalidos):
        errores = dict(error.errores)
        if "__all__" in errores:
            campo = "non_field_errors"
            for tipo, nombre in (
                (ClienteInactivo, "cliente"),
                (MotivoObligatorio, "motivo"),
                (OrdenDuplicado, "orden"),
            ):
                if isinstance(error, tipo):
                    campo = nombre
                    break
            errores[campo] = errores.pop("__all__")
        return ValidationError(errores)
    return error


class PresupuestoPaginacion(PageNumberPagination):
    page_size = 25
    page_size_query_param = None


def presupuestos_con_lineas():
    return Presupuesto.objects.prefetch_related(Prefetch(
        "items", queryset=PresupuestoItem.objects.order_by("orden", "id"),
        to_attr="lineas_respuesta",
    ))


class PresupuestoViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    permission_classes = [IsAuthenticated, PuedeOperarPresupuestos]
    pagination_class = PresupuestoPaginacion
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]
    lookup_value_regex = "[0-9]+"

    def get_queryset(self):
        queryset = Presupuesto.objects.all()
        if self.action in {"list", "retrieve"}:
            queryset = presupuestos_con_lineas()
        return presupuestos_visibles(self.request.user, queryset).order_by("-creado_en", "-id")

    def get_serializer_class(self):
        return {
            'clientes_elegibles': ClienteElegibleSerializer,
            'materiales_elegibles': MaterialElegibleSerializer,
            "list": PresupuestoListadoSerializer,
            "create": PresupuestoEscrituraSerializer,
            "partial_update": PresupuestoEscrituraSerializer,
            "items": PresupuestoItemEscrituraSerializer,
            "item_detalle": PresupuestoItemEscrituraSerializer,
            "historial": PresupuestoEventoSerializer,
            "crear_revision": PresupuestoRevisionSerializer,
            "rechazar_gerencia": PresupuestoMotivoObligatorioSerializer,
            "rechazar_finanzas": PresupuestoMotivoObligatorioSerializer,
            "enviar_finanzas": PresupuestoAccionSerializer,
            "aprobar_finanzas": PresupuestoAccionSerializer,
            "registrar_rechazo_cliente": (
                PresupuestoMotivoObligatorioSerializer
            ),
            "anular": PresupuestoMotivoObligatorioSerializer,
            "enviar_gerencia": PresupuestoAccionSerializer,
            "aprobar_gerencia": PresupuestoAccionSerializer,
            "enviar_cliente": PresupuestoAccionSerializer,
            "registrar_aprobacion_cliente": PresupuestoAccionSerializer,
        }.get(self.action, PresupuestoDetalleSerializer)

    def handle_exception(self, exc):
        return super().handle_exception(traducir_error_presupuesto(exc))

    def _entrada(self, *, partial=False):
        serializer = self.get_serializer(
            data=self.request.data, partial=partial
        )
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data

    def _detalle(self, presupuesto, codigo=status.HTTP_200_OK):
        actual = get_object_or_404(
            presupuestos_visibles(self.request.user, presupuestos_con_lineas()), pk=presupuesto.pk
        )
        return Response(
            PresupuestoDetalleSerializer(actual).data, status=codigo
        )

    @action(detail=False, methods=["get"], url_path="seguimiento-comercial")
    def seguimiento_comercial(self, request):
        rows, resumen = seguimiento_comercial(self.get_queryset(), request.query_params)
        response = self.get_paginated_response(self.paginate_queryset(rows))
        response.data["resumen"] = resumen
        return response

    def create(self, request):
        presupuesto = servicios.crear_presupuesto(
            **self._entrada(), usuario=request.user
        )
        return self._detalle(presupuesto, status.HTTP_201_CREATED)

    @action(detail=False, methods=['get'], url_path='clientes-elegibles')
    def clientes_elegibles(self, request):
        revalidar_presupuestos(request.user, 'selector')
        params = request.query_params
        if set(params)-{'buscar', 'page'} or any(len(params.getlist(k)) != 1 for k in params):
            raise ValidationError({'query': ['Parámetros desconocidos o repetidos.']})
        if 'page' in params and (len(params['page']) > 19 or not params['page'].isascii() or not params['page'].isdecimal()
                                 or not 0 < int(params['page']) <= 9223372036854775807):
            raise ValidationError({'page': ['Indique una página positiva.']})
        queryset = Cliente.objects.filter(activo=True)
        if 'buscar' in params:
            buscar = params['buscar'].strip()
            if not buscar or len(buscar) > 200 or any(ord(c) < 32 for c in buscar):
                raise ValidationError({'buscar': ['Búsqueda inválida.']})
            queryset = queryset.filter(nombre_legal__icontains=buscar)
        # Proyección SQL mínima: nunca cargar PII para este selector.
        pagina = self.paginate_queryset(queryset.order_by('nombre_legal', 'id').values('id', 'nombre_legal', 'tipo_cliente'))
        return self.get_paginated_response(ClienteElegibleSerializer(pagina, many=True).data)

    @action(detail=False, methods=['get'], url_path='materiales-elegibles')
    def materiales_elegibles(self, request):
        revalidar_presupuestos(request.user, 'selector')
        params = request.query_params
        if set(params) - {'buscar', 'page'} or any(len(params.getlist(k)) != 1 for k in params):
            raise ValidationError({'query': ['Parámetros desconocidos o repetidos.']})
        if 'page' in params:
            page = params['page']
            if len(page) > 19 or not page.isascii() or not page.isdecimal() or not 0 < int(page) <= 9223372036854775807:
                raise ValidationError({'page': ['Indique una página positiva.']})
        queryset = ArticuloInventario.objects.filter(activo=True)
        if 'buscar' in params:
            buscar = params['buscar'].strip()
            if not buscar or len(buscar) > 150 or any(ord(c) < 32 for c in buscar):
                raise ValidationError({'buscar': ['Búsqueda inválida.']})
            queryset = queryset.filter(Q(codigo__icontains=buscar) | Q(nombre__icontains=buscar))
        # Catálogo mínimo: no consultar existencias, costos ni datos de actores.
        pagina = self.paginate_queryset(
            queryset.order_by('nombre', 'id').values('id', 'codigo', 'nombre', 'unidad')
        )
        return self.get_paginated_response(MaterialElegibleSerializer(pagina, many=True).data)

    def partial_update(self, request, pk=None):
        presupuesto = self.get_object()
        actualizado = servicios.modificar_presupuesto(
            presupuesto, self._entrada(partial=True), request.user
        )
        return self._detalle(actualizado)

    @action(detail=True, methods=["post"])
    def items(self, request, pk=None):
        presupuesto = self.get_object()
        item = servicios.crear_item(presupuesto, self._entrada(), request.user)
        return Response(
            PresupuestoItemSerializer(item).data,
            status=status.HTTP_201_CREATED,
        )

    @action(
        detail=True, methods=["patch", "delete"],
        url_path=r"items/(?P<item_id>[0-9]+)", url_name="item-detalle",
    )
    def item_detalle(self, request, pk=None, item_id=None):
        presupuesto = self.get_object()
        # Existencia antes de reglas de estado; el servicio revalida bajo lock.
        item = get_object_or_404(
            PresupuestoItem, presupuesto_id=presupuesto.pk, pk=item_id
        )
        if request.method == "DELETE":
            servicios.eliminar_item(presupuesto, item, request.user)
            return Response(status=status.HTTP_204_NO_CONTENT)
        actualizado = servicios.modificar_item(
            presupuesto, item, self._entrada(partial=True), request.user
        )
        return Response(PresupuestoItemSerializer(actualizado).data)

    @action(detail=True, methods=["get"])
    def historial(self, request, pk=None):
        presupuesto = self.get_object()
        pagina = self.paginate_queryset(
            presupuesto.eventos.order_by("creado_en", "id")
        )
        return self.get_paginated_response(
            PresupuestoEventoSerializer(pagina, many=True).data
        )

    def _accion(self, operacion):
        presupuesto = self.get_object()
        resultado = operacion(
            presupuesto, self.request.user, **self._entrada()
        )
        return self._detalle(resultado)

    @action(detail=True, methods=["post"], url_path="enviar-gerencia")
    def enviar_gerencia(self, request, pk=None):
        return self._accion(servicios.enviar_gerencia)

    @action(detail=True, methods=["post"], url_path="enviar-finanzas")
    def enviar_finanzas(self, request, pk=None):
        return self._accion(servicios.enviar_finanzas)

    @action(detail=True, methods=["post"], url_path="aprobar-finanzas")
    def aprobar_finanzas(self, request, pk=None):
        return self._accion(servicios.aprobar_finanzas)

    @action(detail=True, methods=["post"], url_path="rechazar-finanzas")
    def rechazar_finanzas(self, request, pk=None):
        return self._accion(servicios.rechazar_finanzas)

    @action(detail=True, methods=["post"], url_path="aprobar-gerencia")
    def aprobar_gerencia(self, request, pk=None):
        return self._accion(servicios.aprobar_gerencia)

    @action(detail=True, methods=["post"], url_path="rechazar-gerencia")
    def rechazar_gerencia(self, request, pk=None):
        return self._accion(servicios.rechazar_gerencia)

    @action(detail=True, methods=["post"], url_path="enviar-cliente")
    def enviar_cliente(self, request, pk=None):
        return self._accion(servicios.enviar_cliente)

    @action(
        detail=True, methods=["post"], url_path="registrar-aprobacion-cliente"
    )
    def registrar_aprobacion_cliente(self, request, pk=None):
        return self._accion(servicios.registrar_aprobacion_cliente)

    @action(
        detail=True, methods=["post"], url_path="registrar-rechazo-cliente"
    )
    def registrar_rechazo_cliente(self, request, pk=None):
        return self._accion(servicios.registrar_rechazo_cliente)

    @action(detail=True, methods=["post"])
    def anular(self, request, pk=None):
        return self._accion(servicios.anular_presupuesto)

    @action(detail=True, methods=["post"], url_path="crear-revision")
    def crear_revision(self, request, pk=None):
        presupuesto = self.get_object()
        self._entrada()
        revision = servicios.crear_revision(presupuesto, request.user)
        return self._detalle(revision, status.HTTP_201_CREATED)
