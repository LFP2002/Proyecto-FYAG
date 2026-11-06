from django.core.exceptions import ValidationError
from django.test import SimpleTestCase

from apps.comercial.validators import (
    calcular_dv_rut,
    normalizar_rut,
    validar_rut,
)


class NormalizarRutTests(SimpleTestCase):
    def test_formatos_aceptados(self):
        for value in (
            "12.345.678-5", "12345678-5", "123456785",
        ):
            with self.subTest(value=value):
                self.assertEqual(normalizar_rut(value), "12345678-5")

    def test_rechaza_puntos_sin_guion(self):
        for value in ("12.345.6785", "1.2345"):
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):
                    normalizar_rut(value)

    def test_espacios_exteriores(self):
        self.assertEqual(normalizar_rut(" \t12.345.678-5\n"), "12345678-5")

    def test_ceros_iniciales_producen_el_mismo_rut_canonico(self):
        canonico = normalizar_rut("637985-4")
        self.assertEqual(canonico, "637985-4")
        for value in ("00637985-4", "00.637.985-4", "006379854"):
            with self.subTest(value=value):
                self.assertEqual(normalizar_rut(value), canonico)

    def test_elimina_relleno_de_ceros_iniciales(self):
        self.assertEqual(normalizar_rut("00012345678-5"), "12345678-5")

    def test_dv_k_se_normaliza_a_mayuscula(self):
        for value in ("1.000.005-K", "1.000.005-k", "1000005k"):
            with self.subTest(value=value):
                self.assertEqual(normalizar_rut(value), "1000005-K")

    def test_rechaza_valores_no_string(self):
        for value in (None, 123456785, True, [], b"12345678-5"):
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):
                    normalizar_rut(value)

    def test_rechaza_cuerpo_o_dv_vacio(self):
        for value in ("", "   ", "-5", "12345678-", "5", "-"):
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):
                    normalizar_rut(value)

    def test_rechaza_caracteres_invalidos(self):
        for value in (
            "ABC", "12.345.678-X", "12A45678-5", "12345678-?",
            "12345678-55", "+12345678-5", "12 345678-5", "１２３４５６７８-5",
            "12345678-٥", "12345678–5", "12345678-5!",
        ):
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):
                    normalizar_rut(value)

    def test_rechaza_formatos_ambiguos(self):
        for value in (
            "12-345-678-5", "12345678--5", "12..345.678-5",
            ".12345678-5", "12345678.-5", "1234.5678-5", "12.345.678-.5",
        ):
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):
                    normalizar_rut(value)

    def test_rechaza_cuerpo_solo_ceros(self):
        for value in ("00000000-0", "0-0", "00.000.000-0", "000000000"):
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):
                    normalizar_rut(value)

    def test_normalizar_no_verifica_coincidencia_del_dv(self):
        self.assertEqual(normalizar_rut("12.345.678-9"), "12345678-9")


class CalcularDvRutTests(SimpleTestCase):
    def test_cuerpos_con_dv_numerico(self):
        for cuerpo, esperado in (("12345678", "5"), ("1", "9"), ("2", "7")):
            with self.subTest(cuerpo=cuerpo):
                self.assertEqual(calcular_dv_rut(cuerpo), esperado)

    def test_dv_k(self):
        self.assertEqual(calcular_dv_rut("1000005"), "K")

    def test_dv_cero(self):
        self.assertEqual(calcular_dv_rut("14"), "0")

    def test_reinicio_de_factores(self):
        self.assertEqual(calcular_dv_rut("11111111"), "1")

    def test_rechaza_cuerpos_invalidos(self):
        for cuerpo in (
            None, 123, "", " ", "0000", "ABC", "12.345", "12-3", "１２３",
        ):
            with self.subTest(cuerpo=cuerpo):
                with self.assertRaises(ValidationError):
                    calcular_dv_rut(cuerpo)


class ValidarRutTests(SimpleTestCase):
    def test_ceros_iniciales_no_alteran_validacion_del_dv(self):
        for original, relleno, esperado in (
            ("637985-0", "00637985-0", "637985-0"),
            ("12345678-5", "00012345678-5", "12345678-5"),
            ("1000005-K", "0001000005-k", "1000005-K"),
        ):
            with self.subTest(relleno=relleno):
                self.assertEqual(validar_rut(original), esperado)
                self.assertEqual(validar_rut(relleno), esperado)

    def test_relleno_no_permite_dv_incorrecto(self):
        for value in ("637985-4", "00637985-4", "00637985-9"):
            with self.subTest(value=value):
                with self.assertRaises(ValidationError):
                    validar_rut(value)

    def test_cuerpo_solo_ceros_sigue_siendo_invalido(self):
        with self.assertRaises(ValidationError):
            validar_rut("00000000-0")

    def test_rut_valido_devuelve_string_canonico(self):
        self.assertEqual(validar_rut("12.345.678-5"), "12345678-5")

    def test_rut_con_k_valido(self):
        for value in ("1.000.005-K", "1.000.005-k"):
            with self.subTest(value=value):
                self.assertEqual(validar_rut(value), "1000005-K")

    def test_dv_incorrecto(self):
        with self.assertRaises(ValidationError):
            validar_rut("12.345.678-9")

    def test_propaga_error_de_formato(self):
        with self.assertRaises(ValidationError):
            validar_rut("12-345-678-5")
