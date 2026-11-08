from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Event, local
from time import monotonic
from unittest.mock import patch

from django.db import close_old_connections, connection
from django.test import TransactionTestCase
from django.utils import timezone

from apps.obras import services, services_gastos
from apps.obras.exceptions import DatosInvalidos, ErrorObras, EstadoIncompatible
from apps.obras.models import CostoObraEvento, GastoObra, Obra
from .test_gastos import GastosBase


class ConcurrenciaGastosTests(GastosBase, TransactionTestCase):
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

    def test_devoluciones_simultaneas_no_exceden_la_cantidad(self):
        gasto = self.crear_ok(cantidad="1.500")

        def devolver():
            return services_gastos.devolver_gasto(self.obra, gasto.pk, {
                "cantidad": "1.000", "fecha_devolucion": timezone.localdate(),
                "motivo": "Devolución concurrente",
            }, self.supervisor)

        uno, dos = self.en_orden(devolver, devolver)
        self.assertIsInstance(uno, GastoObra)
        self.assertIsInstance(dos, DatosInvalidos)
        gasto.refresh_from_db()
        self.assertEqual(gasto.cantidad_devuelta, Decimal("1.000"))
        self.assertEqual(gasto.eventos.filter(tipo="DEVOLUCION").count(), 1)
        self.assertEqual(gasto.eventos.count(), 2)

    def test_anulacion_frente_a_devolucion_en_ambos_ordenes(self):
        for anulacion_primero in (True, False):
            with self.subTest(anulacion_primero=anulacion_primero):
                gasto = self.crear_ok()
                anular = lambda: services_gastos.anular_gasto(
                    self.obra, gasto.pk, {"motivo": "Registro duplicado"},
                    self.supervisor,
                )
                devolver = lambda: services_gastos.devolver_gasto(
                    self.obra, gasto.pk, {
                        "cantidad": "1.000",
                        "fecha_devolucion": timezone.localdate(),
                        "motivo": "Devolución concurrente",
                    }, self.supervisor,
                )
                if anulacion_primero:
                    uno, dos = self.en_orden(anular, devolver)
                    self.assertIsInstance(uno, GastoObra)
                    self.assertIsInstance(dos, EstadoIncompatible)
                    gasto.refresh_from_db()
                    self.assertFalse(gasto.vigente)
                    self.assertEqual(gasto.cantidad_devuelta, Decimal("0.000"))
                    self.assertEqual(gasto.eventos.filter(tipo="ANULACION").count(), 1)
                    self.assertFalse(gasto.eventos.filter(tipo="DEVOLUCION").exists())
                else:
                    uno, dos = self.en_orden(devolver, anular)
                    self.assertIsInstance(uno, GastoObra)
                    self.assertIsInstance(dos, GastoObra)
                    gasto.refresh_from_db()
                    self.assertFalse(gasto.vigente)
                    self.assertEqual(gasto.cantidad_devuelta, Decimal("1.000"))
                    self.assertEqual(gasto.eventos.filter(tipo="ANULACION").count(), 1)
                    self.assertEqual(gasto.eventos.filter(tipo="DEVOLUCION").count(), 1)

    def test_correccion_frente_a_devolucion_en_ambos_ordenes(self):
        for devolucion_primero in (True, False):
            with self.subTest(devolucion_primero=devolucion_primero):
                gasto = self.crear_ok()
                devolver = lambda: services_gastos.devolver_gasto(
                    self.obra, gasto.pk, {
                        "cantidad": "1.000",
                        "fecha_devolucion": timezone.localdate(),
                        "motivo": "Devolución concurrente",
                    }, self.supervisor,
                )
                corregir = lambda: services_gastos.editar_gasto(
                    self.obra, gasto.pk, {
                        "cantidad": "0.500",
                        "motivo": "Ajuste de factura",
                    }, self.supervisor,
                )
                if devolucion_primero:
                    uno, dos = self.en_orden(devolver, corregir)
                    self.assertIsInstance(uno, GastoObra)
                    self.assertIsInstance(dos, DatosInvalidos)
                    gasto.refresh_from_db()
                    self.assertEqual(gasto.cantidad, Decimal("2.500"))
                    self.assertEqual(gasto.cantidad_devuelta, Decimal("1.000"))
                else:
                    uno, dos = self.en_orden(corregir, devolver)
                    self.assertIsInstance(uno, GastoObra)
                    self.assertIsInstance(dos, DatosInvalidos)
                    gasto.refresh_from_db()
                    self.assertEqual(gasto.cantidad, Decimal("0.500"))
                    self.assertEqual(gasto.cantidad_devuelta, Decimal("0.000"))
                self.assertEqual(gasto.eventos.count(), 2)

    def test_anulaciones_simultaneas_dejan_un_solo_evento(self):
        gasto = self.crear_ok()

        def anular():
            return services_gastos.anular_gasto(
                self.obra, gasto.pk, {"motivo": "Baja concurrente"},
                self.supervisor,
            )

        uno, dos = self.en_orden(anular, anular)
        self.assertIsInstance(uno, GastoObra)
        self.assertIsInstance(dos, EstadoIncompatible)
        gasto.refresh_from_db()
        self.assertFalse(gasto.vigente)
        self.assertEqual(gasto.anulado_por_id, self.supervisor.pk)
        self.assertEqual(gasto.eventos.count(), 2)
        self.assertEqual(gasto.eventos.filter(tipo="ANULACION").count(), 1)
        self.assertEqual(CostoObraEvento.objects.count(), 2)

    def test_correcciones_simultaneas_encadenan_auditoria(self):
        gasto = self.crear_ok()

        def corregir(descripcion):
            return services_gastos.editar_gasto(
                self.obra, gasto.pk, {
                    "descripcion": descripcion,
                    "motivo": "Corrección concurrente",
                }, self.supervisor,
            )

        uno, dos = self.en_orden(
            lambda: corregir("Primera corrección"),
            lambda: corregir("Segunda corrección"),
        )
        self.assertIsInstance(uno, GastoObra)
        self.assertIsInstance(dos, GastoObra)
        eventos = list(gasto.eventos.filter(tipo="CORRECCION").order_by("creado_en", "id"))
        self.assertEqual(len(eventos), 2)
        self.assertEqual(eventos[0].datos_anteriores["descripcion"], "Tubería de cobre")
        self.assertEqual(eventos[0].datos_nuevos["descripcion"], "Primera corrección")
        self.assertEqual(eventos[1].datos_anteriores["descripcion"], "Primera corrección")
        self.assertEqual(eventos[1].datos_nuevos["descripcion"], "Segunda corrección")
        gasto.refresh_from_db()
        self.assertEqual(gasto.descripcion, "Segunda corrección")

    def test_operacion_de_gasto_frente_a_suspension_de_obra(self):
        for gasto_primero in (True, False):
            with self.subTest(gasto_primero=gasto_primero):
                obra = self.otra_obra()
                crear = lambda: services_gastos.crear_gasto(
                    obra, self.entrada(fecha_gasto=timezone.localdate()),
                    self.supervisor,
                )
                suspender = lambda: services.suspender_obra(
                    obra, self.supervisor, "Pausa programada",
                )
                if gasto_primero:
                    uno, dos = self.en_orden(crear, suspender)
                else:
                    uno, dos = self.en_orden(suspender, crear)
                self.assertIsInstance(uno, Obra if not gasto_primero else GastoObra)
                self.assertIsInstance(dos, GastoObra if not gasto_primero else Obra)
                obra.refresh_from_db()
                self.assertEqual(obra.estado, "SUSPENDIDA")
                self.assertEqual(obra.gastos.count(), 1)

    def test_operaciones_de_gastos_distintos_serializan_por_obra(self):
        primero = self.crear_ok()
        segundo = self.crear_ok()

        def devolver(gasto):
            return services_gastos.devolver_gasto(self.obra, gasto.pk, {
                "cantidad": "1.000", "fecha_devolucion": timezone.localdate(),
                "motivo": "Devolución concurrente",
            }, self.supervisor)

        uno, dos = self.en_orden(
            lambda: devolver(primero), lambda: devolver(segundo),
        )
        self.assertIsInstance(uno, GastoObra)
        self.assertIsInstance(dos, GastoObra)
        primero.refresh_from_db()
        segundo.refresh_from_db()
        self.assertEqual(primero.cantidad_devuelta, Decimal("1.000"))
        self.assertEqual(segundo.cantidad_devuelta, Decimal("1.000"))
        self.assertEqual(primero.eventos.filter(tipo="DEVOLUCION").count(), 1)
        self.assertEqual(segundo.eventos.filter(tipo="DEVOLUCION").count(), 1)
