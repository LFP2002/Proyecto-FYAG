"""Carreras reales PostgreSQL para la unidad Obras + bloqueo Comercial."""

from concurrent.futures import ThreadPoolExecutor
from threading import Event
from time import monotonic

from django.db import close_old_connections, connection, transaction
from django.test import TransactionTestCase

from apps.comercial import services_presupuestos as comercial
from apps.comercial.exceptions import (
    ErrorPresupuesto, PresupuestoUtilizado as PresupuestoUtilizadoComercial,
)
from apps.obras import services as obras
from apps.obras.exceptions import (
    ErrorObras, EstadoIncompatible, PresupuestoUtilizado as PresupuestoUtilizadoObras,
)
from apps.obras.models import Obra

from .test_servicios_004a import BaseObras


class ObrasConcurrenciaTests(BaseObras, TransactionTestCase):
    def setUp(self):
        # TransactionTestCase no aplica setUpTestData como TestCase.
        self.setUpTestData()

    def _ejecutar_en_orden(self, primera, segunda):
        bloqueado = Event()
        liberar = Event()
        segunda_lista = Event()
        pids = {}

        def ejecutar(funcion, numero):
            close_old_connections()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET lock_timeout = '10s'")
                    cursor.execute("SET statement_timeout = '15s'")
                    cursor.execute("SELECT pg_backend_pid()")
                    pids[numero] = cursor.fetchone()[0]
                if numero == 1:
                    with transaction.atomic():
                        from apps.comercial.models import Presupuesto
                        Presupuesto.objects.select_for_update().get(
                            pk=self.presupuesto.pk
                        )
                        bloqueado.set()
                        if not liberar.wait(10):
                            raise AssertionError("No se liberó el lock inicial")
                        resultado = funcion()
                else:
                    segunda_lista.set()
                    resultado = funcion()
                return resultado
            except (ErrorObras, ErrorPresupuesto) as exc:
                return exc
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            primero = pool.submit(ejecutar, primera, 1)
            try:
                self.assertTrue(bloqueado.wait(10), "No se adquirió el lock")
                segundo = pool.submit(ejecutar, segunda, 2)
                self.assertTrue(segunda_lista.wait(10), "No inició la segunda acción")
                observado = False
                limite = monotonic() + 5
                while monotonic() < limite:
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT pg_blocking_pids(%s)", [pids[2]])
                        if pids[1] in cursor.fetchone()[0]:
                            observado = True
                            break
                    if segundo.done():
                        break
                self.assertTrue(observado, "No se observó bloqueo PostgreSQL")
            finally:
                liberar.set()
            return primero.result(timeout=15), segundo.result(timeout=15)

    def test_crear_primero_impide_anular(self):
        uno, dos = self._ejecutar_en_orden(
            lambda: obras.crear_obra(self.datos(), self.supervisor),
            lambda: comercial.anular_presupuesto(
                self.presupuesto, self.finanzas, "Desistimiento"
            ),
        )
        self.assertIsInstance(uno, Obra)
        self.assertIsInstance(dos, PresupuestoUtilizadoComercial)
        self.assertEqual(Obra.objects.count(), 1)
        self.assertEqual(uno.eventos.count(), 1)
        self.presupuesto.refresh_from_db()
        self.assertEqual(self.presupuesto.estado, "APROBADO_CLIENTE")
        self.assertEqual(self.presupuesto.eventos.count(), 0)

    def test_anular_primero_impide_crear(self):
        uno, dos = self._ejecutar_en_orden(
            lambda: comercial.anular_presupuesto(
                self.presupuesto, self.finanzas, "Desistimiento"
            ),
            lambda: obras.crear_obra(self.datos(), self.supervisor),
        )
        self.assertEqual(uno.estado, "ANULADO")
        self.assertIsInstance(dos, EstadoIncompatible)
        self.assertFalse(Obra.objects.exists())
        self.assertEqual(self.presupuesto.eventos.count(), 1)

    def test_dos_creaciones_solo_una_obra(self):
        uno, dos = self._ejecutar_en_orden(
            lambda: obras.crear_obra(self.datos(), self.supervisor),
            lambda: obras.crear_obra(self.datos(), self.supervisor),
        )
        self.assertIsInstance(uno, Obra)
        self.assertIsInstance(dos, PresupuestoUtilizadoObras)
        self.assertEqual(Obra.objects.count(), 1)
        self.assertEqual(Obra.objects.get().eventos.count(), 1)
