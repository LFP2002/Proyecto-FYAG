"""PostgreSQL real: espera observada, conexiones independientes, sin sleeps."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from time import monotonic
from uuid import uuid4

from django.db import close_old_connections, connection, transaction
from django.test import TransactionTestCase

from apps.finanzas import services_egresos as egresos, services_pagos as pagos
from apps.finanzas import consultas_egresos as consultas
from apps.finanzas.models import Egreso, EgresoEvento
from apps.usuarios.models import Usuario
from .test_concurrencia import CarrerasPostgreSQL
from .test_egresos import EgresosBase, payload
from .test_flujo_dinero import periodo
from .test_pagos import PagosBase


class EgresosConcurrenciaTests(EgresosBase, CarrerasPostgreSQL, TransactionTestCase):
    def test_uuid_igual_payload_igual_un_alta_un_evento(self):
        key = str(uuid4())
        action = lambda: egresos.registrar_egreso(payload(), self.finanzas, key)
        uno, dos = self.race(action, action)
        self.assertTrue(uno[1])
        self.assertFalse(dos[1])
        self.assertEqual(uno[0].pk, dos[0].pk)
        self.assertEqual(Egreso.objects.count(), 1)
        self.assertEqual(EgresoEvento.objects.count(), 1)

    def test_uuid_igual_payload_distinto_conflicto_controlado(self):
        key = str(uuid4())
        uno, dos = self.race(
            lambda: egresos.registrar_egreso(payload(), self.finanzas, key),
            lambda: egresos.registrar_egreso(payload(monto='99.00'), self.finanzas, key))
        self.assertTrue(uno[1])
        self.assertEqual(dos.status_code, 409)
        self.assertEqual(dos.detail['code'], 'idempotencia_conflictiva')
        self.assertEqual(EgresoEvento.objects.count(), 1)

    def test_doble_anulacion_un_evento_y_conflicto(self):
        e = self.crear_egreso()
        action = lambda: egresos.anular_egreso(e.pk, {'motivo': 'Error', 'referencia_correccion': 'R'}, self.finanzas)
        uno, dos = self.race(action, action)
        self.assertFalse(uno.activo)
        self.assertEqual(dos.status_code, 409)
        self.assertEqual(e.eventos.count(), 2)

    def test_revocacion_durante_espera_anulacion(self):
        e = self.crear_egreso()

        def bloquear_y_revocar():
            Egreso.objects.select_for_update().get(pk=e.pk)
            Usuario.objects.filter(pk=self.finanzas.pk).update(sesion_version=self.finanzas.sesion_version + 1)

        _, dos = self.race(bloquear_y_revocar,
            lambda: egresos.anular_egreso(e.pk, {'motivo': 'Error', 'referencia_correccion': 'R'}, self.finanzas))
        self.assertEqual(dos.status_code, 401)
        e.refresh_from_db()
        self.assertTrue(e.activo)
        self.assertEqual(e.eventos.count(), 1)

    def test_revocacion_durante_espera_uuid(self):
        key = str(uuid4())

        def crear_y_revocar():
            result = egresos.registrar_egreso(payload(), self.finanzas, key)
            Usuario.objects.filter(pk=self.finanzas.pk).update(sesion_version=self.finanzas.sesion_version + 1)
            return result

        _, dos = self.race(crear_y_revocar, lambda: egresos.registrar_egreso(payload(), self.finanzas, key))
        self.assertEqual(dos.status_code, 401)
        self.assertEqual(Egreso.objects.count(), 1)
        self.assertEqual(EgresoEvento.objects.count(), 1)


class SnapshotFlujoTests(EgresosBase, PagosBase, TransactionTestCase):
    def setUp(self):
        self.setUpTestData()
        self.preparar_pagos()

    def comprobar_snapshot(self, mutacion, anterior, siguiente):
        started = Event()
        pid = {}
        lock = 210021

        def leer():
            close_old_connections()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET statement_timeout = '15s'")
                    cursor.execute('SELECT pg_backend_pid()')
                    pid['lector'] = cursor.fetchone()[0]

                def pausa(execute, sql, params, many, context):
                    if 'SPEC-021 snapshot' in sql:
                        # El snapshot de ESTA sentencia precede a la espera por
                        # advisory lock; no se pausa antes de enviar el SELECT.
                        sql = 'WITH espera AS MATERIALIZED (SELECT pg_advisory_xact_lock(%s)) ' + sql
                        sql = sql.rstrip() + ' FROM espera'
                        params = [lock, *params]
                        started.set()
                    return execute(sql, params, many, context)

                with connection.execute_wrapper(pausa):
                    return consultas.resumen(self.finanzas, periodo())
            finally:
                connection.close()

        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_advisory_lock(%s)', [lock])
        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(leer)
            try:
                self.assertTrue(started.wait(10))
                observed = False
                deadline = monotonic() + 5
                while monotonic() < deadline:
                    with connection.cursor() as cursor:
                        cursor.execute('SELECT pg_backend_pid() = ANY(pg_blocking_pids(%s))', [pid['lector']])
                        if cursor.fetchone()[0]:
                            observed = True
                            break
                    if future.done():
                        break
                self.assertTrue(observed, 'No se observó espera del SELECT de resumen')
                # Una sola confirmación cambia ambos dominios mientras SELECT
                # ya tiene su snapshot. El resultado no puede mezclar cortes.
                with transaction.atomic():
                    mutacion()
            finally:
                with connection.cursor() as cursor:
                    cursor.execute('SELECT pg_advisory_unlock(%s)', [lock])
            resultado = future.result(timeout=20)
        self.assertEqual((resultado['ingresos_recibidos'], resultado['egresos_pagados']), anterior)
        resultado = consultas.resumen(self.finanzas, periodo())
        self.assertEqual((resultado['ingresos_recibidos'], resultado['egresos_pagados']), siguiente)

    def test_snapshot_unico_durante_altas_pago_y_egreso(self):
        def altas():
            pagos.registrar_pago(self.doc.pk, self.pago_data(), self.finanzas, str(uuid4()))
            self.crear_egreso()
        self.comprobar_snapshot(altas, ('0.00', '0.00'), ('100.13', '100.25'))

    def test_snapshot_unico_durante_anulaciones_pago_y_egreso(self):
        p, _ = pagos.registrar_pago(self.doc.pk, self.pago_data(), self.finanzas, str(uuid4()))
        e = self.crear_egreso()

        def anulaciones():
            pagos.anular_pago(self.doc.pk, p.pk, {'motivo': 'Error', 'referencia_reversion_externa': 'R'}, self.finanzas)
            egresos.anular_egreso(e.pk, {'motivo': 'Error', 'referencia_correccion': 'R'}, self.finanzas)
        self.comprobar_snapshot(anulaciones, ('100.13', '100.25'), ('0.00', '0.00'))

    def test_egreso_no_espera_locks_raiz_de_pagos(self):
        from apps.comercial.models import Presupuesto
        from apps.obras.models import Obra

        def registrar():
            close_old_connections()
            try:
                return self.crear_egreso(obra=self.obra.pk).pk
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=1) as pool:
            with transaction.atomic():
                Presupuesto.objects.select_for_update(no_key=True).get(pk=self.obra.presupuesto_id)
                Obra.objects.select_for_update(no_key=True).get(pk=self.obra.pk)
                # Los servicios previos usan FOR UPDATE; un egreso sin Obra
                # es totalmente independiente. Para FK informativa, NO KEY
                # UPDATE demuestra compatibilidad con el KEY SHARE nativo.
                self.assertGreater(pool.submit(registrar).result(timeout=10), 0)
