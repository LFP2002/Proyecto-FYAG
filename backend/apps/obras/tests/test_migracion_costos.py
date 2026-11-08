from datetime import timedelta

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone

from apps.obras import services_costos
from apps.obras.models import ControlCostosObra, CostoObraEvento, GastoObra, TurnoObra
from .test_costos import CostosBase


class MigracionControlCostosTests(CostosBase, TransactionTestCase):
    anterior = [("obras", "0009_gastos_costos")]

    def setUp(self):
        self.setUpTestData()
        self.preparar()
        executor = MigrationExecutor(connection)
        self.actuales = executor.loader.graph.leaf_nodes()
        executor.migrate(self.anterior)
        self.addCleanup(lambda: MigrationExecutor(connection).migrate(self.actuales))
        self.apps_historicas = executor.loader.project_state(self.anterior).apps

    def test_preserva_gastos_eventos_y_turnos_previos_sin_backfill_ficticio(self):
        Gasto = self.apps_historicas.get_model("obras", "GastoObra")
        Evento = self.apps_historicas.get_model("obras", "CostoObraEvento")
        Turno = self.apps_historicas.get_model("obras", "TurnoObra")
        gasto = Gasto.objects.create(obra_id=self.obra.pk, tipo="MATERIAL", descripcion="Material histórico", unidad="metro", cantidad="2.500", cantidad_devuelta="1.000", costo_unitario_neto="8000.00", fecha_gasto=timezone.localdate(), registrado_por_id=self.supervisor.pk)
        for tipo, datos in (("ALTA", {"cantidad": "2.500"}), ("DEVOLUCION", {"devolucion": {"cantidad": "1.000", "fecha": timezone.localdate().isoformat()}})):
            Evento.objects.create(obra_id=self.obra.pk, gasto=gasto, tipo=tipo, registrado_por_id=self.supervisor.pk, motivo="Registro histórico", datos_nuevos=datos)
        inicio = timezone.now()
        Turno.objects.create(obra_id=self.obra.pk, tecnico_id=self.tecnico.pk, iniciado_en=inicio, terminado_en=inicio + timedelta(seconds=3600), modo_cierre="TECNICO", cerrado_por_id=self.tecnico.pk, duracion_segundos="3600.000000", descripcion_trabajo="Histórico", estado_revision="VALIDADO", costo_hora_neto="10000.00", revisado_por_id=self.supervisor.pk, revisado_en=timezone.now(), observacion_revision="Acreditado")
        gastos_antes = list(Gasto.objects.values())
        turnos_antes = list(Turno.objects.values())
        eventos_antes = list(Evento.objects.order_by("id").values())
        MigrationExecutor(connection).migrate(self.actuales)
        self.assertEqual(list(GastoObra.objects.values()), gastos_antes)
        self.assertEqual(list(TurnoObra.objects.values()), turnos_antes)
        eventos = list(CostoObraEvento.objects.order_by("id").values())
        for evento in eventos:
            self.assertIsNone(evento.pop("control_id"))
            self.assertIsNone(evento.pop("cortesia_id"))
        self.assertEqual(eventos, eventos_antes)
        self.assertFalse(ControlCostosObra.objects.exists())
        resumen = services_costos.resumen_costos(self.obra, self.supervisor)
        self.assertEqual(resumen["materiales_total"], "12000.00")
        self.assertEqual(resumen["mano_obra_total"], "10000.00")
        self.assertEqual(resumen["costo_total"], "22000.00")
        self.assertEqual(resumen["version_actual"], 0)
        self.assertEqual(resumen["materiales_estado"], "PENDIENTE")
        self.assertFalse(resumen["costos_validados"])
        self.assertEqual(services_costos.resumen_costos(self.obra, self.supervisor), resumen)
        virtual = services_costos.consultar_control(self.obra, self.supervisor)
        self.assertIsNone(virtual["id"])
        self.assertIsNone(virtual["creado_en"])
        self.assertFalse(ControlCostosObra.objects.exists())
        self.assertEqual(list(GastoObra.objects.values()), gastos_antes)
        self.assertEqual(list(TurnoObra.objects.values()), turnos_antes)
        self.assertEqual(CostoObraEvento.objects.count(), len(eventos_antes))
