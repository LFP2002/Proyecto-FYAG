import logging
from uuid import uuid4

from rest_framework.exceptions import APIException
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .permissions import PuedeLeerAuditoria
from .serializers import EventoPublicoSerializer, FechaSantiago
from .services import consultar

logger = logging.getLogger(__name__)


class EventosAuditoriaView(APIView):
    permission_classes = [IsAuthenticated, PuedeLeerAuditoria]
    http_method_names = ["get", "head", "options"]

    def get(self, request):
        resultado = consultar(request.user, request.query_params)
        resultado["results"] = EventoPublicoSerializer(resultado["results"], many=True).data
        resultado["fecha_corte"] = FechaSantiago().to_representation(resultado["fecha_corte"])
        return Response(resultado)

    def handle_exception(self, exc):
        if isinstance(exc, APIException):
            return super().handle_exception(exc)
        correlacion = str(uuid4())
        # No loggear str(exc), traceback, request, cursor ni headers: los errores
        # SQL pueden contener filas/snapshots con datos privados.
        logger.error("auditoria_error correlacion=%s clase=%s", correlacion, type(exc).__name__)
        return Response({"detail": "No fue posible consultar la auditoría.", "correlacion": correlacion}, status=500, headers={"X-Correlation-ID": correlacion})

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        return response
