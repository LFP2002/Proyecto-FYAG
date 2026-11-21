from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import consultas_solicitudes as consultas, services_solicitudes as services
from .permissions_solicitudes import PermisoSolicitudes
from .serializers_solicitudes import ArticuloSolicitableSerializer, SolicitudSerializer, SolicitudCreacionSerializer, SolicitudDetalleSerializer
from .views import InventarioPaginacion, articulo_filtro
from .views_materiales import CabecerasMateriales


class SolicitudesAPIView(CabecerasMateriales, APIView):
    permission_classes = [IsAuthenticated, PermisoSolicitudes]
    parser_classes = [JSONParser]
    http_method_names = ['get', 'head', 'options']
    accion_escritura = 'crear'

    def paginar(self, qs, serializer):
        paginador = InventarioPaginacion()
        pagina = paginador.paginate_queryset(qs, self.request, view=self)
        return paginador.get_paginated_response(serializer(pagina, many=True).data)


class ArticulosSolicitablesView(SolicitudesAPIView):
    def get(self, request):
        return self.paginar(consultas.catalogo(request.user, request.query_params), ArticuloSolicitableSerializer)


class SolicitudesMaterialesView(SolicitudesAPIView):
    http_method_names = ['get', 'post', 'head', 'options']

    def get(self, request):
        return self.paginar(consultas.listado(request.user, request.query_params), SolicitudSerializer)

    def post(self, request):
        consultas.validar_query(request.query_params)
        solicitud, nueva = services.crear_solicitud(request.data, request.user)
        return Response(SolicitudCreacionSerializer(solicitud).data, status=201 if nueva else 200,
            headers={'Idempotency-Replayed': 'false' if nueva else 'true'})


class SolicitudDetalleView(SolicitudesAPIView):
    def get(self, request, solicitud_id):
        pk = articulo_filtro({'articulo': solicitud_id})
        return Response(SolicitudDetalleSerializer(consultas.obtener(request.user, pk, request.query_params)).data)


class SolicitudDecidirView(SolicitudesAPIView):
    http_method_names = ['post', 'options']
    accion_escritura = 'decidir'

    def post(self, request, solicitud_id):
        consultas.validar_query(request.query_params)
        pk = articulo_filtro({'articulo': solicitud_id})
        solicitud, nueva = services.decidir_solicitud(pk, request.data, request.user)
        return Response(SolicitudSerializer(solicitud).data,
            headers={'Idempotency-Replayed': 'false' if nueva else 'true'})
