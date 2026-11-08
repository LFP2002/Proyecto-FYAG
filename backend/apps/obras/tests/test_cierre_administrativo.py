from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.obras import services, services_turnos as turnos
from apps.obras.exceptions import PermisoDenegado
from apps.obras.models import Obra, ObraParticipante, TurnoObra
from .test_turnos import TurnosBase


class CierreAdministrativoTests(TurnosBase, TestCase):
    def setUp(self):
        self.preparar()
        self.turno = self.abrir()
        self.autenticar(self.supervisor)
        self.ruta = self.url + f"{self.turno.pk}/cerrar-administrativamente/"
        self.entrada = {"motivo": "  Técnico sin acceso  ", "descripcion_trabajo": "  Instalación comprobada por Supervisor  "}
        self.fin = self.turno.iniciado_en + timedelta(hours=2)

    def cerrar_admin(self, **extras):
        with patch("apps.obras.services_turnos.timezone.now", return_value=self.fin):
            return self.client.post(self.ruta, self.entrada | extras, format="json")

    def validar(self):
        return self.client.post(self.url + f"{self.turno.pk}/revisar/", {
            "decision": "VALIDAR", "motivo": "Verificado", "costo_hora_neto": "8000.00",
        }, format="json")

    def corregir(self, **datos):
        return self.client.post(self.url + f"{self.turno.pk}/corregir/", {"motivo": "Rectificación verificada"} | datos, format="json")

    def test_cierre_activo_auditoria_y_desbloqueo(self):
        obra = Obra.objects.values().get(pk=self.obra.pk)
        participantes = list(ObraParticipante.objects.filter(obra=self.obra).values())
        respuesta = self.cerrar_admin()
        self.assertEqual(respuesta.status_code, 200, respuesta.data)
        self.turno.refresh_from_db()
        self.assertEqual(self.turno.tecnico_id, self.tecnico.pk)
        self.assertEqual(self.turno.terminado_en, self.fin)
        self.assertEqual(self.turno.duracion_segundos, 7200)
        self.assertEqual(self.turno.modo_cierre, "SUPERVISOR")
        self.assertEqual(self.turno.cerrado_por_id, self.supervisor.pk)
        self.assertEqual(self.turno.descripcion_trabajo, self.entrada["descripcion_trabajo"].strip())
        self.assertEqual(self.turno.estado_revision, "PENDIENTE_REVISION")
        self.assertIsNone(self.turno.costo_hora_neto)
        evento = self.turno.eventos.get(tipo="CIERRE_ADMINISTRATIVO")
        self.assertEqual(evento.registrado_por_id, self.supervisor.pk)
        self.assertEqual(evento.motivo, "Técnico sin acceso")
        self.assertEqual(evento.creado_en, self.fin)
        self.assertIsNone(evento.datos_anteriores["cerrado_por"])
        self.assertEqual(evento.datos_nuevos["cerrado_por"], self.supervisor.pk)
        self.assertEqual(Obra.objects.values().get(pk=self.obra.pk), obra)
        self.assertEqual(list(ObraParticipante.objects.filter(obra=self.obra).values()), participantes)
        self.assertEqual(self.cerrar_admin().status_code, 409)
        self.autenticar(self.tecnico)
        self.assertEqual(self.client.post(self.url + f"{self.turno.pk}/finalizar/", {"descripcion_trabajo": "Duplicado"}, format="json").status_code, 409)
        lectura = self.client.get(self.url).data["results"][0]
        self.assertEqual(lectura["modo_cierre"], "SUPERVISOR")
        self.assertEqual(lectura["cerrado_por"], self.supervisor.pk)
        self.assertNotIn("costo_hora_neto", lectura)
        services.cambiar_tecnico(self.obra, self.otro_tecnico.pk, self.supervisor, "Reemplazo")
        services.suspender_obra(self.obra, self.supervisor, "Pausa")
        self.assertEqual(self.turno.eventos.count(), 2)

    def test_cierre_tecnico_inactivo_sin_password(self):
        self.tecnico.is_active = False
        self.tecnico.set_unusable_password()
        self.tecnico.save()
        self.assertEqual(self.cerrar_admin().status_code, 200)
        self.turno.refresh_from_db()
        self.assertEqual(self.turno.tecnico_id, self.tecnico.pk)

    def test_permisos_incluso_superusuarios_y_supervisor_inactivo(self):
        for usuario in (self.tecnico, self.otro_tecnico, self.gerencia, self.finanzas):
            usuario.is_superuser = True
            usuario.save()
            self.autenticar(usuario)
            self.assertEqual(self.cerrar_admin().status_code, 403)
        self.supervisor.is_active = False
        self.supervisor.save()
        with self.assertRaises(PermisoDenegado):
            turnos.cerrar_administrativamente(self.obra, self.turno.pk, self.entrada, self.supervisor)
        self.client.credentials()
        self.assertEqual(self.cerrar_admin().status_code, 401)
        self.assertEqual(self.turno.eventos.count(), 1)

    def test_contrato_estricto_motivo_descripcion_y_ajustes(self):
        casos = [{}, {"motivo": "Falta descripción"}, {"descripcion_trabajo": "Falta motivo"}]
        for campo in ("motivo", "descripcion_trabajo"):
            casos.extend(self.entrada | {campo: valor} for valor in (" ", 123, True, None, "x" * 2001))
        for campo in ("tecnico", "iniciado_en", "terminado_en", "horas", "estado_revision", "cerrado_por", "modo_cierre", "fotos[]", "costo_hora_neto"):
            casos.append(self.entrada | {campo: 1})
        casos.extend(self.entrada | {"duracion_ajustada_segundos": valor} for valor in (0, -1, True, "1", 1.2, 7201))
        antes = TurnoObra.objects.values().get(pk=self.turno.pk)
        for datos in casos:
            with self.subTest(datos=datos), patch("apps.obras.services_turnos.timezone.now", return_value=self.fin):
                respuesta = self.client.post(self.ruta, datos, format="json")
                self.assertEqual(respuesta.status_code, 400, respuesta.data)
        self.assertEqual(TurnoObra.objects.values().get(pk=self.turno.pk), antes)
        self.assertEqual(self.turno.eventos.count(), 1)

    def test_sin_ajuste_no_validacion_ni_costo_y_rectificacion(self):
        self.assertEqual(self.cerrar_admin().status_code, 200)
        self.assertEqual(self.validar().status_code, 409)
        self.assertEqual(self.corregir(costo_hora_neto="8000.00").status_code, 200)
        self.turno.refresh_from_db()
        self.assertIsNone(self.turno.costo_mano_obra)
        self.assertEqual(self.corregir(duracion_ajustada_segundos=7201).status_code, 400)
        respuesta = self.corregir(duracion_ajustada_segundos=3600)
        self.assertEqual(respuesta.status_code, 200, respuesta.data)
        self.assertEqual(self.validar().status_code, 200)
        self.turno.refresh_from_db()
        self.assertEqual(self.turno.costo_mano_obra, 8000)
        self.assertEqual(self.turno.terminado_en, self.fin)
        self.assertEqual(self.turno.duracion_segundos, 7200)
        self.assertEqual(self.corregir(duracion_ajustada_segundos=None).status_code, 200)
        self.assertEqual(self.validar().status_code, 409)
        self.turno.refresh_from_db()
        self.assertEqual(self.turno.estado_revision, "PENDIENTE_REVISION")
        self.assertIsNone(self.turno.costo_mano_obra)

    def test_ajuste_al_cerrar_no_valida_automaticamente(self):
        respuesta = self.cerrar_admin(duracion_ajustada_segundos=7200)
        self.assertEqual(respuesta.status_code, 200, respuesta.data)
        self.assertEqual(respuesta.data["estado_revision"], "PENDIENTE_REVISION")
        self.assertIsNone(respuesta.data["costo_mano_obra"])
        self.assertEqual(self.validar().status_code, 200)

    def test_rectificar_descripcion_preserva_subsanacion_y_tiempos(self):
        self.cerrar_admin(duracion_ajustada_segundos=3600)
        turnos.revisar_turno(self.obra, self.turno.pk, {"decision": "OBSERVAR", "motivo": "Aclarar"}, self.supervisor)
        turnos.subsanar_turno(self.obra, self.turno.pk, {"descripcion_trabajo": "Aclaración propia del técnico"}, self.tecnico)
        self.assertEqual(self.validar().status_code, 200)
        for descripcion in ("Primera rectificación", "Segunda rectificación"):
            respuesta = self.corregir(descripcion_trabajo=descripcion)
            self.assertEqual(respuesta.status_code, 200, respuesta.data)
            self.assertEqual(respuesta.data["descripcion_trabajo"], descripcion + "\nAclaración propia del técnico")
        self.turno.refresh_from_db()
        self.assertEqual(self.turno.estado_revision, "PENDIENTE_REVISION")
        self.assertEqual(self.turno.terminado_en, self.fin)
        evento = self.turno.eventos.filter(tipo="CORRECCION").order_by("id").last()
        self.assertIn("Primera rectificación", evento.datos_anteriores["descripcion_trabajo"])
        self.assertIn("Segunda rectificación", evento.datos_nuevos["descripcion_trabajo"])

    def test_cierre_ordinario_atribuido_y_descripcion_no_editable(self):
        self.cerrar(self.turno)
        self.turno.refresh_from_db()
        self.assertEqual(self.turno.modo_cierre, "TECNICO")
        self.assertEqual(self.turno.cerrado_por_id, self.tecnico.pk)
        self.assertEqual(self.corregir(descripcion_trabajo="Sobrescribir").status_code, 400)
        self.assertEqual(self.cerrar_admin().status_code, 409)

    def test_estado_obra_recurso_ajeno_y_duracion_no_positiva(self):
        otra = self.otra_obra()
        self.assertEqual(self.client.post(f"/api/obras/{otra.pk}/turnos/{self.turno.pk}/cerrar-administrativamente/", self.entrada, format="json").status_code, 404)
        Obra.objects.filter(pk=self.obra.pk).update(estado="SUSPENDIDA")
        self.assertEqual(self.cerrar_admin().status_code, 409)
        Obra.objects.filter(pk=self.obra.pk).update(estado="EN_PROCESO")
        self.fin = self.turno.iniciado_en
        self.assertEqual(self.cerrar_admin().status_code, 409)
        self.assertEqual(self.turno.eventos.count(), 1)

    def test_fallo_evento_revierte_cierre(self):
        antes = TurnoObra.objects.values().get(pk=self.turno.pk)
        with patch("apps.obras.services_turnos._evento", side_effect=RuntimeError("Fallo evento")):
            with self.assertRaises(RuntimeError):
                turnos.cerrar_administrativamente(self.obra, self.turno.pk, self.entrada, self.supervisor)
        self.assertEqual(TurnoObra.objects.values().get(pk=self.turno.pk), antes)
        self.assertEqual(self.turno.eventos.count(), 1)
