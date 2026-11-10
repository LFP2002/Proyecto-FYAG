from django.conf import settings
from django.test import override_settings
from rest_framework.test import APIClient, APITestCase
from rest_framework_simplejwt.tokens import AccessToken as LegacyAccess
from rest_framework_simplejwt.tokens import RefreshToken as LegacyRefresh

from apps.usuarios import services_usuarios as services
from apps.usuarios.tokens import AccessToken, RefreshToken
from .test_administracion import AdminBase, PASSWORD, NEW_PASSWORD


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class SesionesTests(AdminBase, APITestCase):
    def assert_revoked(self, access, refresh):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        self.assertEqual(client.get("/api/auth/me/").status_code, 401)
        client.cookies[settings.JWT_REFRESH_COOKIE_NAME] = str(refresh)
        self.assertEqual(client.post("/api/auth/refresh/").status_code, 401)

    def test_claims_y_outstanding_coherente(self):
        from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
        refresh = RefreshToken.for_user(self.target)
        self.assertEqual(refresh["sesion_version"], 1)
        self.assertEqual(refresh.access_token["sesion_version"], 1)
        self.assertEqual(OutstandingToken.objects.get(jti=refresh["jti"]).token, str(refresh))

    def test_legacy_y_tipos_de_version_invalidos(self):
        self.assert_revoked(LegacyAccess.for_user(self.target), LegacyRefresh.for_user(self.target))
        for value in [None, True, "1", 0, -1, 2, [], {}]:
            access, refresh = AccessToken.for_user(self.target), RefreshToken.for_user(self.target)
            access["sesion_version"] = refresh["sesion_version"] = value
            self.assert_revoked(access, refresh)

    def test_mutaciones_revocan_ambos_tokens(self):
        actions = [
            lambda: services.editar_usuario(self.target, {"email": "otra_identidad@example.test"}, self.manager),
            lambda: services.cambiar_rol(self.target, {"rol": "SUPERVISOR_OBRAS", "motivo": "Nueva función"}, self.manager),
            lambda: services.establecer_clave(self.target, {"nueva_clave": NEW_PASSWORD, "motivo": "Cambio"}, self.manager),
            lambda: services.actividad_usuario(self.target, {"motivo": "Baja"}, self.manager, activo=False),
            lambda: services.actividad_usuario(self.target, {"motivo": "Alta"}, self.manager, activo=True),
        ]
        for action in actions:
            self.target.refresh_from_db()
            access, refresh = AccessToken.for_user(self.target), RefreshToken.for_user(self.target)
            action()
            self.assert_revoked(access, refresh)

    def test_identificador_claim_malformado_no_produce_500(self):
        for value in [None, True, [], {}, "x", "²", -1, "9223372036854775808"]:
            access, refresh = AccessToken.for_user(self.target), RefreshToken.for_user(self.target)
            access["user_id"] = refresh["user_id"] = value
            self.assert_revoked(access, refresh)

    def test_perfil_no_revoca_y_rol_persistido_en_comercial_obras(self):
        token = AccessToken.for_user(self.target)
        token["rol"] = "GERENCIA"
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual(self.client.get("/api/usuarios/").status_code, 403)
        services.editar_usuario(self.target, {"first_name": "Nombre"}, self.manager)
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 200)
        services.cambiar_rol(self.target, {"rol": "GERENCIA", "motivo": "Promoción"}, self.manager)
        self.assertEqual(self.client.get("/api/clientes/").status_code, 401)
        self.assertEqual(self.client.get("/api/obras/").status_code, 401)
        self.authenticate(self.target)
        self.assertEqual(self.client.get("/api/clientes/").status_code, 200)
        self.assertEqual(self.client.get("/api/obras/").status_code, 200)

    def test_usuario_borrado_inactivo_y_hash_revocado(self):
        for change in ["hash", "inactivo", "borrado"]:
            self.target.refresh_from_db()
            access, refresh = AccessToken.for_user(self.target), RefreshToken.for_user(self.target)
            if change == "hash":
                self.target.set_password(NEW_PASSWORD)
                self.target.save()
            elif change == "inactivo":
                self.target.is_active = False
                self.target.save()
            else:
                self.target.delete()
            self.assert_revoked(access, refresh)

    def test_csrf_real_login_refresh_logout_y_origen(self):
        client = APIClient(enforce_csrf_checks=True)
        data = {"email": self.manager.email, "password": PASSWORD}
        self.assertEqual(client.post("/api/auth/login/", data).status_code, 403)
        old = client.get("/api/auth/csrf/").data["csrfToken"]
        self.assertEqual(client.post("/api/auth/login/", data, HTTP_X_CSRFTOKEN="x" * 64).status_code, 403)
        self.assertEqual(client.post("/api/auth/login/", data, HTTP_X_CSRFTOKEN=old, HTTP_ORIGIN="https://evil.example").status_code, 403)
        login = client.post("/api/auth/login/", data, HTTP_X_CSRFTOKEN=old)
        self.assertEqual(login.status_code, 200, login.data)
        self.assertTrue(login.cookies[settings.JWT_REFRESH_COOKIE_NAME]["httponly"])
        self.assertNotIn("refresh", login.data)
        current = login.data["csrfToken"]
        for path in ["refresh", "logout"]:
            url = f"/api/auth/{path}/"
            for headers in [{}, {"HTTP_X_CSRFTOKEN": old}, {"HTTP_X_CSRFTOKEN": "x" * 64}, {"HTTP_X_CSRFTOKEN": current, "HTTP_ORIGIN": "https://evil.example"}]:
                self.assertEqual(client.post(url, **headers).status_code, 403)
        self.assertEqual(client.get("/api/auth/me/").status_code, 401)
        original = client.cookies[settings.JWT_REFRESH_COOKIE_NAME].value
        self.assertEqual(client.post("/api/auth/refresh/", HTTP_X_CSRFTOKEN=current, HTTP_ORIGIN="http://testserver").status_code, 200)
        self.assertNotEqual(client.cookies[settings.JWT_REFRESH_COOKIE_NAME].value, original)
        replay = APIClient()
        replay.cookies[settings.JWT_REFRESH_COOKIE_NAME] = original
        self.assertEqual(replay.post("/api/auth/refresh/").status_code, 401)
        self.assertEqual(client.post("/api/auth/logout/", HTTP_X_CSRFTOKEN=current).status_code, 204)
