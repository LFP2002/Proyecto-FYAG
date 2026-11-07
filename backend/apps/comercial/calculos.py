"""Cálculos netos CLP; el dominio recibe Decimal, nunca floats."""

from decimal import Decimal, ROUND_HALF_UP, localcontext
from typing import Iterable

from django.core.exceptions import ValidationError
from django.core.validators import DecimalValidator


CENTAVO = Decimal("0.01")
CANTIDAD_MAXIMA = Decimal("999999999.999")
PRECIO_MAXIMO = Decimal("9999999999999.99")


def normalizar_decimal(
    valor: Decimal, *, max_digits: int, decimal_places: int,
    minimo: Decimal, maximo: Decimal,
) -> Decimal:
    """Valida tipo, finitud y escala antes de completar decimales con ceros."""
    if not isinstance(valor, Decimal) or not valor.is_finite():
        raise ValidationError("Se requiere un Decimal finito.")
    DecimalValidator(max_digits, decimal_places)(valor)
    if not minimo <= valor <= maximo:
        raise ValidationError("Valor decimal fuera del rango permitido.")
    with localcontext() as contexto:
        contexto.prec = 50
        return valor.quantize(Decimal(1).scaleb(-decimal_places))


def normalizar_cantidad(valor: Decimal) -> Decimal:
    return normalizar_decimal(
        valor, max_digits=12, decimal_places=3,
        minimo=Decimal("0.001"), maximo=CANTIDAD_MAXIMA,
    )


def normalizar_precio(valor: Decimal) -> Decimal:
    return normalizar_decimal(
        valor, max_digits=15, decimal_places=2,
        minimo=Decimal("0.00"), maximo=PRECIO_MAXIMO,
    )


def calcular_subtotal(cantidad: Decimal, precio_unitario: Decimal) -> Decimal:
    cantidad = normalizar_cantidad(cantidad)
    precio_unitario = normalizar_precio(precio_unitario)
    with localcontext() as contexto:
        contexto.prec = 50
        return (cantidad * precio_unitario).quantize(
            CENTAVO, rounding=ROUND_HALF_UP
        )


def sumar_monto_neto(subtotales: Iterable[Decimal]) -> Decimal:
    """Suma líneas ya redondeadas, sin volver a redondear sus productos."""
    with localcontext() as contexto:
        contexto.prec = 50
        total = Decimal("0.00")
        for subtotal in subtotales:
            if (
                not isinstance(subtotal, Decimal)
                or not subtotal.is_finite()
                or subtotal < 0
            ):
                raise ValidationError("El subtotal debe ser Decimal finito.")
            # Un producto máximo de línea tiene hasta 22 dígitos enteros.
            DecimalValidator(24, 2)(subtotal)
            total += subtotal
        return total.quantize(CENTAVO)
