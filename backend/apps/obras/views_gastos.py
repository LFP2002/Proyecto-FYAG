from django.shortcuts import get_object_or_404
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound
from rest_framework.parsers import JSONParser
from rest_framework.response import Response

from . import services_gastos
from .models import CostoObraEvento
from .serializers_gastos import CostoObraEventoSerializer, GastoLecturaSerializer


class GastosMixin:
    """Materiales y otros gastos directos: Gerencia lee, Supervisor escribe."""

    def _gasto_autorizado(self, obra, gasto_id):
        if (not gasto_id or not gasto_id.isdigit() or len(gasto_id) > 19
                or not 0 < int(gasto_id) <= 9223372036854775807):
            raise NotFound()
        return get_object_or_404(obra.gastos, pk=int(gasto_id))

    def _sin_filtros(self):
        from .views import _validar_query_params
        _validar_query_params(self.request.query_params, set())

    def _respuesta_gasto(self, gasto, status=200):
        return Response(GastoLecturaSerializer(gasto).data, status=status)

    @action(
        detail=True, methods=["get", "post"], url_path="gastos",
        parser_classes=[JSONParser],
    )
    def gastos(self, request, pk=None):
        obra = self.get_object()
        if request.method == "POST":
            gasto = services_gastos.crear_gasto(
                obra, self._datos(), request.user,
            )
            return self._respuesta_gasto(gasto, 201)
        self._sin_filtros()
        return self._paginado(
            obra.gastos.order_by("-creado_en", "-id"), GastoLecturaSerializer,
        )

    @action(
        detail=True, methods=["patch"],
        url_path=r"gastos/(?P<gasto_id>[0-9]+)", parser_classes=[JSONParser],
    )
    def editar_gasto(self, request, pk=None, gasto_id=None):
        obra = self.get_object()
        self._gasto_autorizado(obra, gasto_id)
        gasto = services_gastos.editar_gasto(
            obra, int(gasto_id), self._datos(), request.user,
        )
        return self._respuesta_gasto(gasto)

    @action(
        detail=True, methods=["post"],
        url_path=r"gastos/(?P<gasto_id>[0-9]+)/devolver",
        parser_classes=[JSONParser],
    )
    def devolver_gasto(self, request, pk=None, gasto_id=None):
        obra = self.get_object()
        self._gasto_autorizado(obra, gasto_id)
        gasto = services_gastos.devolver_gasto(
            obra, int(gasto_id), self._datos(), request.user,
        )
        return self._respuesta_gasto(gasto)

    @action(
        detail=True, methods=["post"],
        url_path=r"gastos/(?P<gasto_id>[0-9]+)/anular",
        parser_classes=[JSONParser],
    )
    def anular_gasto(self, request, pk=None, gasto_id=None):
        obra = self.get_object()
        self._gasto_autorizado(obra, gasto_id)
        gasto = services_gastos.anular_gasto(
            obra, int(gasto_id), self._datos(), request.user,
        )
        return self._respuesta_gasto(gasto)

    @action(detail=True, methods=["get"], url_path="costos/historial")
    def historial_costos(self, request, pk=None):
        obra = self.get_object()
        self._sin_filtros()
        return self._paginado(
            CostoObraEvento.objects.filter(obra=obra).order_by("creado_en", "id"),
            CostoObraEventoSerializer,
        )
