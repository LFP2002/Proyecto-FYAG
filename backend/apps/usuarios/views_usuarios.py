from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from django.utils.decorators import method_decorator
from django.db.models import Count, Q, Value
from django.db.models.functions import Concat
from django.views.decorators.debug import sensitive_post_parameters, sensitive_variables

from . import services_usuarios as services
from .models import EventoAcceso, RecuperacionCorreoEvento, RecuperacionTIEvento, Usuario
from .permissions import EsAdministradorTIActivo
from .serializers_usuarios import (
    CambiarClavePropiaSerializer, CrearUsuarioSerializer, EstablecerClaveSerializer,
    MotivoUsuarioSerializer, PerfilUsuarioSerializer, RolUsuarioSerializer,
    AccesoHistorialSerializer, RecuperacionHistorialSerializer, UsuarioEventoSerializer, UsuarioLecturaSerializer,
)
from .services import delete_refresh_cookie, sin_cache


class UsuariosPaginacion(PageNumberPagination):
    page_size = 25
    page_size_query_param = None


def validar_query(params, allowed):
    errors = {key: ["Parámetro no permitido."] for key in params if key not in allowed | {"page"}}
    errors.update({key: ["Parámetro repetido."] for key in params if len(params.getlist(key)) != 1})
    if errors:
        raise ValidationError(errors)


@method_decorator(sensitive_post_parameters("password", "nueva_clave"), name="dispatch")
class UsuarioViewSet(mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated, EsAdministradorTIActivo]
    parser_classes = [JSONParser]
    pagination_class = UsuariosPaginacion
    http_method_names = ["get", "post", "patch", "head", "options"]
    lookup_value_regex = r"[1-9][0-9]{0,18}"

    def get_queryset(self):
        from .configuracion_c2 import relaciones_seguridad
        return Usuario.objects.select_related(*relaciones_seguridad()).order_by("id")

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
            "restablecer_clave": MotivoUsuarioSerializer,
            "historial": UsuarioEventoSerializer,
        }.get(self.action, UsuarioLecturaSerializer)

    def _datos(self):
        serializer = self.get_serializer(data=self.request.data)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data

    def _respuesta(self, user, code=200):
        return Response(UsuarioLecturaSerializer(user).data, status=code)

    def list(self, request):
        validar_query(request.query_params, {"rol", "activo", "buscar", "resumen"})
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
        if "buscar" in request.query_params:
            term = request.query_params["buscar"].strip()
            if not term or len(term) > 150 or any(ord(c) < 32 for c in term):
                raise ValidationError({"buscar": ["Ingrese entre 1 y 150 caracteres."]})
            queryset = queryset.annotate(nombre_completo=Concat("first_name", Value(" "), "last_name")).filter(
                Q(username__icontains=term) | Q(email__icontains=term) | Q(nombre_completo__icontains=term))
        resumen = request.query_params.get("resumen")
        if resumen is not None and resumen != "true":
            raise ValidationError({"resumen": ["Use true."]})
        pagina = self.paginate_queryset(queryset)
        response = self.get_paginated_response(UsuarioLecturaSerializer(pagina, many=True).data)
        if resumen == "true":
            response.data["resumen"] = Usuario.objects.aggregate(
                total=Count("pk"),
                activas=Count("pk", filter=Q(is_active=True)),
                inactivas=Count("pk", filter=Q(is_active=False)),
                temporales=Count("pk", filter=Q(seguridad_credencial__estado__in=["INICIAL", "RECUPERACION"])),
            )
        return sin_cache(response)

    @sensitive_variables()
    def _credencial(self, issued, code=200):
        data = dict(UsuarioLecturaSerializer(issued.usuario).data)
        data.update(credencial_temporal=issued.credencial_temporal, credencial_vence_en=issued.vence_en.isoformat())
        return sin_cache(Response(data, status=code))

    @sensitive_variables()
    def create(self, request):
        return self._credencial(services.crear_usuario(self._datos(), request.user), status.HTTP_201_CREATED)

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
        return self._respuesta(services.establecer_clave(target, {}, request.user))

    @action(detail=True, methods=["post"], url_path="restablecer-clave")
    @sensitive_variables()
    def restablecer_clave(self, request, pk=None):
        from .credenciales import restablecer_clave
        target = self.get_object()
        return self._credencial(restablecer_clave(target, self._datos(), request.user))

    @action(detail=True, methods=["get"])
    def historial(self, request, pk=None):
        target = self.get_object()
        validar_query(request.query_params, set())
        fuentes = (target.eventos_administrativos.select_related('recuperacionacceso'), RecuperacionCorreoEvento.objects.filter(usuario=target),
                   RecuperacionTIEvento.objects.filter(usuario=target),
                   target.eventos_acceso.filter(tipo__in=EventoAcceso.TIPOS_PUBLICOS, actor_tipo='SISTEMA'))
        # Una única paginación SQL; el discriminador solo desempata IDs de distintas fuentes.
        refs, *otros = [fuente.order_by().annotate(origen=Value(i)).values_list('creado_en', 'id', 'origen')
                        for i, fuente in enumerate(fuentes)]
        page = self.paginate_queryset(refs.union(*otros, all=True).order_by('creado_en', 'id', 'origen'))
        filas = [fuente.in_bulk([pk for _, pk, origen in page if origen == i]) for i, fuente in enumerate(fuentes)]
        serializadores = (UsuarioEventoSerializer, RecuperacionHistorialSerializer, RecuperacionHistorialSerializer, AccesoHistorialSerializer)
        return self.get_paginated_response([serializadores[origen](filas[origen][pk]).data for _, pk, origen in page])


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
