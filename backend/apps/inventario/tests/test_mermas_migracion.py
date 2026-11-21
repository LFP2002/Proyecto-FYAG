from importlib import import_module

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.exceptions import IrreversibleError
from django.test import TransactionTestCase

from apps.inventario.models import Merma
from .test_mermas import MermasBase


class MigracionMermasTests(MermasBase, TransactionTestCase):
    def test_upgrade_c1_preserva_historia_y_reversion_con_merma_bloqueada(self):
        self.setUpTestData()
        self.preparar_mermas()
        self.preparar_entrega()
        self.devolver(self.entrega, '1.000')
        self.decidir(self.solicitar())
        executor = MigrationExecutor(connection)
        hojas = executor.loader.graph.leaf_nodes()
        previo = [('inventario', '0006_integridad_solicitudes')]
        modelos = [('inventario', n) for n in ['ArticuloInventario', 'ExistenciaInventario', 'MovimientoInventario', 'EstadoValoracion', 'OperacionMaterial', 'SolicitudMaterialObra', 'SolicitudMaterialEvento']]
        modelos += [('obras', n) for n in ['Obra', 'ObraParticipante', 'GastoObra', 'CostoObraEvento', 'ControlCostosObra']]
        try:
            executor.migrate(previo)
            hist = MigrationExecutor(connection).loader.project_state(previo).apps
            antes = {m: list(hist.get_model(*m).objects.order_by('pk').values()) for m in modelos}
            MigrationExecutor(connection).migrate(hojas)
            actual = MigrationExecutor(connection).loader.project_state(hojas).apps
            for m, filas in antes.items():
                self.assertTrue(filas, m)
                self.assertEqual(list(actual.get_model(*m).objects.order_by('pk').values(*filas[0])), filas, m)
            self.assertFalse(Merma.objects.exists())
            self.resolver(self.informar('OBRA'))
            migration = import_module('apps.inventario.migrations.0008_integridad_mermas')
            with self.assertRaises(IrreversibleError), connection.schema_editor() as editor:
                migration.restaurar(actual, editor)
        finally:
            MigrationExecutor(connection).migrate(hojas)
