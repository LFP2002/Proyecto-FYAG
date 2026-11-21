from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import authenticate
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.db import IntegrityError, connection, transaction
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from rest_framework.exceptions import APIException
from rest_framework.test import APIClient

from apps.usuarios.acceso import estado_acceso
from apps.usuarios.autenticacion_c2 import preflight_qa, verificar_acceso
from apps.usuarios.configuracion_c2 import habilitado
from apps.usuarios import credenciales, services_usuarios as services
from apps.usuarios.models import EstadoAcceso, EventoAcceso, RecuperacionAcceso, SeguridadCredencial, Usuario, UsuarioEvento
from apps.usuarios.serializers import LoginSerializer, VersionedRefreshSerializer
from apps.usuarios.tokens import AccessToken, RefreshToken
from .c2_helpers import BaseC2
from .test_administracion import PASSWORD, NEW_PASSWORD
from .test_credenciales_018 import login_request


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class AutenticacionC2Tests(BaseC2, TestCase):
    def test_hash_fuera_del_atomic_y_sin_doble_verificacion(self):
        from django.contrib.auth.hashers import check_password
        calls = []
        def verificar(*args, **kwargs):
            calls.append(connection.savepoint_ids[:])
            return check_password(*args, **kwargs)
        with patch("apps.usuarios.autenticacion_c2.check_password", side_effect=verificar):
            self.assertEqual(self.login().status_code, 200)
        self.assertEqual(len(calls), 1)
        # TestCase posee su propia atomic; el verificador no añadió savepoint.
        self.assertEqual(calls[0], connection.savepoint_ids)

    def test_fallos_reales_acierto_y_conteo_una_vez(self):
        self.fail(count=4)
        self.assertEqual(EstadoAcceso.objects.get(usuario=self.target).intentos, 4)
        self.assertEqual(self.login().status_code, 200)
        self.assertEqual(EstadoAcceso.objects.get(usuario=self.target).intentos, 0)
        self.assertEqual(EventoAcceso.objects.filter(tipo="REINICIO_RACHA").count(), 1)
        self.assertIsNone(authenticate(email=self.target.email, password="incorrecta-sintetica"))
        self.assertEqual(EstadoAcceso.objects.get(usuario=self.target).intentos, 1)

    def test_cuatro_ciclos_y_version_revocada_por_ciclo(self):
        self.four_cycles()
        state = EstadoAcceso.objects.get(usuario=self.target)
        self.target.refresh_from_db()
        self.assertEqual((state.estado, len(state.ciclos_en), self.target.sesion_version), ("REQUIERE_TI", 4, 5))
        before = state.version
        self.now += timedelta(days=2)
        self.assertEqual(self.login().status_code, 401)
        self.assertEqual(EstadoAcceso.objects.get(usuario=self.target).version, before)
        self.assertTrue(self.target.is_active)

    def test_temporal_expira_exacto_sin_resucitar_tokens_anteriores(self):
        session = self.login().data
        self.fail()
        self.now += timedelta(minutes=15, microseconds=-1)
        self.assertEqual(self.login().status_code, 401)
        self.now += timedelta(microseconds=1)
        self.assertEqual(self.login().status_code, 200)
        reader = APIClient()
        reader.credentials(HTTP_AUTHORIZATION=f"Bearer {session['access']}")
        self.assertEqual(reader.get("/api/auth/me/").status_code, 401)

    def test_jwt_refresh_y_revalidaciones_anteriores_denegados(self):
        session = self.login().data
        old_user = Usuario.objects.get(pk=self.target.pk)
        refresh = self.client.cookies["fyag_refresh"].value
        self.fail()
        reader = APIClient()
        reader.credentials(HTTP_AUTHORIZATION=f"Bearer {session['access']}")
        for path in ("/api/auth/me/", "/api/clientes/", "/api/presupuestos/", "/api/obras/"):
            self.assertEqual(reader.get(path).status_code, 401)
        with self.assertRaises(APIException):
            VersionedRefreshSerializer().validate({"refresh": refresh})
        from apps.documentos.permissions import revalidar
        from apps.adjuntos.permissions import actor_actual
        for action in (revalidar, actor_actual):
            with self.assertRaises(APIException):
                action(old_user)

    def test_desafio_previo_bloqueo_invalido_sin_bypass(self):
        issued = services.crear_usuario({"email": "qa_c2_temp@example.test", "username": "qa_c2_temp", "rol": "TECNICO"}, self.manager)
        services.actividad_usuario(issued.usuario, {"motivo": "QA"}, self.manager, activo=True)
        challenge = self.login(issued.usuario, issued.credencial_temporal).data["desafio"]
        self.fail(issued.usuario)
        with self.assertRaises(APIException):
            credenciales.primer_cambio({"desafio": challenge, "nueva_clave": NEW_PASSWORD})
        self.now += timedelta(minutes=15)
        result = self.login(issued.usuario, issued.credencial_temporal)
        self.assertEqual(result.status_code, 200)
        self.assertNotIn("access", result.data)
        self.assertEqual(result.data["estado"], "CAMBIO_OBLIGATORIO")
        credenciales.primer_cambio({"desafio": result.data["desafio"], "nueva_clave": NEW_PASSWORD})

    def test_reset_ti_transaccional_reemite_y_no_reactiva(self):
        self.four_cycles()
        services.actividad_usuario(self.target, {"motivo": "QA baja"}, self.manager, activo=False)
        issued = credenciales.restablecer_clave(self.target, {"motivo": "QA identidad verificada manualmente"}, self.manager)
        state = EstadoAcceso.objects.get(usuario=self.target)
        self.target.refresh_from_db()
        self.assertEqual((state.estado, state.intentos, state.ciclos_en), ("NORMAL", 0, []))
        self.assertFalse(self.target.is_active)
        self.assertFalse(self.target.check_password(PASSWORD))
        self.assertTrue(self.target.check_password(issued.credencial_temporal))
        event = RecuperacionAcceso.objects.get()
        self.assertEqual(event.reemision.tipo, "REEMISION")
        self.assertEqual(event.actor_id, self.manager.pk)
        self.assertEqual(event.estado_anterior, "REQUIERE_TI")

    def test_recuperacion_solo_ti_ajena_y_motivo(self):
        for actor in (self.target, Usuario.objects.create_user(username="qa_c2_g", email="qa_c2_g@example.test", rol="GERENCIA", is_superuser=True)):
            with self.assertRaises(APIException) as caught:
                credenciales.restablecer_clave(self.other, {"motivo": "QA"}, actor)
            self.assertEqual(caught.exception.status_code, 403)
        with self.assertRaises(APIException) as caught:
            credenciales.restablecer_clave(self.manager, {"motivo": "QA"}, self.manager)
        self.assertEqual(caught.exception.status_code, 409)
        with self.assertRaises(APIException):
            credenciales.restablecer_clave(self.target, {"motivo": " "}, self.manager)
        self.assertFalse(RecuperacionAcceso.objects.exists())

    def test_reset_fallido_revierte_clave_version_estado_y_auditoria(self):
        self.fail()
        before = (Usuario.objects.get(pk=self.target.pk).password, Usuario.objects.get(pk=self.target.pk).sesion_version,
                  list(EstadoAcceso.objects.filter(usuario=self.target).values()), UsuarioEvento.objects.count())
        with patch.object(RecuperacionAcceso.objects, "create", side_effect=IntegrityError("QA")):
            with self.assertRaises(IntegrityError):
                credenciales.restablecer_clave(self.target, {"motivo": "QA"}, self.manager)
        after = (Usuario.objects.get(pk=self.target.pk).password, Usuario.objects.get(pk=self.target.pk).sesion_version,
                 list(EstadoAcceso.objects.filter(usuario=self.target).values()), UsuarioEvento.objects.count())
        self.assertTrue(before == after)

    def test_evento_fallido_revierte_quinto_y_sesion_version(self):
        self.fail(count=4)
        before = list(EstadoAcceso.objects.filter(usuario=self.target).values())
        with patch.object(EventoAcceso.objects, "create", side_effect=IntegrityError("QA")):
            with self.assertRaises(IntegrityError):
                verificar_acceso(self.target.email, "incorrecta-sintetica", None)
        self.assertEqual(list(EstadoAcceso.objects.filter(usuario=self.target).values()), before)
        self.target.refresh_from_db()
        self.assertEqual(self.target.sesion_version, 1)

    def test_snapshot_cambiado_no_cuenta_ni_emite_hash_bajo_lock(self):
        from django.contrib.auth.hashers import check_password
        def cambiado(raw, encoded):
            result = check_password(raw, encoded)
            Usuario.objects.filter(pk=self.target.pk).update(sesion_version=2)
            return result
        for password in (PASSWORD, "incorrecta-sintetica"):
            Usuario.objects.filter(pk=self.target.pk).update(sesion_version=1)
            with patch("apps.usuarios.autenticacion_c2.check_password", side_effect=cambiado):
                self.assertIsNone(verificar_acceso(self.target.email, password, None))
        self.assertEqual(EstadoAcceso.objects.get(usuario=self.target).intentos, 0)

    def test_exclusiones_inexistente_csrf_json_429_tokens(self):
        before = list(EstadoAcceso.objects.values())
        url = "/api/auth/login/"
        payload = {"email": self.target.email, "password": "incorrecta-sintetica"}
        self.assertEqual(self.client.post(url, payload, format="json").status_code, 403)
        self.assertEqual(self.client.post(url, "{", content_type="application/json", HTTP_X_CSRFTOKEN=self.csrf).status_code, 400)
        self.assertEqual(self.client.post(url, [], format="json", HTTP_X_CSRFTOKEN=self.csrf).status_code, 400)
        self.assertEqual(self.client.post(url, {**payload, "password": []}, format="json", HTTP_X_CSRFTOKEN=self.csrf).status_code, 400)
        with patch("apps.usuarios.throttles.LoginIPRateThrottle.allow_request", return_value=False), patch("apps.usuarios.throttles.LoginIPRateThrottle.wait", return_value=10):
            self.assertEqual(self.client.post(url, payload, format="json", HTTP_X_CSRFTOKEN=self.csrf).status_code, 429)
        self.assertEqual(self.client.post(url, {**payload, "email": "inexistente@example.test"}, format="json", HTTP_X_CSRFTOKEN=self.csrf).status_code, 401)
        with self.assertRaises(Exception):
            VersionedRefreshSerializer().validate({"refresh": "token-invalido"})
        self.assertEqual(list(EstadoAcceso.objects.values()), before)

    def test_no_disponible_no_se_repara_en_login_jwt_o_reset(self):
        access = str(AccessToken.for_user(self.target))
        EstadoAcceso.objects.filter(usuario=self.target).delete()
        self.assertEqual(self.login().status_code, 401)
        self.assertIsNone(authenticate(email=self.target.email, password=PASSWORD))
        reader = APIClient()
        reader.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        self.assertEqual(reader.get("/api/auth/me/").status_code, 401)
        with self.assertRaises(APIException) as caught:
            credenciales.restablecer_clave(self.target, {"motivo": "QA"}, self.manager)
        self.assertEqual(caught.exception.status_code, 409)
        self.assertFalse(EstadoAcceso.objects.filter(usuario=self.target).exists())

    def test_credencial_ausente_conserva_fail_closed(self):
        SeguridadCredencial.objects.filter(usuario=self.target).delete()
        self.fail(count=1)
        self.assertEqual(EstadoAcceso.objects.get(usuario=self.target).intentos, 0)
        self.assertFalse(SeguridadCredencial.objects.filter(usuario=self.target).exists())

    def test_ultima_recuperadora_no_se_bloquea_y_preflight_rechaza_unica(self):
        preflight_qa()
        self.fail(self.manager)
        self.fail(self.other)
        self.assertEqual(EstadoAcceso.objects.get(usuario=self.manager).estado, "BLOQUEO_TEMPORAL")
        self.assertEqual(EstadoAcceso.objects.get(usuario=self.other).estado, "NORMAL")
        self.assertEqual(EstadoAcceso.objects.get(usuario=self.other).intentos, 4)
        self.assertEqual(self.login(self.other).status_code, 200)
        with self.assertRaises(ImproperlyConfigured):
            preflight_qa()
        with override_settings(BLOQUEOS_C2_TI_QA_IDS=(self.other.pk,)):
            with self.assertRaises(ImproperlyConfigured):
                habilitado()

    def test_perfiles_ti_con_estado_y_me_sin_estado_sin_n1(self):
        self.fail()
        admin = APIClient()
        admin.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(self.manager)}")
        with CaptureQueriesContext(connection) as queries:
            result = admin.get("/api/usuarios/")
        self.assertEqual(result.status_code, 200)
        self.assertTrue(all("estado_acceso" in u for u in result.data["results"]))
        self.assertLessEqual(len(queries), 5)
        self.assertNotIn("estado_acceso", admin.get("/api/auth/me/").data)

    def test_bloqueo_malicioso_sigue_riesgo_y_no_enumera_respuestas(self):
        self.fail()
        wrong = self.login(password="incorrecta-sintetica")
        correct = self.login()
        missing = self.client.post("/api/auth/login/", {"email": "ausente@example.test", "password": PASSWORD}, format="json", HTTP_X_CSRFTOKEN=self.csrf)
        self.assertEqual(wrong.data, correct.data)
        self.assertEqual(correct.data, missing.data)
        self.assertNotIn("Retry-After", correct)
        self.assertNotIn("access", correct.data)

    def test_django_sesion_no_resucita_tras_expirar_bloqueo(self):
        from django.test import Client
        browser = Client()
        self.assertTrue(browser.login(email=self.target.email, password=PASSWORD))
        old_hash = Usuario.objects.get(pk=self.target.pk).get_session_auth_hash()
        self.fail()
        self.now += timedelta(minutes=15)
        self.target.refresh_from_db()
        self.assertNotEqual(self.target.get_session_auth_hash(), old_hash)
        from django.contrib.auth import get_user
        from django.test import RequestFactory
        request = RequestFactory().get("/api/auth/me/")
        request.session = browser.session
        self.assertFalse(get_user(request).is_authenticated)

    def test_auditoria_recuperacion_inmutable_sin_secretos(self):
        self.fail()
        credenciales.restablecer_clave(self.target, {"motivo": "QA verificación manual"}, self.manager)
        event = RecuperacionAcceso.objects.get()
        with self.assertRaises(ValidationError):
            event.save()
        with self.assertRaises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
            cursor.execute("DELETE FROM usuarios_recuperacionacceso")
        with self.assertRaises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
            cursor.execute("UPDATE usuarios_usuarioevento SET motivo=motivo WHERE id=%s", [event.reemision_id])
        self.assertEqual(set(RecuperacionAcceso.objects.values().get()), {"id", "usuario_id", "actor_id", "reemision_id", "estado_anterior", "version_anterior", "version_nueva", "creado_en"})

    def test_activar_c2_sin_confirmaciones_denegado(self):
        for field, value in (("BLOQUEOS_C2_ENTORNO", "produccion"), ("BLOQUEOS_C2_RECUPERACION_QA_CONFIRMADA", False),
                             ("BLOQUEOS_C2_RIESGO_DOS_QA_ACEPTADO", False), ("BLOQUEOS_C2_RESPUESTAS", "423"),
                             ("BLOQUEOS_C2_SESIONES_TEMPORALES", "")):
            with override_settings(**{field: value}):
                with self.assertRaises(ImproperlyConfigured):
                    habilitado()

    def test_flujo_http_reset_temporal_primer_cambio_y_login_nuevo(self):
        old = self.login().data["access"]
        self.four_cycles()
        ti = self.login(self.manager).data["access"]
        reset = self.client.post(f"/api/usuarios/{self.target.pk}/restablecer-clave/", {"motivo": "QA identidad verificada"},
            format="json", HTTP_AUTHORIZATION=f"Bearer {ti}")
        self.assertEqual(reset.status_code, 200)
        self.assertEqual(reset.data["estado_acceso"], "NORMAL")
        temporary = self.login(self.target, reset.data["credencial_temporal"])
        self.assertEqual(temporary.status_code, 200)
        self.assertNotIn("access", temporary.data)
        change = self.client.post("/api/auth/primer-cambio-clave/", {"desafio": temporary.data["desafio"], "nueva_clave": NEW_PASSWORD},
                                  format="json", HTTP_X_CSRFTOKEN=self.csrf)
        self.assertEqual(change.status_code, 200)
        self.assertEqual(self.login(self.target, NEW_PASSWORD).status_code, 200)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {old}")
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 401)

    def test_snapshot_hash_identidad_rol_y_actividad_cambiados(self):
        from django.contrib.auth.hashers import check_password
        initial = {field: getattr(self.target, field) for field in ("email", "password", "rol", "is_active")}
        for changes in ({"password": "!qa-inutilizable"}, {"email": "qa_nuevo_correo@example.test"},
                        {"rol": "SUPERVISOR_OBRAS"}, {"is_active": False}):
            Usuario.objects.filter(pk=self.target.pk).update(**initial)
            def verify(raw, encoded):
                result = check_password(raw, encoded)
                Usuario.objects.filter(pk=self.target.pk).update(**changes)
                return result
            with patch("apps.usuarios.autenticacion_c2.check_password", side_effect=verify):
                self.assertIsNone(verificar_acceso(self.target.email, PASSWORD, None))
        self.assertEqual(EstadoAcceso.objects.get(usuario=self.target).intentos, 0)

    def test_ti_configurada_no_puede_degradarse_ni_desactivarse(self):
        for action in (lambda: services.actividad_usuario(self.other, {"motivo": "QA"}, self.manager, activo=False),
                       lambda: services.cambiar_rol(self.other, {"rol": "TECNICO", "motivo": "QA"}, self.manager)):
            with self.assertRaises(APIException) as caught:
                action()
            self.assertEqual(caught.exception.status_code, 409)

    def test_activacion_dinamica_sin_dos_ti_reales_denegada(self):
        Usuario.objects.filter(pk=self.other.pk).delete()
        with self.assertRaises(ImproperlyConfigured):
            verificar_acceso(self.target.email, PASSWORD, None)
        self.assertEqual(EstadoAcceso.objects.get(usuario=self.target).intentos, 0)

    def test_los_cinco_roles_bloqueados_no_acceden_ni_resetean(self):
        for role in Usuario.Rol.values:
            user = Usuario.objects.create_user(username=f"qa_c2_{role}", email=f"qa_c2_{role.lower()}@example.test", password=PASSWORD, rol=role)
            token = str(AccessToken.for_user(user))
            self.fail(user)
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
            self.assertEqual(client.get("/api/auth/me/").status_code, 401)
            self.assertEqual(client.post(f"/api/usuarios/{self.target.pk}/restablecer-clave/", {"motivo": "QA"}, format="json").status_code, 401)

    def test_429_real_del_sexto_login_no_invoca_verificador(self):
        cache.clear()
        for _ in range(5):
            self.assertEqual(self.login(password="incorrecta-sintetica", clear_rate=False).status_code, 401)
        before = list(EstadoAcceso.objects.filter(usuario=self.target).values())
        with patch("apps.usuarios.autenticacion_c2.verificar_acceso") as verify:
            result = self.login(clear_rate=False)
        self.assertEqual(result.status_code, 429)
        verify.assert_not_called()
        self.assertEqual(list(EstadoAcceso.objects.filter(usuario=self.target).values()), before)

    def test_hash_inutilizable_no_es_verificacion_incorrecta(self):
        self.target.set_unusable_password()
        self.target.save(update_fields=["password"])
        self.assertEqual(self.login().status_code, 401)
        self.assertEqual(EstadoAcceso.objects.get(usuario=self.target).intentos, 0)

    def test_recuperadora_con_hash_inutilizable_no_satisface_preflight_ni_guarda(self):
        self.other.set_unusable_password()
        self.other.save(update_fields=["password"])
        with self.assertRaises(ImproperlyConfigured):
            preflight_qa()
        with self.assertRaises(ImproperlyConfigured):
            verificar_acceso(self.manager.email, PASSWORD, None)
        self.assertEqual(EstadoAcceso.objects.get(usuario=self.manager).intentos, 0)
        # Con hash válido pero pendiente de primer cambio tampoco es recuperadora.
        self.other.set_password(PASSWORD)
        self.other.save(update_fields=["password"])
        credenciales.restablecer_clave(self.other, {"motivo": "QA recuperación"}, self.manager)
        self.fail(self.manager)
        self.assertEqual(EstadoAcceso.objects.get(usuario=self.manager).estado, "NORMAL")
        self.assertEqual(EstadoAcceso.objects.get(usuario=self.manager).intentos, 4)
