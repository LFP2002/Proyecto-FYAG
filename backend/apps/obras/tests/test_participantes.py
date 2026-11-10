from unittest.mock import patch

from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient
from apps.usuarios.tokens import AccessToken

from apps.obras import services
from apps.obras.exceptions import DatosInvalidos, EstadoIncompatible, PermisoDenegado, SinCambios
from apps.obras.models import Obra, ObraParticipante, ObraParticipanteEvento
from .test_servicios_004a import BaseObras
from . import test_concurrencia_004a


class ParticipantesTests(BaseObras, TestCase):
    def setUp(self):
        self.obra = self.crear(tecnico_responsable=self.tecnico.pk, motivo="Principal")
        self.client = APIClient()
        self.autenticar(self.supervisor)
        self.url = f"/api/obras/{self.obra.pk}/participantes/"

    def autenticar(self, usuario):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(usuario)}")

    def asignar(self):
        return services.asignar_participante(self.obra, {
            "tecnico": self.otro_tecnico.pk, "motivo": "Apoyo",
        }, self.supervisor)[0]

    def test_principal_sin_duplica_evento_004a(self):
        principal = self.obra.participantes.get()
        self.assertTrue(principal.activo)
        self.assertEqual(principal.tecnico_id, self.tecnico.pk)
        self.assertEqual(principal.asignado_por_id, self.supervisor.pk)
        self.assertEqual(principal.eventos.get().motivo, "Principal")
        self.assertEqual(self.obra.eventos.count(), 1)
        with self.assertRaises(EstadoIncompatible):
            services.desasignar_participante(self.obra, principal.pk, self.supervisor, "Baja")
        self.assertEqual(principal.eventos.count(), 1)

    def test_alta_duplicado_baja_reactivacion_historia(self):
        datos = {"tecnico": self.otro_tecnico.pk, "motivo": " Apoyo "}
        alta = self.client.post(self.url, datos, format="json")
        self.assertEqual(alta.status_code, 201, alta.data)
        pk = alta.data["id"]
        self.assertFalse(alta.data["es_responsable"])
        repetida = self.client.post(self.url, datos, format="json")
        self.assertEqual(repetida.status_code, 409)
        self.assertEqual(repetida.data["code"], "sin_cambios")
        ruta = self.url + f"{pk}/desasignar/"
        self.assertEqual(self.client.post(ruta, {"motivo": "Baja"}, format="json").status_code, 200)
        self.assertEqual(self.client.post(ruta, {"motivo": "Baja"}, format="json").status_code, 409)
        reactivada = self.client.post(self.url, datos, format="json")
        self.assertEqual(reactivada.status_code, 200, reactivada.data)
        self.assertEqual(reactivada.data["id"], pk)
        participante = ObraParticipante.objects.get(pk=pk)
        self.assertIsNone(participante.desasignado_en)
        eventos = list(participante.eventos.all())
        self.assertEqual([e.tipo for e in eventos], ["ASIGNACION", "DESASIGNACION", "REACTIVACION"])
        self.assertFalse(eventos[2].datos_anteriores["activo"])
        self.assertEqual(eventos[2].datos_anteriores["motivo_desasignacion"], "Baja")
        self.assertEqual(self.obra.eventos.count(), 1)

    def test_acceso_multiples_sin_duplicados_y_baja_inmediata(self):
        participante = self.asignar()
        for tecnico in (self.tecnico, self.otro_tecnico):
            self.autenticar(tecnico)
            for ruta in ("/api/obras/", "/api/obras/mis-obras/"):
                respuesta = self.client.get(ruta)
                self.assertEqual(respuesta.data["count"], 1)
                self.assertEqual(respuesta.data["results"][0]["id"], self.obra.pk)
                self.assertNotIn("costo", str(respuesta.data))
            self.assertEqual(self.client.get(f"/api/obras/{self.obra.pk}/").status_code, 200)
        services.desasignar_participante(self.obra, participante.pk, self.supervisor, "Baja")
        self.assertEqual(self.client.get("/api/obras/mis-obras/").data["count"], 0)
        self.assertEqual(self.client.get(f"/api/obras/{self.obra.pk}/").status_code, 404)

    def test_reasignar_a_adicional_y_reincorporar_principal(self):
        nuevo = self.asignar()
        services.cambiar_tecnico(self.obra, self.otro_tecnico.pk, self.supervisor, "Relevo")
        viejo = self.obra.participantes.get(tecnico=self.tecnico)
        self.assertFalse(viejo.activo)
        self.assertEqual(nuevo.eventos.count(), 1)  # No hubo cambio de membresía.
        self.assertEqual(self.obra.eventos.count(), 2)
        self.autenticar(self.tecnico)
        self.assertEqual(self.client.get("/api/obras/").data["count"], 0)
        services.asignar_participante(self.obra, {"tecnico": self.tecnico.pk, "motivo": "Apoyo adicional"}, self.supervisor)
        self.assertEqual(self.client.get("/api/obras/").data["count"], 1)
        services.cambiar_tecnico(self.obra, None, self.supervisor, "Reprogramar")
        nuevo.refresh_from_db()
        self.assertFalse(nuevo.activo)

    def test_roles_y_superusuario_sin_bypass(self):
        participante = self.asignar()
        for usuario in (self.gerencia, self.finanzas, self.supervisor, self.tecnico):
            self.autenticar(usuario)
            lectura = 200 if usuario in (self.gerencia, self.supervisor) else 403
            for sufijo in ("", "historial/"):
                self.assertEqual(self.client.get(self.url + sufijo).status_code, lectura)
            respuesta = self.client.post(self.url, {"tecnico": self.otro_tecnico.pk, "motivo": "Repetido"}, format="json")
            self.assertEqual(respuesta.status_code, 409 if usuario == self.supervisor else 403)
            self.assertEqual(self.client.get("/api/obras/mis-obras/").status_code, 200 if usuario == self.tecnico else 403)
            if usuario != self.supervisor:
                self.assertEqual(self.client.post(self.url + f"{participante.pk}/desasignar/", {"motivo": "Baja"}, format="json").status_code, 403)
        self.tecnico.is_superuser = True
        self.tecnico.save()
        self.autenticar(self.tecnico)
        for accion in ("iniciar", "suspender", "reanudar", "cambiar-tecnico"):
            self.assertEqual(self.client.post(f"/api/obras/{self.obra.pk}/{accion}/", {}, format="json").status_code, 403)
        self.assertEqual(self.client.patch(f"/api/obras/{self.obra.pk}/", {}, format="json").status_code, 403)
        self.assertEqual(self.client.options(self.url).status_code, 403)
        self.client.credentials()
        self.assertEqual(self.client.get(self.url).status_code, 401)

    def test_contrato_estricto_filtros_y_ambito(self):
        for datos in ({"tecnico": True, "motivo": "Apoyo"}, {"tecnico": "2", "motivo": "Apoyo"}, {"tecnico": self.otro_tecnico.pk, "motivo": " "}, {"tecnico": self.otro_tecnico.pk, "motivo": "Apoyo", "obra": self.obra.pk}):
            self.assertEqual(self.client.post(self.url, datos, format="json").status_code, 400)
        for query in ("activo=1", "activo=True", "activo=true&activo=false", "rol=TECNICO"):
            self.assertEqual(self.client.get(self.url + "?" + query).status_code, 400)
        self.assertEqual(self.client.get(self.url + "?activo=false").data["count"], 0)
        self.assertEqual(self.client.post(self.url + "999999/desasignar/", {}, format="json").status_code, 404)
        self.assertEqual(self.client.delete(self.url).status_code, 405)
        self.assertEqual(self.client.get(self.url + "historial/").data["count"], 1)
        self.assertNotIn("email", str(self.client.get(self.url).data))

    def test_elegibilidad_estado_y_rol_persistidos(self):
        self.otro_tecnico.is_active = False
        self.otro_tecnico.save()
        with self.assertRaises(DatosInvalidos):
            self.asignar()
        with self.assertRaises(DatosInvalidos):
            services.asignar_participante(self.obra, {"tecnico": self.gerencia.pk, "motivo": "Apoyo"}, self.supervisor)
        Obra.objects.filter(pk=self.obra.pk).update(estado="FINALIZADA", iniciado_en=timezone.now(), finalizado_en=timezone.now())
        with self.assertRaises(EstadoIncompatible):
            self.asignar()
        type(self.supervisor).objects.filter(pk=self.supervisor.pk).update(rol="GERENCIA")
        with self.assertRaises(PermisoDenegado):
            self.asignar()

    def test_rollback_alta_y_reasignacion_si_falla_evento(self):
        with patch("apps.obras.services._evento_participante", side_effect=RuntimeError("fallo")):
            with self.assertRaises(RuntimeError):
                self.asignar()
            with self.assertRaises(RuntimeError):
                services.cambiar_tecnico(self.obra, self.otro_tecnico.pk, self.supervisor, "Cambio")
        self.obra.refresh_from_db()
        self.assertEqual(self.obra.tecnico_responsable_id, self.tecnico.pk)
        self.assertTrue(self.obra.participantes.get().activo)
        self.assertEqual(self.obra.eventos.count(), 1)
        self.assertEqual(ObraParticipanteEvento.objects.count(), 1)

    def test_unicidad_postgres_y_protect(self):
        principal = self.obra.participantes.get()
        with self.assertRaises(IntegrityError), transaction.atomic():
            ObraParticipante.objects.bulk_create([ObraParticipante(obra=self.obra, tecnico=self.tecnico, origen_registro="MIGRACION_004B")])
        with self.assertRaises(ProtectedError):
            principal.delete()
        with self.assertRaises(ProtectedError):
            self.obra.delete()

    def test_paginacion_filtra_antes_de_contar_y_sin_n_mas_uno(self):
        from apps.comercial.models import Presupuesto
        for indice in range(26):
            presupuesto = Presupuesto.objects.create(
                cliente=self.cliente, creado_por=self.finanzas,
                descripcion=f"Servicio {indice}", estado="APROBADO_CLIENTE",
            )
            obra = services.crear_obra(self.datos(presupuesto=presupuesto.pk), self.supervisor)
            if indice < 25:
                services.asignar_participante(obra, {"tecnico": self.tecnico.pk, "motivo": "Apoyo"}, self.supervisor)
        self.autenticar(self.tecnico)
        with self.assertNumQueries(3):  # JWT, count y página con relaciones precargadas.
            primera = self.client.get("/api/obras/mis-obras/")
        self.assertEqual(primera.data["count"], 26)
        self.assertEqual(len(primera.data["results"]), 25)
        segunda = self.client.get("/api/obras/mis-obras/?page=2")
        self.assertEqual(len(segunda.data["results"]), 1)
        self.assertEqual(self.client.get(f"/api/obras/{obra.pk}/").status_code, 404)
        self.autenticar(self.supervisor)
        principal = self.obra.participantes.get()
        respuesta = self.client.post(
            f"/api/obras/{obra.pk}/participantes/{principal.pk}/desasignar/",
            {"motivo": "Ajeno"}, format="json",
        )
        self.assertEqual(respuesta.status_code, 404)

    def test_creacion_revierte_todo_si_falla_evento_membresia(self):
        from apps.comercial.models import Presupuesto
        presupuesto = Presupuesto.objects.create(
            cliente=self.cliente, creado_por=self.finanzas,
            descripcion="Otra obra", estado="APROBADO_CLIENTE",
        )
        with patch("apps.obras.services._evento_participante", side_effect=RuntimeError("fallo")):
            with self.assertRaises(RuntimeError):
                services.crear_obra(self.datos(presupuesto=presupuesto.pk, tecnico_responsable=self.tecnico.pk, motivo="Inicial"), self.supervisor)
        self.assertFalse(Obra.objects.filter(presupuesto=presupuesto).exists())
        self.assertEqual(ObraParticipante.objects.count(), 1)
        self.assertEqual(ObraParticipanteEvento.objects.count(), 1)

    def test_participante_adicional_no_sustituye_principal(self):
        services.cambiar_tecnico(self.obra, None, self.supervisor, "Planificar")
        self.asignar()
        with self.assertRaises(DatosInvalidos):
            services.iniciar_obra(self.obra, self.supervisor, "Inicio")
        services.cambiar_tecnico(self.obra, self.otro_tecnico.pk, self.supervisor, "Principal")
        services.iniciar_obra(self.obra, self.supervisor, "Inicio")
        participante, _ = services.asignar_participante(self.obra, {"tecnico": self.tecnico.pk, "motivo": "Apoyo"}, self.supervisor)
        services.desasignar_participante(self.obra, participante.pk, self.supervisor, "Retirar apoyo")
        services.suspender_obra(self.obra, self.supervisor, "Pausa")
        self.assertFalse(services.asignar_participante(self.obra, {"tecnico": self.tecnico.pk, "motivo": "Retomar apoyo"}, self.supervisor)[1])


class ParticipantesConcurrenciaTests(BaseObras, TransactionTestCase):
    _ejecutar_en_orden = test_concurrencia_004a.ObrasConcurrenciaTests._ejecutar_en_orden

    def setUp(self):
        self.setUpTestData()
        self.obra = self.crear()

    def test_asignaciones_concurrentes_una_fila_un_evento(self):
        def asignar():
            return services.asignar_participante(self.obra, {"tecnico": self.tecnico.pk, "motivo": "Apoyo"}, self.supervisor)
        uno, dos = self._ejecutar_en_orden(asignar, asignar)
        self.assertTrue(uno[1])
        self.assertIsInstance(dos, SinCambios)
        self.assertEqual(self.obra.participantes.count(), 1)
        self.assertEqual(ObraParticipanteEvento.objects.count(), 1)

    def test_reactivaciones_concurrentes_un_solo_evento(self):
        datos = {"tecnico": self.tecnico.pk, "motivo": "Apoyo"}
        participante, _ = services.asignar_participante(self.obra, datos, self.supervisor)
        services.desasignar_participante(self.obra, participante.pk, self.supervisor, "Baja")
        uno, dos = self._ejecutar_en_orden(
            lambda: services.asignar_participante(self.obra, datos, self.supervisor),
            lambda: services.asignar_participante(self.obra, datos, self.supervisor),
        )
        self.assertFalse(uno[1])
        self.assertIsInstance(dos, SinCambios)
        self.assertEqual(participante.eventos.count(), 3)
