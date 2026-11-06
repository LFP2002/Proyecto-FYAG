from decimal import Decimal, ROUND_DOWN, getcontext, localcontext

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from apps.comercial.calculos import (
    CANTIDAD_MAXIMA,
    PRECIO_MAXIMO,
    calcular_subtotal,
    normalizar_cantidad,
    normalizar_precio,
    sumar_monto_neto,
)


class PresupuestoDecimalTests(SimpleTestCase):
    def test_ejemplo_spec_half_up(self):
        self.assertEqual(
            calcular_subtotal(Decimal("2.500"), Decimal("100.25")),
            Decimal("250.63"),
        )

    def test_producto_redondea_a_cero(self):
        self.assertEqual(
            calcular_subtotal(Decimal("0.001"), Decimal("0.01")),
            Decimal("0.00"),
        )

    def test_suma_despues_de_redondear_lineas(self):
        subtotal = calcular_subtotal(Decimal("0.500"), Decimal("0.01"))
        self.assertEqual(subtotal, Decimal("0.01"))
        self.assertEqual(
            sumar_monto_neto([subtotal, subtotal]), Decimal("0.02")
        )

    def test_suma_vacia(self):
        self.assertEqual(str(sumar_monto_neto([])), "0.00")

    def test_limites_maximos(self):
        self.assertEqual(normalizar_cantidad(CANTIDAD_MAXIMA), CANTIDAD_MAXIMA)
        self.assertEqual(normalizar_precio(PRECIO_MAXIMO), PRECIO_MAXIMO)
        self.assertEqual(
            calcular_subtotal(CANTIDAD_MAXIMA, PRECIO_MAXIMO),
            Decimal("9999999999989990000000.00"),
        )

    def test_completa_escala_sin_redondear(self):
        self.assertEqual(str(normalizar_cantidad(Decimal("2"))), "2.000")
        self.assertEqual(str(normalizar_precio(Decimal("2"))), "2.00")

    def test_exceso_escala_rechazado(self):
        for funcion, valor in (
            (normalizar_cantidad, "1.0000"),
            (normalizar_cantidad, "0.0001"),
            (normalizar_precio, "1.001"),
            (normalizar_precio, "1.000"),
        ):
            with self.subTest(funcion=funcion.__name__, valor=valor):
                with self.assertRaises(ValidationError):
                    funcion(Decimal(valor))

    def test_exceso_precision_rechazado(self):
        for funcion, valor in (
            (normalizar_cantidad, "1000000000"),
            (normalizar_precio, "10000000000000"),
        ):
            with self.subTest(valor=valor):
                with self.assertRaises(ValidationError):
                    funcion(Decimal(valor))

    def test_negativos_rechazados(self):
        for funcion in (normalizar_cantidad, normalizar_precio):
            with self.subTest(funcion=funcion.__name__):
                with self.assertRaises(ValidationError):
                    funcion(Decimal("-1"))

    def test_cantidad_cero_rechazada(self):
        with self.assertRaises(ValidationError):
            normalizar_cantidad(Decimal("0"))

    def test_precio_cero_permitido(self):
        self.assertEqual(
            calcular_subtotal(Decimal("2"), Decimal("0")), Decimal("0.00")
        )

    def test_tipos_no_decimal_rechazados(self):
        for valor in (1.5, True, False, 1, "1.5", "ABC", "1,5", None):
            for funcion in (normalizar_cantidad, normalizar_precio):
                with self.subTest(valor=valor, funcion=funcion.__name__):
                    with self.assertRaises(ValidationError):
                        funcion(valor)

    def test_no_finitos_rechazados(self):
        for valor in ("NaN", "sNaN", "Infinity", "-Infinity"):
            for funcion in (normalizar_cantidad, normalizar_precio):
                with self.subTest(valor=valor, funcion=funcion.__name__):
                    with self.assertRaises(ValidationError):
                        funcion(Decimal(valor))

    def test_sumar_rechaza_subtotal_invalido_o_sin_redondear(self):
        for valor in (
            True, 0.1, "0.10", Decimal("NaN"), Decimal("Infinity"),
            Decimal("-1"), Decimal("0.005"),
        ):
            with self.subTest(valor=valor):
                with self.assertRaises(ValidationError):
                    sumar_monto_neto([valor])

    def test_contexto_global_no_cambia(self):
        with localcontext() as contexto:
            contexto.prec = 6
            contexto.rounding = ROUND_DOWN
            antes = contexto.copy()
            subtotal = calcular_subtotal(CANTIDAD_MAXIMA, PRECIO_MAXIMO)
            self.assertEqual(
                sumar_monto_neto([subtotal, subtotal]),
                Decimal("19999999999979980000000.00"),
            )
            self.assertEqual(
                calcular_subtotal(Decimal("2.5"), Decimal("100.25")),
                Decimal("250.63"),
            )
            self.assertEqual(getcontext().prec, antes.prec)
            self.assertEqual(getcontext().rounding, antes.rounding)
            self.assertEqual(getcontext().flags, antes.flags)
            self.assertEqual(getcontext().traps, antes.traps)
