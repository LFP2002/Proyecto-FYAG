from datetime import timedelta

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone

from .test_turnos import TurnosBase


class MigracionCierreAdministrativoTests(TurnosBase, TransactionTestCase):
    anterior = [("obras", "0007_turnos_evidencias")]

    def setUp(self):
        self.setUpTestData()
        self.preparar()
        executor = MigrationExecutor(connection)
        self.actuales = executor.loader.graph.leaf_nodes()
        executor.migrate(self.anterior)
        apps = executor.loader.project_state(self.anterior).apps
        self.Turno = apps.get_model("obras", "TurnoObra")
        self.Evento = apps.get_model("obras", "TurnoObraEvento")

    def tearDown(self):
        # También restaurar esquema si la migración rechazó históricos ambiguos.
        self.Evento.objects.all().delete()
        self.Turno.objects.all().delete()
        MigrationExecutor(connection).migrate(self.actuales)
        super().tearDown()

    def cerrado(self):
        inicio = timezone.now() - timedelta(seconds=60)
        return self.Turno.objects.create(
            obra_id=self.obra.pk, tecnico_id=self.tecnico.pk,
            iniciado_en=inicio, terminado_en=inicio + timedelta(seconds=60),
            duracion_segundos=60, descripcion_trabajo="Histórica", estado_revision="PENDIENTE_REVISION",
        )

    def evento(self, turno, actor):
        return self.Evento.objects.create(turno=turno, tipo="CIERRE", registrado_por_id=actor.pk,
            motivo="Cierre histórico", datos_anteriores={}, datos_nuevos={"descripcion_trabajo": "Histórica"})

    def test_backfill_actor_del_evento_sin_modificar_historia(self):
        cerrado = self.cerrado()
        self.evento(cerrado, self.tecnico)
        abierto = self.Turno.objects.create(obra_id=self.obra.pk, tecnico_id=self.tecnico.pk, iniciado_en=timezone.now())
        original = self.Turno.objects.values().get(pk=cerrado.pk)
        eventos = list(self.Evento.objects.values())
        MigrationExecutor(connection).migrate(self.actuales)
        from apps.obras.models import TurnoObra, TurnoObraEvento
        nuevo = TurnoObra.objects.values().get(pk=cerrado.pk)
        self.assertEqual(nuevo.pop("modo_cierre"), "TECNICO")
        self.assertEqual(nuevo.pop("cerrado_por_id"), self.tecnico.pk)
        self.assertEqual(nuevo, original)
        abierto = TurnoObra.objects.get(pk=abierto.pk)
        self.assertIsNone(abierto.modo_cierre)
        self.assertIsNone(abierto.cerrado_por_id)
        self.assertEqual(list(TurnoObraEvento.objects.values()), eventos)

    def test_historicos_sin_evento_duplicados_o_actor_incoherente_detienen_migracion(self):
        for caso in ("sin_evento", "duplicado", "otro_actor"):
            with self.subTest(caso=caso):
                turno = self.cerrado()
                if caso == "duplicado":
                    self.evento(turno, self.tecnico)
                    self.evento(turno, self.tecnico)
                elif caso == "otro_actor":
                    self.evento(turno, self.supervisor)
                with self.assertRaisesRegex(RuntimeError, f"Turno {turno.pk}.*inequívoco"):
                    MigrationExecutor(connection).migrate(self.actuales)
                self.assertEqual(self.Turno.objects.get(pk=turno.pk).descripcion_trabajo, "Histórica")
                self.Evento.objects.all().delete()
                self.Turno.objects.all().delete()
