from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import consultas_mermas as consultas, services_mermas as services
from .consultas_solicitudes import validar_query
from .permissions_mermas import PermisoMermas
from .serializers_mermas import MermaSerializer, MermaCostoSerializer
from .views import InventarioPaginacion, articulo_filtro
from .views_materiales import CabecerasMateriales


class MermasAPIView(CabecerasMateriales, APIView):
    permission_classes = [IsAuthenticated, PermisoMermas]
    parser_classes = [JSONParser]
    ambito = None
    accion_escritura = 'crear'
    http_method_names = ['get', 'head', 'options']

    def serializar(self, merma, **contexto):
        economico = self.request.user.rol in {'ADMINISTRATIVO_FINANZAS', 'SUPERVISOR_OBRAS', 'GERENCIA'}
        return (MermaCostoSerializer if economico else MermaSerializer)(merma, context=contexto).data


class MermasView(MermasAPIView):
    http_method_names = ['get', 'post', 'head', 'options']

    def get(self, request):
        qs = consultas.listado(request.user, self.ambito, request.query_params)
        paginador = InventarioPaginacion()
        pagina = paginador.paginate_queryset(qs, request, view=self)
        return paginador.get_paginated_response([self.serializar(m) for m in pagina])

    def post(self, request):
        validar_query(request.query_params)
        merma, nueva = services.crear(self.ambito, request.data, request.user)
        return Response(self.serializar(merma, creacion=True), status=201 if nueva else 200,
            headers={'Idempotency-Replayed': 'false' if nueva else 'true'})


class MermaDetalleView(MermasAPIView):
    def get(self, request, merma_id):
        pk = articulo_filtro({'articulo': merma_id})
        return Response(self.serializar(consultas.obtener(request.user, self.ambito, pk, request.query_params), detalle=True))


class MermaDecidirView(MermasAPIView):
    accion_escritura = 'decidir'
    http_method_names = ['post', 'options']

    def post(self, request, merma_id):
        validar_query(request.query_params)
        pk = articulo_filtro({'articulo': merma_id})
        merma, nueva = services.decidir(self.ambito, pk, request.data, request.user)
        return Response(self.serializar(merma), headers={'Idempotency-Replayed': 'false' if nueva else 'true'})
