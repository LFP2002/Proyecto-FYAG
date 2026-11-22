from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

from apps.comercial.models import Presupuesto, PresupuestoEvento, PresupuestoItem
from .test_presupuesto_services import ServiciosPresupuestoMixin


class UpgradeConservador024(ServiciosPresupuestoMixin, TransactionTestCase):
    def test_upgrade_sin_migraciones_ni_reescritura_historica(self):
        self.setUpTestData()
        for estado in ('BORRADOR', 'PENDIENTE_GERENCIA', 'APROBADO_GERENCIA',
                       'RECHAZADO_GERENCIA', 'APROBADO_CLIENTE', 'RECHAZADO_FINANZAS'):
            self.preparar(estado)
        modelos = (Presupuesto, PresupuestoItem, PresupuestoEvento)
        antes = [list(m.objects.order_by('pk').values()) for m in modelos]
        executor = MigrationExecutor(connection)
        objetivos = executor.loader.graph.leaf_nodes()
        self.assertEqual(executor.migration_plan(objetivos), [])
        executor.migrate(objetivos)
        self.assertEqual(antes, [list(m.objects.order_by('pk').values()) for m in modelos])
