from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase


Usuario = get_user_model()


class UsuarioModelTests(TestCase):

    def test_email_se_normaliza_antes_de_guardar(self):
        usuario = Usuario.objects.create_user(
            username="normalizacion",
            email="  Usuario.PRUEBA@GMAIL.COM  ",
            password="Prueba123!",
            rol="GERENCIA",
        )

        self.assertEqual(
            usuario.email,
            "usuario.prueba@gmail.com",
        )

        usuario.refresh_from_db()

        self.assertEqual(
            usuario.email,
            "usuario.prueba@gmail.com",
        )

    def test_email_no_permite_duplicado_por_mayusculas(self):
        Usuario.objects.create_user(
            username="usuario1",
            email="usuario@gmail.com",
            password="Prueba123!",
            rol="GERENCIA",
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Usuario.objects.create_user(
                    username="usuario2",
                    email="USUARIO@GMAIL.COM",
                    password="Prueba123!",
                    rol="TECNICO",
                )

    def test_base_de_datos_rechaza_rol_invalido(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Usuario.objects.create_user(
                    username="rolinvalido",
                    email="rolinvalido@gmail.com",
                    password="Prueba123!",
                    rol="ADMIN_TOTAL",
                )