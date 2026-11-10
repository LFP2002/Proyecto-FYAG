from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

from apps.obras.models import Obra, CierreCostosObra
from apps.comercial.models import Presupuesto
from .base import FinanzasBase


class MigracionTests(FinanzasBase, TransactionTestCase):
    def test_instalacion_sobre_historia_sin_generar_documentos(self):
        self.setUpTestData()
        self.preparar_finanzas()
        ids = (self.obra.pk, self.presupuesto.pk, self.cliente.pk)
        before = self.estado_persistido()
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        previous = [(app, name) for app, name in latest if app != "finanzas"] + [("finanzas", None)]
        executor.migrate(previous)
        try:
            self.assertEqual(Obra.objects.get(pk=ids[0]).presupuesto_id, ids[1])
            self.assertEqual(Presupuesto.objects.get(pk=ids[1]).cliente_id, ids[2])
            self.assertTrue(CierreCostosObra.objects.filter(obra_id=ids[0]).exists())
            executor = MigrationExecutor(connection)
            executor.migrate(latest)
            apps = executor.loader.project_state(latest).apps
            for name in ["DocumentoCobro", "CierreSinCobro", "FinanzasEvento"]:
                self.assertEqual(apps.get_model("finanzas", name).objects.count(), 0)
            self.assertEqual(self.estado_persistido(), before)
        finally:
            MigrationExecutor(connection).migrate(latest)
