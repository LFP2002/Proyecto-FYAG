"""Carreras PostgreSQL: conexiones distintas, barreras y bloqueo observado, sin sleeps."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from time import monotonic

from django.db import close_old_connections, connection, transaction
from django.test import TransactionTestCase, override_settings
from rest_framework.exceptions import APIException
from rest_framework_simplejwt.exceptions import TokenError

from apps.obras import services as obras
from apps.obras import services_turnos as turnos
from apps.obras.exceptions import ErrorObras
from apps.obras.tests.test_servicios_004a import BaseObras
from apps.usuarios import services_usuarios as usuarios
from apps.usuarios.models import Usuario, UsuarioEvento
from apps.usuarios.serializers import VersionedRefreshSerializer
from apps.usuarios.tokens import RefreshToken
from .test_administracion import PASSWORD


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ConcurrenciaTests(BaseObras, TransactionTestCase):
    def setUp(self):
        self.setUpTestData()
        self.ti = Usuario.objects.create_user(username="ti", email="ti@example.test", rol="ADMINISTRADOR_TI")

    def race(self, first, second):
        ready, release, started = Event(), Event(), Event()
        pids = {}

        def worker(action, index):
            close_old_connections()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET lock_timeout = '10s'")
                    cursor.execute("SET statement_timeout = '15s'")
                    cursor.execute("SELECT pg_backend_pid()")
                    pids[index] = cursor.fetchone()[0]
                if index == 1:
                    with transaction.atomic():
                        result = action()
                        ready.set()
                        if not release.wait(10):
                            raise AssertionError("No se liberó primera transacción")
                    return result
                started.set()
                return action()
            except (APIException, ErrorObras, TokenError) as exc:
                return exc
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            one = pool.submit(worker, first, 1)
            try:
                self.assertTrue(ready.wait(10), "Primera acción no alcanzó barrera")
                two = pool.submit(worker, second, 2)
                self.assertTrue(started.wait(10))
                blocked = False
                deadline = monotonic() + 5
                while monotonic() < deadline:
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT pg_blocking_pids(%s)", [pids[2]])
                        if pids[1] in cursor.fetchone()[0]:
                            blocked = True
                            break
                    if two.done():
                        break
                self.assertTrue(blocked, "No se observó bloqueo real de PostgreSQL")
            finally:
                release.set()
            return one.result(timeout=15), two.result(timeout=15)

    def deactivate(self):
        return usuarios.actividad_usuario(self.tecnico, {"motivo": "Baja"}, self.ti, activo=False)

    def demote(self):
        return usuarios.cambiar_rol(self.tecnico, {"rol": "SUPERVISOR_OBRAS", "motivo": "Cambio"}, self.ti)

    def test_ti_desactivaciones_cruzadas(self):
        other = Usuario.objects.create_user(username="segunda", email="segunda@example.test", rol="ADMINISTRADOR_TI")
        one, two = self.race(
            lambda: usuarios.actividad_usuario(other, {"motivo": "Baja"}, self.ti, activo=False),
            lambda: usuarios.actividad_usuario(self.ti, {"motivo": "Baja"}, other, activo=False),
        )
        self.assertIsInstance(one, Usuario)
        self.assertIsInstance(two, APIException)
        self.assertEqual(Usuario.objects.filter(rol="ADMINISTRADOR_TI", is_active=True).count(), 1)
        self.assertEqual(UsuarioEvento.objects.count(), 1)

    def test_ti_degradaciones_cruzadas(self):
        other = Usuario.objects.create_user(username="segunda", email="segunda@example.test", rol="ADMINISTRADOR_TI")
        one, two = self.race(
            lambda: usuarios.cambiar_rol(other, {"rol": "SUPERVISOR_OBRAS", "motivo": "Cambio"}, self.ti),
            lambda: usuarios.cambiar_rol(self.ti, {"rol": "SUPERVISOR_OBRAS", "motivo": "Cambio"}, other),
        )
        self.assertIsInstance(one, Usuario)
        self.assertIsInstance(two, APIException)
        self.assertEqual(Usuario.objects.filter(rol="ADMINISTRADOR_TI", is_active=True).count(), 1)

    def test_activacion_duplicada_un_evento(self):
        Usuario.objects.filter(pk=self.tecnico.pk).update(is_active=False)
        action = lambda: usuarios.actividad_usuario(self.tecnico, {"motivo": "Alta"}, self.ti, activo=True)
        self.race(action, action)
        self.tecnico.refresh_from_db()
        self.assertEqual(self.tecnico.sesion_version, 2)
        self.assertEqual(UsuarioEvento.objects.count(), 1)

    def test_alta_duplicada_400_sin_doble_evento(self):
        data = {"username": "nueva", "email": "nueva@example.test", "rol": "TECNICO", "password": PASSWORD}
        action = lambda: usuarios.crear_usuario(data, self.ti)
        one, two = self.race(action, action)
        self.assertIsInstance(one, Usuario)
        self.assertEqual(two.status_code, 400)
        self.assertEqual(UsuarioEvento.objects.count(), 1)

    def test_asignacion_antes_de_baja(self):
        obra = self.crear()
        one, two = self.race(lambda: obras.cambiar_tecnico(obra, self.tecnico.pk, self.supervisor, "Asignación"), self.deactivate)
        self.assertIsInstance(two, usuarios.ConflictoUsuario)
        self.assertEqual(two.detail["code"], "asignaciones_pendientes")

    def test_baja_antes_de_asignacion(self):
        obra = self.crear()
        one, two = self.race(self.deactivate, lambda: obras.cambiar_tecnico(obra, self.tecnico.pk, self.supervisor, "Asignación"))
        self.assertIsInstance(two, ErrorObras)
        obra.refresh_from_db()
        self.assertIsNone(obra.tecnico_responsable_id)

    def test_rol_antes_de_asignar_participante(self):
        obra = self.crear()
        one, two = self.race(self.demote, lambda: obras.asignar_participante(obra, {"tecnico": self.tecnico.pk, "motivo": "Apoyo"}, self.supervisor))
        self.assertIsInstance(two, ErrorObras)
        self.assertFalse(obra.participantes.exists())

    def test_participante_antes_de_cambio_rol(self):
        obra = self.crear()
        one, two = self.race(lambda: obras.asignar_participante(obra, {"tecnico": self.tecnico.pk, "motivo": "Apoyo"}, self.supervisor), self.demote)
        self.assertIsInstance(two, usuarios.ConflictoUsuario)

    def test_inicio_turno_antes_de_baja(self):
        obra = self.crear(tecnico_responsable=self.tecnico.pk, motivo="Asignación")
        obras.iniciar_obra(obra, self.supervisor, "Inicio")
        one, two = self.race(lambda: turnos.iniciar_turno(obra, {}, self.tecnico), self.deactivate)
        self.assertIsInstance(two, usuarios.ConflictoUsuario)
        self.assertEqual(obra.turnos.count(), 1)

    def test_refresh_duplicado_solo_una_rotacion(self):
        token = str(RefreshToken.for_user(self.tecnico))
        def refresh():
            serializer = VersionedRefreshSerializer(data={"refresh": token})
            serializer.is_valid(raise_exception=True)
            return serializer.validated_data
        one, two = self.race(refresh, refresh)
        self.assertIn("access", one)
        self.assertIsInstance(two, TokenError)

    def test_revocacion_antes_de_refresh(self):
        token = str(RefreshToken.for_user(self.tecnico))
        one, two = self.race(self.deactivate, lambda: VersionedRefreshSerializer().validate({"refresh": token}))
        self.assertIsInstance(two, APIException)

    def test_refresh_antes_de_revocacion_sus_tokens_tambien_quedan_obsoletos(self):
        from apps.usuarios.authentication import validar_sesion
        from apps.usuarios.tokens import AccessToken
        token = str(RefreshToken.for_user(self.tecnico))
        one, two = self.race(lambda: VersionedRefreshSerializer().validate({"refresh": token}), self.deactivate)
        self.assertIsInstance(two, Usuario)
        self.tecnico.refresh_from_db()
        with self.assertRaises(APIException):
            validar_sesion(AccessToken(one["access"]), self.tecnico)
        with self.assertRaises(APIException):
            VersionedRefreshSerializer().validate({"refresh": one["refresh"]})
