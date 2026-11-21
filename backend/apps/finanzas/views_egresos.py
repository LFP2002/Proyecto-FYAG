from django.utils.cache import patch_vary_headers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from . import consultas_egresos as consultas, services_egresos as services
from .permissions_egresos import PermisoEgresos
from .serializers_egresos import EgresoLecturaSerializer, EgresoRegistroSerializer, EgresoEventoSerializer
from .views_documentos import pk_url
from .views_pagos import FinanzasAPIView


class EgresosAPIView(FinanzasAPIView):
    permission_classes = [IsAuthenticated, PermisoEgresos]
    http_method_names = ["get", "head", "options"]

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        patch_vary_headers(response, ["Authorization"])
        return response


class EgresosListaView(EgresosAPIView):
    http_method_names = ["get", "post", "head", "options"]

    def get(self, request):
        return self.paginar(consultas.listado(request.user, request.query_params), EgresoLecturaSerializer)

    def post(self, request):
        consultas.validar_query(request.query_params)
        egreso, creado = services.registrar_egreso(request.data, request.user, request.headers.get("Idempotency-Key"))
        return Response(EgresoRegistroSerializer(egreso).data, status=201 if creado else 200,
                        headers={"Idempotency-Replayed": "false" if creado else "true"})


class EgresoDetalleView(EgresosAPIView):
    def get(self, request, egreso_id):
        consultas.validar_query(request.query_params)
        return Response(EgresoLecturaSerializer(consultas.obtener(request.user, pk_url(egreso_id))).data)


class EgresoAnularView(EgresosAPIView):
    http_method_names = ["post", "options"]

    def post(self, request, egreso_id):
        consultas.validar_query(request.query_params)
        egreso = services.anular_egreso(pk_url(egreso_id), request.data, request.user)
        return Response(EgresoLecturaSerializer(egreso).data)


class EgresoHistorialView(EgresosAPIView):
    def get(self, request, egreso_id):
        return self.paginar(consultas.historial(request.user, pk_url(egreso_id), request.query_params), EgresoEventoSerializer)


class FlujoDineroResumenView(EgresosAPIView):
    def get(self, request):
        return Response(consultas.resumen(request.user, request.query_params))
