from uuid import uuid4

from django.http import FileResponse
from django.utils.cache import patch_vary_headers
from rest_framework.exceptions import APIException
from rest_framework.negotiation import DefaultContentNegotiation
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.utils.urls import replace_query_param
from rest_framework.views import APIView

from apps.documentos.parsers import JSONEstricto
from apps.documentos.validaciones import entero_ascii, query
from . import almacen, services
from .exceptions import AlmacenNoDisponible
from .parsers import MultipartAdjunto
from .permissions import PuedeOperarAdjuntos
from .validaciones import idempotencia


class NegociacionAdjuntos(DefaultContentNegotiation):
    def select_renderer(self, request, renderers, format_suffix=None):
        return renderers[0], renderers[0].media_type


class BaseAdjuntos(APIView):
    permission_classes = [IsAuthenticated, PuedeOperarAdjuntos]
    renderer_classes = [JSONRenderer]
    content_negotiation_class = NegociacionAdjuntos
    parser_classes = [JSONEstricto]
    http_method_names = ["get", "head", "options"]

    def initial(self, request, *args, **kwargs):
        self.correlacion = str(uuid4())
        super().initial(request, *args, **kwargs)

    def handle_exception(self, exc):
        if not isinstance(exc, APIException):
            # No eco ni traceback de PDF, scanner, SQL o almacenamiento privado.
            exc = AlmacenNoDisponible()
        actor = self.request.user if getattr(self.request.user, "is_authenticated", False) else None
        ident = self.kwargs.get("id", "") if not self.kwargs.get("tipo") else ""
        ident = int(ident) if ident.isascii() and ident.isdecimal() and len(ident) <= 19 else None
        services.registrar(actor, ident, "operacion_adjunto", f"error_{exc.status_code}", self.correlacion)
        return super().handle_exception(exc)

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        response["X-Correlation-ID"] = self.correlacion
        patch_vary_headers(response, ["Authorization"])
        return response


class DestinoView(BaseAdjuntos):
    http_method_names = ["get", "head", "options", "post"]
    parser_classes = [MultipartAdjunto]

    def get(self, request, tipo, id):
        query(request.query_params, {"page"})
        page = entero_ascii(request.query_params.get("page", "1"), "page")
        data = services.listado(request.user, tipo, entero_ascii(id, "id"), page, request.auth)
        url = request.build_absolute_uri()
        data["next"] = replace_query_param(url, "page", page+1) if page*25 < data["count"] else None
        data["previous"] = replace_query_param(url, "page", page-1) if page > 1 else None
        return Response(data)

    def post(self, request, tipo, id):
        query(request.query_params, set())
        destino = entero_ascii(id, "id")
        key = idempotencia(request.headers.get("Idempotency-Key"))
        services.preflight(request.user, tipo, destino, key, request.auth)
        adjunto, nuevo = services.subir(request.user, tipo, destino, key, request.data, self.correlacion, request.auth)
        return Response(services.representar(adjunto), status=201 if nuevo else 200)


class DetalleView(BaseAdjuntos):
    def get(self, request, id):
        query(request.query_params, set())
        _, adjunto = services.autorizado(request.user, entero_ascii(id, "id"), request.auth)
        return Response(services.representar(adjunto))


class DescargarView(BaseAdjuntos):
    def get(self, request, id):
        query(request.query_params, set())
        actor, adjunto = services.autorizado(request.user, entero_ascii(id, "id"), request.auth)
        archivo = almacen.copia_verificada(adjunto)
        try:
            response = FileResponse(archivo, as_attachment=True, filename=adjunto.nombre_visible, content_type=adjunto.mime)
            response["Content-Security-Policy"] = "default-src 'none'; sandbox"
            services.registrar(actor, adjunto.pk, "descarga_adjunto", "archivo_verificado_no_confirma_guardado", self.correlacion)
            return response
        except BaseException:
            archivo.close()
            raise


class AnotacionesView(BaseAdjuntos):
    http_method_names = ["get", "head", "options", "patch"]

    def get(self, request, id):
        from . import metadata
        query(request.query_params, set())
        actor, adjunto = services.autorizado(request.user, entero_ascii(id, "id"), request.auth)
        return Response(metadata.leer(adjunto))

    def patch(self, request, id):
        from . import metadata
        query(request.query_params, set())
        actor, adjunto = services.autorizado(request.user, entero_ascii(id, "id"), request.auth, editar=True)
        return Response(metadata.editar(adjunto, actor, request.data, self.correlacion))
