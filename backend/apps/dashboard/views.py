import logging
from uuid import uuid4

from django.utils.cache import patch_vary_headers
from rest_framework.exceptions import APIException, NotFound, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import consultas, services
from .consistencia import lectura_estable
from .filtros import entero, query_estricta
from .permissions import PuedeLeerDashboard, revalidar
from .serializers import ObraActivaSerializer, ResumenSerializer, SerieSerializer

logger = logging.getLogger(__name__)


class PaginaDashboard(PageNumberPagination):
    page_size = 25

    def paginate_queryset(self, queryset, request, view=None):
        try:
            return super().paginate_queryset(queryset, request, view)
        except NotFound:
            raise ValidationError({"page": "Página fuera de rango."}) from None


class DashboardBaseView(APIView):
    permission_classes = [IsAuthenticated, PuedeLeerDashboard]
    http_method_names = ["get", "head", "options"]

    def handle_exception(self, exc):
        if isinstance(exc, APIException):
            return super().handle_exception(exc)
        correlacion = str(uuid4())
        logger.error("dashboard_error correlacion=%s clase=%s", correlacion, type(exc).__name__)
        return Response({"detail": "No fue posible consultar el dashboard.", "correlacion": correlacion}, status=500, headers={"X-Correlation-ID": correlacion})

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        patch_vary_headers(response, ["Authorization"])
        return response


class ResumenDashboardView(DashboardBaseView):
    def get(self, request):
        return Response(ResumenSerializer(services.resumen(request.user, request.query_params)).data)


class SerieObrasView(DashboardBaseView):
    def get(self, request):
        return Response(SerieSerializer(services.serie_obras(request.user, request.query_params)).data)


class ObrasActivasView(DashboardBaseView):
    def get(self, request):
        query_estricta(request.query_params, {"page"})
        entero(request.query_params.get("page", "1"), "page")
        with lectura_estable():
            revalidar(request.user)
            pagina = PaginaDashboard()
            filas = pagina.paginate_queryset(consultas.obras_activas(), request, view=self)
            # Evaluar relaciones/ítems dentro del mismo snapshot, no de forma lazy.
            return pagina.get_paginated_response(ObraActivaSerializer(filas, many=True).data)
