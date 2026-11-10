from django.test import TestCase
from django.utils import timezone

from apps.obras import services as obras
from apps.obras import services_turnos as turnos
from apps.obras.models import ObraParticipante
from apps.obras.tests.test_servicios_004a import BaseObras
from apps.usuarios import services_usuarios as usuarios


class DependenciasTests(BaseObras, TestCase):
    def deny_changes(self, tecnico):
        for action in [
            lambda: usuarios.actividad_usuario(tecnico, {"motivo": "Baja"}, self.gerencia, activo=False),
            lambda: usuarios.cambiar_rol(tecnico, {"rol": "SUPERVISOR_OBRAS", "motivo": "Cambio"}, self.gerencia),
        ]:
            with self.assertRaises(usuarios.ConflictoUsuario) as caught:
                action()
            self.assertEqual(caught.exception.detail["code"], "asignaciones_pendientes")
        tecnico.refresh_from_db()
        self.assertTrue(tecnico.is_active)
        self.assertEqual(tecnico.rol, "TECNICO")
        self.assertEqual(tecnico.eventos_administrativos.count(), 0)

    def test_responsable_y_resolucion_operativa_sin_alterar_historia(self):
        obra = self.crear(tecnico_responsable=self.tecnico.pk, motivo="Asignación")
        self.deny_changes(self.tecnico)
        obras.cambiar_tecnico(obra, self.otro_tecnico.pk, self.supervisor, "Relevo")
        usuarios.actividad_usuario(self.tecnico, {"motivo": "Resuelto"}, self.gerencia, activo=False)
        self.assertTrue(ObraParticipante.objects.filter(obra=obra, tecnico=self.tecnico, activo=False).exists())
        obra.refresh_from_db()
        self.assertEqual(obra.tecnico_responsable_id, self.otro_tecnico.pk)

    def test_participante_activo_y_desasignacion(self):
        obra = self.crear()
        participante, _ = obras.asignar_participante(obra, {"tecnico": self.tecnico.pk, "motivo": "Apoyo"}, self.supervisor)
        self.deny_changes(self.tecnico)
        obras.desasignar_participante(obra, participante.pk, self.supervisor, "Apoyo terminado")
        usuarios.cambiar_rol(self.tecnico, {"rol": "SUPERVISOR_OBRAS", "motivo": "Sin pendientes"}, self.gerencia)
        participante.refresh_from_db()
        self.assertFalse(participante.activo)

    def test_turno_abierto_incluso_sin_membresia_vigente(self):
        obra = self.crear(tecnico_responsable=self.otro_tecnico.pk, motivo="Responsable")
        participante, _ = obras.asignar_participante(obra, {"tecnico": self.tecnico.pk, "motivo": "Apoyo"}, self.supervisor)
        obras.iniciar_obra(obra, self.supervisor, "Inicio")
        turno = turnos.iniciar_turno(obra, {}, self.tecnico)
        # Simula vínculo histórico anómalo: el turno debe proteger por sí solo.
        ObraParticipante.objects.filter(pk=participante.pk).update(activo=False, desasignado_por=self.supervisor, desasignado_en=timezone.now(), motivo_desasignacion="Fixture histórico")
        self.deny_changes(self.tecnico)
        turno.refresh_from_db()
        self.assertIsNone(turno.terminado_en)

    def test_vinculos_terminales_se_conservan(self):
        obra = self.crear(tecnico_responsable=self.tecnico.pk, motivo="Responsable")
        # Estado histórico: 004A no expone todavía una acción de cancelación.
        type(obra).objects.filter(pk=obra.pk).update(estado="CANCELADA", cancelado_en=timezone.now())
        usuarios.actividad_usuario(self.tecnico, {"motivo": "Sin obligaciones vigentes"}, self.gerencia, activo=False)
        obra.refresh_from_db()
        self.assertEqual(obra.tecnico_responsable_id, self.tecnico.pk)
        self.assertTrue(ObraParticipante.objects.filter(obra=obra, tecnico=self.tecnico).exists())
