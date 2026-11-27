from django.test import TransactionTestCase
from django.utils import timezone

from apps.obras import services, services_costos as costos, services_gastos as gastos, services_turnos as turnos
from apps.obras.exceptions import CostosIncompletos, SinCambios, VersionCostosObsoleta
from apps.obras.models import ControlCostosObra, CostoObraEvento
from . import test_concurrencia_gastos
from .test_costos import CostosBase


class ConcurrenciaCostosTests(CostosBase, TransactionTestCase):
    en_orden = test_concurrencia_gastos.ConcurrenciaGastosTests.en_orden

    def setUp(self):
        self.setUpTestData()
        self.preparar()

    def validacion_revisada(self):
        # La versión se captura antes de lanzar las dos operaciones.
        datos = self.revision("Costos revisados")
        return lambda: costos.validar_costos(self.obra, datos, self.supervisor)

    def completa(self, *, material=False):
        turno = self.acreditar()
        gasto = self.crear_ok() if material else None
        self.declarar(**({"materiales_estado": "CON_REGISTROS"} if material else {}))
        return turno, gasto

    def test_devolucion_frente_validacion_ambos_ordenes(self):
        _, gasto = self.completa(material=True)
        for modificar_primero in (True, False):
            antes = self.control().version_actual
            modificar = lambda: gastos.devolver_gasto(self.obra, gasto.pk, {
                "cantidad": "0.500", "fecha_devolucion": timezone.localdate(), "motivo": "Sobrante",
            }, self.supervisor)
            if modificar_primero:
                _, validado = self.en_orden(modificar, self.validacion_revisada())
                self.assertIsInstance(validado, VersionCostosObsoleta)
                self.assertFalse(self.control().costos_validados)
                # Una nueva revisión explícita, no un reintento ciego.
                self.assertTrue(self.validar()["costos_validados"])
            else:
                # La validación anterior ya está vigente: retirarla mediante una
                # corrección real antes de probar el orden validar -> devolver.
                gastos.editar_gasto(self.obra, gasto.pk, {"observacion": "Verificada", "motivo": "Revisión"}, self.supervisor)
                antes += 1
                validado, _ = self.en_orden(self.validacion_revisada(), modificar)
                self.assertTrue(validado["costos_validados"])
                self.assertFalse(self.control().costos_validados)
            self.assertEqual(self.control().version_actual, antes + 1)

    def test_correccion_turno_frente_validacion_ambos_ordenes(self):
        turno, _ = self.completa()
        modificar = lambda: turnos.corregir_turno(self.obra, turno.pk, {
            "duracion_ajustada_segundos": 1800, "motivo": "Duración contrastada",
        }, self.supervisor)
        primero, segundo = self.en_orden(self.validacion_revisada(), modificar)
        self.assertTrue(primero["costos_validados"])
        self.assertFalse(self.control().costos_validados)
        self.revisar(turno)
        modificar = lambda: turnos.corregir_turno(self.obra, turno.pk, {
            "duracion_ajustada_segundos": 1900, "motivo": "Otra duración contrastada",
        }, self.supervisor)
        _, segundo = self.en_orden(modificar, self.validacion_revisada())
        self.assertIsInstance(segundo, VersionCostosObsoleta)
        self.assertIsNone(self.control().version_validada)
        with self.assertRaises(CostosIncompletos):
            self.validar()

    def test_cortesia_frente_validacion_ambos_ordenes(self):
        self.completa()
        crear = lambda: costos.registrar_cortesia(self.obra, {"justificacion": "Atención excepcional"}, self.supervisor)
        validado, _ = self.en_orden(self.validacion_revisada(), crear)
        self.assertTrue(validado["costos_validados"])
        self.assertFalse(self.control().costos_validados)
        rectificar = lambda: costos.registrar_cortesia(self.obra, {
            "justificacion": "Atención excepcional documentada", "motivo": "Respaldo adicional",
        }, self.supervisor)
        _, validado = self.en_orden(rectificar, self.validacion_revisada())
        self.assertIsInstance(validado, VersionCostosObsoleta)
        self.assertFalse(self.control().costos_validados)
        self.assertTrue(self.validar()["costos_validados"])

    def test_doble_validacion_un_solo_evento_y_version(self):
        self.completa()
        antes = self.control().version_actual
        primero, segundo = self.en_orden(self.validacion_revisada(), self.validacion_revisada())
        self.assertTrue(primero["costos_validados"])
        self.assertIsInstance(segundo, SinCambios)
        self.assertEqual(self.control().version_actual, antes)
        self.assertEqual(CostoObraEvento.objects.filter(tipo="VALIDACION").count(), 1)

    def test_consultas_concurrentes_sin_control_no_crean_filas(self):
        consultar = lambda: costos.consultar_control(self.obra, self.supervisor)
        primero, segundo = self.en_orden(consultar, consultar)
        self.assertEqual(primero, segundo)
        self.assertFalse(ControlCostosObra.objects.filter(obra=self.obra).exists())
        self.assertEqual(primero["version_actual"], 0)
        self.assertIsNone(primero["id"])

    def test_primeras_escrituras_concurrentes_crean_un_control(self):
        self.assertFalse(ControlCostosObra.objects.exists())

        def declarar(rubro):
            return costos.declarar_rubros(self.obra, {
                f"{rubro}_estado": "NO_APLICA", f"{rubro}_justificacion": "Sin registros",
                "motivo": "Revisión de rubro",
            }, self.supervisor)

        primero, segundo = self.en_orden(lambda: declarar("materiales"), lambda: declarar("otros"))
        self.assertEqual(primero["id"], segundo["id"])
        self.assertEqual(primero["version_actual"], 1)
        self.assertEqual(segundo["version_actual"], 2)
        self.assertEqual(ControlCostosObra.objects.filter(obra=self.obra).count(), 1)
        self.assertEqual(CostoObraEvento.objects.filter(tipo="DECLARACION").count(), 2)

    def test_alta_frente_validacion_exige_revision_actualizada(self):
        self.completa()
        primero, _ = self.en_orden(self.validacion_revisada(), lambda: self.crear_ok())
        self.assertTrue(primero["costos_validados"])
        self.assertFalse(self.control().costos_validados)
        self.assertEqual(self.control().materiales_estado, "PENDIENTE")
        _, segundo = self.en_orden(lambda: self.crear_ok(), self.validacion_revisada())
        self.assertIsInstance(segundo, VersionCostosObsoleta)
        self.assertFalse(self.control().costos_validados)
        # La revisión actualizada deriva automáticamente el rubro.
        self.assertTrue(self.validar()["costos_validados"])
        self.assertEqual(self.control().materiales_estado, "CON_REGISTROS")

    def test_reasignacion_frente_validacion_una_invalidacion(self):
        self.completa()
        antes = self.control().version_actual
        validado, _ = self.en_orden(self.validacion_revisada(), lambda: services.cambiar_tecnico(
            self.obra, self.otro_tecnico.pk, self.supervisor, "Nuevo principal",
        ))
        self.assertTrue(validado["costos_validados"])
        self.assertEqual(self.control().version_actual, antes + 1)
        self.assertFalse(self.control().costos_validados)
