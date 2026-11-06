from django.conf import settings
from django.contrib.auth import get_user_model

from rest_framework import status
from rest_framework.test import APITestCase

from django.core.cache import cache

from rest_framework.test import APIClient

from datetime import timedelta

from django.utils import timezone
from rest_framework_simplejwt.tokens import AccessToken

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
        self.logout_url = "/api/auth/logout/"
        self.me_url = "/api/auth/me/"

        cache.clear()

        self.csrf_url = "/api/auth/csrf/"

    def login(self):
        return self.client.post(
            self.login_url,
            {
                "email": "gerencia@gmail.com",
                "password": self.password,
            },
            format="json",
        )

    def test_login_correcto(self):
        response = self.login()

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertIn(
            "access",
            response.data,
        )

        self.assertNotIn(
            "refresh",
            response.data,
        )

        self.assertIn(
            settings.JWT_REFRESH_COOKIE_NAME,
            response.cookies,
        )

        cookie = response.cookies[settings.JWT_REFRESH_COOKIE_NAME]

        self.assertTrue(cookie["httponly"])

        self.assertEqual(
            response.data["user"]["username"],
            "gerencia",
        )

        self.assertEqual(
            response.data["user"]["email"],
            "gerencia@gmail.com",
        )

        self.assertEqual(
            response.data["user"]["role"],
            "GERENCIA",
        )

    def test_login_con_username_sin_email_es_rechazado(self):
        response = self.client.post(
            self.login_url,
            {"username": "gerencia", "password": self.password},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", response.data)
        self.assertNotIn(settings.JWT_REFRESH_COOKIE_NAME, response.cookies)

    def test_login_no_acepta_alias_como_email(self):
        response = self.client.post(
            self.login_url,
            {"email": "gerencia", "password": self.password},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_login_normaliza_email(self):
        response = self.client.post(
            self.login_url,
            {"email": "  GERENCIA@GMAIL.COM  ", "password": self.password},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["user"]["email"], self.usuario.email)

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

    def test_usuario_inactivo_no_puede_ingresar(self):
        self.usuario.is_active = False
        self.usuario.save()

        response = self.login()

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_refresh_desde_cookie(self):
        self.login()

        response = self.client.post(
            self.refresh_url,
            {},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertIn(
            "access",
            response.data,
        )

        self.assertNotIn(
            "refresh",
            response.data,
        )

    def test_refresh_rota_token(self):
        login = self.login()

        cookie_name = settings.JWT_REFRESH_COOKIE_NAME

        refresh_anterior = login.cookies[cookie_name].value

        response = self.client.post(
            self.refresh_url,
            {},
            format="json",
        )

        refresh_nuevo = response.cookies[cookie_name].value

        self.assertNotEqual(
            refresh_anterior,
            refresh_nuevo,
        )

    def test_refresh_anterior_no_puede_reutilizarse(self):
        login = self.login()

        cookie_name = settings.JWT_REFRESH_COOKIE_NAME

        refresh_anterior = login.cookies[cookie_name].value

        self.client.post(
            self.refresh_url,
            {},
            format="json",
        )

        self.client.cookies[cookie_name] = refresh_anterior

        response = self.client.post(
            self.refresh_url,
            {},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_logout_revoca_refresh(self):
        login = self.login()

        cookie_name = settings.JWT_REFRESH_COOKIE_NAME

        refresh_token = login.cookies[cookie_name].value

        response = self.client.post(
            self.logout_url,
            {},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_204_NO_CONTENT,
        )

        self.client.cookies[cookie_name] = refresh_token

        response = self.client.post(
            self.refresh_url,
            {},
            format="json",
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_endpoint_protegido_sin_token(self):
        response = self.client.get(self.me_url)

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_endpoint_protegido_con_token(self):
        login = self.login()

        access = login.data["access"]

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

        response = self.client.get(self.me_url)

        self.assertEqual(
            response.status_code,
            status.HTTP_200_OK,
        )

        self.assertEqual(
            response.data["email"],
            "gerencia@gmail.com",
        )

        self.assertEqual(
            response.data["username"],
            "gerencia",
        )

        self.assertEqual(
            response.data["role"],
            "GERENCIA",
        )

    def test_login_requiere_csrf_en_cliente_real(self):
        client = APIClient(enforce_csrf_checks=True)

        sin_csrf = client.post(
            self.login_url,
            {
                "email": "gerencia@gmail.com",
                "password": self.password,
            },
            format="json",
        )

        self.assertEqual(
            sin_csrf.status_code,
            status.HTTP_403_FORBIDDEN,
        )

        csrf_response = client.get(self.csrf_url)

        csrf_token = csrf_response.data["csrfToken"]

        con_csrf = client.post(
            self.login_url,
            {
                "email": "gerencia@gmail.com",
                "password": self.password,
            },
            format="json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )

        self.assertEqual(
            con_csrf.status_code,
            status.HTTP_200_OK,
        )

    def test_refresh_requiere_csrf(self):
        client = APIClient(enforce_csrf_checks=True)

        csrf_response = client.get(self.csrf_url)

        csrf_token = csrf_response.data["csrfToken"]

        login = client.post(
            self.login_url,
            {
                "email": "gerencia@gmail.com",
                "password": self.password,
            },
            format="json",
            HTTP_X_CSRFTOKEN=csrf_token,
        )

        # Login rota el CSRF.
        csrf_nuevo = login.data["csrfToken"]

        sin_csrf = client.post(
            self.refresh_url,
            {},
            format="json",
        )

        self.assertEqual(
            sin_csrf.status_code,
            status.HTTP_403_FORBIDDEN,
        )

        con_csrf = client.post(
            self.refresh_url,
            {},
            format="json",
            HTTP_X_CSRFTOKEN=csrf_nuevo,
        )

        self.assertEqual(
            con_csrf.status_code,
            status.HTTP_200_OK,
        )

    def test_login_rate_limit_por_email(self):
        for _ in range(5):
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
            status.HTTP_429_TOO_MANY_REQUESTS,
        )

    def test_jwt_manipulado_es_rechazado(self):
        login = self.login()

        access = login.data["access"]

        header, payload, signature = access.split(".")

        primer_caracter = "A" if signature[0] != "A" else "B"

        signature_manipulada = primer_caracter + signature[1:]

        token_manipulado = ".".join(
            [
                header,
                payload,
                signature_manipulada,
            ]
        )

        self.client.credentials(HTTP_AUTHORIZATION=(f"Bearer {token_manipulado}"))

        response = self.client.get(self.me_url)

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_jwt_expirado_es_rechazado(self):
        token = AccessToken.for_user(self.usuario)

        token.set_exp(
            from_time=(timezone.now() - timedelta(minutes=5)),
            lifetime=timedelta(minutes=1),
        )

        self.client.credentials(HTTP_AUTHORIZATION=(f"Bearer {str(token)}"))

        response = self.client.get(self.me_url)

        self.assertEqual(
            response.status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_contrasena_incorrecta_no_revela_detalles(self):
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

    def test_usuario_inexistente_no_revela_detalles(self):
        response = self.client.post(
            self.login_url,
            {
                "email": "noexiste@gmail.com",
                "password": "Prueba123!",
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
