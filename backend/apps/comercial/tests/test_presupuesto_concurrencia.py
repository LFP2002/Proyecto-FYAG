from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Event
from time import monotonic

from django.db import close_old_connections, connection, transaction
from django.test import TransactionTestCase

from apps.comercial import services_presupuestos as servicios
from apps.comercial.exceptions import (
    ClienteInactivo,
    ErrorPresupuesto,
    EstadoIncompatible,
    OrdenDuplicado,
)
from apps.comercial.models import Cliente, Presupuesto
from apps.comercial.services import desactivar_cliente
from apps.comercial.tests.test_presupuesto_services import (
    ServiciosPresupuestoMixin,
    datos_item,
)


class PresupuestoConcurrenciaTests(
    ServiciosPresupuestoMixin, TransactionTestCase
):
    def setUp(self):
        # TransactionTestCase no ejecuta setUpTestData automáticamente.
        self.setUpTestData()

    def ejecutar_en_orden(self, primera, segunda, recurso):
        """Observa el bloqueo entre conexiones reales antes de liberarlo."""
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
                        type(recurso).objects.select_for_update().get(
                            pk=recurso.pk
                        )
                        bloqueado.set()
                        if not liberar.wait(10):
                            raise AssertionError("No se liberó el primer lock")
                        resultado = funcion()
                else:
                    segunda_lista.set()
                    resultado = funcion()
                return resultado
            except ErrorPresupuesto as exc:
                return exc
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as executor:
            uno = executor.submit(ejecutar, primera, 1)
            try:
                self.assertTrue(bloqueado.wait(10), "Primer lock no adquirido")
                dos = executor.submit(ejecutar, segunda, 2)
                self.assertTrue(segunda_lista.wait(10))
                limite = monotonic() + 5
                espera_observada = False
                # Se verifica el grafo de locks real, no una espera por sleep.
                while monotonic() < limite:
                    with connection.cursor() as cursor:
                        cursor.execute(
                            "SELECT pg_blocking_pids(%s)", [pids[2]]
                        )
                        if pids[1] in cursor.fetchone()[0]:
                            espera_observada = True
                            break
                    if dos.done():
                        break
                self.assertTrue(
                    espera_observada, "El servicio no esperó el lock"
                )
            finally:
                liberar.set()
            return uno.result(timeout=15), dos.result(timeout=15)

    def test_gerencia_aprobar_antes_de_rechazar(self):
        presupuesto = self.preparar("PENDIENTE_GERENCIA")
        uno, dos = self.ejecutar_en_orden(
            lambda: servicios.aprobar_gerencia(presupuesto, self.usuario),
            lambda: servicios.rechazar_gerencia(
                presupuesto, self.usuario, "Rechazo"
            ), presupuesto,
        )
        self.assertEqual(uno.estado, "APROBADO_GERENCIA")
        self.assertIsInstance(dos, EstadoIncompatible)
        self.assertEqual(presupuesto.eventos.count(), 2)

    def test_gerencia_rechazar_antes_de_aprobar(self):
        presupuesto = self.preparar("PENDIENTE_GERENCIA")
        uno, dos = self.ejecutar_en_orden(
            lambda: servicios.rechazar_gerencia(
                presupuesto, self.usuario, "Rechazo"
            ),
            lambda: servicios.aprobar_gerencia(presupuesto, self.usuario),
            presupuesto,
        )
        self.assertEqual(uno.estado, "RECHAZADO_GERENCIA")
        self.assertIsInstance(dos, EstadoIncompatible)
        self.assertEqual(presupuesto.eventos.count(), 2)

    def test_cliente_anulacion_primero_impide_aprobacion(self):
        presupuesto = self.preparar("ENVIADO_CLIENTE")
        uno, dos = self.ejecutar_en_orden(
            lambda: servicios.anular_presupuesto(
                presupuesto, self.usuario, "Retirado"
            ),
            lambda: servicios.registrar_aprobacion_cliente(
                presupuesto, self.usuario
            ), presupuesto,
        )
        self.assertEqual(uno.estado, "ANULADO")
        self.assertIsInstance(dos, EstadoIncompatible)
        self.assertEqual(presupuesto.eventos.count(), 2)

    def test_cliente_aprobacion_primero_permite_ambos_exitos(self):
        presupuesto = self.preparar("ENVIADO_CLIENTE")
        uno, dos = self.ejecutar_en_orden(
            lambda: servicios.registrar_aprobacion_cliente(
                presupuesto, self.usuario
            ),
            lambda: servicios.anular_presupuesto(
                presupuesto, self.usuario, "Cambio comercial"
            ), presupuesto,
        )
        self.assertEqual(uno.estado, "APROBADO_CLIENTE")
        self.assertEqual(dos.estado, "ANULADO")
        self.assertEqual(list(presupuesto.eventos.exclude(
            estado_anterior=None
        ).values_list("estado_anterior", "estado_nuevo")), [
            ("ENVIADO_CLIENTE", "APROBADO_CLIENTE"),
            ("APROBADO_CLIENTE", "ANULADO"),
        ])

    def test_item_antes_de_salida_recalcula_con_nuevos_valores(self):
        presupuesto = self.crear()
        item = servicios.crear_item(presupuesto, datos_item())
        uno, dos = self.ejecutar_en_orden(
            lambda: servicios.modificar_item(presupuesto, item, {
                "precio_unitario": Decimal("0"),
            }),
            lambda: servicios.enviar_gerencia(presupuesto, self.usuario),
            presupuesto,
        )
        self.assertEqual(uno.precio_unitario, Decimal("0.00"))
        self.assertIsInstance(dos, ErrorPresupuesto)
        self.assertEqual(dos.codigo, "datos_invalidos")
        presupuesto.refresh_from_db()
        self.assertEqual(presupuesto.estado, "BORRADOR")
        self.assertEqual(presupuesto.eventos.count(), 1)

    def test_salida_antes_de_item_congela_contenido(self):
        presupuesto = self.crear()
        item = servicios.crear_item(presupuesto, datos_item())
        uno, dos = self.ejecutar_en_orden(
            lambda: servicios.enviar_gerencia(presupuesto, self.usuario),
            lambda: servicios.modificar_item(presupuesto, item, {
                "precio_unitario": Decimal("0"),
            }), presupuesto,
        )
        self.assertEqual(uno.estado, "PENDIENTE_GERENCIA")
        self.assertIsInstance(dos, EstadoIncompatible)
        item.refresh_from_db()
        self.assertEqual(item.precio_unitario, Decimal("100.25"))

    def test_orden_duplicado_concurrente(self):
        presupuesto = self.crear()
        uno, dos = self.ejecutar_en_orden(
            lambda: servicios.crear_item(presupuesto, datos_item()),
            lambda: servicios.crear_item(presupuesto, datos_item()),
            presupuesto,
        )
        self.assertEqual(uno.orden, 1)
        self.assertIsInstance(dos, OrdenDuplicado)
        self.assertEqual(presupuesto.items.count(), 1)

    def test_desactivacion_cliente_antes_de_salida(self):
        presupuesto = self.crear()
        servicios.crear_item(presupuesto, datos_item())
        uno, dos = self.ejecutar_en_orden(
            lambda: desactivar_cliente(self.cliente),
            lambda: servicios.enviar_gerencia(presupuesto, self.usuario),
            self.cliente,
        )
        self.assertIsInstance(uno, Cliente)
        self.assertFalse(uno.activo)
        self.assertIsInstance(dos, ClienteInactivo)
        presupuesto.refresh_from_db()
        self.assertEqual(presupuesto.estado, "BORRADOR")

    def test_revisiones_concurrentes_son_filas_independientes(self):
        origen = self.preparar("ANULADO")
        uno, dos = self.ejecutar_en_orden(
            lambda: servicios.crear_revision(origen, self.usuario),
            lambda: servicios.crear_revision(origen, self.usuario), origen,
        )
        self.assertIsInstance(uno, Presupuesto)
        self.assertIsInstance(dos, Presupuesto)
        self.assertNotEqual(uno.pk, dos.pk)
        self.assertEqual(origen.revisiones.count(), 2)
        self.assertEqual(uno.eventos.count(), 1)
        self.assertEqual(dos.eventos.count(), 1)
