import re
from datetime import date

from rest_framework import mixins, viewsets
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .models import ArticuloInventario, ExistenciaInventario, MovimientoInventario
from .permissions import PuedeOperarInventario
from .serializers import ArticuloSerializer, ExistenciaSerializer, MovimientoSerializer


class InventarioPaginacion(PageNumberPagination):
    page_size = 25
    page_size_query_param = None


def query(params, allowed):
    if set(params) - (set(allowed) | {"page"}) or any(len(params.getlist(k)) != 1 or not params[k] for k in params):
        raise ValidationError({"query": ["Parámetro desconocido, repetido o vacío."]})
    if "page" in params and not re.fullmatch(r"[1-9][0-9]{0,8}", params["page"]):
        raise ValidationError({"page": ["Página entera positiva requerida."]})


def articulo_filtro(params):
    value = params["articulo"]
    if not re.fullmatch(r"[1-9][0-9]{0,18}", value) or int(value) > 9223372036854775807:
        raise ValidationError({"articulo": ["Identificador inválido."]})
    return int(value)


class InventarioViewSet(viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated, PuedeOperarInventario]
    parser_classes = [JSONParser]
    pagination_class = InventarioPaginacion
    http_method_names = ["get", "head", "options"]
    lookup_value_regex = r"[1-9][0-9]{0,18}"


class ArticuloViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, InventarioViewSet):
    serializer_class = ArticuloSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        params = self.request.query_params
        query(params, {"buscar", "activo"} if self.action == "list" else set())
        qs = ArticuloInventario.objects.order_by("id")
        if "activo" in params:
            if params["activo"] not in {"true", "false"}:
                raise ValidationError({"activo": ["Use true o false."]})
            qs = qs.filter(activo=params["activo"] == "true")
        if "buscar" in params:
            from django.db.models import Q
            search = services.texto(params["buscar"], "buscar", 150)
            qs = qs.filter(Q(codigo__icontains=search) | Q(nombre__icontains=search))
        return qs

    def get_object(self):
        if int(self.kwargs["pk"]) > 9223372036854775807:
            raise NotFound("Artículo no disponible.")
        return super().get_object()

    def create(self, request):
        query(request.query_params, set())
        return Response(ArticuloSerializer(services.crear_articulo(request.data, request.user)).data, status=201)

    def partial_update(self, request, pk=None):
        target = self.get_object()
        return Response(ArticuloSerializer(services.editar_articulo(target.pk, request.data, request.user)).data)


class ExistenciaViewSet(mixins.ListModelMixin, InventarioViewSet):
    serializer_class = ExistenciaSerializer

    def get_queryset(self):
        params = self.request.query_params
        query(params, {"articulo"})
        qs = ExistenciaInventario.objects.select_related("articulo").order_by("articulo_id")
        if "articulo" in params:
            qs = qs.filter(articulo_id=articulo_filtro(params))
        return qs


class MovimientoViewSet(mixins.ListModelMixin, InventarioViewSet):
    serializer_class = MovimientoSerializer

    def get_queryset(self):
        params = self.request.query_params
        query(params, {"articulo", "tipo", "desde", "hasta"})
        qs = MovimientoInventario.objects.order_by("creado_en", "id")
        if "articulo" in params:
            qs = qs.filter(articulo_id=articulo_filtro(params))
        if "tipo" in params:
            if params["tipo"] != "INGRESO":
                raise ValidationError({"tipo": ["Tipo no publicado en 019A."]})
            qs = qs.filter(tipo="INGRESO")
        dates = {}
        for key in ("desde", "hasta"):
            if key in params:
                try:
                    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", params[key]):
                        raise ValueError
                    dates[key] = date.fromisoformat(params[key])
                except ValueError:
                    raise ValidationError({key: ["Fecha civil ISO válida requerida."]}) from None
        if len(dates) == 2 and dates["desde"] > dates["hasta"]:
            raise ValidationError({"hasta": ["Rango de fechas invertido."]})
        for key, lookup in (("desde", "gte"), ("hasta", "lte")):
            if key in dates:
                qs = qs.filter(**{f"creado_en__date__{lookup}": dates[key]})
        return qs


class IngresoView(APIView):
    permission_classes = [IsAuthenticated, PuedeOperarInventario]
    parser_classes = [JSONParser]
    http_method_names = ["post", "options"]

    def post(self, request):
        query(request.query_params, set())
        movement, created = services.registrar_ingreso(request.data, request.user)
        response = Response(MovimientoSerializer(movement).data, status=201 if created else 200)
        response["Idempotency-Replayed"] = "false" if created else "true"
        return response
