from importlib import import_module
from uuid import uuid4

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.exceptions import IrreversibleError
from django.test import TransactionTestCase

from apps.finanzas import services_documentos, services_pagos, services_egresos
from apps.finanzas.tests.base import FinanzasBase
from apps.finanzas.tests.test_egresos import payload as egreso_payload
from apps.finanzas.validaciones import hoy_santiago
from apps.inventario.models import SolicitudMaterialObra, OperacionMaterial
from .test_solicitudes import SolicitudesBase


class MigracionSolicitudesTests(SolicitudesBase, TransactionTestCase):
    def test_upgrade_preserva_019b_021_y_no_fabrica_solicitudes(self):
        self.setUpTestData()
        self.preparar_solicitudes()
        self.recibir()
        e = self.entregar('2.000')
        self.devolver(e)
        principal = self.obra
        self.obra = self.otra_obra()
        FinanzasBase.items(self, self.obra.presupuesto)
        self.completa()
        self.finalizar()
        doc = services_documentos.registrar_documento(FinanzasBase.payload(self), self.finanzas)
        services_pagos.registrar_pago(doc.pk, {'monto': '100.00', 'fecha_pago': str(hoy_santiago()), 'medio': 'EFECTIVO',
            'referencia_respaldo': 'Pago recibido antes de 019C-1'}, self.finanzas, str(uuid4()))
        services_egresos.registrar_egreso(egreso_payload(), self.finanzas, str(uuid4()))
        self.obra = principal
        executor = MigrationExecutor(connection)
        hojas = executor.loader.graph.leaf_nodes()
        previo = [('inventario', '0004_integridad_materiales')]
        try:
            executor.migrate(previo)
            # Consultar exactamente las columnas existentes antes de 019C-1.
            hist = MigrationExecutor(connection).loader.project_state(previo + [('finanzas', '0003_egresos_flujo_dinero')]).apps
            modelos = [('inventario', n) for n in ['ArticuloInventario', 'ExistenciaInventario', 'EstadoValoracion', 'MovimientoInventario', 'OperacionMaterial']]
            modelos += [('obras', n) for n in ['Obra', 'ObraParticipante', 'GastoObra', 'CostoObraEvento', 'ControlCostosObra', 'CierreCostosObra']]
            modelos += [('finanzas', n) for n in ['DocumentoCobro', 'PagoDocumento', 'Egreso']]
            antes = {m: list(hist.get_model(*m).objects.order_by('pk').values()) for m in modelos}
            MigrationExecutor(connection).migrate(hojas)
            actual = MigrationExecutor(connection).loader.project_state(hojas).apps
            for m, filas in antes.items():
                self.assertTrue(filas, m)
                self.assertEqual(list(actual.get_model(*m).objects.order_by('pk').values(*filas[0])), filas, m)
            self.assertFalse(SolicitudMaterialObra.objects.exists())
            self.assertFalse(OperacionMaterial.objects.filter(solicitud_material__isnull=False).exists())
            s = self.solicitar()
            self.decidir(s)
            migration = import_module('apps.inventario.migrations.0006_integridad_solicitudes')
            with self.assertRaises(IrreversibleError), connection.schema_editor() as editor:
                migration.preservar_historia(actual, editor)
        finally:
            MigrationExecutor(connection).migrate(hojas)
