"""Auditoría C3: regresiones demostradas y límites de abuso, solo PostgreSQL QA."""
from unittest.mock import patch

from django.core.cache import cache
from django.db import connection, IntegrityError, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from rest_framework.exceptions import APIException
from rest_framework.test import APIClient
from rest_framework_simplejwt.exceptions import TokenError

from apps.usuarios import credenciales
from apps.usuarios.autenticacion_c2 import preflight_qa
from apps.usuarios.models import EstadoAcceso, RecuperacionAcceso, Usuario
from apps.usuarios.serializers import VersionedRefreshSerializer
from apps.usuarios.tokens import AccessToken, RefreshToken
from .c2_helpers import BaseC2
from . import test_concurrencia_006 as concurrencia
from .test_administracion import PASSWORD


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ValidacionC3Tests(BaseC2, TestCase):
    def test_reset_no_retira_la_ultima_recuperadora_configurada(self):
        third = Usuario.objects.create_user(username="qa_c3_ti3", email="qa_c3_ti3@example.test",
                                           rol="ADMINISTRADOR_TI", password=PASSWORD)
        credenciales.restablecer_clave(self.other, {"motivo": "QA C3 primer cambio pendiente"}, self.manager)
        before = list(Usuario.objects.filter(pk=self.manager.pk).values())
        with self.assertRaises(APIException) as caught:
            credenciales.restablecer_clave(self.manager, {"motivo": "QA C3 no retirar última recuperadora"}, third)
        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(list(Usuario.objects.filter(pk=self.manager.pk).values()), before)
        self.assertEqual(RecuperacionAcceso.objects.count(), 1)

    def test_hash_persistido_malformado_deniega_sin_500_ni_conteo(self):
        # El algoritmo existe, pero el coste persistido no es un entero.
        Usuario.objects.filter(pk=self.target.pk).update(password="pbkdf2_sha256$invalido$salt$encoded")
        with override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher",
                                               "django.contrib.auth.hashers.PBKDF2PasswordHasher"]):
            response = self.login()
        self.assertEqual(response.status_code, 401)
        self.assertEqual(EstadoAcceso.objects.get(usuario=self.target).intentos, 0)

    def test_hash_malformado_tambien_deniega_con_c2_apagada(self):
        Usuario.objects.filter(pk=self.target.pk).update(password="pbkdf2_sha256$invalido$salt$encoded")
        with override_settings(BLOQUEOS_C2_HABILITADO=False, PASSWORD_HASHERS=[
            "django.contrib.auth.hashers.MD5PasswordHasher", "django.contrib.auth.hashers.PBKDF2PasswordHasher"]):
            self.assertEqual(self.login().status_code, 401)

    def test_cinco_ip_distintas_pueden_bloquear_un_objetivo(self):
        cache.clear()
        for i in range(5):
            result = self.client.post("/api/auth/login/", {"email": self.target.email, "password": "qa-error"},
                format="json", HTTP_X_CSRFTOKEN=self.csrf, REMOTE_ADDR=f"192.0.2.{i+1}")
            self.assertEqual(result.status_code, 401)
        self.assertEqual(EstadoAcceso.objects.get(usuario=self.target).estado, "BLOQUEO_TEMPORAL")
        result = self.client.post("/api/auth/login/", {"email": self.target.email, "password": PASSWORD},
            format="json", HTTP_X_CSRFTOKEN=self.csrf, REMOTE_ADDR="192.0.2.99")
        self.assertEqual(result.status_code, 429)  # Email comparte cuota en este proceso.

    def test_bloqueadas_cinco_roles_denegadas_en_todos_los_modulos(self):
        paths = ("/api/obras/", "/api/finanzas/documentos/", "/api/documentos-metadata/",
                 "/api/clientes/", "/api/presupuestos/", "/api/usuarios/")
        for role in Usuario.Rol.values:
            user = Usuario.objects.create_user(username=f"qa_c3_{role}", email=f"qa_c3_{role.lower()}@example.test",
                                               rol=role, password=PASSWORD)
            token = str(AccessToken.for_user(user))
            self.fail(user)
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
            for path in paths:
                self.assertEqual(client.get(path).status_code, 401, (role, path))

    def test_cors_lista_explicita_no_sustituye_csrf(self):
        with override_settings(CORS_ALLOWED_ORIGINS=["https://qa.example.test"],
                               CSRF_TRUSTED_ORIGINS=["https://qa.example.test"]):
            for origin, allowed in (("https://qa.example.test", True), ("https://otro.example.test", False)):
                response = self.client.options("/api/auth/login/", HTTP_ORIGIN=origin,
                                               HTTP_ACCESS_CONTROL_REQUEST_METHOD="POST")
                self.assertEqual(response.get("Access-Control-Allow-Origin"), origin if allowed else None)
            response = self.client.post("/api/auth/login/", {"email": self.target.email, "password": PASSWORD},
                                        format="json", HTTP_ORIGIN="https://qa.example.test")
            self.assertEqual(response.status_code, 403)  # Sin token, aun con origin aprobado.

    def test_logout_consume_cookie_y_no_revoca_access_por_si_solo(self):
        session = self.login()
        cookie = self.client.cookies["fyag_refresh"]
        self.assertTrue(cookie["httponly"])
        self.assertTrue(cookie["secure"])
        self.assertEqual(cookie["samesite"], "Strict")
        self.assertEqual(cookie["path"], "/api/auth/")
        refresh = cookie.value
        result = self.client.post("/api/auth/logout/", {}, format="json", HTTP_X_CSRFTOKEN=self.csrf)
        self.assertEqual(result.status_code, 204)
        with self.assertRaises(TokenError):
            VersionedRefreshSerializer().validate({"refresh": refresh})
        # Logout no promete revocación global del access ya emitido.
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {session.data['access']}")
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 200)

    def test_triggers_publicos_habilitados(self):
        with connection.cursor() as cursor:
            cursor.execute("SELECT tgname, tgenabled FROM pg_trigger WHERE NOT tgisinternal AND tgname LIKE 'fyag_%'")
            triggers = dict(cursor.fetchall())
        for name in ("fyag_usuario_seguridad_inicial", "fyag_usuario_acceso_inicial", "fyag_evento_acceso_inmutable",
                     "fyag_validar_recuperacion_c2", "fyag_recuperacion_c2_inmutable", "fyag_reemision_c2_inmutable"):
            self.assertEqual(triggers.get(name), "O", name)

    def test_sql_no_permite_mutar_auditoria_ni_contadores_invalidos(self):
        self.fail()
        credenciales.restablecer_clave(self.target, {"motivo": "QA C3"}, self.manager)
        event = RecuperacionAcceso.objects.get()
        statements = [
            ("UPDATE usuarios_recuperacionacceso SET version_nueva=version_nueva", []),
            ("DELETE FROM usuarios_recuperacionacceso", []),
            ("UPDATE usuarios_eventoacceso SET cantidad_fallos=cantidad_fallos", []),
            ("DELETE FROM usuarios_eventoacceso", []),
            ("UPDATE usuarios_usuarioevento SET motivo=motivo WHERE id=%s", [event.reemision_id]),
            ("DELETE FROM usuarios_usuarioevento WHERE id=%s", [event.reemision_id]),
            ("UPDATE usuarios_estadoacceso SET intentos=5 WHERE usuario_id=%s", [self.target.pk]),
            ("UPDATE usuarios_seguridadcredencial SET estado='PERSONAL' WHERE usuario_id=%s", [self.target.pk]),
        ]
        for sql, params in statements:
            with self.assertRaises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
                cursor.execute(sql, params)

    def test_recuperacion_aun_permitida_si_objetivo_no_es_ultima(self):
        preflight_qa()
        credenciales.restablecer_clave(self.other, {"motivo": "QA C3"}, self.manager)
        self.assertEqual(RecuperacionAcceso.objects.count(), 1)
        self.assertEqual(self.login(self.manager).status_code, 200)

    def test_error_interno_hash_no_se_oculta_como_clave_incorrecta(self):
        with patch("apps.usuarios.autenticacion_c2.check_password", side_effect=RuntimeError("QA interno")):
            with self.assertRaises(RuntimeError):
                self.login()
        self.assertEqual(EstadoAcceso.objects.get(usuario=self.target).intentos, 0)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ConcurrenciaC3Tests(BaseC2, TransactionTestCase):
    race = concurrencia.ConcurrenciaTests.race

    def test_dos_resets_ti_no_retiraran_ambas_recuperadoras(self):
        third = Usuario.objects.create_user(username="qa_c3_ti3", email="qa_c3_ti3@example.test",
                                           rol="ADMINISTRADOR_TI", password=PASSWORD)
        one, two = self.race(
            lambda: credenciales.restablecer_clave(self.other, {"motivo": "QA C3"}, third),
            lambda: credenciales.restablecer_clave(self.manager, {"motivo": "QA C3"}, third))
        self.assertIsInstance(one, credenciales.CredencialEmitida)
        self.assertIsInstance(two, APIException)
        self.assertEqual(two.status_code, 409)
        self.assertEqual(RecuperacionAcceso.objects.count(), 1)

    def test_dos_refresh_concurrentes_solo_una_rotacion(self):
        token = str(RefreshToken.for_user(self.target))
        action = lambda: VersionedRefreshSerializer().validate({"refresh": token})
        one, two = self.race(action, action)
        self.assertIn("access", one)
        self.assertIsInstance(two, TokenError)
