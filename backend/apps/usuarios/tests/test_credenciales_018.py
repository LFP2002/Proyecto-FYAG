"""SPEC-018 A: identidades sintéticas, secretos solo en memoria, nunca logs."""
import hashlib
import json
import secrets
from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth.hashers import identify_hasher
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.test import RequestFactory, SimpleTestCase, override_settings
from django.urls import resolve
from django.utils import timezone
from rest_framework.exceptions import APIException
from rest_framework.test import APIClient, APITestCase
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken

from apps.usuarios import credenciales, services_usuarios as services
from apps.usuarios.models import SeguridadCredencial, Usuario, UsuarioEvento
from apps.usuarios.serializers import LoginSerializer, VersionedRefreshSerializer
from apps.usuarios.tokens import AccessToken, RefreshToken
from .test_administracion import AdminBase, NEW_PASSWORD, PASSWORD

FIRST = "/api/auth/primer-cambio-clave/"


def login_request():
    """Contexto HTTP explícito, también en tests de servicios/concurrencia."""
    request = RequestFactory().post("/api/auth/login/")
    request.resolver_match = resolve(request.path_info)
    return request


class CredencialesBase(AdminBase):
    def emit(self, *, activate=True):
        issued = services.crear_usuario(self.new_data(), self.manager)
        user = issued.usuario
        if activate:
            services.actividad_usuario(user, {"motivo": "Activación QA"}, self.manager, activo=True)
            user.refresh_from_db()
        return issued

    def challenge(self, issued):
        return LoginSerializer(context={"request": login_request()}).validate({"email": issued.usuario.email, "password": issued.credencial_temporal})

    def reset(self, target=None):
        return credenciales.restablecer_clave(target or self.target, {"motivo": "Recuperación QA"}, self.manager)

    def assert_old_tokens_denied(self, access, refresh):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        self.assertEqual(client.get("/api/auth/me/").status_code, 401)
        client.cookies[settings.JWT_REFRESH_COOKIE_NAME] = str(refresh)
        self.assertEqual(client.post("/api/auth/refresh/", {}, format="json").status_code, 401)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class CredencialesTests(CredencialesBase, APITestCase):
    def test_listado_precarga_estado_sin_n_mas_uno(self):
        for index in range(26):
            Usuario.objects.create_user(username=f"qa_lista_{index}", email=f"qa_lista_{index}@example.test", rol="TECNICO")
        # Usuario JWT + permiso TI persistido + count + pagina con estado 1:1.
        with self.assertNumQueries(4):
            response = self.client.get("/api/usuarios/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 25)
        self.assertTrue(all(user["estado_credencial"] == "PERSONAL" for user in response.data["results"]))

    def test_alta_csprng_256_bits_hash_y_exposicion_unica(self):
        with patch("apps.usuarios.credenciales.secrets.token_urlsafe", wraps=secrets.token_urlsafe) as rng:
            response = self.client.post("/api/usuarios/", self.new_data(), format="json")
        self.assertEqual(response.status_code, 201)
        rng.assert_called_once_with(32)
        user = Usuario.objects.get(pk=response.data["id"])
        secret = response.data["credencial_temporal"]
        self.assertEqual(len(secret), 43)
        self.assertTrue(user.check_password(secret))
        self.assertFalse(user.password == secret)
        self.assertFalse(user.is_active)
        self.assertEqual(response.data["estado_credencial"], "INICIAL")
        self.assertTrue(response.data["cambio_obligatorio"])
        self.assertEqual(response["Cache-Control"], "no-store")
        for path in ["/api/usuarios/", f"/api/usuarios/{user.pk}/", f"/api/usuarios/{user.pk}/historial/"]:
            text = json.dumps(self.client.get(path).data, default=str)
            self.assertFalse(secret in text or user.password in text)
            self.assertNotIn("desafio_digest", text)
            self.assertNotIn("credencial_temporal", text)
        state = user.seguridad_credencial
        self.assertEqual(state.vence_en - state.emitida_en, timedelta(hours=24))

    def test_alta_rechaza_password_y_campos_internos(self):
        states_before = SeguridadCredencial.objects.count()
        for key, value in [("password", PASSWORD), ("cambio_obligatorio", False), ("estado_credencial", "PERSONAL"),
                           ("sesion_version", 99), ("vence_en", None), ("is_active", True)]:
            self.assertEqual(self.client.post("/api/usuarios/", self.new_data(**{key: value}), format="json").status_code, 400)
        self.assertEqual(SeguridadCredencial.objects.count(), states_before)

    def test_login_temporal_solo_desafio_no_outstanding_y_cookie_eliminada(self):
        issued = self.emit()
        before = OutstandingToken.objects.count()
        self.client.cookies[settings.JWT_REFRESH_COOKIE_NAME] = "cookie-obsoleta"
        result = self.client.post("/api/auth/login/", {"email": issued.usuario.email, "password": issued.credencial_temporal}, format="json")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(set(result.data), {"estado", "desafio", "desafio_vence_en", "csrfToken"})
        self.assertEqual(result.data["estado"], "CAMBIO_OBLIGATORIO")
        self.assertEqual(result.cookies[settings.JWT_REFRESH_COOKIE_NAME]["max-age"], 0)
        self.assertEqual(OutstandingToken.objects.count(), before)
        state = SeguridadCredencial.objects.get(usuario=issued.usuario)
        self.assertEqual(state.desafio_digest, hashlib.sha256(result.data["desafio"].encode()).hexdigest())
        self.assertFalse(result.data["desafio"] in str(state.__dict__))
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {result.data['desafio']}")
        for path in ["/api/auth/me/", "/api/obras/", "/api/usuarios/"]:
            self.assertEqual(self.client.get(path).status_code, 401)

    def test_temporal_inactiva_no_autentica_y_no_enumera(self):
        issued = self.emit(activate=False)
        responses = []
        for email, password in [(issued.usuario.email, issued.credencial_temporal), ("nadie@example.test", "incorrecta"), (self.target.email, "incorrecta")]:
            r = self.client.post("/api/auth/login/", {"email": email, "password": password}, format="json")
            self.assertEqual(r.status_code, 401)
            responses.append(r.data)
        self.assertEqual(responses[0], responses[1])
        self.assertEqual(responses[1], responses[2])

    def test_cambio_exitoso_consume_version_auditoria_y_login_nuevo(self):
        issued = self.emit()
        user = issued.usuario
        old_version = user.sesion_version
        data = self.challenge(issued)
        r = self.client.post(FIRST, {"desafio": data["desafio"], "nueva_clave": NEW_PASSWORD}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data, {"estado": "CLAVE_PERSONAL_CONFIRMADA", "login_requerido": True})
        user.refresh_from_db()
        self.assertEqual(user.sesion_version, old_version + 1)
        self.assertTrue(user.check_password(NEW_PASSWORD))
        state = SeguridadCredencial.objects.get(usuario=user)
        self.assertEqual(state.estado, "PERSONAL")
        self.assertIsNone(state.desafio_digest)
        self.assertIsNone(state.vence_en)
        event = user.eventos_administrativos.get(tipo="CAMBIO_INICIAL")
        self.assertEqual(event.actor_id, user.pk)
        self.assertEqual(event.datos_nuevos, {})
        self.assertEqual(event.datos_anteriores, {})
        cache.clear()
        self.assertEqual(self.client.post("/api/auth/login/", {"email": user.email, "password": issued.credencial_temporal}, format="json").status_code, 401)
        normal = self.client.post("/api/auth/login/", {"email": user.email, "password": NEW_PASSWORD}, format="json")
        self.assertEqual(normal.status_code, 200)
        self.assertIn("access", normal.data)
        self.assertNotIn("refresh", normal.data)

    def test_misma_temporal_y_validadores_no_consumen_desafio(self):
        issued = self.emit()
        challenge = self.challenge(issued)["desafio"]
        for password in [issued.credencial_temporal, "123", "12345678", "password", issued.usuario.email]:
            self.assertEqual(self.client.post(FIRST, {"desafio": challenge, "nueva_clave": password}, format="json").status_code, 400)
        self.assertEqual(self.client.post(FIRST, {"desafio": challenge, "nueva_clave": NEW_PASSWORD}, format="json").status_code, 200)

    def test_reuso_manipulacion_y_otro_usuario_rechazados(self):
        challenge = self.challenge(self.emit())["desafio"]
        # JSON con surrogate aislado no debe provocar UnicodeEncodeError/500.
        malformed = b'{"desafio":"' + b"\\ud800" * 43 + b'","nueva_clave":"entrada-descartada"}'
        self.assertIn(self.client.generic("POST", FIRST, malformed, content_type="application/json").status_code, [400, 401])
        with self.assertRaises(APIException):
            credenciales.primer_cambio({"desafio": "\ud800" * 43, "nueva_clave": NEW_PASSWORD})
        for data in [{"desafio": "x" * 43, "nueva_clave": NEW_PASSWORD},
                     {"desafio": challenge, "nueva_clave": NEW_PASSWORD, "usuario": self.target.pk}]:
            self.assertIn(self.client.post(FIRST, data, format="json").status_code, [400, 401])
        self.assertEqual(self.client.post(FIRST, {"desafio": challenge, "nueva_clave": NEW_PASSWORD}, format="json").status_code, 200)
        reused = self.client.post(FIRST, {"desafio": challenge, "nueva_clave": NEW_PASSWORD}, format="json")
        self.assertEqual(reused.status_code, 401)
        self.assertEqual(reused.data, {"detail": "Desafío no disponible."})

    def test_nuevo_login_reemplaza_desafio(self):
        issued = self.emit()
        first, second = self.challenge(issued), self.challenge(issued)
        with self.assertRaises(APIException):
            credenciales.primer_cambio({"desafio": first["desafio"], "nueva_clave": NEW_PASSWORD})
        credenciales.primer_cambio({"desafio": second["desafio"], "nueva_clave": NEW_PASSWORD})

    def test_desafio_ttl_configurable_y_frontera(self):
        issued = self.emit()
        now = timezone.now()
        with override_settings(PRIMER_CAMBIO_TTL_SECONDS=17), patch("apps.usuarios.credenciales.timezone.now", return_value=now):
            challenge = self.challenge(issued)
        state = SeguridadCredencial.objects.get(usuario=issued.usuario)
        self.assertEqual(state.desafio_vence_en, now + timedelta(seconds=17))
        with patch("apps.usuarios.credenciales.timezone.now", return_value=state.desafio_vence_en):
            with self.assertRaises(APIException):
                credenciales.primer_cambio({"desafio": challenge["desafio"], "nueva_clave": NEW_PASSWORD})

    def test_temporal_ttl_configurable_frontera_y_reemision(self):
        now = timezone.now()
        with override_settings(CREDENCIAL_TEMPORAL_TTL_SECONDS=30), patch("apps.usuarios.credenciales.timezone.now", return_value=now):
            issued = self.emit()
        state = SeguridadCredencial.objects.get(usuario=issued.usuario)
        self.assertEqual(state.vence_en, now + timedelta(seconds=30))
        with patch("apps.usuarios.credenciales.timezone.now", return_value=state.vence_en):
            with self.assertRaises(APIException):
                self.challenge(issued)
        new = self.reset(issued.usuario)
        self.assertFalse(new.credencial_temporal == issued.credencial_temporal)
        self.assertEqual(self.challenge(new)["estado"], "CAMBIO_OBLIGATORIO")

    def test_desafio_limitado_por_vencimiento_temporal_y_expira_tambien(self):
        issued = self.emit()
        state = SeguridadCredencial.objects.get(usuario=issued.usuario)
        now = state.vence_en - timedelta(seconds=1)
        with patch("apps.usuarios.credenciales.timezone.now", return_value=now):
            challenge = self.challenge(issued)
        self.assertEqual(SeguridadCredencial.objects.get(usuario=issued.usuario).desafio_vence_en, state.vence_en)
        with patch("apps.usuarios.credenciales.timezone.now", return_value=state.vence_en):
            with self.assertRaises(APIException):
                credenciales.primer_cambio({"desafio": challenge["desafio"], "nueva_clave": NEW_PASSWORD})

    def test_reset_revoca_ambos_tokens_y_no_reactiva(self):
        access, refresh = AccessToken.for_user(self.target), RefreshToken.for_user(self.target)
        self.target.is_active = False
        self.target.save(update_fields=["is_active"])
        result = self.client.post(self.url + "restablecer-clave/", {"motivo": "Recuperación QA"}, format="json")
        self.assertEqual(result.status_code, 200)
        self.target.refresh_from_db()
        self.assertFalse(self.target.is_active)
        self.assertEqual(result.data["estado_credencial"], "RECUPERACION")
        self.assertTrue(self.target.check_password(result.data["credencial_temporal"]))
        self.assertEqual(result["Cache-Control"], "no-store")
        self.assert_old_tokens_denied(access, refresh)

    def test_reset_invalida_desafio_y_temporal_anterior(self):
        issued = self.emit()
        challenge = self.challenge(issued)
        self.reset(issued.usuario)
        for action in [lambda: self.challenge(issued), lambda: credenciales.primer_cambio({"desafio": challenge["desafio"], "nueva_clave": NEW_PASSWORD})]:
            with self.assertRaises(APIException):
                action()

    def test_ti_motivo_y_autooperacion_protegidos(self):
        for data in [{}, {"motivo": " "}, {"motivo": "QA", "nueva_clave": NEW_PASSWORD}]:
            self.assertEqual(self.client.post(self.url + "restablecer-clave/", data, format="json").status_code, 400)
        self.assertEqual(self.client.post(f"/api/usuarios/{self.manager.pk}/restablecer-clave/", {"motivo": "QA"}, format="json").status_code, 409)
        self.manager.is_active = False
        self.manager.save()
        with self.assertRaises(APIException):
            self.reset()

    def test_otros_roles_aun_staff_superuser_no_resetean_ni_enumeran(self):
        for role, user in self.users.items():
            if role == Usuario.Rol.ADMINISTRADOR_TI:
                continue
            user.is_staff = user.is_superuser = True
            user.save()
            self.authenticate(user)
            for pk in [self.target.pk, 99999999]:
                self.assertEqual(self.client.post(f"/api/usuarios/{pk}/restablecer-clave/", {"motivo": "QA"}, format="json").status_code, 403)

    def test_ti_persistido_y_version_revalidados_por_servicio(self):
        Usuario.objects.filter(pk=self.manager.pk).update(rol="TECNICO")
        with self.assertRaises(APIException):
            self.reset()
        Usuario.objects.filter(pk=self.manager.pk).update(rol="ADMINISTRADOR_TI", sesion_version=2)
        with self.assertRaises(APIException):
            self.reset()

    def test_establecer_clave_retirado_no_es_bypass(self):
        response = self.client.post(self.url + "establecer-clave/", {"motivo": "QA", "nueva_clave": NEW_PASSWORD}, format="json")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "operacion_retirada")
        with self.assertRaises(APIException):
            services.establecer_clave(self.target, {"motivo": "QA", "nueva_clave": NEW_PASSWORD}, self.manager)
        self.target.refresh_from_db()
        self.assertTrue(self.target.check_password(PASSWORD))

    def test_tokens_emitidos_artificialmente_no_sortean_estado_temporal(self):
        issued = self.emit()
        user = issued.usuario
        self.assert_old_tokens_denied(AccessToken.for_user(user), RefreshToken.for_user(user))
        with self.assertRaises(APIException):
            services.cambiar_clave_propia({"clave_actual": issued.credencial_temporal, "nueva_clave": NEW_PASSWORD}, user)

    def test_correo_revoca_desafio_y_noop_lo_preserva(self):
        issued = self.emit()
        challenge = self.challenge(issued)
        services.editar_usuario(issued.usuario, {"email": issued.usuario.email.upper()}, self.manager)
        credenciales.primer_cambio({"desafio": challenge["desafio"], "nueva_clave": NEW_PASSWORD})
        issued = self.reset(issued.usuario)
        challenge = self.challenge(issued)
        services.editar_usuario(issued.usuario, {"email": "actualizado@example.test"}, self.manager)
        with self.assertRaises(APIException):
            credenciales.primer_cambio({"desafio": challenge["desafio"], "nueva_clave": NEW_PASSWORD})

    def test_rollback_primer_cambio_y_reset_si_auditoria_falla(self):
        issued = self.emit()
        challenge = self.challenge(issued)
        before = Usuario.objects.get(pk=issued.usuario.pk)
        state_before = SeguridadCredencial.objects.get(usuario=before)
        with patch("apps.usuarios.services_usuarios._event", side_effect=RuntimeError("QA controlado")):
            with self.assertRaises(RuntimeError):
                credenciales.primer_cambio({"desafio": challenge["desafio"], "nueva_clave": NEW_PASSWORD})
            with self.assertRaises(RuntimeError):
                self.reset(before)
        after = Usuario.objects.get(pk=before.pk)
        self.assertTrue(after.password == before.password)
        self.assertEqual(after.sesion_version, before.sesion_version)
        self.assertEqual(SeguridadCredencial.objects.get(usuario=before).desafio_digest, state_before.desafio_digest)
        credenciales.primer_cambio({"desafio": challenge["desafio"], "nueva_clave": NEW_PASSWORD})

    def test_eventos_de_credencial_no_admiten_snapshots(self):
        from django.core.exceptions import ValidationError
        for kind in ["CREACION_CREDENCIAL_TEMPORAL", "REEMISION", "CAMBIO_INICIAL"]:
            with self.assertRaises(ValidationError):
                UsuarioEvento.objects.create(usuario_objetivo=self.target, actor=self.manager, tipo=kind, datos_nuevos={"email": self.target.email})

    def test_constraints_impiden_estados_imposibles(self):
        issued = self.emit()
        state = SeguridadCredencial.objects.get(usuario=issued.usuario)
        for data in [{"estado": "OTRO"}, {"vence_en": None}, {"estado": "PERSONAL"},
                     {"desafio_digest": "a" * 64}, {"desafio_version": 1},
                     {"desafio_digest": "a" * 64, "desafio_version": 1, "desafio_vence_en": state.vence_en + timedelta(seconds=1)}]:
            with self.assertRaises(IntegrityError), transaction.atomic():
                SeguridadCredencial.objects.filter(pk=state.pk).update(**data)

    def test_csrf_efectivo_y_sin_sesion_automatica(self):
        issued = self.emit()
        client = APIClient(enforce_csrf_checks=True)
        csrf = client.get("/api/auth/csrf/").data["csrfToken"]
        login = client.post("/api/auth/login/", {"email": issued.usuario.email, "password": issued.credencial_temporal}, format="json", HTTP_X_CSRFTOKEN=csrf)
        self.assertEqual(login.status_code, 200)
        data = {"desafio": login.data["desafio"], "nueva_clave": NEW_PASSWORD}
        for headers in [{}, {"HTTP_X_CSRFTOKEN": csrf}, {"HTTP_X_CSRFTOKEN": login.data["csrfToken"], "HTTP_ORIGIN": "https://evil.example"}]:
            self.assertEqual(client.post(FIRST, data, format="json", **headers).status_code, 403)
        r = client.post(FIRST, data, format="json", HTTP_X_CSRFTOKEN=login.data["csrfToken"])
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("access", r.data)
        self.assertEqual(client.get("/api/auth/me/").status_code, 401)

    def test_primer_cambio_reutiliza_throttle_no_lockout(self):
        issued = self.emit()
        data = {"desafio": self.challenge(issued)["desafio"], "nueva_clave": NEW_PASSWORD}
        with override_settings(REST_FRAMEWORK={**settings.REST_FRAMEWORK, "DEFAULT_THROTTLE_RATES": {"refresh_ip": "1/min"}}):
            # DRF almacena las tasas de clase; controlar la tasa, no el resultado HTTP.
            with patch("apps.usuarios.throttles.RefreshIPRateThrottle.get_rate", return_value="1/min"):
                self.assertEqual(self.client.post(FIRST, {**data, "nueva_clave": "123"}, format="json").status_code, 400)
                self.assertEqual(self.client.post(FIRST, data, format="json").status_code, 429)
        cache.clear()
        self.assertEqual(self.client.post(FIRST, data, format="json").status_code, 200)


class HashRealTests(CredencialesBase, APITestCase):
    def test_hash_real_django_y_repr_sin_credencial(self):
        issued = self.emit(activate=False)
        self.assertNotEqual(identify_hasher(issued.usuario.password).algorithm, "md5")
        self.assertTrue(issued.usuario.check_password(issued.credencial_temporal))
        self.assertFalse(issued.credencial_temporal in repr(issued))


class ConfiguracionTTLTests(SimpleTestCase):
    def test_reporter_y_logger_no_exponen_json_locales_cookies_ni_excepcion(self):
        import logging
        import sys
        from django.test import RequestFactory
        from apps.usuarios.exception_filter import CredencialesExceptionReporter, CredencialesLogFilter
        secret = secrets.token_urlsafe(32)
        request = RequestFactory().post(FIRST, {"desafio": secret, "nueva_clave": secret}, content_type="application/json")
        request.COOKIES["fyag_refresh"] = secret
        try:
            raise RuntimeError(secret)
        except RuntimeError:
            info = sys.exc_info()
            with override_settings(DEBUG=False):
                reporter = CredencialesExceptionReporter(request, *info)
                self.assertFalse(secret in reporter.get_traceback_text())
                self.assertFalse(secret in reporter.get_traceback_html())
            record = logging.LogRecord("django.request", logging.ERROR, __file__, 1, "Fallo %s", (secret,), info)
            record.request = request
            self.assertTrue(CredencialesLogFilter().filter(record))
            self.assertFalse(secret in logging.Formatter().format(record))

    def test_ttl_entero_positivo_falla_cerrado(self):
        from config.settings import _ttl_credencial
        from django.core.exceptions import ImproperlyConfigured
        for value in ["0", "-1", "abc", "1.5", "2147483648"]:
            with patch.dict("os.environ", {"FYAG_QA_TTL_TEST": value}):
                with self.assertRaises(ImproperlyConfigured):
                    _ttl_credencial("FYAG_QA_TTL_TEST", 300)

    def test_openapi_referencias_contratos_rutas_y_schemas(self):
        from django.urls import resolve
        from apps.usuarios.serializers_usuarios import CrearUsuarioSerializer, UsuarioLecturaSerializer
        schema = json.loads((settings.BASE_DIR / "docs/openapi/SPEC-018A-v1.json").read_text(encoding="utf-8"))
        self.assertEqual(schema["openapi"], "3.0.3")
        self.assertEqual(schema["info"]["version"], "1.1.1")
        self.assertEqual(set(schema["components"]["schemas"]["Usuario"]["properties"]["estado_credencial"]["enum"]),
                         {"PERSONAL", "INICIAL", "RECUPERACION", "NO_DISPONIBLE"})
        self.assertIn("seguridad_no_disponible", schema["components"]["responses"]["Conflicto"]["description"])

        def walk(value):
            if isinstance(value, dict):
                if "$ref" in value:
                    target = schema
                    self.assertTrue(value["$ref"].startswith("#/"))
                    for part in value["$ref"][2:].split("/"):
                        target = target[part]
                for child in value.values():
                    walk(child)
            elif isinstance(value, list):
                for child in value:
                    walk(child)
        walk(schema)
        for path in schema["paths"]:
            self.assertIsNotNone(resolve(path.replace("{id}", "1")))
        definitions = schema["components"]["schemas"]
        self.assertEqual(set(definitions["Alta"]["properties"]), set(CrearUsuarioSerializer().fields))
        self.assertEqual(set(definitions["Usuario"]["properties"]), set(UsuarioLecturaSerializer().fields))
        self.assertEqual(set(definitions["LoginRestringido"]["properties"]), {"estado", "desafio", "desafio_vence_en", "csrfToken"})
        self.assertTrue(schema["paths"]["/api/usuarios/{id}/establecer-clave/"]["post"]["deprecated"])
        self.assertNotIn("password", definitions["Alta"]["properties"])
