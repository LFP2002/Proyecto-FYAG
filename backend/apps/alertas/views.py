import logging
from uuid import uuid4

from django.db.models import Count
from django.utils import timezone
from rest_framework.exceptions import APIException, NotFound, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .catalogo import CATALOGO, ESTADOS
from .consultas import contexto
from .models import Alerta, EstadoReconciliacion
from .parsers import JSONEstrictoParser
from .permissions import PuedeLeerAlertas
from .serializers import (AlertaSerializer, AlertaEventoSerializer, AtenderSerializer,
                          FechaSantiago, FILTROS, filtrar, validar_query)
from . import services

logger = logging.getLogger(__name__)


class PaginaAlertas(PageNumberPagination):
    page_size = 25

    def paginate_queryset(self, queryset, request, view=None):
        try:
            return super().paginate_queryset(queryset, request, view)
        except NotFound:
            raise ValidationError({"page": "Página fuera de rango."}) from None


def representar(alertas, many=False):
    filas = list(alertas) if many else [alertas]
    return AlertaSerializer(filas if many else alertas, many=many, context={"recursos": contexto(filas)}).data


class AlertasBaseView(APIView):
    permission_classes = [IsAuthenticated, PuedeLeerAlertas]
    parser_classes = [JSONEstrictoParser]
    http_method_names = ["get", "head", "options"]

    def options(self, request, *args, **kwargs):
        if "pk" in kwargs:
            services.obtener(request.user, kwargs["pk"])
        return super().options(request, *args, **kwargs)

    def handle_exception(self, exc):
        if isinstance(exc, APIException):
            return super().handle_exception(exc)
        correlacion = str(uuid4())
        logger.error("alertas_error correlacion=%s clase=%s", correlacion, type(exc).__name__)
        return Response({"detail": "No fue posible procesar las alertas.", "correlacion": correlacion}, status=500, headers={"X-Correlation-ID": correlacion})

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response["Cache-Control"] = "private, no-store"
        return response


class ListadoAlertasView(AlertasBaseView):
    def get(self, request):
        filtros = validar_query(request.query_params, FILTROS)
        qs = filtrar(Alerta.objects.filter(rol_destinatario=request.user.rol), filtros)
        pagina = PaginaAlertas()
        filas = pagina.paginate_queryset(qs, request, view=self)
        return pagina.get_paginated_response(representar(filas, many=True))


class ResumenAlertasView(AlertasBaseView):
    def get(self, request):
        validar_query(request.query_params, set())
        tipos = {tipo: dict.fromkeys(ESTADOS, 0) for tipo, regla in CATALOGO.items() if request.user.rol in regla.roles}
        estados = dict.fromkeys(ESTADOS, 0)
        for row in Alerta.objects.filter(rol_destinatario=request.user.rol).order_by().values("tipo", "estado").annotate(total=Count("pk")):
            tipos[row["tipo"]][row["estado"]] = row["total"]
            estados[row["estado"]] += row["total"]
        ultima = EstadoReconciliacion.objects.filter(pk=1).values_list("ultima_correcta_en", flat=True).first()
        ahora = timezone.now()
        return Response({"generado_en": FechaSantiago().to_representation(ahora), "zona_horaria": "America/Santiago",
            "por_estado": estados, "activas": estados["PENDIENTE"] + estados["ATENDIDA"], "por_tipo": tipos,
            "sincronizacion": {"ultima_correcta_en": FechaSantiago().to_representation(ultima) if ultima else None,
                               "desactualizada": ultima is None or (ahora - ultima).total_seconds() > 180}})


class DetalleAlertaView(AlertasBaseView):
    def get(self, request, pk):
        validar_query(request.query_params, set())
        return Response(representar(services.obtener(request.user, pk)))


class HistorialAlertaView(AlertasBaseView):
    def get(self, request, pk):
        validar_query(request.query_params, {"page"})
        alerta = services.obtener(request.user, pk)
        pagina = PaginaAlertas()
        filas = pagina.paginate_queryset(alerta.eventos.all(), request, view=self)
        return pagina.get_paginated_response(AlertaEventoSerializer(filas, many=True).data)


class AtenderAlertaView(AlertasBaseView):
    http_method_names = ["post", "options"]

    def post(self, request, pk):
        validar_query(request.query_params, set())
        # Localizar antes de procesar JSON: una alerta ajena sigue siendo 404.
        services.obtener(request.user, pk)
        entrada = AtenderSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        alerta = services.atender(request.user, pk, entrada.validated_data["motivo"])
        return Response(representar(alerta))
