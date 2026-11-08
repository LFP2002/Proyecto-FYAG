from django.test import TransactionTestCase
from django.utils import timezone

from apps.obras import services, services_costos as costos, services_gastos as gastos, services_turnos as turnos
from apps.obras.exceptions import CostosIncompletos, EstadoIncompatible
from apps.obras.models import CierreCostosObra
from . import test_concurrencia_gastos
from .test_finalizacion import FinalizacionBase


class ConcurrenciaFinalizacionTests(FinalizacionBase, TransactionTestCase):
    en_orden = test_concurrencia_gastos.ConcurrenciaGastosTests.en_orden

    def setUp(self):
        self.setUpTestData()
        self.preparar()

    def escenario(self, *, material=False):
        self.obra = self.otra_obra()
        self.url = f"/api/obras/{self.obra.pk}/gastos/"
        return self.completa(material=material)

    def test_dos_finalizaciones_un_solo_cierre_y_evento(self):
        self.completa()
        primero, segundo = self.en_orden(self.finalizar, self.finalizar)
        self.assertEqual(primero.estado, "FINALIZADA")
        self.assertIsInstance(segundo, EstadoIncompatible)
        self.assertEqual(CierreCostosObra.objects.filter(obra=self.obra).count(), 1)
        self.assertEqual(self.obra.eventos.filter(estado_nuevo="FINALIZADA").count(), 1)

    def test_finalizar_frente_devolucion_y_correccion_gasto_ambos_ordenes(self):
        for accion in ("devolver", "corregir"):
            for finalizar_primero in (True, False):
                with self.subTest(accion=accion, finalizar_primero=finalizar_primero):
                    _, gasto = self.escenario(material=True)
                    modificar = (lambda: gastos.devolver_gasto(self.obra, gasto.pk, {
                        "cantidad": "1.000", "fecha_devolucion": timezone.localdate(), "motivo": "Sobrante",
                    }, self.supervisor)) if accion == "devolver" else (lambda: gastos.editar_gasto(self.obra, gasto.pk, {
                        "costo_unitario_neto": "13000.00", "motivo": "Corrección de factura",
                    }, self.supervisor))
                    if finalizar_primero:
                        primero, segundo = self.en_orden(self.finalizar, modificar)
                        self.assertEqual(primero.estado, "FINALIZADA")
                        self.assertIsInstance(segundo, EstadoIncompatible)
                        self.assertEqual(CierreCostosObra.objects.get(obra=self.obra).costo_total, 39250)
                    else:
                        _, segundo = self.en_orden(modificar, self.finalizar)
                        self.assertIsInstance(segundo, CostosIncompletos)
                        self.assertFalse(CierreCostosObra.objects.filter(obra=self.obra).exists())
                        self.assertFalse(self.control().costos_validados)

    def test_finalizar_frente_correccion_turno_ambos_ordenes(self):
        for finalizar_primero in (True, False):
            turno, _ = self.escenario()
            modificar = lambda: turnos.corregir_turno(self.obra, turno.pk, {
                "duracion_ajustada_segundos": 1800, "motivo": "Duración contrastada",
            }, self.supervisor)
            if finalizar_primero:
                primero, segundo = self.en_orden(self.finalizar, modificar)
                self.assertEqual(primero.estado, "FINALIZADA")
                self.assertIsInstance(segundo, EstadoIncompatible)
            else:
                _, segundo = self.en_orden(modificar, self.finalizar)
                self.assertIsInstance(segundo, CostosIncompletos)
                self.assertFalse(CierreCostosObra.objects.filter(obra=self.obra).exists())

    def test_finalizar_frente_revision_pendiente_no_valida_implicitamente(self):
        for finalizar_primero in (True, False):
            turno, _ = self.escenario()
            turnos.corregir_turno(self.obra, turno.pk, {"duracion_ajustada_segundos": 1800, "motivo": "Ajuste"}, self.supervisor)
            # Incluso una marca aparentemente vigente no reemplaza el recálculo.
            self.marcar_validado()
            revisar = lambda: self.revisar(turno)
            if finalizar_primero:
                primero, segundo = self.en_orden(self.finalizar, revisar)
                self.assertIsInstance(primero, CostosIncompletos)
                self.assertEqual(segundo.estado_revision, "VALIDADO")
            else:
                primero, segundo = self.en_orden(revisar, self.finalizar)
                self.assertEqual(primero.estado_revision, "VALIDADO")
                self.assertIsInstance(segundo, CostosIncompletos)
            self.assertFalse(CierreCostosObra.objects.filter(obra=self.obra).exists())

    def test_finalizar_frente_nueva_validacion_ambos_ordenes(self):
        for finalizar_primero in (True, False):
            _, gasto = self.escenario(material=True)
            gastos.editar_gasto(self.obra, gasto.pk, {"observacion": "Respaldo", "motivo": "Nueva evidencia"}, self.supervisor)
            if finalizar_primero:
                primero, segundo = self.en_orden(self.finalizar, self.validar)
                self.assertIsInstance(primero, CostosIncompletos)
                self.assertTrue(segundo["costos_validados"])
                self.assertFalse(CierreCostosObra.objects.filter(obra=self.obra).exists())
            else:
                primero, segundo = self.en_orden(self.validar, self.finalizar)
                self.assertTrue(primero["costos_validados"])
                self.assertEqual(segundo.estado, "FINALIZADA")
                self.assertEqual(CierreCostosObra.objects.filter(obra=self.obra).count(), 1)

    def test_finalizar_frente_suspension_ambos_ordenes(self):
        for finalizar_primero in (True, False):
            self.escenario()
            suspender = lambda: services.suspender_obra(self.obra, self.supervisor, "Pausa")
            if finalizar_primero:
                primero, segundo = self.en_orden(self.finalizar, suspender)
                self.assertEqual(primero.estado, "FINALIZADA")
                self.assertIsInstance(segundo, EstadoIncompatible)
            else:
                primero, segundo = self.en_orden(suspender, self.finalizar)
                self.assertEqual(primero.estado, "SUSPENDIDA")
                self.assertIsInstance(segundo, EstadoIncompatible)
                self.assertFalse(CierreCostosObra.objects.filter(obra=self.obra).exists())

    def test_finalizar_frente_reasignacion_ambos_ordenes(self):
        for finalizar_primero in (True, False):
            self.escenario()
            reasignar = lambda: services.cambiar_tecnico(self.obra, self.otro_tecnico.pk, self.supervisor, "Nuevo principal")
            if finalizar_primero:
                primero, segundo = self.en_orden(self.finalizar, reasignar)
                self.assertEqual(primero.estado, "FINALIZADA")
                self.assertIsInstance(segundo, EstadoIncompatible)
            else:
                _, segundo = self.en_orden(reasignar, self.finalizar)
                self.assertIsInstance(segundo, CostosIncompletos)
                self.assertFalse(CierreCostosObra.objects.filter(obra=self.obra).exists())

    def test_finalizar_frente_rectificacion_cortesia_ambos_ordenes(self):
        for finalizar_primero in (True, False):
            self.escenario()
            costos.registrar_cortesia(self.obra, {"justificacion": "Atención excepcional"}, self.supervisor)
            self.validar()
            rectificar = lambda: costos.registrar_cortesia(self.obra, {
                "justificacion": "Atención excepcional documentada", "motivo": "Respaldo adicional",
            }, self.supervisor)
            if finalizar_primero:
                primero, segundo = self.en_orden(self.finalizar, rectificar)
                self.assertEqual(primero.estado, "FINALIZADA")
                self.assertIsInstance(segundo, EstadoIncompatible)
            else:
                _, segundo = self.en_orden(rectificar, self.finalizar)
                self.assertIsInstance(segundo, CostosIncompletos)
                self.assertFalse(CierreCostosObra.objects.filter(obra=self.obra).exists())
