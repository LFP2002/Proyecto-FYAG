from datetime import timedelta
from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.core.cache import cache
from django.db import IntegrityError, connection, transaction
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.usuarios import bloqueos
from apps.usuarios.checks_bloqueos import comprobar_configuracion_bloqueos
from apps.usuarios.models import EstadoAcceso, EventoAcceso, SeguridadCredencial, Usuario, UsuarioEvento
from apps.usuarios.politica_bloqueos import Senal
from .test_administracion import PASSWORD


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
                   BLOQUEOS_C1_SIMULACION_HABILITADA=True)
class PersistenciaC1Tests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = Usuario.objects.create_user(username="qa_c1", email="qa_c1@example.test", password=PASSWORD, rol="TECNICO")
        self.now = timezone.now() + timedelta(seconds=1)

    def signal(self, signal=Senal.CLAVE_INCORRECTA, now=None):
        with patch("apps.usuarios.bloqueos.timezone.now", return_value=now or self.now):
            return bloqueos.registrar_verificacion(self.user.pk, signal)

    def five(self, now=None):
        for _ in range(5):
            result = self.signal(now=now)
        return result

    def test_contador_ventana_version_y_ciclo_atomico(self):
        for count in range(1, 5):
            self.signal()
            state = EstadoAcceso.objects.get(usuario=self.user)
            self.assertEqual(state.intentos, count)
            self.assertEqual(state.version, count + 1)
            self.assertEqual(state.ventana_inicio, self.now)
            self.assertEqual(state.ventana_hasta, self.now + timedelta(minutes=15))
        self.assertFalse(EventoAcceso.objects.exists())
        self.signal()
        state = EstadoAcceso.objects.get(usuario=self.user)
        self.assertEqual(state.estado, "BLOQUEO_TEMPORAL")
        self.assertEqual(state.intentos, 0)
        self.assertEqual(state.ciclos_en, [self.now])
        event = EventoAcceso.objects.get()
        self.assertEqual((event.tipo, event.actor_tipo, event.actor_id, event.cantidad_fallos), ("BLOQUEO_TEMPORAL", "SISTEMA", None, 5))

    def test_cuatro_ciclos_persisten_y_acierto_no_libera_ti(self):
        now = self.now
        for minutes in (15, 60, 240):
            self.five(now)
            state = EstadoAcceso.objects.get(usuario=self.user)
            self.assertEqual(state.bloqueado_hasta, now + timedelta(minutes=minutes))
            now = state.bloqueado_hasta
        self.five(now)
        before = list(EstadoAcceso.objects.values())
        self.signal(Senal.CLAVE_CORRECTA, now + timedelta(days=2))
        self.assertEqual(list(EstadoAcceso.objects.values()), before)
        self.assertEqual(EventoAcceso.objects.filter(tipo="BLOQUEO_TI").count(), 1)

    def test_acierto_reinicia_racha_con_actor_titular(self):
        self.signal()
        self.signal(Senal.CLAVE_CORRECTA)
        state = EstadoAcceso.objects.get(usuario=self.user)
        self.assertEqual(state.intentos, 0)
        event = EventoAcceso.objects.get()
        self.assertEqual((event.tipo, event.actor_tipo, event.actor_id), ("REINICIO_RACHA", "TITULAR", self.user.pk))

    def test_sin_verificacion_no_consulta_y_inexistente_no_crea(self):
        with self.assertNumQueries(0):
            self.assertIsNone(bloqueos.registrar_verificacion(self.user.pk, Senal.SIN_VERIFICACION))
        self.assertIsNone(bloqueos.registrar_verificacion(999999999, Senal.CLAVE_INCORRECTA))
        self.assertEqual(EstadoAcceso.objects.count(), 1)
        self.assertEqual(EstadoAcceso.objects.get().intentos, 0)

    def test_deshabilitado_por_defecto_y_config_invalida(self):
        with override_settings(BLOQUEOS_C1_SIMULACION_HABILITADA=False):
            with self.assertNumQueries(0), self.assertRaises(ImproperlyConfigured):
                self.signal()
        for config in (None, {}, {"intentos": 4}):
            with override_settings(BLOQUEOS_C1_POLITICA=config):
                self.assertEqual(comprobar_configuracion_bloqueos(None)[0].id, "usuarios.E018")
                with self.assertRaises(ImproperlyConfigured):
                    self.signal()
        with override_settings(BLOQUEOS_C1_SIMULACION_HABILITADA="false"):
            with self.assertRaises(ImproperlyConfigured):
                self.signal()

    def test_ausencia_de_credencial_no_repara_ni_cuenta(self):
        SeguridadCredencial.objects.filter(usuario=self.user).delete()
        with self.assertRaises(bloqueos.EstadoAccesoNoDisponible):
            self.signal()
        self.assertEqual(EstadoAcceso.objects.get().intentos, 0)
        self.assertFalse(SeguridadCredencial.objects.exists())
        self.assertFalse(EventoAcceso.objects.exists())

    def test_ausencia_estado_acceso_no_reconstruye(self):
        EstadoAcceso.objects.filter(usuario=self.user).delete()
        with self.assertRaises(bloqueos.EstadoAccesoNoDisponible):
            self.signal()
        self.assertFalse(EstadoAcceso.objects.exists())

    def test_rollback_si_evento_falla_revierte_quinto_fallo(self):
        for _ in range(4):
            self.signal()
        before = list(EstadoAcceso.objects.values())
        with patch.object(EventoAcceso.objects, "create", side_effect=IntegrityError("QA")):
            with self.assertRaises(IntegrityError):
                self.signal()
        self.assertEqual(list(EstadoAcceso.objects.values()), before)
        self.assertFalse(EventoAcceso.objects.exists())

    def test_rollback_transaccion_externa_incluye_estado_eventos(self):
        before = list(EstadoAcceso.objects.values())
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                self.five()
                raise RuntimeError("QA rollback")
        self.assertEqual(list(EstadoAcceso.objects.values()), before)
        self.assertFalse(EventoAcceso.objects.exists())

    def test_constraints_rechazan_estados_imposibles(self):
        for changes in ({"intentos": -1}, {"intentos": 5}, {"estado": "OTRO"}, {"estado": "REQUIERE_TI"},
                        {"estado": "BLOQUEO_TEMPORAL"}, {"version": 0}, {"fallos_en": [None]},
                        {"ciclos_en": [self.now] * 5}, {"ciclos_en": [self.now, self.now - timedelta(seconds=1)]},
                        {"ciclos_en": [self.now + timedelta(days=1)]}):
            with self.subTest(fields=list(changes)), self.assertRaises(IntegrityError), transaction.atomic():
                EstadoAcceso.objects.filter(usuario=self.user).update(**changes)

    def test_eventos_inmutables_orm_y_sql_y_sin_campos_secretos(self):
        self.five()
        event = EventoAcceso.objects.get()
        for action in (lambda: event.save(), lambda: event.delete(),
                       lambda: EventoAcceso.objects.update(tipo="EXPIRACION"), lambda: EventoAcceso.objects.all().delete()):
            with self.assertRaises(ValidationError):
                action()
        for sql in ("UPDATE usuarios_eventoacceso SET cantidad_fallos=5", "DELETE FROM usuarios_eventoacceso"):
            with self.assertRaises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
                cursor.execute(sql)
        self.assertEqual(set(EventoAcceso.objects.values().get()), {"id", "usuario_id", "tipo", "actor_tipo", "actor_id", "version", "cantidad_fallos", "creado_en"})
        self.assertFalse(UsuarioEvento.objects.exists())

    def test_altas_internas_bulk_create_y_rollback_trigger(self):
        users = [Usuario(username=f"qa_bulk_c1_{i}", email=f"qa_bulk_c1_{i}@example.test", rol="TECNICO") for i in range(2)]
        Usuario.objects.bulk_create(users)
        for user in users:
            state = EstadoAcceso.objects.get(usuario=user)
            self.assertEqual((state.estado, state.intentos, state.ciclos_en, state.version), ("NORMAL", 0, [], 1))
        before = EstadoAcceso.objects.count()
        with self.assertRaises(RuntimeError), transaction.atomic():
            Usuario.objects.create_user(username="qa_rollback_c1", email="qa_rollback_c1@example.test", rol="GERENCIA")
            raise RuntimeError("QA")
        self.assertEqual(EstadoAcceso.objects.count(), before)

    def test_reloj_regresivo_y_version_agotada_fallan_sin_cambios(self):
        self.signal()
        with self.assertRaises(bloqueos.EstadoAccesoNoDisponible):
            self.signal(now=self.now - timedelta(microseconds=1))
        EstadoAcceso.objects.filter(usuario=self.user).update(version=9223372036854775807)
        with self.assertRaises(bloqueos.EstadoAccesoNoDisponible):
            self.signal()

    def test_login_jwt_refresh_no_consultan_ni_aplican_c1(self):
        # Incluso estado simulado REQUIERE_TI no cambia contratos en esta fase.
        now = self.now
        for minutes in (15, 60, 240):
            self.five(now)
            now += timedelta(minutes=minutes)
        self.five(now)
        before = list(EstadoAcceso.objects.values())
        client = APIClient(enforce_csrf_checks=True)
        csrf = client.get("/api/auth/csrf/").data["csrfToken"]
        result = client.post("/api/auth/login/", {"email": self.user.email, "password": PASSWORD}, format="json", HTTP_X_CSRFTOKEN=csrf)
        self.assertEqual(result.status_code, 200)
        self.assertIn("access", result.data)
        self.assertNotIn("estado_acceso", result.data)
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {result.data['access']}")
        self.assertEqual(client.get("/api/auth/me/").status_code, 200)
        self.assertEqual(client.post("/api/auth/refresh/", {}, format="json", HTTP_X_CSRFTOKEN=result.data["csrfToken"]).status_code, 200)
        self.assertEqual(list(EstadoAcceso.objects.values()), before)

    def test_errores_http_no_registran_fallos_c1(self):
        client = APIClient(enforce_csrf_checks=True)
        csrf = client.get("/api/auth/csrf/").data["csrfToken"]
        before = list(EstadoAcceso.objects.values())
        with patch("apps.usuarios.bloqueos.registrar_verificacion") as engine:
            url = "/api/auth/login/"
            payload = {"email": self.user.email, "password": "incorrecta-sintetica"}
            self.assertEqual(client.post(url, payload, format="json").status_code, 403)
            self.assertEqual(client.post(url, payload, format="json", HTTP_X_CSRFTOKEN=csrf).status_code, 401)
            self.assertEqual(client.post(url, {**payload, "email": "inexistente@example.test"}, format="json", HTTP_X_CSRFTOKEN=csrf).status_code, 401)
            self.assertEqual(client.post(url, "{", content_type="application/json", HTTP_X_CSRFTOKEN=csrf).status_code, 400)
            with patch("apps.usuarios.throttles.LoginIPRateThrottle.allow_request", return_value=False), patch("apps.usuarios.throttles.LoginIPRateThrottle.wait", return_value=10):
                self.assertEqual(client.post(url, payload, format="json", HTTP_X_CSRFTOKEN=csrf).status_code, 429)
            client.credentials(HTTP_AUTHORIZATION="Bearer token-sintetico-invalido")
            self.assertEqual(client.get("/api/auth/me/").status_code, 401)
            engine.assert_not_called()
        self.assertEqual(list(EstadoAcceso.objects.values()), before)
        self.assertFalse(EventoAcceso.objects.exists())

    def test_credenciales_temporales_independientes_de_acceso(self):
        for name in ("INICIAL", "RECUPERACION"):
            with self.subTest(estado=name):
                SeguridadCredencial.objects.filter(usuario=self.user).update(
                    estado=name, emitida_en=self.now, vence_en=self.now + timedelta(days=1))
                self.signal()
                self.assertEqual(SeguridadCredencial.objects.get(usuario=self.user).estado, name)
        self.assertEqual(EstadoAcceso.objects.get().intentos, 2)

    def test_evento_rechaza_falsificacion_actor_o_cantidad(self):
        for fields in ({"actor_tipo": "TI"}, {"actor": self.user}, {"cantidad_fallos": 4}, {"tipo": "DESBLOQUEO_TI"}):
            data = {"usuario": self.user, "tipo": "BLOQUEO_TEMPORAL", "actor_tipo": "SISTEMA", "actor": None,
                    "version": 2, "cantidad_fallos": 5, "creado_en": self.now, **fields}
            with self.assertRaises(ValidationError):
                EventoAcceso.objects.create(**data)
