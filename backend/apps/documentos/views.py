import logging
from uuid import uuid4

from django.utils.cache import patch_vary_headers
from rest_framework.exceptions import APIException, ValidationError, UnsupportedMediaType
from rest_framework.negotiation import DefaultContentNegotiation
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.utils.urls import replace_query_param
from rest_framework.views import APIView

from . import services
from .parsers import JSONEstricto
from .permissions import PuedeOperarDocumentos
from .validaciones import entero_ascii, query, patch_documento

logger = logging.getLogger(__name__)


class JSONDocumental(DefaultContentNegotiation):
    def select_renderer(self, request, renderers, format_suffix=None):
        return renderers[0], renderers[0].media_type


class DocumentosView(APIView):
    permission_classes = [IsAuthenticated, PuedeOperarDocumentos]
    parser_classes = [JSONEstricto]
    renderer_classes = [JSONRenderer]
    content_negotiation_class = JSONDocumental
    http_method_names = ["get", "head", "options"]

    def initial(self, request, *args, **kwargs):
        self.correlacion = str(uuid4())
        super().initial(request, *args, **kwargs)

    def handle_exception(self, exc):
        if isinstance(exc, UnsupportedMediaType):
            exc = ValidationError({"body": "Use Content-Type application/json."})
        if not isinstance(exc, APIException):
            # No traceback/valores libres; errores de infraestructura saneados.
            from .exceptions import MongoNoDisponible
            logger.error("documentos_error correlacion=%s clase=%s", self.correlacion, type(exc).__name__)
            exc = MongoNoDisponible()
        if self.request.method == "PATCH":
            ident = self.kwargs.get("evidencia", "")
            ident = int(ident) if ident.isascii() and ident.isdecimal() and len(ident) <= 19 else None
            services.registrar(self.request.user if getattr(self.request.user, "is_authenticated", False) else None,
                ident, f"error_{exc.status_code}", None, self.correlacion)
        return super().handle_exception(exc)

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        response["X-Correlation-ID"] = self.correlacion
        patch_vary_headers(response, ["Authorization"])
        return response


class ListadoView(DocumentosView):
    def get(self, request):
        query(request.query_params, {"obra", "page"}, {"obra"})
        obra = entero_ascii(request.query_params["obra"], "obra")
        page = entero_ascii(request.query_params.get("page", "1"), "page")
        data = services.listar(request.user, obra, page, request.auth)
        url = request.build_absolute_uri()
        data["next"] = replace_query_param(url, "page", page + 1) if page * 25 < data["count"] else None
        data["previous"] = replace_query_param(url, "page", page - 1) if page > 1 else None
        return Response(data)


class DetalleView(DocumentosView):
    http_method_names = ["get", "head", "options", "patch"]

    def _id(self, request, evidencia):
        query(request.query_params, set())
        return entero_ascii(evidencia, "evidencia")

    def get(self, request, evidencia):
        return Response(services.detalle(request.user, self._id(request, evidencia), request.auth))

    def patch(self, request, evidencia):
        ident = self._id(request, evidencia)
        revision, cambios = patch_documento(request.data)
        return Response(services.editar(request.user, ident, revision, cambios, self.correlacion, request.auth))
