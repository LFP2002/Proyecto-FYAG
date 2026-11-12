import logging
from uuid import uuid4

from django.db import OperationalError
from django.http import FileResponse, StreamingHttpResponse
from django.utils.cache import patch_vary_headers
from rest_framework.exceptions import APIException
from rest_framework.permissions import IsAuthenticated
from rest_framework.negotiation import DefaultContentNegotiation
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.utils.urls import replace_query_param
from rest_framework.views import APIView

from . import services
from .permissions import PuedeLeerReportes
from .throttles import ExportacionThrottle
from .consistencia import TiempoAgotado

logger = logging.getLogger(__name__)
MIMES = {"csv": "text/csv; charset=utf-8", "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "pdf": "application/pdf"}


class NegociacionReportes(DefaultContentNegotiation):
    def select_renderer(self, request, renderers, format_suffix=None):
        # La query formato gobierna el FileResponse. Los demás endpoints y
        # errores son JSON. No admitir el atajo DRF ?format= que eludiría la
        # whitelist (404 de renderer en lugar del 400 contractual).
        return renderers[0], renderers[0].media_type


class ReportesBaseView(APIView):
    renderer_classes = [JSONRenderer]
    content_negotiation_class = NegociacionReportes
    permission_classes = [IsAuthenticated, PuedeLeerReportes]
    http_method_names = ["get", "head", "options"]

    def initial(self, request, *args, **kwargs):
        self.correlacion = str(uuid4())
        super().initial(request, *args, **kwargs)

    def handle_exception(self, exc):
        if isinstance(exc, OperationalError) and getattr(exc.__cause__, "sqlstate", None) == "57014":
            exc = TiempoAgotado()
        if isinstance(exc, APIException):
            if exc.status_code >= 500 or exc.status_code == 409:
                logger.warning("reportes_error correlacion=%s clase=%s", self.correlacion, type(exc).__name__)
            response = super().handle_exception(exc)
            if exc.status_code >= 500:
                response.data["correlacion"] = self.correlacion
                response["X-Correlation-ID"] = self.correlacion
            return response
        logger.error("reportes_error correlacion=%s clase=%s", self.correlacion, type(exc).__name__)
        return Response({"detail": "No fue posible generar el reporte.", "correlacion": self.correlacion}, status=500, headers={"X-Correlation-ID": self.correlacion})

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        response["Content-Security-Policy"] = "default-src 'none'; sandbox"
        patch_vary_headers(response, ["Authorization"])
        return response


class CatalogoView(ReportesBaseView):
    def get(self, request):
        return Response(services.catalogo_visible(request.user, request.query_params))


class ReporteListadoView(ReportesBaseView):
    def get(self, request, tipo):
        data, page = services.listar(request.user, tipo, request.query_params)
        data.pop("filtros")
        url = request.build_absolute_uri()
        data["next"] = replace_query_param(url, "page", page + 1) if page * 25 < data["count"] else None
        data["previous"] = replace_query_param(url, "page", page - 1) if page > 1 else None
        return Response(data)


class ExportarView(ReportesBaseView):
    def get_throttles(self):
        return [ExportacionThrottle()] if self.request.method in ("GET", "HEAD") else []

    def get(self, request, tipo):
        return self._descarga(request, tipo, False)

    def head(self, request, tipo):
        return self._descarga(request, tipo, True)

    def _descarga(self, request, tipo, head):
        archivo, nombre, _ = services.exportar(request.user, tipo, request.query_params, self.correlacion, head=head)
        try:
            if head:
                response = StreamingHttpResponse(iter(()), content_type=MIMES[request.query_params["formato"]])
                response["Content-Disposition"] = f'attachment; filename="{nombre}"'
            else:
                response = FileResponse(archivo, as_attachment=True, filename=nombre, content_type=MIMES[request.query_params["formato"]])
            return response
        except Exception:
            if archivo is not None:
                archivo.close()
            raise
