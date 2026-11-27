"""Temporales: sin request o fuera del POST LoginView jamás autentican."""
from types import SimpleNamespace

from django.contrib.auth import authenticate
from django.test import RequestFactory, override_settings
from django.urls import resolve
from rest_framework.exceptions import APIException
from rest_framework.test import APIClient, APITestCase

from apps.usuarios.backends import contexto_login_restringido
from apps.usuarios.serializers import LoginSerializer
from .test_administracion import PASSWORD
from .test_credenciales_018 import CredencialesBase, FIRST, login_request


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ContextoTemporalTests(CredencialesBase, APITestCase):
    def test_temporal_sin_request_denegada_en_authenticate_y_serializer(self):
        issued = self.emit()
        data = {"email": issued.usuario.email, "password": issued.credencial_temporal}
        self.assertIsNone(authenticate(request=None, **data))
        self.assertIsNone(authenticate(**data))
        with self.assertRaises(APIException):
            LoginSerializer().validate(data)

    def test_personal_sin_request_conserva_autenticacion_y_jwt(self):
        user = authenticate(request=None, email=self.target.email, password=PASSWORD)
        self.assertEqual(user.pk, self.target.pk)
        result = LoginSerializer().validate({"email": self.target.email, "password": PASSWORD})
        self.assertIn("access", result)
        self.assertIn("refresh", result)

    def test_contextos_incompletos_y_otras_vistas_no_autorizan_temporal(self):
        issued = self.emit()
        factory = RequestFactory()
        other = factory.post("/api/auth/login/")
        other.resolver_match = resolve(FIRST)  # URL escrita no sustituye vista real.
        fake = factory.post("/api/auth/login/")
        fake.resolver_match = SimpleNamespace(url_name="login", func=lambda request: None)
        incomplete = factory.post("/api/auth/login/")
        incomplete.resolver_match = SimpleNamespace(url_name="login")
        get = factory.get("/api/auth/login/")
        get.resolver_match = resolve(get.path_info)
        for request in [None, factory.post("/api/auth/login/"), factory.post("/admin/login/"),
                        factory.post("/api/auth/refresh/"), factory.post(FIRST), other, fake, incomplete, get]:
            self.assertFalse(contexto_login_restringido(request))
            self.assertIsNone(authenticate(request=request, email=issued.usuario.email, password=issued.credencial_temporal))
        self.assertTrue(contexto_login_restringido(login_request()))

    def test_login_http_temporal_con_csrf_solo_devuelve_desafio(self):
        issued = self.emit()
        client = APIClient(enforce_csrf_checks=True)
        csrf = client.get("/api/auth/csrf/").data["csrfToken"]
        data = {"email": issued.usuario.email, "password": issued.credencial_temporal}
        self.assertEqual(client.post("/api/auth/login/", data, format="json").status_code, 403)
        result = client.post("/api/auth/login/", data, format="json", HTTP_X_CSRFTOKEN=csrf)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(set(result.data), {"estado", "desafio", "desafio_vence_en", "csrfToken"})
        self.assertEqual(result.data["estado"], "CAMBIO_OBLIGATORIO")
        self.assertEqual(client.get("/api/auth/me/").status_code, 401)
        self.assertEqual(client.post("/api/auth/refresh/", {}, format="json", HTTP_X_CSRFTOKEN=result.data["csrfToken"]).status_code, 401)

    def test_contexto_autorizado_no_sortea_estado_ausente(self):
        issued = self.emit()
        # Simulación únicamente sobre la cuenta sintética de la BD efímera de test.
        issued.usuario.seguridad_credencial.delete()
        self.assertIsNone(authenticate(request=login_request(), email=issued.usuario.email, password=issued.credencial_temporal))

    @override_settings(JWT_REFRESH_COOKIE_SECURE=True, CSRF_COOKIE_SECURE=True)
    def test_cors_csrf_y_cookies_en_api_separada(self):
        with override_settings(CORS_ALLOWED_ORIGINS=["https://app.example.test"], CSRF_TRUSTED_ORIGINS=["https://app.example.test"]):
            client = APIClient(enforce_csrf_checks=True)
            preflight = client.options("/api/auth/login/", HTTP_ORIGIN="https://app.example.test", HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST", HTTP_ACCESS_CONTROL_REQUEST_HEADERS="content-type,x-csrftoken")
            self.assertEqual(preflight["access-control-allow-origin"], "https://app.example.test")
            self.assertEqual(preflight["access-control-allow-credentials"], "true")
            denied = client.options("/api/auth/login/", HTTP_ORIGIN="https://evil.example", HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST")
            self.assertNotIn("access-control-allow-origin", denied)
            csrf = client.get("/api/auth/csrf/", secure=True).data["csrfToken"]
            result = client.post("/api/auth/login/", {"email": self.target.email, "password": PASSWORD}, format="json", secure=True, HTTP_ORIGIN="https://app.example.test", HTTP_X_CSRFTOKEN=csrf)
            self.assertEqual(result.status_code, 200)
            from django.conf import settings
            cookie = result.cookies[settings.JWT_REFRESH_COOKIE_NAME]
            self.assertTrue(cookie["httponly"])
            self.assertTrue(cookie["secure"])
            self.assertEqual(cookie["samesite"], "Strict")
            self.assertEqual(cookie["path"], "/api/auth/")
