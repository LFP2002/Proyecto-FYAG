"""Importes documentales CLP: sin floats, redondeos de entrada ni IVA supuesto."""
from decimal import Decimal, localcontext
from zoneinfo import ZoneInfo

from django.core.exceptions import ValidationError
from django.core.validators import DecimalValidator
from django.utils import timezone

LIMITE = Decimal("999999999999999999999999999999999999.99")


def hoy_santiago():
    return timezone.localdate(timezone=ZoneInfo("America/Santiago"))


def importe(value):
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValidationError("Se requiere Decimal finito.")
    DecimalValidator(38, 2)(value)
    if not Decimal("0") <= value <= LIMITE:
        raise ValidationError("Importe fuera de rango.")
    return value


def validar_montos(neto, impuesto, total, tipo):
    for value in (neto, impuesto, total):
        importe(value)
    with localcontext() as ctx:
        ctx.prec = 50
        suma = neto + impuesto
    if suma > LIMITE or total != suma or total <= 0:
        raise ValidationError({"monto_total": "Debe ser positivo, estar en rango e igualar neto más impuesto."})
    if ((tipo == "FACTURA_EXENTA" and impuesto != 0)
        or (tipo == "FACTURA_AFECTA" and impuesto <= 0)):
        raise ValidationError({"monto_impuesto": "Impuesto incompatible con el tipo documental."})
