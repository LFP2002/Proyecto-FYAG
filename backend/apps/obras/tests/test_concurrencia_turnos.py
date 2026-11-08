from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, local
from time import monotonic
from unittest.mock import patch

from django.db import close_old_connections, connection, transaction
from django.test import TransactionTestCase, override_settings

from apps.obras import services, services_turnos as turnos
from apps.obras.exceptions import ErrorObras, EstadoIncompatible, RecursoNoEncontrado
from apps.obras.models import TurnoObra, EvidenciaTurno
from .test_turnos import TurnosBase, foto


class ConcurrenciaTurnosTests(TurnosBase, TransactionTestCase):
    def setUp(self):
        self.setUpTestData()
        self.preparar()

    def en_orden(self, primera, segunda, gate="_obra_bloqueada"):
        adquirido, liberar, segundo_listo = Event(), Event(), Event()
        contexto = local()
        pids = {}
        original = getattr(services, gate)

        def bloquear(*args, **kwargs):
            resultado = original(*args, **kwargs)
            if contexto.numero == 1:
                adquirido.set()
                if not liberar.wait(10):
                    raise AssertionError("No se liberó el bloqueo")
            return resultado

        def ejecutar(funcion, numero):
            close_old_connections()
            contexto.numero = numero
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET lock_timeout='10s'")
                    cursor.execute("SELECT pg_backend_pid()")
                    pids[numero] = cursor.fetchone()[0]
                if numero == 2:
                    segundo_listo.set()
                return funcion()
            except ErrorObras as exc:
                return exc
            finally:
                connection.close()

        with patch.object(services, gate, side_effect=bloquear), ThreadPoolExecutor(max_workers=2) as pool:
            uno = pool.submit(ejecutar, primera, 1)
            try:
                self.assertTrue(adquirido.wait(10))
                dos = pool.submit(ejecutar, segunda, 2)
                self.assertTrue(segundo_listo.wait(10))
                observado = False
                limite = monotonic() + 5
                while monotonic() < limite:
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT pg_blocking_pids(%s)", [pids[2]])
                        if pids[1] in cursor.fetchone()[0]:
                            observado = True
                            break
                    if dos.done():
                        break
                self.assertTrue(observado, "Debe observarse espera real PostgreSQL")
            finally:
                liberar.set()
            return uno.result(15), dos.result(15)

    def test_doble_inicio_misma_obra(self):
        uno, dos = self.en_orden(lambda: self.abrir(), lambda: self.abrir())
        self.assertIsInstance(uno, TurnoObra)
        self.assertIsInstance(dos, EstadoIncompatible)
        self.assertEqual(TurnoObra.objects.count(), 1)
        self.assertEqual(uno.eventos.count(), 1)

    def test_doble_inicio_distintas_obras(self):
        otra = self.otra_obra()
        uno, dos = self.en_orden(lambda: self.abrir(), lambda: self.abrir(obra=otra), gate="_tecnico_elegible")
        self.assertIsInstance(uno, TurnoObra)
        self.assertIsInstance(dos, EstadoIncompatible)
        self.assertEqual(TurnoObra.objects.count(), 1)

    def test_cierre_duplicado(self):
        turno = self.abrir()
        cerrar = lambda: turnos.finalizar_turno(self.obra, turno.pk, {"descripcion_trabajo": "Trabajo"}, self.tecnico)
        uno, dos = self.en_orden(cerrar, cerrar)
        self.assertIsInstance(uno, TurnoObra)
        self.assertIsInstance(dos, EstadoIncompatible)
        self.assertEqual(turno.eventos.count(), 2)

    def test_cierres_administrativos_concurrentes_y_ordinario_ambos_ordenes(self):
        for orden in ("administrativo_primero", "ordinario_primero", "ambos_administrativos"):
            with self.subTest(orden=orden):
                turno = self.abrir()
                administrativo = lambda: turnos.cerrar_administrativamente(self.obra, turno.pk, {
                    "descripcion_trabajo": "Verificado por Supervisor", "motivo": "Sin acceso",
                }, self.supervisor)
                ordinario = lambda: turnos.finalizar_turno(self.obra, turno.pk, {"descripcion_trabajo": "Trabajo"}, self.tecnico)
                primera, segunda = {
                    "administrativo_primero": (administrativo, ordinario),
                    "ordinario_primero": (ordinario, administrativo),
                    "ambos_administrativos": (administrativo, administrativo),
                }[orden]
                uno, dos = self.en_orden(primera, segunda)
                self.assertIsInstance(uno, TurnoObra)
                self.assertIsInstance(dos, EstadoIncompatible)
                self.assertEqual(turno.eventos.count(), 2)
                self.assertEqual(turno.eventos.filter(tipo__in=["CIERRE", "CIERRE_ADMINISTRATIVO"]).count(), 1)
                turno.refresh_from_db()
                self.assertEqual(turno.modo_cierre, "TECNICO" if orden == "ordinario_primero" else "SUPERVISOR")

    def test_cierre_administrativo_frente_suspension_ambos_ordenes(self):
        for cierre_primero in (False, True):
            with self.subTest(cierre_primero=cierre_primero):
                turno = self.abrir()
                cerrar = lambda: turnos.cerrar_administrativamente(self.obra, turno.pk, {
                    "descripcion_trabajo": "Verificado", "motivo": "Sin acceso",
                }, self.supervisor)
                suspender = lambda: services.suspender_obra(self.obra, self.supervisor, "Pausa")
                if cierre_primero:
                    uno, dos = self.en_orden(cerrar, suspender)
                    self.assertEqual(uno.estado_revision, "PENDIENTE_REVISION")
                    self.assertEqual(dos.estado, "SUSPENDIDA")
                else:
                    uno, dos = self.en_orden(suspender, cerrar)
                    self.assertIsInstance(uno, EstadoIncompatible)
                    self.assertEqual(dos.estado_revision, "PENDIENTE_REVISION")

    def test_cierre_antes_de_suspension(self):
        turno = self.abrir()
        uno, dos = self.en_orden(
            lambda: turnos.finalizar_turno(self.obra, turno.pk, {"descripcion_trabajo": "Trabajo"}, self.tecnico),
            lambda: services.suspender_obra(self.obra, self.supervisor, "Pausa"),
        )
        self.assertEqual(uno.estado_revision, "PENDIENTE_REVISION")
        self.assertEqual(dos.estado, "SUSPENDIDA")

    def test_suspension_antes_de_cierre_rechaza(self):
        turno = self.abrir()
        uno, dos = self.en_orden(
            lambda: services.suspender_obra(self.obra, self.supervisor, "Pausa"),
            lambda: turnos.finalizar_turno(self.obra, turno.pk, {"descripcion_trabajo": "Trabajo"}, self.tecnico),
        )
        self.assertIsInstance(uno, EstadoIncompatible)
        self.assertEqual(dos.estado_revision, "PENDIENTE_REVISION")

    def test_cierre_antes_de_desasignacion(self):
        turno = self.abrir(self.otro_tecnico)
        uno, dos = self.en_orden(
            lambda: turnos.finalizar_turno(self.obra, turno.pk, {"descripcion_trabajo": "Trabajo"}, self.otro_tecnico),
            lambda: services.desasignar_participante(self.obra, self.miembro.pk, self.supervisor, "Baja"),
        )
        self.assertEqual(uno.estado_revision, "PENDIENTE_REVISION")
        self.assertFalse(dos.activo)

    def test_desasignacion_antes_de_cierre_rechaza(self):
        turno = self.abrir(self.otro_tecnico)
        uno, dos = self.en_orden(
            lambda: services.desasignar_participante(self.obra, self.miembro.pk, self.supervisor, "Baja"),
            lambda: turnos.finalizar_turno(self.obra, turno.pk, {"descripcion_trabajo": "Trabajo"}, self.otro_tecnico),
        )
        self.assertIsInstance(uno, EstadoIncompatible)
        self.assertEqual(dos.estado_revision, "PENDIENTE_REVISION")

    def test_desasignacion_antes_de_inicio(self):
        uno, dos = self.en_orden(
            lambda: services.desasignar_participante(self.obra, self.miembro.pk, self.supervisor, "Baja"),
            lambda: self.abrir(self.otro_tecnico),
        )
        self.assertFalse(uno.activo)
        self.assertIsInstance(dos, RecursoNoEncontrado)

    def test_commit_fallido_limpia_archivos_y_rollback(self):
        turno = self.abrir()
        with TemporaryDirectory() as carpeta, override_settings(EVIDENCIAS_ROOT=carpeta):
            from django.db import OperationalError
            with patch.object(connection, "commit", side_effect=OperationalError("Commit falló")):
                with self.assertRaises(OperationalError):
                    turnos.finalizar_turno(self.obra, turno.pk, {"descripcion_trabajo": "Trabajo"}, self.tecnico, fotos=[foto()])
            self.assertEqual(list(Path(carpeta).iterdir()), [])
            turno.refresh_from_db()
            self.assertIsNone(turno.terminado_en)
            self.assertFalse(EvidenciaTurno.objects.exists())

    def test_atomic_externo_no_puede_dejar_archivos_huerfanos(self):
        turno = self.abrir()
        with TemporaryDirectory() as carpeta, override_settings(EVIDENCIAS_ROOT=carpeta):
            with transaction.atomic(), self.assertRaises(RuntimeError):
                turnos.finalizar_turno(self.obra, turno.pk, {"descripcion_trabajo": "Trabajo"}, self.tecnico, fotos=[foto()])
            self.assertEqual(list(Path(carpeta).iterdir()), [])
            self.assertFalse(EvidenciaTurno.objects.exists())
