"""API 004A: no expone finalizar, cancelar ni escrituras de eventos."""

from datetime import date
import re

from django.contrib.auth import get_user_model
from django.db.models import F
from django.db.models.functions import Lower
from django.shortcuts import get_object_or_404
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import APIException, NotFound, PermissionDenied, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.comercial.models import Presupuesto
from apps.usuarios.models import Usuario

from . import services
from .exceptions import (
    DatosInvalidos, ErrorObras, EstadoIncompatible, PermisoDenegado,
    PresupuestoUtilizado, RecursoNoEncontrado, SinCambios,
)
from .models import CategoriaServicio, Obra
from .permissions import PuedeOperarCategorias, PuedeOperarObras
from .serializers import (
    CambioTecnicoSerializer, CategoriaServicioEventoSerializer,
    CategoriaServicioSerializer, MotivoCategoriaSerializer,
    MotivoObligatorioSerializer, NombreCategoriaSerializer,
    ObraCrearSerializer, ObraEditarSerializer, ObraEventoSerializer,
    ObraFinanzasSerializer, ObraLecturaSerializer,
    PresupuestoDisponibleSerializer, RenombrarCategoriaSerializer,
    TecnicoDisponibleSerializer,
)


class ConflictoObras(APIException):
    status_code = status.HTTP_409_CONFLICT

    def __init__(self, error):
        super().__init__({"detail": str(error), "code": error.codigo})


def traducir_error_obras(error):
    if isinstance(error, (EstadoIncompatible, PresupuestoUtilizado, SinCambios)):
        return ConflictoObras(error)
    if isinstance(error, RecursoNoEncontrado):
        return NotFound(str(error))
    if isinstance(error, PermisoDenegado):
        return PermissionDenied(str(error))
    if isinstance(error, DatosInvalidos):
        errores = dict(error.errores)
        if "__all__" in errores:
            errores["non_field_errors"] = errores.pop("__all__")
        return ValidationError(errores)
    return error


class ObrasPaginacion(PageNumberPagination):
    page_size = 25
    page_size_query_param = None


def _entero_query(query, nombre):
    """Filtros solo con enteros en base diez positivos."""
    if not re.fullmatch(r"[0-9]+", query) or int(query) < 1 or int(query) > 9223372036854775807:
        raise ValidationError({nombre: ["Debe ser un identificador entero positivo."]})
    return int(query)


def _fecha_query(query, nombre):
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", query):
        raise ValidationError({nombre: ["Use YYYY-MM-DD."]})
    try:
        return date.fromisoformat(query)
    except ValueError as exc:
        raise ValidationError({nombre: ["Fecha inválida."]}) from exc


def _validar_query_params(params, permitidos):
    extra = set(params) - set(permitidos) - {"page"}
    if extra:
        raise ValidationError({campo: ["Parámetro no permitido."] for campo in sorted(extra)})
    repetidos = [campo for campo in params if len(params.getlist(campo)) != 1]
    if repetidos:
        raise ValidationError({campo: ["Parámetro repetido."] for campo in repetidos})


class ObraViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    permission_classes = [IsAuthenticated, PuedeOperarObras]
    pagination_class = ObrasPaginacion
    http_method_names = ["get", "post", "patch", "head", "options"]
    lookup_value_regex = "[0-9]+"

    def get_queryset(self):
        queryset = Obra.objects.select_related(
            "presupuesto", "presupuesto__cliente", "categoria_servicio",
            "tecnico_responsable",
        )
        # Importante: filtrar ANTES de paginar y antes de buscar detalles.
        if self.request.user.rol == Usuario.Rol.TECNICO:
            queryset = queryset.filter(tecnico_responsable_id=self.request.user.pk)
        return queryset.order_by("-creado_en", "-id")

    def get_serializer_class(self):
        clases = {
            "create": ObraCrearSerializer,
            "partial_update": ObraEditarSerializer,
            "cambiar_tecnico": CambioTecnicoSerializer,
            "iniciar": MotivoObligatorioSerializer,
            "suspender": MotivoObligatorioSerializer,
            "reanudar": MotivoObligatorioSerializer,
            "historial": ObraEventoSerializer,
            "presupuestos_disponibles": PresupuestoDisponibleSerializer,
            "tecnicos_disponibles": TecnicoDisponibleSerializer,
        }
        accion = getattr(self, "action", None)
        if accion in clases:
            return clases[accion]
        if self.request.user.rol == Usuario.Rol.ADMINISTRATIVO_FINANZAS:
            return ObraFinanzasSerializer
        return ObraLecturaSerializer

    def handle_exception(self, exc):
        return super().handle_exception(traducir_error_obras(exc))

    def _datos(self):
        serializer = self.get_serializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data

    def _paginado(self, queryset, serializer_class):
        pagina = self.paginate_queryset(queryset)
        return self.get_paginated_response(serializer_class(pagina, many=True).data)

    def _detalle(self, obra, codigo=status.HTTP_200_OK):
        # No confiar en un objeto obsoleto que el servicio recibió de la view.
        actual = get_object_or_404(self.get_queryset(), pk=obra.pk)
        return Response(ObraLecturaSerializer(actual).data, status=codigo)

    def list(self, request, *args, **kwargs):
        filtros = {"estado", "tecnico_responsable", "cliente", "categoria_servicio",
                   "fecha_programada_desde", "fecha_programada_hasta", "ordering"}
        _validar_query_params(request.query_params, filtros)
        queryset = self.get_queryset()
        for nombre in ("tecnico_responsable", "cliente", "categoria_servicio"):
            if nombre in request.query_params:
                filtro = {
                    "tecnico_responsable": "tecnico_responsable_id",
                    "cliente": "presupuesto__cliente_id",
                    "categoria_servicio": "categoria_servicio_id",
                }[nombre]
                queryset = queryset.filter(**{
                    filtro: _entero_query(request.query_params[nombre], nombre),
                })
        if "estado" in request.query_params:
            estado = request.query_params["estado"]
            if estado not in Obra.Estado.values:
                raise ValidationError({"estado": ["Estado desconocido."]})
            queryset = queryset.filter(estado=estado)
        desde = hasta = None
        if "fecha_programada_desde" in request.query_params:
            desde = _fecha_query(request.query_params["fecha_programada_desde"], "fecha_programada_desde")
            queryset = queryset.filter(fecha_programada__gte=desde)
        if "fecha_programada_hasta" in request.query_params:
            hasta = _fecha_query(request.query_params["fecha_programada_hasta"], "fecha_programada_hasta")
            queryset = queryset.filter(fecha_programada__lte=hasta)
        if desde and hasta and desde > hasta:
            raise ValidationError({"fecha_programada_hasta": ["Debe ser igual o posterior a desde."]})
        if "ordering" in request.query_params:
            orden = request.query_params["ordering"]
            if orden not in {"creado_en", "-creado_en", "fecha_programada", "-fecha_programada"}:
                raise ValidationError({"ordering": ["Orden no permitido."]})
            columna = orden.removeprefix("-")
            descendente = orden.startswith("-")
            if columna == "fecha_programada":
                campo = (F(columna).desc(nulls_last=True) if descendente
                         else F(columna).asc(nulls_last=True))
                queryset = queryset.order_by(campo, "-id" if descendente else "id")
            else:
                queryset = queryset.order_by(orden, "-id" if descendente else "id")
        return self._paginado(queryset, self.get_serializer_class())

    def create(self, request, *args, **kwargs):
        obra = services.crear_obra(self._datos(), request.user)
        return self._detalle(obra, status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None, *args, **kwargs):
        obra = self.get_object()
        actual = services.editar_obra(obra, self._datos(), request.user)
        return self._detalle(actual)

    @action(detail=True, methods=["post"], url_path="cambiar-tecnico")
    def cambiar_tecnico(self, request, pk=None):
        obra = self.get_object()
        datos = self._datos()
        actual = services.cambiar_tecnico(obra, usuario=request.user, **datos)
        return self._detalle(actual)

    def _transicion(self, operacion):
        obra = self.get_object()
        actual = operacion(obra, self.request.user, **self._datos())
        return self._detalle(actual)

    @action(detail=True, methods=["post"])
    def iniciar(self, request, pk=None):
        return self._transicion(services.iniciar_obra)

    @action(detail=True, methods=["post"])
    def suspender(self, request, pk=None):
        return self._transicion(services.suspender_obra)

    @action(detail=True, methods=["post"])
    def reanudar(self, request, pk=None):
        return self._transicion(services.reanudar_obra)

    @action(detail=True, methods=["get"])
    def historial(self, request, pk=None):
        obra = self.get_object()
        _validar_query_params(request.query_params, set())
        return self._paginado(
            obra.eventos.order_by("creado_en", "id"), ObraEventoSerializer,
        )

    @action(detail=False, methods=["get"], url_path="presupuestos-disponibles")
    def presupuestos_disponibles(self, request):
        _validar_query_params(request.query_params, set())
        disponibles = Presupuesto.objects.select_related("cliente").filter(
            estado=Presupuesto.Estado.APROBADO_CLIENTE,
            obra__isnull=True,
        ).order_by("-creado_en", "-id")
        return self._paginado(disponibles, PresupuestoDisponibleSerializer)

    @action(detail=False, methods=["get"], url_path="tecnicos-disponibles")
    def tecnicos_disponibles(self, request):
        _validar_query_params(request.query_params, set())
        tecnicos = get_user_model().objects.filter(
            rol=Usuario.Rol.TECNICO, is_active=True,
        ).order_by("id")
        return self._paginado(tecnicos, TecnicoDisponibleSerializer)


class CategoriaServicioViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    permission_classes = [IsAuthenticated, PuedeOperarCategorias]
    pagination_class = ObrasPaginacion
    http_method_names = ["get", "post", "patch", "head", "options"]
    lookup_value_regex = "[0-9]+"

    def get_queryset(self):
        return CategoriaServicio.objects.all().order_by(Lower("nombre"), "id")

    def get_serializer_class(self):
        return {
            "create": NombreCategoriaSerializer,
            "partial_update": RenombrarCategoriaSerializer,
            "activar": MotivoCategoriaSerializer,
            "desactivar": MotivoCategoriaSerializer,
            "historial": CategoriaServicioEventoSerializer,
        }.get(getattr(self, "action", None), CategoriaServicioSerializer)

    def handle_exception(self, exc):
        return super().handle_exception(traducir_error_obras(exc))

    def _datos(self):
        serializer = self.get_serializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data

    def _paginado(self, queryset, clase):
        pagina = self.paginate_queryset(queryset)
        return self.get_paginated_response(clase(pagina, many=True).data)

    def list(self, request, *args, **kwargs):
        _validar_query_params(request.query_params, {"activo"})
        queryset = self.get_queryset()
        if "activo" in request.query_params:
            activo = request.query_params["activo"]
            if activo not in {"true", "false"}:
                raise ValidationError({"activo": ["Use true o false."]})
            queryset = queryset.filter(activo=activo == "true")
        return self._paginado(queryset, CategoriaServicioSerializer)

    def _detalle(self, categoria, codigo=status.HTTP_200_OK):
        actual = get_object_or_404(self.get_queryset(), pk=categoria.pk)
        return Response(CategoriaServicioSerializer(actual).data, status=codigo)

    def create(self, request):
        categoria = services.crear_categoria(**self._datos(), usuario=request.user)
        return self._detalle(categoria, status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        categoria = self.get_object()
        actual = services.renombrar_categoria(
            categoria, **self._datos(), usuario=request.user,
        )
        return self._detalle(actual)

    def _accion(self, operacion):
        categoria = self.get_object()
        actual = operacion(categoria, self.request.user, **self._datos())
        return self._detalle(actual)

    @action(detail=True, methods=["post"])
    def activar(self, request, pk=None):
        return self._accion(services.activar_categoria)

    @action(detail=True, methods=["post"])
    def desactivar(self, request, pk=None):
        return self._accion(services.desactivar_categoria)

    @action(detail=True, methods=["get"])
    def historial(self, request, pk=None):
        categoria = self.get_object()
        _validar_query_params(request.query_params, set())
        return self._paginado(
            categoria.eventos.order_by("creado_en", "id"),
            CategoriaServicioEventoSerializer,
        )
