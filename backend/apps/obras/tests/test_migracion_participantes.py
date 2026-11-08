from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from apps.obras import services
from apps.obras.models import ObraParticipante, ObraParticipanteEvento
from .test_servicios_004a import BaseObras


class MigracionParticipantesTests(BaseObras, TransactionTestCase):
    anterior = [("obras", "0004_remove_obraevento_obra_evento_transicion_valida_and_more")]
    destino = [("obras", "0006_participantes_historicos")]

    def test_backfill_preserva_datos_y_acceso_sin_inventar_historia(self):
        executor = MigrationExecutor(connection)
        actuales = executor.loader.graph.leaf_nodes()
        executor.migrate(self.anterior)
        try:
            self.setUpTestData()
            apps = executor.loader.project_state(self.anterior).apps
            Obra = apps.get_model("obras", "Obra")
            Evento = apps.get_model("obras", "ObraEvento")
            obra = Obra.objects.create(
                presupuesto_id=self.presupuesto.pk, categoria_servicio_id=self.categoria.pk,
                descripcion="Obra histórica", tecnico_responsable_id=self.tecnico.pk,
                creado_por_id=self.supervisor.pk,
            )
            Evento.objects.create(
                obra=obra, tipo="CREACION", estado_nuevo="PLANIFICADA",
                registrado_por_id=self.supervisor.pk, motivo="Original",
                datos_nuevos={"tecnico_responsable": self.tecnico.pk},
            )
            original = Obra.objects.values().get(pk=obra.pk)
            eventos = list(Evento.objects.values())
            presupuesto = type(self.presupuesto).objects.values().get(pk=self.presupuesto.pk)
            MigrationExecutor(connection).migrate(self.destino)
            miembro = ObraParticipante.objects.get(obra_id=obra.pk)
            self.assertTrue(miembro.activo)
            self.assertEqual(miembro.origen_registro, "MIGRACION_004B")
            self.assertIsNone(miembro.asignado_por_id)
            self.assertIsNone(miembro.asignado_en)
            self.assertEqual(miembro.motivo_asignacion, "")
            self.assertFalse(ObraParticipanteEvento.objects.exists())
            self.assertEqual(Obra.objects.values().get(pk=obra.pk), original)
            self.assertEqual(list(Evento.objects.values()), eventos)
            self.assertEqual(type(self.presupuesto).objects.values().get(pk=self.presupuesto.pk), presupuesto)
            # Los servicios actuales requieren el esquema posterior a 004B-1.
            MigrationExecutor(connection).migrate(actuales)
            from apps.obras.models import TurnoObra
            self.assertFalse(TurnoObra.objects.exists())
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(self.tecnico)}")
            self.assertEqual(client.get("/api/obras/mis-obras/").data["count"], 1)
            self.assertEqual(client.get(f"/api/obras/{obra.pk}/").status_code, 200)
            services.cambiar_tecnico(obra.pk, None, self.supervisor, "Reprogramar")
            services.asignar_participante(obra.pk, {"tecnico": self.tecnico.pk, "motivo": "Apoyo"}, self.supervisor)
            miembro.refresh_from_db()
            self.assertEqual(miembro.origen_registro, "MIGRACION_004B")
            self.assertEqual(miembro.asignado_por_id, self.supervisor.pk)
            self.assertEqual(miembro.eventos.count(), 2)
        finally:
            MigrationExecutor(connection).migrate(actuales)
