from datetime import date, timedelta
from unittest.mock import patch

from django.db import connection, DatabaseError, models
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from apps.alertas import services
from apps.alertas.catalogo import CATALOGO
from apps.alertas.models import Alerta, AlertaEvento, EstadoReconciliacion
from apps.alertas.serializers import inicio_civil
from apps.comercial.models import Presupuesto
from apps.obras import services as obras
from apps.usuarios.models import Usuario
from apps.usuarios.tokens import AccessToken
from .base import AlertasBase, URL

PUBLICOS = {"id", "tipo", "estado", "severidad", "rol_destinatario", "recurso_tipo", "recurso_id", "recurso_codigo", "obra", "titulo", "descripcion", "creado_en", "atendida_por", "atendida_en", "motivo_atencion", "resuelta_en", "acciones_permitidas"}


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class AlertasAPITests(AlertasBase, TestCase):
    def setUp(self):
        self.preparar_alertas()
        self.a = self.suspender()

    def test_listado_detalle_esquema_identico_nullables_y_acciones(self):
        lista = self.client.get(URL)
        detalle = self.client.get(f"{URL}{self.a.pk}/")
        self.assertEqual(lista.status_code, 200, lista.data)
        self.assertEqual(set(lista.data), {"count", "next", "previous", "results"})
        self.assertEqual(lista.data["count"], 1)
        self.assertEqual(lista.data["results"][0], detalle.data)
        self.assertEqual(set(detalle.data), PUBLICOS)
        self.assertEqual(detalle.data["acciones_permitidas"], ["ATENDER"])
        self.assertEqual(detalle.data["obra"], self.obra.pk)
        self.assertEqual(detalle.data["recurso_codigo"], self.obra.codigo)
        for campo in ("atendida_por", "atendida_en", "motivo_atencion", "resuelta_en"):
            self.assertIsNone(detalle.data[campo])
        self.assertEqual(detalle["Cache-Control"], "private, no-store")

    def test_atender_body_exacto_y_historial_sin_snapshots(self):
        antes = timezone.now()
        result = self.client.post(f"{URL}{self.a.pk}/atender/", {"motivo": "  Coordinado  "}, format="json")
        self.assertEqual(result.status_code, 200, result.data)
        self.assertEqual(set(result.data), PUBLICOS)
        self.assertEqual(result.data["estado"], "ATENDIDA")
        self.assertEqual(result.data["motivo_atencion"], "Coordinado")
        self.assertEqual(result.data["atendida_por"], self.gerencia.pk)
        self.assertEqual(result.data["acciones_permitidas"], [])
        self.a.refresh_from_db()
        self.assertGreaterEqual(self.a.atendida_en, antes)
        historial = self.client.get(f"{URL}{self.a.pk}/historial/")
        self.assertEqual(historial.status_code, 200, historial.data)
        self.assertEqual(historial.data["count"], 2)
        evento = historial.data["results"][0]
        self.assertEqual(set(evento), {"id", "alerta", "tipo", "estado_anterior", "estado_nuevo", "actor", "motivo", "registrado_en"})
        self.assertEqual(evento["actor"], self.gerencia.pk)
        self.assertEqual(historial.data["results"][1]["actor"], None)

    def test_cinco_roles_flags_y_claims_no_escalan(self):
        for actor in (self.gerencia, self.supervisor, self.finanzas, self.tecnico, self.ti()):
            actor.is_staff = actor.is_superuser = True
            actor.save()
            token = AccessToken.for_user(actor)
            token["rol"] = "GERENCIA"
            self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
            esperado = 200 if actor.rol in ("GERENCIA", "SUPERVISOR_OBRAS") else 403
            for ruta in (URL, URL + "resumen/"):
                response = self.client.get(ruta)
                self.assertEqual(response.status_code, esperado, (actor.rol, response.data))
                self.assertEqual(self.client.options(ruta).status_code, esperado)
            if esperado == 200:
                self.assertTrue(all(a["rol_destinatario"] == actor.rol for a in self.client.get(URL).data["results"]))

    def test_otro_rol_404_en_detalle_historial_atencion_y_id_extremo(self):
        ajena = Alerta.objects.get(rol_destinatario="SUPERVISOR_OBRAS")
        for pk in (ajena.pk, 9223372036854775807, 9223372036854775808):
            self.assertEqual(self.client.get(f"{URL}{pk}/").status_code, 404)
            self.assertEqual(self.client.get(f"{URL}{pk}/historial/").status_code, 404)
            self.assertEqual(self.client.post(f"{URL}{pk}/atender/", {"motivo": "X"}, format="json").status_code, 404)
            for sufijo in ("", "historial/", "atender/"):
                self.assertEqual(self.client.options(f"{URL}{pk}/{sufijo}").status_code, 404)

    def test_mismo_rol_comparte_atencion(self):
        otro = Usuario.objects.create_user(username="g009", email="g009@example.test", rol="GERENCIA")
        services.atender(self.gerencia, self.a.pk, "Coordinado")
        self.autenticar(otro)
        result = self.client.post(f"{URL}{self.a.pk}/atender/", {"motivo": "Segundo"}, format="json")
        self.assertEqual(result.status_code, 409)
        self.assertEqual(result.data["code"], "alerta_ya_atendida")

    def test_409_resuelta_y_desactualizada_acciones_lectura_no_reconcilia(self):
        obras.reanudar_obra(self.obra, self.supervisor, "Continuar")
        self.assertEqual(self.client.get(f"{URL}{self.a.pk}/").data["acciones_permitidas"], [])
        response = self.client.post(f"{URL}{self.a.pk}/atender/", {"motivo": "X"}, format="json")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "alerta_desactualizada")
        services.reconciliar()
        response = self.client.post(f"{URL}{self.a.pk}/atender/", {"motivo": "X"}, format="json")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "alerta_resuelta")
        self.assertEqual(self.client.get(URL).data["count"], 0)
        self.assertEqual(self.client.get(URL, {"estado": "TODAS"}).data["count"], 1)

    def test_json_estricto_motivos_tipos_campos_y_claves_duplicadas(self):
        ruta = f"{URL}{self.a.pk}/atender/"
        for data in ({}, [], None, {"motivo": ""}, {"motivo": "   "}, {"motivo": 123}, {"motivo": True}, {"motivo": None}, {"motivo": "x" * 2001}, {"motivo": "X", "actor": 1}, {"motivo": ["X"]}):
            # None se codifica explícitamente como JSON null.
            response = self.client.generic("POST", ruta, data="null", content_type="application/json") if data is None else self.client.post(ruta, data, format="json")
            self.assertEqual(response.status_code, 400, (data, response.data))
        for raw in ('{"motivo":"A","motivo":"B"}', '{', '{"motivo":NaN}'):
            self.assertEqual(self.client.post(ruta, raw, content_type="application/json").status_code, 400)
        self.assertEqual(self.a.eventos.count(), 1)
        self.assertEqual(self.client.post(ruta, {"motivo": " " + "x" * 2000 + " "}, format="json").status_code, 200)

    def test_filtros_estrictos_y_parametros_por_ruta(self):
        invalidos = ["otro=1", "estado=", "estado=OTRA", "estado=PENDIENTE&estado=ATENDIDA", "tipo=OTRO", "rol_destinatario=GERENCIA", "recurso_tipo=OTRO", "recurso_id=1", "recurso_tipo=OBRA&recurso_id=0", "recurso_tipo=OBRA&recurso_id=true", "recurso_tipo=OBRA&recurso_id=9223372036854775808", "tipo=OBRA_SUSPENDIDA&recurso_tipo=TURNO", "desde=2026-01-01", "desde=2026-02-30&hasta=2026-03-01", "desde=2026-03-01&hasta=2026-02-01", "desde=2024-01-01&hasta=2025-01-01", "desde=9999-12-31&hasta=9999-12-31", "page=0", "page=-1", "page=1.0", "page=last", "page=99999999999999999999", "page=2", "page=1&page=1"]
        for query in invalidos:
            r = self.client.get(URL + "?" + query)
            self.assertEqual(r.status_code, 400, (query, r.data))
        for ruta in ("resumen/", f"{self.a.pk}/", f"{self.a.pk}/historial/"):
            self.assertEqual(self.client.get(URL + ruta, {"estado": "PENDIENTE"}).status_code, 400)
        self.assertEqual(self.client.get(URL + "resumen/", {"page": 1}).status_code, 400)
        self.assertEqual(self.client.get(URL, {"desde": "2024-01-01", "hasta": "2024-12-31"}).status_code, 200)

    def test_filtros_validos_y_recurso_fuera_ambito_vacio(self):
        for params, cantidad in [({"estado": "PENDIENTE"}, 1), ({"estado": "ATENDIDA"}, 0), ({"estado": "RESUELTA"}, 0), ({"tipo": self.a.tipo}, 1), ({"recurso_tipo": "OBRA", "recurso_id": str(self.obra.pk)}, 1), ({"recurso_tipo": "DOCUMENTO", "recurso_id": "9223372036854775807"}, 0)]:
            r = self.client.get(URL, params)
            self.assertEqual(r.status_code, 200, r.data)
            self.assertEqual(r.data["count"], cantidad)

    def test_resumen_ceros_conteos_exclusivos_y_salud_sin_crear_estado(self):
        EstadoReconciliacion.objects.all().delete()
        response = self.client.get(URL + "resumen/")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(set(response.data), {"generado_en", "zona_horaria", "por_estado", "activas", "por_tipo", "sincronizacion"})
        self.assertEqual(response.data["por_estado"], {"PENDIENTE": 1, "ATENDIDA": 0, "RESUELTA": 0})
        self.assertEqual(set(response.data["por_tipo"]), {"PRESUPUESTO_PENDIENTE_GERENCIA", "OBRA_SUSPENDIDA", "COBRANZA_VENCIDA"})
        self.assertEqual(response.data["sincronizacion"], {"ultima_correcta_en": None, "desactualizada": True})
        self.assertFalse(EstadoReconciliacion.objects.exists())
        ahora = timezone.now()
        for edad, stale in [(0, False), (180, False), (181, True)]:
            EstadoReconciliacion.objects.update_or_create(pk=1, defaults={"ultima_correcta_en": ahora - timedelta(seconds=edad)})
            with patch("apps.alertas.views.timezone.now", return_value=ahora):
                self.assertEqual(self.client.get(URL + "resumen/").data["sincronizacion"]["desactualizada"], stale)
        self.autenticar(self.supervisor)
        self.assertEqual(set(self.client.get(URL + "resumen/").data["por_tipo"]), {"OBRA_SUSPENDIDA", "TURNO_PENDIENTE_REVISION"})

    def test_get_head_options_sin_writes(self):
        for ruta in (URL, URL + "resumen/", f"{URL}{self.a.pk}/", f"{URL}{self.a.pk}/historial/"):
            with CaptureQueriesContext(connection) as queries:
                self.assertEqual(self.client.get(ruta).status_code, 200)
                head = self.client.head(ruta)
                self.assertEqual(head.status_code, 200)
                self.assertEqual(head.content, b"")
                self.assertEqual(self.client.options(ruta).status_code, 200)
            self.assertFalse(any(q["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE", "CREATE", "ALTER")) for q in queries))

    def test_401_y_revocacion_expiracion_actividad(self):
        self.client.credentials()
        self.assertEqual(self.client.get(URL).status_code, 401)
        token = AccessToken.for_user(self.gerencia)
        token.set_exp(from_time=timezone.now() - timedelta(days=1), lifetime=timedelta(seconds=1))
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual(self.client.get(URL).status_code, 401)
        self.autenticar(self.gerencia)
        self.gerencia.sesion_version += 1
        self.gerencia.save()
        self.assertEqual(self.client.get(URL).status_code, 401)
        self.autenticar(self.gerencia)
        self.gerencia.is_active = False
        self.gerencia.save()
        self.assertEqual(self.client.get(URL).status_code, 401)

    def test_metodos_no_permitidos(self):
        for ruta in (URL, URL + "resumen/", f"{URL}{self.a.pk}/", f"{URL}{self.a.pk}/historial/"):
            for metodo in ("post", "put", "patch", "delete"):
                self.assertEqual(getattr(self.client, metodo)(ruta, {}, format="json").status_code, 405)
        self.assertEqual(self.client.get(f"{URL}{self.a.pk}/atender/").status_code, 405)

    def test_500_saneado_correlacion_sin_secretos(self):
        with patch("apps.alertas.views.filtrar", side_effect=DatabaseError("SQL password=SECRETO")), self.assertLogs("apps.alertas.views", level="ERROR") as logs:
            response = self.client.get(URL)
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response["X-Correlation-ID"], response.data["correlacion"])
        self.assertNotIn("SECRETO", str(logs.output) + str(response.data))

    def test_paginacion_25_orden_empates_y_consultas_sin_n_mas_uno(self):
        ahora = timezone.now()
        for i in range(30):
            p = Presupuesto.objects.create(cliente=self.cliente, creado_por=self.finanzas, descripcion=f"Presupuesto {i}", estado="PENDIENTE_GERENCIA")
            services.reconciliar_recurso("PRESUPUESTO_PENDIENTE_GERENCIA", p.pk)
        models.QuerySet(model=Alerta).update(creado_en=ahora, ultima_comprobacion_en=timezone.now())
        with CaptureQueriesContext(connection) as queries:
            r = self.client.get(URL)
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["count"], 31)
        self.assertEqual(len(r.data["results"]), 25)
        self.assertLessEqual(len(queries), 8)  # auth, permiso, count, página y dos consultas por tipo
        segunda = self.client.get(r.data["next"])
        self.assertEqual(len(segunda.data["results"]), 6)
        ids = [a["id"] for a in r.data["results"] + segunda.data["results"]]
        self.assertEqual(ids, sorted(ids, reverse=True))
        self.assertEqual(len(ids), len(set(ids)))
        self.assertIsNone(segunda.data["next"])

    def test_fronteras_civiles_inclusivas_y_activas_sin_ventana_default(self):
        instante = inicio_civil(date(2026, 9, 6))
        models.QuerySet(model=Alerta).filter(pk=self.a.pk).update(creado_en=instante)
        self.assertEqual(self.client.get(URL).data["count"], 1)
        for dia, esperado in [("2026-09-06", 1), ("2026-09-05", 0), ("2026-09-07", 0)]:
            self.assertEqual(self.client.get(URL, {"desde": dia, "hasta": dia}).data["count"], esperado)

    def test_proyeccion_no_filtra_pii_tarifas_evidencias_ni_descripciones(self):
        obras.reanudar_obra(self.obra, self.supervisor, "Continuar")
        t = self.abrir()
        self.cerrar(t)
        services.reconciliar()
        self.autenticar(self.supervisor)
        r = self.client.get(URL)
        texto = str(r.data)
        for secreto in (self.cliente.correo, self.cliente.nombre_legal, "Trabajo realizado", "costo_hora_neto", "password", "fotos", "monto_total"):
            self.assertNotIn(secreto, texto)
        turno = next(a for a in r.data["results"] if a["recurso_tipo"] == "TURNO")
        self.assertIsNone(turno["recurso_codigo"])
        self.assertEqual(turno["obra"], self.obra.pk)

    def test_openapi_catalogos_rutas_y_campos_alineados(self):
        import json
        from pathlib import Path
        from django.conf import settings
        from apps.alertas.serializers import AlertaEventoSerializer
        schema = json.loads((Path(settings.BASE_DIR) / "docs/openapi/SPEC-009-v1.json").read_text())
        self.assertEqual(schema["openapi"], "3.1.0")
        self.assertEqual(set(schema["components"]["schemas"]["Tipo"]["enum"]), set(CATALOGO))
        self.assertEqual(set(schema["components"]["schemas"]["Alerta"]["required"]), PUBLICOS)
        self.assertEqual(set(schema["components"]["schemas"]["Evento"]["required"]), set(AlertaEventoSerializer().fields))
        self.assertEqual(set(schema["paths"]), {URL, URL + "resumen/", URL + "{id}/", URL + "{id}/historial/", URL + "{id}/atender/"})
        def recorrer(value):
            if isinstance(value, dict):
                if "$ref" in value:
                    target = schema
                    for parte in value["$ref"].removeprefix("#/").split("/"):
                        target = target[parte]
                for child in value.values():
                    recorrer(child)
            elif isinstance(value, list):
                for child in value:
                    recorrer(child)
        recorrer(schema)
