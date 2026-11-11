from decimal import Decimal

from django.db.models import Count, Q, Sum
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services_pagos
from .consultas_cobranzas import ESTADOS_COBRANZA, campo_importe
from .models import DocumentoCobro, PagoDocumento, FinanzasEvento
from .permissions import PermisoFinanciero
from .serializers_documentos import DocumentoLecturaSerializer, FinanzasEventoSerializer, FechaISO
from .serializers_pagos import PagoLecturaSerializer, PagoRegistroSerializer
from .services_documentos import ConflictoFinanciero
from .validaciones import LIMITE
from .views_documentos import FinanzasPaginacion, documentos_lectura, pk_url, query_estricta


def documento_lectura(value):
    pk = pk_url(value)
    if not DocumentoCobro.objects.filter(pk=pk).exists():
        raise NotFound("Documento no encontrado.")
    return pk


def filtrar_fechas(qs, params, field):
    dates = {}
    for suffix, lookup in [("desde", "gte"), ("hasta", "lte")]:
        key = f"{field}_{suffix}"
        if key in params:
            try:
                dates[suffix] = FechaISO().run_validation(params[key])
            except ValidationError as exc:
                raise ValidationError({key: exc.detail}) from None
            qs = qs.filter(**{f"{field}__{lookup}": dates[suffix]})
    if len(dates) == 2 and dates["desde"] > dates["hasta"]:
        raise ValidationError({field: "Rango de fechas invertido."})
    return qs


class FinanzasAPIView(APIView):
    permission_classes = [IsAuthenticated, PermisoFinanciero]
    parser_classes = [JSONParser]

    def paginar(self, qs, serializer):
        paginator = FinanzasPaginacion()
        page = paginator.paginate_queryset(qs, self.request, view=self)
        return paginator.get_paginated_response(serializer(page, many=True).data)


class PagosListaView(FinanzasAPIView):
    def get(self, request, documento_id):
        params = request.query_params
        query_estricta(params, {"activo", "medio", "fecha_pago_desde", "fecha_pago_hasta"})
        pk = documento_lectura(documento_id)
        qs = PagoDocumento.objects.filter(documento_id=pk).order_by("-registrado_en", "-id")
        if "activo" in params:
            if params["activo"] not in {"true", "false"}:
                raise ValidationError({"activo": "Use true o false."})
            qs = qs.filter(activo=params["activo"] == "true")
        if "medio" in params:
            if params["medio"] not in PagoDocumento.Medio.values:
                raise ValidationError({"medio": "Medio no permitido."})
            qs = qs.filter(medio=params["medio"])
        return self.paginar(filtrar_fechas(qs, params, "fecha_pago"), PagoLecturaSerializer)

    def post(self, request, documento_id):
        pago, creado = services_pagos.registrar_pago(pk_url(documento_id), request.data, request.user, request.headers.get("Idempotency-Key"))
        return Response(PagoRegistroSerializer(pago).data, status=201 if creado else 200,
                        headers={"Idempotency-Replayed": "false" if creado else "true"})


class PagoDetalleView(FinanzasAPIView):
    def get(self, request, documento_id, pago_id):
        query_estricta(request.query_params)
        pk = documento_lectura(documento_id)
        pago = PagoDocumento.objects.filter(documento_id=pk, pk=pk_url(pago_id)).first()
        if pago is None:
            raise NotFound("Pago no encontrado en el documento.")
        return Response(PagoLecturaSerializer(pago).data)


class PagoAnularView(FinanzasAPIView):
    def post(self, request, documento_id, pago_id):
        pago = services_pagos.anular_pago(pk_url(documento_id), pk_url(pago_id), request.data, request.user)
        return Response(PagoLecturaSerializer(pago).data)


class PagosHistorialView(FinanzasAPIView):
    def get(self, request, documento_id):
        query_estricta(request.query_params)
        pk = documento_lectura(documento_id)
        qs = FinanzasEvento.objects.filter(pago__documento_id=pk).order_by("creado_en", "id")
        return self.paginar(qs, FinanzasEventoSerializer)


def cartera_filtrada(params):
    query_estricta(params, {"estado", "cliente", "obra", "fecha_vencimiento_desde", "fecha_vencimiento_hasta", "fecha_emision_desde", "fecha_emision_hasta"})
    qs = documentos_lectura().filter(estado="VIGENTE")
    if "estado" in params:
        if params["estado"] not in ESTADOS_COBRANZA:
            raise ValidationError({"estado": "Estado de cobranza no permitido."})
        qs = qs.filter(estado_cobranza_calculado=params["estado"])
    for field, lookup in [("cliente", "obra__presupuesto__cliente_id"), ("obra", "obra_id")]:
        if field in params:
            qs = qs.filter(**{lookup: pk_url(params[field])})
    for field in ["fecha_vencimiento", "fecha_emision"]:
        qs = filtrar_fechas(qs, params, field)
    return qs.order_by("fecha_vencimiento", "id")


class CobranzasView(FinanzasAPIView):
    def get(self, request):
        return self.paginar(cartera_filtrada(request.query_params), DocumentoLecturaSerializer)


class CobranzasResumenView(FinanzasAPIView):
    def get(self, request):
        qs = cartera_filtrada(request.query_params)
        result = qs.aggregate(
            documentos=Count("pk"),
            pendiente=Count("pk", filter=Q(estado_cobranza_calculado="PENDIENTE")),
            parcial=Count("pk", filter=Q(estado_cobranza_calculado="PARCIAL")),
            pagada=Count("pk", filter=Q(estado_cobranza_calculado="PAGADA")),
            vencida=Count("pk", filter=Q(estado_cobranza_calculado="VENCIDA")),
            monto_documentado_total=Sum("monto_total", output_field=campo_importe()),
            abonado_total=Sum("abonado_calculado", output_field=campo_importe()),
            saldo_total=Sum("saldo_calculado", output_field=campo_importe()),
            saldo_vencido=Sum("saldo_calculado", filter=Q(estado_cobranza_calculado="VENCIDA"), output_field=campo_importe()),
        )
        totals = {}
        for key in ["monto_documentado_total", "abonado_total", "saldo_total", "saldo_vencido"]:
            value = result.pop(key) or Decimal("0.00")
            if not value.is_finite() or not 0 <= value <= LIMITE:
                raise ConflictoFinanciero("importe_fuera_rango", "El agregado financiero excede el rango admitido o requiere revisión.")
            totals[key] = format(value, ".2f")
        return Response({"moneda": "CLP", "documentos": result.pop("documentos"),
                         "conteos": {key.upper(): value for key, value in result.items()}, **totals})
