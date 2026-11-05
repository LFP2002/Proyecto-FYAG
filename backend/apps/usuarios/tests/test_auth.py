from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APITestCase


Usuario = get_user_model()


class AutenticacionTests(APITestCase):

    def setUp(self):
        self.password = "Prueba123!"

        self.usuario = Usuario.objects.create_user(
            username="gerencia",
            email="gerencia@gmail.com",
            password=self.password,
            rol="GERENCIA",
        )

        self.login_url = "/api/auth/login/"
        self.refresh_url = "/api/auth/refresh/"
        self.me_url = "/api/auth/me/"

    def test_login_correcto(self):
        response = self.client.post(
            self.login_url,
            {
                "email": "gerencia@gmail.com",
                "password": self.password,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)

        self.assertEqual(
            response.data["user"]["email"],
            "gerencia@gmail.com",
        )

        self.assertEqual(
            response.data["user"]["role"],
            "GERENCIA",
        )

    def test_login_contrasena_incorrecta(self):
        response = self.client.post(
            self.login_url,
            {
                "email": "gerencia@gmail.com",
                "password": "incorrecta",
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

        self.assertEqual(
            response.data["detail"],
            "Credenciales inválidas.",
        )

    def test_usuario_inactivo_no_puede_ingresar(self):
        self.usuario.is_active = False
        self.usuario.save()

        response = self.client.post(
            self.login_url,
            {
                "email": "gerencia@gmail.com",
                "password": self.password,
            },
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_refresh_token(self):
        login = self.client.post(
            self.login_url,
            {
                "email": "gerencia@gmail.com",
                "password": self.password,
            },
            format="json",
        )

        response = self.client.post(
            self.refresh_url,
            {
                "refresh": login.data["refresh"],
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)

    def test_endpoint_protegido_sin_token(self):
        response = self.client.get(self.me_url)

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_endpoint_protegido_con_token(self):
        login = self.client.post(
            self.login_url,
            {
                "email": "gerencia@gmail.com",
                "password": self.password,
            },
            format="json",
        )

        access = login.data["access"]

        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {access}"
        )

        response = self.client.get(self.me_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data["email"],
            "gerencia@gmail.com",
        )
        self.assertEqual(
            response.data["role"],
            "GERENCIA",
        )