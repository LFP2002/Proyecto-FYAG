from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Cliente
from .permissions import PuedeGestionarClientes
from .serializers import ClienteSerializer, ejecutar_validacion_modelo
from .services import activar_cliente, desactivar_cliente


class ClienteViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    mixins.RetrieveModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    queryset = Cliente.objects.order_by("nombre_legal", "id")
    serializer_class = ClienteSerializer
    permission_classes = [IsAuthenticated, PuedeGestionarClientes]
    http_method_names = ["get", "post", "patch", "head", "options"]

    @action(detail=True, methods=["post"])
    def activar(self, request, pk=None):
        cliente = ejecutar_validacion_modelo(
            activar_cliente, self.get_object()
        )
        return Response(self.get_serializer(cliente).data)

    @action(detail=True, methods=["post"])
    def desactivar(self, request, pk=None):
        cliente = ejecutar_validacion_modelo(
            desactivar_cliente, self.get_object()
        )
        return Response(self.get_serializer(cliente).data)
