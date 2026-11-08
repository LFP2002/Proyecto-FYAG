from django.db import connection, IntegrityError, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

from apps.obras.models import CierreCostosObra, ObraEvento
from .test_finalizacion import FinalizacionBase


class MigracionFinalizacionTests(FinalizacionBase, TransactionTestCase):
    anterior = [("obras", "0010_control_costos_cortesia")]

    def setUp(self):
        self.setUpTestData()
        self.preparar()
        self.completa(material=True)
        executor = MigrationExecutor(connection)
        self.actuales = executor.loader.graph.leaf_nodes()
        executor.migrate(self.anterior)
        self.addCleanup(lambda: MigrationExecutor(connection).migrate(self.actuales))

    def test_migracion_preserva_historicos_y_no_fabrica_cierres(self):
        antes = {clave: filas for clave, filas in self.estado_sin_cierre().items()}
        MigrationExecutor(connection).migrate(self.actuales)
        self.assertEqual(self.estado_sin_cierre(), antes)
        self.assertFalse(CierreCostosObra.objects.exists())
        self.finalizar()
        self.assertEqual(CierreCostosObra.objects.get(obra=self.obra).costo_total, 39250)

    def estado_sin_cierre(self):
        from apps.obras.models import Obra, ControlCostosObra, CostoObraEvento, GastoObra, TurnoObra
        return {modelo.__name__: list(modelo.objects.order_by("pk").values()) for modelo in (
            Obra, ControlCostosObra, ObraEvento, CostoObraEvento, GastoObra, TurnoObra,
        )}

    def test_constraint_amplia_solo_en_proceso_a_finalizada(self):
        MigrationExecutor(connection).migrate(self.actuales)
        permitidos = {("PLANIFICADA", "EN_PROCESO"), ("EN_PROCESO", "SUSPENDIDA"),
                      ("SUSPENDIDA", "EN_PROCESO"), ("EN_PROCESO", "FINALIZADA")}
        estados = ("PLANIFICADA", "EN_PROCESO", "SUSPENDIDA", "FINALIZADA", "CANCELADA")
        for anterior in estados:
            for nuevo in estados:
                evento = ObraEvento(obra=self.obra, tipo="CAMBIO_ESTADO", estado_anterior=anterior,
                                    estado_nuevo=nuevo, registrado_por=self.supervisor, motivo="Prueba de transición")
                if (anterior, nuevo) in permitidos:
                    with transaction.atomic():
                        ObraEvento.objects.bulk_create([evento])
                else:
                    with self.subTest(anterior=anterior, nuevo=nuevo), self.assertRaises(IntegrityError), transaction.atomic():
                        ObraEvento.objects.bulk_create([evento])
