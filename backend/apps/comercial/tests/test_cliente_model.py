from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.comercial.models import Cliente


def datos_cliente(**cambios):
    datos = {
        "tipo_cliente": "EMPRESA",
        "tipo_identificacion": "SIN_IDENTIFICACION",
        "nombre_legal": "Cliente de prueba",
        "correo": "contacto@example.com",
    }
    datos.update(cambios)
    return datos


def datos_extranjero(**cambios):
    datos = datos_cliente(
        tipo_identificacion="DOCUMENTO_EXTRANJERO",
        numero_identificacion="12345678",
        pais_identificacion="AR",
        tipo_documento_extranjero="DNI",
    )
    datos.update(cambios)
    return datos


class ClienteValidacionTests(TestCase):
    def assert_invalido(self, campo, **datos):
        with self.assertRaises(ValidationError) as error:
            Cliente(**datos).full_clean()
        self.assertIn(campo, error.exception.message_dict)

    def test_creacion_rut_canonico(self):
        cliente = Cliente.objects.create(**datos_cliente(
            tipo_identificacion="RUT",
            numero_identificacion="12.345.678-5",
        ))
        cliente.refresh_from_db()
        self.assertEqual(cliente.numero_identificacion, "12345678-5")
        self.assertTrue(cliente.activo)
        self.assertIsNotNone(cliente.pk)
        self.assertIsNotNone(cliente.creado_en)
        self.assertIsNotNone(cliente.actualizado_en)

    def test_normalizacion_comercial(self):
        cliente = Cliente.objects.create(**datos_cliente(
            nombre_legal="  Empresa Mixta  ",
            nombre_contacto="  Ana Pérez  ",
            correo="  CONTACTO@EXAMPLE.COM  ",
            telefono="  +54 11 1234 5678  ",
        ))
        cliente.refresh_from_db()
        self.assertEqual(cliente.nombre_legal, "Empresa Mixta")
        self.assertEqual(cliente.nombre_contacto, "Ana Pérez")
        self.assertEqual(cliente.correo, "contacto@example.com")
        self.assertEqual(cliente.telefono, "+54 11 1234 5678")

    def test_documento_extranjero_normalizado_sin_modulo_11(self):
        cliente = Cliente.objects.create(**datos_extranjero(
            pais_identificacion=" ar ",
            tipo_documento_extranjero=" DNI ",
            numero_identificacion=" 12345678 ",
        ))
        cliente.refresh_from_db()
        self.assertEqual(cliente.pais_identificacion, "AR")
        self.assertEqual(cliente.tipo_documento_extranjero, "DNI")
        self.assertEqual(cliente.numero_identificacion, "12345678")

    def test_rut_invalido_en_full_clean(self):
        self.assert_invalido("numero_identificacion", **datos_cliente(
            tipo_identificacion="RUT", numero_identificacion="12345678-9",
        ))

    def test_tipo_documental_se_persiste_en_mayusculas(self):
        for entrada, esperado in (
            (" dni ", "DNI"), (" pasaporte ", "PASAPORTE"),
        ):
            with self.subTest(entrada=entrada):
                cliente = Cliente.objects.create(**datos_extranjero(
                    tipo_documento_extranjero=entrada,
                ))
                cliente.refresh_from_db()
                self.assertEqual(cliente.tipo_documento_extranjero, esperado)

    def test_numero_extranjero_conserva_case(self):
        for numero in (" AbC123 ", " ABC123 "):
            with self.subTest(numero=numero):
                cliente = Cliente.objects.create(**datos_extranjero(
                    numero_identificacion=numero,
                ))
                cliente.refresh_from_db()
                self.assertEqual(cliente.numero_identificacion, numero.strip())
        self.assertEqual(Cliente.objects.count(), 2)

    def test_save_rechaza_rut_invalido(self):
        with self.assertRaises(ValidationError):
            Cliente.objects.create(**datos_cliente(
                tipo_identificacion="RUT", numero_identificacion="12345678-9",
            ))

    def test_empresa_sin_identificacion(self):
        cliente = Cliente.objects.create(**datos_cliente())
        self.assertIsNone(cliente.numero_identificacion)
        self.assertIsNone(cliente.pais_identificacion)
        self.assertIsNone(cliente.tipo_documento_extranjero)

    def test_persona_sin_identificacion(self):
        cliente = Cliente.objects.create(**datos_cliente(
            tipo_cliente="PERSONA",
        ))
        self.assertEqual(cliente.tipo_cliente, "PERSONA")
        self.assertEqual(cliente.nombre_contacto, "")

    def test_multiples_sin_identificacion_y_mismo_nombre(self):
        primero = Cliente.objects.create(**datos_cliente())
        segundo = Cliente.objects.create(**datos_cliente())
        self.assertNotEqual(primero.pk, segundo.pk)

    def test_extranjero_sin_pais(self):
        self.assert_invalido("pais_identificacion", **datos_extranjero(
            pais_identificacion=None,
        ))

    def test_extranjero_sin_numero(self):
        self.assert_invalido("numero_identificacion", **datos_extranjero(
            numero_identificacion=None,
        ))

    def test_extranjero_sin_tipo_documento(self):
        self.assert_invalido("tipo_documento_extranjero", **datos_extranjero(
            tipo_documento_extranjero=None,
        ))

    def test_pais_invalido(self):
        for pais in ("A", "ARG", "12", "@!", "ÁR", "", "  "):
            with self.subTest(pais=pais):
                self.assert_invalido("pais_identificacion", **datos_extranjero(
                    pais_identificacion=pais,
                ))

    def test_rut_con_datos_extranjeros(self):
        for campo, valor in (
            ("pais_identificacion", "CL"),
            ("tipo_documento_extranjero", "DNI"),
            ("pais_identificacion", ""),
        ):
            with self.subTest(campo=campo, valor=valor):
                self.assert_invalido(campo, **datos_cliente(
                    tipo_identificacion="RUT",
                    numero_identificacion="12345678-5",
                    **{campo: valor},
                ))

    def test_sin_identificacion_rechaza_datos_incluso_vacios(self):
        for campo in (
            "numero_identificacion", "pais_identificacion",
            "tipo_documento_extranjero",
        ):
            for valor in ("AR", "", "  "):
                with self.subTest(campo=campo, valor=valor):
                    self.assert_invalido(campo, **datos_cliente(
                        **{campo: valor},
                    ))

    def test_sin_contacto(self):
        for vacio in ("", "  "):
            with self.subTest(vacio=vacio):
                self.assert_invalido("correo", **datos_cliente(
                    correo=vacio, telefono=vacio,
                ))

    def test_solo_telefono_es_valido(self):
        cliente = Cliente.objects.create(**datos_cliente(
            correo="", telefono="+1 123456789",
        ))
        self.assertEqual(cliente.correo, "")

    def test_correo_invalido(self):
        self.assert_invalido("correo", **datos_cliente(correo="sin-arroba"))

    def test_nombre_legal_invalido(self):
        for nombre in ("", "  ", None, 123):
            with self.subTest(nombre=nombre):
                self.assert_invalido("nombre_legal", **datos_cliente(
                    nombre_legal=nombre,
                ))

    def test_actualizacion_y_representacion(self):
        cliente = Cliente.objects.create(**datos_cliente())
        fecha = cliente.actualizado_en
        cliente.nombre_legal = "  Nombre nuevo  "
        cliente.save()
        cliente.refresh_from_db()
        self.assertEqual(str(cliente), "Nombre nuevo")
        self.assertGreater(cliente.actualizado_en, fecha)


class ClienteConstraintsTests(TestCase):
    def assert_rechazado_por_bd(self, datos, constraint):
        # bulk_create omite save(), full_clean() y toda normalización Python.
        with self.assertRaises(IntegrityError) as error:
            with transaction.atomic():
                Cliente.objects.bulk_create([Cliente(**datos)])
        self.assertEqual(
            error.exception.__cause__.diag.constraint_name, constraint
        )

    def test_tipo_cliente_invalido(self):
        self.assert_rechazado_por_bd(
            datos_cliente(tipo_cliente="OTRO"), "cliente_tipo_valido"
        )

    def test_tipo_identificacion_invalido(self):
        # Más de un check protege este estado: basta el rechazo de PostgreSQL.
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Cliente.objects.bulk_create([Cliente(**datos_cliente(
                    tipo_identificacion="OTRO",
                ))])

    def test_contacto_obligatorio(self):
        self.assert_rechazado_por_bd(
            datos_cliente(correo="", telefono=""),
            "cliente_contacto_obligatorio",
        )

    def test_nombre_no_vacio_y_normalizado(self):
        for nombre in ("", "   ", " Nombre", "Nombre "):
            with self.subTest(nombre=nombre):
                self.assert_rechazado_por_bd(
                    datos_cliente(nombre_legal=nombre),
                    "cliente_nombre_normalizado",
                )

    def test_contacto_normalizado(self):
        for cambios in (
            {"correo": " CONTACTO@EXAMPLE.COM "},
            {"correo": "", "telefono": "   "},
            {"nombre_contacto": " Ana "},
        ):
            with self.subTest(cambios=cambios):
                self.assert_rechazado_por_bd(
                    datos_cliente(**cambios), "cliente_contacto_normalizado"
                )

    def test_rut_formato_canonico_obligatorio(self):
        for rut in (None, "", "12.345.678-5", "012345678-5", "123456785",
                    "ABC-5", "12345678-k", "00000000-0"):
            with self.subTest(rut=rut):
                self.assert_rechazado_por_bd(datos_cliente(
                    tipo_identificacion="RUT", numero_identificacion=rut,
                ), "cliente_identificacion_coherente")

    def test_rut_rechaza_datos_extranjeros(self):
        for campo in ("pais_identificacion", "tipo_documento_extranjero"):
            with self.subTest(campo=campo):
                self.assert_rechazado_por_bd(datos_cliente(
                    tipo_identificacion="RUT",
                    numero_identificacion="12345678-5",
                    **{campo: "AR"},
                ), "cliente_identificacion_coherente")

    def test_extranjero_campos_obligatorios(self):
        for campo in (
            "numero_identificacion", "pais_identificacion",
            "tipo_documento_extranjero",
        ):
            for valor in (None, "", "  "):
                with self.subTest(campo=campo, valor=valor):
                    self.assert_rechazado_por_bd(
                        datos_extranjero(**{campo: valor}),
                        "cliente_identificacion_coherente",
                    )

    def test_extranjero_pais_ascii_mayusculas(self):
        for pais in ("ar", "A", "12", "@!", "ÁR"):
            with self.subTest(pais=pais):
                self.assert_rechazado_por_bd(
                    datos_extranjero(pais_identificacion=pais),
                    "cliente_identificacion_coherente",
                )

    def test_sin_identificacion_exige_null(self):
        for campo in (
            "numero_identificacion", "pais_identificacion",
            "tipo_documento_extranjero",
        ):
            for valor in ("AR", ""):
                with self.subTest(campo=campo, valor=valor):
                    self.assert_rechazado_por_bd(
                        datos_cliente(**{campo: valor}),
                        "cliente_identificacion_coherente",
                    )

    def test_rut_duplicado_normalizado(self):
        Cliente.objects.create(**datos_cliente(
            tipo_identificacion="RUT", numero_identificacion="12.345.678-5",
        ))
        with self.assertRaises(IntegrityError) as error:
            with transaction.atomic():
                Cliente.objects.create(**datos_cliente(
                    tipo_identificacion="RUT",
                    numero_identificacion="00012345678-5",
                ))
        self.assertEqual(
            error.exception.__cause__.diag.constraint_name, "cliente_rut_unico"
        )

    def test_rut_duplicado_sin_validacion_python(self):
        datos = datos_cliente(
            tipo_identificacion="RUT", numero_identificacion="12345678-5",
        )
        Cliente.objects.bulk_create([Cliente(**datos)])
        self.assert_rechazado_por_bd(datos, "cliente_rut_unico")

    def test_documento_extranjero_duplicado(self):
        Cliente.objects.create(**datos_extranjero())
        self.assert_rechazado_por_bd(
            datos_extranjero(), "cliente_documento_unico"
        )

    def test_tipo_documental_no_canonico_rechazado_por_bd(self):
        for tipo in ("dni", "Dni", " DNI ", " pasaporte "):
            with self.subTest(tipo=tipo):
                self.assert_rechazado_por_bd(
                    datos_extranjero(tipo_documento_extranjero=tipo),
                    "cliente_identificacion_coherente",
                )

    def test_unicidad_documental_tras_normalizar_categoria(self):
        Cliente.objects.create(**datos_extranjero())
        for tipo in ("dni", "Dni", " dni "):
            with self.subTest(tipo=tipo):
                with self.assertRaises(IntegrityError) as error:
                    with transaction.atomic():
                        Cliente.objects.create(**datos_extranjero(
                            tipo_documento_extranjero=tipo,
                        ))
                self.assertEqual(
                    error.exception.__cause__.diag.constraint_name,
                    "cliente_documento_unico",
                )

    def test_documento_mismo_numero_distinto_pais_o_tipo(self):
        Cliente.objects.create(**datos_extranjero())
        Cliente.objects.create(**datos_extranjero(pais_identificacion="PE"))
        Cliente.objects.create(**datos_extranjero(
            tipo_documento_extranjero="PASAPORTE",
        ))
        self.assertEqual(Cliente.objects.count(), 3)

    def test_update_no_puede_eliminar_contacto(self):
        cliente = Cliente.objects.create(**datos_cliente())
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Cliente.objects.filter(pk=cliente.pk).update(correo="")
