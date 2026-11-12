"""Consultas puras. Ningún servicio mutador ni dependencia de Alertas/Auditoría."""
from decimal import Decimal, localcontext
from itertools import islice
import logging
from uuid import uuid4

from django.db.models import Count, F, Prefetch, Q, Sum
from django.db.models.functions import TruncMonth
from rest_framework.exceptions import APIException

from apps.comercial.calculos import calcular_subtotal, sumar_monto_neto
from apps.comercial.models import Presupuesto, PresupuestoItem
from apps.obras.models import Obra
from apps.finanzas.consultas_cobranzas import campo_importe, con_cobranza
from apps.finanzas.models import DocumentoCobro
from apps.finanzas.validaciones import LIMITE
from .filtros import ZONA, desplazar_mes, inicio_civil, rango

logger = logging.getLogger(__name__)
ESTADOS = ("PLANIFICADA", "EN_PROCESO", "SUSPENDIDA", "FINALIZADA", "CANCELADA")
LOTE = 500


class OrigenInconsistente(APIException):
    status_code = 409

    def __init__(self, code, detail):
        correlacion = str(uuid4())
        logger.warning("dashboard_origen_inconsistente correlacion=%s code=%s", correlacion, code)
        super().__init__({"code": code, "detail": detail})


def finalizadas(desde, hasta, corte):
    inicio, fin = rango(desde, hasta)
    return Obra.objects.filter(estado="FINALIZADA", finalizado_en__gte=inicio, finalizado_en__lt=fin, finalizado_en__lte=corte)


def rentabilidad(qs):
    """PK/importe de cierres en lotes; líneas iteradas sin cargar todo el histórico.

    OneToOne Obra/Presupuesto/Cierre impide multiplicar filas. No se unen ítems
    con cierres: el cálculo oficial redondea cada línea en Python.
    """
    filas = qs.order_by("pk").values_list("presupuesto_id", "cierre_costos__costo_total").iterator(chunk_size=LOTE)
    cantidad = 0
    presupuesto = costo = Decimal("0.00")
    # Incluso sumas de importes de 38 dígitos y cardinalidades BigInt caben aquí.
    with localcontext() as ctx:
        ctx.prec = 80
        while lote := list(islice(filas, LOTE)):
            if any(importe is None for _, importe in lote):
                raise OrigenInconsistente("cierre_costos_inconsistente", "Existen Obras finalizadas sin cierre real de costos en el periodo.")
            cantidad += len(lote)
            costo += sum((importe for _, importe in lote), Decimal("0.00"))
            items = PresupuestoItem.objects.filter(presupuesto_id__in=[pk for pk, _ in lote]).order_by("pk").values_list("cantidad", "precio_unitario").iterator(chunk_size=LOTE)
            presupuesto += sumar_monto_neto(calcular_subtotal(c, p) for c, p in items)
        margen = presupuesto - costo
    return {"obras_con_cierre": cantidad, "presupuesto_neto": format(presupuesto, ".2f"),
            "costo_real_neto": format(costo, ".2f"), "margen_real_neto": format(margen, ".2f")}


def cartera_actual():
    # Invocar al principio del resumen para fijar la fecha civil oficial en la
    # expresión de cobranza antes del procesamiento de líneas históricas.
    return con_cobranza(DocumentoCobro.objects.filter(estado="VIGENTE"))


def cobranza(qs):
    result = qs.aggregate(
        documentos_vigentes=Count("pk"),
        invalidos=Count("pk", filter=Q(abonado_calculado__lt=0) | Q(abonado_calculado__gt=F("monto_total")) | Q(saldo_calculado__lt=0)),
        monto_documentado_bruto=Sum("monto_total", output_field=campo_importe()),
        abonado=Sum("abonado_calculado", output_field=campo_importe()),
        saldo=Sum("saldo_calculado", output_field=campo_importe()),
        saldo_vencido=Sum("saldo_calculado", filter=Q(estado_cobranza_calculado="VENCIDA"), output_field=campo_importe()),
    )
    if result.pop("invalidos"):
        raise OrigenInconsistente("saldo_inconsistente", "La cartera requiere revisión de integridad financiera.")
    for campo in ("monto_documentado_bruto", "abonado", "saldo", "saldo_vencido"):
        result[campo] = result[campo] if result[campo] is not None else Decimal("0.00")
        if not result[campo].is_finite() or not 0 <= result[campo] <= LIMITE:
            raise OrigenInconsistente("importe_fuera_rango", "El agregado financiero excede el rango admitido o requiere revisión.")
    with localcontext() as ctx:
        ctx.prec = 80
        if result["monto_documentado_bruto"] != result["abonado"] + result["saldo"]:
            raise OrigenInconsistente("saldo_inconsistente", "La cartera requiere revisión de integridad financiera.")
    return {key: format(value, ".2f") if isinstance(value, Decimal) else value for key, value in result.items()}


def operacion_actual():
    estados = dict.fromkeys(ESTADOS, 0)
    for row in Obra.objects.order_by().values("estado").annotate(total=Count("pk")):
        estados[row["estado"]] = row["total"]
    return {"obras_por_estado_actual": estados,
            "presupuestos_pendientes_gerencia_actual": Presupuesto.objects.filter(estado="PENDIENTE_GERENCIA").count()}


def serie(meses, corte):
    hoy = corte.astimezone(ZONA).date()
    inicio = desplazar_mes(hoy, 1 - meses)
    qs = Obra.objects.filter(estado="FINALIZADA", finalizado_en__gte=inicio_civil(inicio), finalizado_en__lte=corte)
    conteos = {row["mes"].strftime("%Y-%m"): row["cantidad"] for row in qs.order_by().annotate(mes=TruncMonth("finalizado_en", tzinfo=ZONA)).values("mes").annotate(cantidad=Count("pk"))}
    puntos = []
    for n in range(meses):
        mes = desplazar_mes(inicio, n).strftime("%Y-%m")
        puntos.append({"mes": mes, "cantidad": conteos.get(mes, 0)})
    return {"metrica": "OBRAS_FINALIZADAS", "zona_horaria": "America/Santiago", "puntos": puntos}


def obras_activas():
    return Obra.objects.filter(estado="EN_PROCESO").select_related(
        "presupuesto__cliente", "categoria_servicio", "tecnico_responsable",
    ).only("id", "creado_en", "estado", "fecha_programada", "presupuesto_id", "presupuesto__cliente_id",
           "presupuesto__cliente__nombre_legal", "categoria_servicio_id", "categoria_servicio__nombre",
           "tecnico_responsable_id", "tecnico_responsable__first_name", "tecnico_responsable__last_name", "tecnico_responsable__username"
    ).prefetch_related(Prefetch("presupuesto__items", queryset=PresupuestoItem.objects.only("presupuesto_id", "cantidad", "precio_unitario"))).order_by("-creado_en", "-id")
