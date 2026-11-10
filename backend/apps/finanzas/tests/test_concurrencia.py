"""Conexiones PostgreSQL independientes, barreras y bloqueo observado; sin sleep."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from time import monotonic

from django.db import close_old_connections, connection, transaction
from django.test import TransactionTestCase
from rest_framework.exceptions import APIException

from apps.finanzas import services_documentos as services
from apps.finanzas.models import DocumentoCobro, CierreSinCobro, FinanzasEvento
from .base import FinanzasBase


class CarrerasPostgreSQL:
    def setUp(self):
        self.setUpTestData()
        self.preparar_finanzas()

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
            except APIException as exc:
                return exc
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            one = pool.submit(worker, first, 1)
            try:
                self.assertTrue(ready.wait(10), "Primera operación no alcanzó barrera")
                two = pool.submit(worker, second, 2)
                self.assertTrue(started.wait(10))
                observed = False
                deadline = monotonic() + 5
                while monotonic() < deadline:
                    with connection.cursor() as cursor:
                        cursor.execute("SELECT pg_blocking_pids(%s)", [pids[2]])
                        if pids[1] in cursor.fetchone()[0]:
                            observed = True
                            break
                    if two.done():
                        break
                self.assertTrue(observed, "No se observó bloqueo real en PostgreSQL")
            finally:
                release.set()
            return one.result(timeout=15), two.result(timeout=15)

class ConcurrenciaTests(FinanzasBase, CarrerasPostgreSQL, TransactionTestCase):
    def test_documentos_misma_obra_solo_uno_vigente(self):
        one, two = self.race(
            lambda: services.registrar_documento(self.payload(), self.finanzas),
            lambda: services.registrar_documento(self.payload(folio_externo="10002"), self.finanzas),
        )
        self.assertIsInstance(one, DocumentoCobro)
        self.assertEqual(two.detail["code"], "documento_duplicado")
        self.assertEqual(DocumentoCobro.objects.count(), 1)
        self.assertEqual(FinanzasEvento.objects.count(), 1)

    def test_folio_mismo_tipo_obras_distintas_constraint_db(self):
        otra = self.otra_finalizada()
        one, two = self.race(
            lambda: services.registrar_documento(self.payload(), self.finanzas),
            lambda: services.registrar_documento(self.payload(obra=otra.pk), self.finanzas),
        )
        self.assertIsInstance(one, DocumentoCobro)
        self.assertEqual(two.status_code, 409)
        self.assertEqual(two.detail["code"], "documento_duplicado")
        self.assertEqual(DocumentoCobro.objects.count(), 1)
        self.assertEqual(FinanzasEvento.objects.count(), 1)

    def test_reversion_doble_no_duplica_evento(self):
        obj = services.registrar_documento(self.payload(), self.finanzas)
        action = lambda: services.revertir_documento(obj.pk, {"motivo": "Rectificación", "referencia_rectificacion_externa": "Respaldo externo"}, self.finanzas)
        one, two = self.race(action, action)
        self.assertIsInstance(one, DocumentoCobro)
        self.assertEqual(two.detail["code"], "documento_ya_revertido")
        self.assertEqual(obj.eventos.count(), 2)

    def test_reversion_antes_de_re_registro(self):
        obj = services.registrar_documento(self.payload(), self.finanzas)
        one, two = self.race(
            lambda: services.revertir_documento(obj.pk, {"motivo": "Rectificación", "referencia_rectificacion_externa": "Respaldo externo"}, self.finanzas),
            lambda: services.registrar_documento(self.payload(folio_externo="10002"), self.finanzas),
        )
        self.assertEqual(one.estado, "REVERTIDO")
        self.assertEqual(two.estado, "VIGENTE")
        self.assertEqual(DocumentoCobro.objects.filter(estado="VIGENTE").count(), 1)
        self.assertEqual(FinanzasEvento.objects.count(), 3)


class SinCobroConcurrenciaTests(FinanzasBase, CarrerasPostgreSQL, TransactionTestCase):
    con_cortesia = True

    def test_doble_cierre_sin_cobro_un_evento(self):
        action = lambda: services.registrar_sin_cobro(self.obra.pk, {"motivo_registro": "Garantía archivada"}, self.finanzas)
        one, two = self.race(action, action)
        self.assertIsInstance(one, CierreSinCobro)
        self.assertEqual(two.detail["code"], "sin_cobro_ya_registrado")
        self.assertEqual(CierreSinCobro.objects.count(), 1)
        self.assertEqual(FinanzasEvento.objects.count(), 1)
