"""Una subconsulta por documento evita multiplicar pagos al unir otras tablas."""
from decimal import Decimal, localcontext

from django.db.models import Case, When, Value, CharField, DecimalField, ExpressionWrapper, F, OuterRef, Subquery, Sum
from django.db.models.functions import Coalesce

from .models import PagoDocumento
from .validaciones import hoy_santiago, LIMITE

ESTADOS_COBRANZA = ("PENDIENTE", "PARCIAL", "PAGADA", "VENCIDA")


def campo_importe():
    return DecimalField(max_digits=38, decimal_places=2)


def con_cobranza(queryset, *, hoy=None):
    # Fecha opcional para fachadas con un único corte civil por snapshot.
    # Los callers existentes conservan exactamente el reloj y fórmula originales.
    hoy = hoy_santiago() if hoy is None else hoy
    pagos = PagoDocumento.objects.filter(documento_id=OuterRef("pk"), activo=True).order_by().values("documento_id").annotate(total=Sum("monto", output_field=campo_importe())).values("total")
    return queryset.annotate(
        abonado_calculado=Coalesce(Subquery(pagos, output_field=campo_importe()), Value(Decimal("0.00")), output_field=campo_importe()),
    ).annotate(
        saldo_calculado=ExpressionWrapper(F("monto_total") - F("abonado_calculado"), output_field=campo_importe()),
    ).annotate(estado_cobranza_calculado=Case(
        When(saldo_calculado=0, then=Value("PAGADA")),
        When(fecha_vencimiento__lt=hoy, then=Value("VENCIDA")),
        When(abonado_calculado__gt=0, then=Value("PARCIAL")),
        default=Value("PENDIENTE"), output_field=CharField(),
    ))


def abonado_documento(documento):
    return documento.pagos.filter(activo=True).aggregate(total=Sum("monto", output_field=campo_importe()))["total"] or Decimal("0.00")


def saldo_documento(documento):
    abonado = abonado_documento(documento)
    with localcontext() as ctx:
        ctx.prec = 50
        saldo = documento.monto_total - abonado
    if not 0 <= abonado <= documento.monto_total or not 0 <= saldo <= LIMITE:
        from .services_documentos import ConflictoFinanciero
        raise ConflictoFinanciero("saldo_inconsistente", "El documento requiere revisión de integridad financiera.")
    return abonado, saldo


def resumen_documento(documento):
    if documento.estado != "VIGENTE":
        return None
    if not hasattr(documento, "abonado_calculado"):
        documento = con_cobranza(type(documento).objects.filter(pk=documento.pk)).get()
        if documento.estado != "VIGENTE":
            return None
    return {"moneda": "CLP", "abonado": format(documento.abonado_calculado, ".2f"),
            "saldo": format(documento.saldo_calculado, ".2f"), "estado": documento.estado_cobranza_calculado}
