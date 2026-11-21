from django.utils.cache import patch_vary_headers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from . import services_materiales, consultas_materiales
from .permissions_materiales import PermisoMateriales
from .serializers_materiales import OperacionSerializer, OperacionCostoSerializer
from .views import InventarioViewSet, query


class CabecerasMateriales:
    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response['Cache-Control'] = 'private, no-store'
        patch_vary_headers(response, ['Authorization'])
        return response


class OperacionesViewSet(CabecerasMateriales, InventarioViewSet):
    permission_classes = [IsAuthenticated, PermisoMateriales]
    http_method_names = ['get', 'post', 'head', 'options']
    tipo = None

    def get_serializer_class(self):
        if self.tipo in {'VALORIZACION', 'REGULARIZACION'} or (
            self.tipo in {'ENTREGA', 'DEVOLUCION'} and self.request.user.rol in {'SUPERVISOR_OBRAS', 'GERENCIA'}):
            return OperacionCostoSerializer
        return OperacionSerializer

    def list(self, request):
        qs = consultas_materiales.listado(request.user, self.tipo, request.query_params)
        return self.get_paginated_response(self.get_serializer(self.paginate_queryset(qs), many=True).data)

    def create(self, request):
        query(request.query_params, set())
        if request.query_params:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({'query': ['No se admiten parámetros en POST.']})
        op, creado = services_materiales.operar(self.tipo, request.data, request.user)
        return Response(self.get_serializer(op).data, status=201 if creado else 200,
            headers={'Idempotency-Replayed': 'false' if creado else 'true'})


class EstadosValoracionViewSet(CabecerasMateriales, InventarioViewSet):
    def list(self, request):
        qs = consultas_materiales.estados(request.user, request.query_params).select_related('articulo__existencia')
        return self.get_paginated_response([consultas_materiales.estado_publico(v) for v in self.paginate_queryset(qs)])
