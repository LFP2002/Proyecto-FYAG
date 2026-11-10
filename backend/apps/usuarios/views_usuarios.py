from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services_usuarios as services
from .models import Usuario
from .permissions import EsGerenciaActiva
from .serializers_usuarios import (
    CambiarClavePropiaSerializer, CrearUsuarioSerializer, EstablecerClaveSerializer,
    MotivoUsuarioSerializer, PerfilUsuarioSerializer, RolUsuarioSerializer,
    UsuarioEventoSerializer, UsuarioLecturaSerializer,
)
from .services import delete_refresh_cookie


class UsuariosPaginacion(PageNumberPagination):
    page_size = 25
    page_size_query_param = None


def validar_query(params, allowed):
    errors = {key: ["Parámetro no permitido."] for key in params if key not in allowed | {"page"}}
    errors.update({key: ["Parámetro repetido."] for key in params if len(params.getlist(key)) != 1})
    if errors:
        raise ValidationError(errors)


class UsuarioViewSet(mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated, EsGerenciaActiva]
    parser_classes = [JSONParser]
    pagination_class = UsuariosPaginacion
    http_method_names = ["get", "post", "patch", "head", "options"]
    lookup_value_regex = r"[1-9][0-9]{0,18}"

    def get_queryset(self):
        return Usuario.objects.order_by("id")

    def get_object(self):
        # BigAutoField de PostgreSQL: no permitir que un número excesivo llegue a SQL.
        value = int(self.kwargs[self.lookup_field])
        if value > 9223372036854775807:
            from rest_framework.exceptions import NotFound
            raise NotFound("Cuenta no disponible.")
        return super().get_object()

    def get_serializer_class(self):
        return {
            "create": CrearUsuarioSerializer, "partial_update": PerfilUsuarioSerializer,
            "activar": MotivoUsuarioSerializer, "desactivar": MotivoUsuarioSerializer,
            "cambiar_rol": RolUsuarioSerializer, "establecer_clave": EstablecerClaveSerializer,
            "historial": UsuarioEventoSerializer,
        }.get(self.action, UsuarioLecturaSerializer)

    def _datos(self):
        serializer = self.get_serializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data

    def _respuesta(self, user, code=200):
        return Response(UsuarioLecturaSerializer(user).data, status=code)

    def list(self, request):
        validar_query(request.query_params, {"rol", "activo"})
        queryset = self.get_queryset()
        if "rol" in request.query_params:
            role = request.query_params["rol"]
            if role not in Usuario.Rol.values:
                raise ValidationError({"rol": ["Rol no permitido."]})
            queryset = queryset.filter(rol=role)
        if "activo" in request.query_params:
            active = request.query_params["activo"]
            if active not in {"true", "false"}:
                raise ValidationError({"activo": ["Use true o false."]})
            queryset = queryset.filter(is_active=active == "true")
        pagina = self.paginate_queryset(queryset)
        return self.get_paginated_response(UsuarioLecturaSerializer(pagina, many=True).data)

    def create(self, request):
        return self._respuesta(services.crear_usuario(self._datos(), request.user), status.HTTP_201_CREATED)

    def partial_update(self, request, pk=None):
        target = self.get_object()
        return self._respuesta(services.editar_usuario(target, self._datos(), request.user))

    @action(detail=True, methods=["post"])
    def activar(self, request, pk=None):
        target = self.get_object()
        return self._respuesta(services.actividad_usuario(target, self._datos(), request.user, activo=True))

    @action(detail=True, methods=["post"])
    def desactivar(self, request, pk=None):
        target = self.get_object()
        return self._respuesta(services.actividad_usuario(target, self._datos(), request.user, activo=False))

    @action(detail=True, methods=["post"], url_path="cambiar-rol")
    def cambiar_rol(self, request, pk=None):
        target = self.get_object()
        return self._respuesta(services.cambiar_rol(target, self._datos(), request.user))

    @action(detail=True, methods=["post"], url_path="establecer-clave")
    def establecer_clave(self, request, pk=None):
        target = self.get_object()
        return self._respuesta(services.establecer_clave(target, self._datos(), request.user))

    @action(detail=True, methods=["get"])
    def historial(self, request, pk=None):
        target = self.get_object()
        validar_query(request.query_params, set())
        page = self.paginate_queryset(target.eventos_administrativos.order_by("creado_en", "id"))
        return self.get_paginated_response(UsuarioEventoSerializer(page, many=True).data)


class CambiarClavePropiaView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser]

    def post(self, request):
        serializer = CambiarClavePropiaSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.cambiar_clave_propia(serializer.validated_data, request.user)
        response = Response(status=status.HTTP_204_NO_CONTENT)
        delete_refresh_cookie(response)
        return response
