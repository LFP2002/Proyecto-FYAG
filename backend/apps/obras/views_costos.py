from rest_framework.decorators import action
from rest_framework.parsers import JSONParser
from rest_framework.response import Response

from apps.usuarios.models import Usuario
from . import services_costos
from .serializers_costos import ResumenCostosSerializer, ResumenFinanzasSerializer


class CostosMixin:
    @action(detail=True, methods=["get", "patch"], url_path="costos/control", parser_classes=[JSONParser])
    def control_costos(self, request, pk=None):
        obra = self.get_object()
        if request.method == "PATCH":
            return Response(services_costos.declarar_rubros(obra, self._datos(), request.user))
        self._sin_filtros()
        return Response(services_costos.consultar_control(obra, request.user))

    @action(detail=True, methods=["post"], url_path="costos/validar", parser_classes=[JSONParser])
    def validar_costos(self, request, pk=None):
        obra = self.get_object()
        return Response(services_costos.validar_costos(obra, self._datos(), request.user))

    @action(detail=True, methods=["get"], url_path="costos/resumen")
    def resumen_costos(self, request, pk=None):
        obra = self.get_object()
        self._sin_filtros()
        datos = services_costos.resumen_costos(obra, request.user)
        clase = ResumenFinanzasSerializer if request.user.rol == Usuario.Rol.ADMINISTRATIVO_FINANZAS else ResumenCostosSerializer
        return Response(clase(datos).data)

    @action(detail=True, methods=["post"], url_path="cortesia-sin-cobro", parser_classes=[JSONParser])
    def cortesia_sin_cobro(self, request, pk=None):
        obra = self.get_object()
        return Response(services_costos.registrar_cortesia(obra, self._datos(), request.user))
