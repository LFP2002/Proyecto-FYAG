from datetime import datetime, timedelta, timezone as utc
from unittest.mock import patch

from django.core import signing
from django.db import connection, models, DatabaseError
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.auditoria.adapters import FUENTES
from apps.auditoria.cursors import SALT
from apps.auditoria.serializers import inicio_civil, filtros_query
from apps.obras.models import TurnoObraEvento
from apps.usuarios.models import UsuarioEvento
from apps.usuarios.tokens import AccessToken
from apps.usuarios import services_usuarios
from .base import AuditoriaBase, URL


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class AuditoriaTests(AuditoriaBase, TestCase):
    def setUp(self):
        self.preparar_auditoria()

    def test_ocho_fuentes_con_esquema_exacto_y_ids_de_origen(self):
        campos = {"id", "evento_id", "fuente", "modulo", "recurso_tipo", "recurso_id", "tipo", "actor", "actor_etiqueta", "motivo", "creado_en", "datos_anteriores", "datos_nuevos"}
        for name in FUENTES:
            self.autenticar(self.ti if name == "USUARIO_EVENTO" else self.gerencia)
            result = self.client.get(URL, {"fuente": name})
            self.assertEqual(result.status_code, 200, result.data)
            self.assertEqual(set(result.data), {"results", "next_cursor", "has_more", "fecha_corte", "zona_horaria"})
            self.assertTrue(result.data["results"], name)
            for event in result.data["results"]:
                self.assertEqual(set(event), campos)
                self.assertEqual(event["id"], f"{name}:{event['evento_id']}")
                self.assertEqual(event["fuente"], name)
                self.assertIsInstance(event["recurso_id"], int)

    def test_presupuesto_deriva_tipo_y_estados_sin_atributo_tipo(self):
        result = self.client.get(URL, {"fuente": "PRESUPUESTO_EVENTO"})
        self.assertEqual({row["tipo"] for row in result.data["results"]}, {"CREACION", "CAMBIO_ESTADO"})
        for row in result.data["results"]:
            self.assertEqual(row["recurso_id"], self.presupuesto.pk)
            self.assertIn("estado", row["datos_nuevos"])
        result = self.client.get(URL, {"fuente": "PRESUPUESTO_EVENTO", "tipo": "CREACION"})
        self.assertEqual(len(result.data["results"]), 1)
        self.assertEqual(result.data["results"][0]["datos_anteriores"], {})

    def test_recursos_tipados_costos_y_finanzas_no_son_id_obra(self):
        result = self.client.get(URL, {"fuente": "COSTO_OBRA_EVENTO", "limit": "50"})
        self.assertEqual({e["recurso_tipo"] for e in result.data["results"]}, {"GASTO", "CONTROL_COSTOS", "CORTESIA"})
        row = next(e for e in result.data["results"] if e["recurso_tipo"] == "GASTO")
        self.assertEqual(row["recurso_id"], 91)
        self.assertNotEqual(row["recurso_id"], self.obra.pk)
        result = self.client.get(URL, {"fuente": "FINANZAS_EVENTO"})
        self.assertEqual({e["recurso_tipo"] for e in result.data["results"]}, {"DOCUMENTO", "CIERRE_SIN_COBRO", "PAGO"})
        self.assertEqual(next(e for e in result.data["results"] if e["recurso_tipo"] == "PAGO")["recurso_id"], 79)
        result = self.client.get(URL, {"recurso_tipo": "PAGO", "recurso_id": "79"})
        self.assertEqual(len(result.data["results"]), 1)
        self.assertEqual(result.data["results"][0]["recurso_id"], 79)

    def test_cinco_roles_flags_y_denegacion_antes_de_consultar_fuentes(self):
        expectativas = {"GERENCIA": set(FUENTES) - {"USUARIO_EVENTO"},
            "SUPERVISOR_OBRAS": {"OBRA_EVENTO", "PARTICIPANTE_EVENTO", "TURNO_EVENTO", "COSTO_OBRA_EVENTO"},
            "ADMINISTRATIVO_FINANZAS": {"FINANZAS_EVENTO"}, "ADMINISTRADOR_TI": {"USUARIO_EVENTO"}}
        for user in [self.gerencia, self.supervisor, self.finanzas, self.ti, self.tecnico]:
            user.is_staff = user.is_superuser = True
            user.save()
            self.autenticar(user)
            if user == self.tecnico:
                self.assertEqual(self.client.get(URL).status_code, 403)
                self.assertEqual(self.client.options(URL).status_code, 403)
                continue
            with CaptureQueriesContext(connection) as queries:
                result = self.client.get(URL, {"limit": "50"})
            self.assertEqual(result.status_code, 200, result.data)
            self.assertEqual({e["fuente"] for e in result.data["results"]}, expectativas[user.rol])
            for name in set(FUENTES) - expectativas[user.rol]:
                self.assertFalse(any(FUENTES[name].modelo._meta.db_table in q["sql"] for q in queries), name)
                self.assertEqual(self.client.get(URL, {"fuente": name}).status_code, 403)
            self.assertEqual(self.client.get(URL, {"modulo": "USUARIOS" if user != self.ti else "OBRAS"}).status_code, 403)

    def test_categorias_solo_gerencia_no_amplia_permiso_supervisor(self):
        self.autenticar(self.supervisor)
        self.assertEqual(self.client.get(URL, {"fuente": "CATEGORIA_SERVICIO_EVENTO"}).status_code, 403)
        result = self.client.get(URL, {"modulo": "OBRAS", "limit": 50})
        self.assertNotIn("CATEGORIA_SERVICIO_EVENTO", {e["fuente"] for e in result.data["results"]})

    def test_turnos_gerencia_minimos_supervisor_sin_evidencias(self):
        turno = TurnoObraEvento.objects.first()
        data = {"costo_hora_neto": "12.34", "estado_revision": "VALIDADO", "observacion_revision": "Revisión privada", "iniciado_en": timezone.now().isoformat(), "duracion_segundos": "3600.000000", "fotos": [1], "nombre_interno": "privado.jpg", "token": "NO MOSTRAR"}
        models.QuerySet(model=TurnoObraEvento).filter(pk=turno.pk).update(datos_anteriores=data, datos_nuevos=data)
        for user in [self.gerencia, self.supervisor]:
            self.autenticar(user)
            result = self.client.get(URL, {"fuente": "TURNO_EVENTO", "limit": 50})
            row = next(e for e in result.data["results"] if e["evento_id"] == turno.pk)
            self.assertNotIn("fotos", row["datos_nuevos"])
            self.assertNotIn("nombre_interno", row["datos_nuevos"])
            self.assertNotIn("NO MOSTRAR", str(result.data))
            if user == self.gerencia:
                self.assertNotIn("costo_hora_neto", row["datos_nuevos"])
                self.assertNotIn("observacion_revision", row["datos_nuevos"])
            else:
                self.assertEqual(row["datos_nuevos"]["costo_hora_neto"], "12.34")
            self.assertEqual(row["datos_nuevos"]["duracion_segundos"], "3600.000000")

    def test_usuarios_claves_vacias_finanzas_sanitizadas_y_decimales_estrictos(self):
        evento = UsuarioEvento.objects.get(tipo="ESTABLECER_CLAVE")
        models.QuerySet(model=UsuarioEvento).filter(pk=evento.pk).update(datos_nuevos={"email": "no-mostrar@example.test", "password": "NO MOSTRAR"})
        self.autenticar(self.ti)
        result = self.client.get(URL, {"fuente": "USUARIO_EVENTO"})
        row = next(e for e in result.data["results"] if e["evento_id"] == evento.pk)
        self.assertEqual(row["datos_nuevos"], {})
        self.assertNotIn("NO MOSTRAR", str(result.data))
        fuente = FUENTES["FINANZAS_EVENTO"]
        evento = fuente.modelo.objects.get(tipo="PAGO_REGISTRADO")
        models.QuerySet(model=fuente.modelo).filter(pk=evento.pk).update(datos_nuevos={"monto": "1.2", "monto_total": "NaN", "password": "NO MOSTRAR", "cuenta_bancaria": "NO MOSTRAR", "costo_total": "NO MOSTRAR", "activo": True})
        self.autenticar(self.finanzas)
        result = self.client.get(URL)
        row = next(e for e in result.data["results"] if e["evento_id"] == evento.pk)
        self.assertEqual(row["datos_nuevos"], {"monto": "1.20", "activo": True})

    def test_actor_inactivo_conserva_id_etiqueta_solo_si_autorizada(self):
        self.finanzas.is_active = False
        self.finanzas.save()
        result = self.client.get(URL, {"fuente": "FINANZAS_EVENTO"})
        self.assertTrue(all(e["actor"] == self.finanzas.pk and e["actor_etiqueta"] is None for e in result.data["results"]))
        self.ti.first_name, self.ti.last_name = "Nombre", "Laboral"
        self.ti.save()
        self.autenticar(self.ti)
        result = self.client.get(URL)
        self.assertTrue(all(e["actor_etiqueta"] == "Nombre Laboral" for e in result.data["results"]))
        self.assertNotIn(self.ti.email, str(result.data["results"][0].get("actor_etiqueta")))

    def test_filtros_actor_recurso_inexistente_uniformes_y_tipo_literal(self):
        for query in [{"actor": "9223372036854775807"}, {"recurso_tipo": "OBRA", "recurso_id": "9223372036854775807"}]:
            result = self.client.get(URL, query)
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.data["results"], [])
            self.assertFalse(result.data["has_more"])
        result = self.client.get(URL, {"tipo": "CREACION", "limit": "50"})
        self.assertTrue(all(e["tipo"] == "CREACION" for e in result.data["results"]))

    def test_validacion_query_estricta(self):
        queries = ["otro=x", "limit=0", "limit=51", "limit=1.0", "limit=true", "limit=1&limit=2", "actor=0", "actor=-1", "actor=true", "actor=9223372036854775808", "recurso_id=1", "fuente=OTRO", "modulo=OTRO", "tipo=OTRO", "recurso_tipo=USUARIO&tipo=OTRO", "desde=2026-02-30", "hasta=2026-1-01", "desde=2026-02-01&hasta=2026-01-01", "desde=2020-01-01&hasta=2021-01-01", "hasta=0001-01-01", "hasta=9999-12-31", "fuente=OBRA_EVENTO&modulo=COMERCIAL", "fuente=OBRA_EVENTO&recurso_tipo=PAGO", "recurso_tipo=FINANZAS"]
        for query in queries:
            result = self.client.get(URL + "?" + query)
            self.assertEqual(result.status_code, 400, (query, result.data))

    def test_defaults_y_rango_366_dias_inclusivos(self):
        filtros = filtros_query({})
        self.assertEqual((datetime.fromisoformat(filtros["hasta"]) - datetime.fromisoformat(filtros["desde"])).days, 29)
        self.assertEqual(filtros["limit"], 25)
        self.assertEqual(self.client.get(URL, {"desde": "2024-01-01", "hasta": "2024-12-31"}).status_code, 200)
        self.assertEqual(self.client.get(URL, {"desde": "2024-01-01", "hasta": "2025-01-01"}).status_code, 400)

    def test_fechas_santiago_dst_no_son_86400_segundos(self):
        from datetime import date
        primavera = (inicio_civil(date(2026, 9, 7)).astimezone(utc.utc) - inicio_civil(date(2026, 9, 6)).astimezone(utc.utc)).total_seconds()
        otono = (inicio_civil(date(2026, 4, 5)).astimezone(utc.utc) - inicio_civil(date(2026, 4, 4)).astimezone(utc.utc)).total_seconds()
        self.assertEqual(primavera, 23 * 3600)
        self.assertEqual(otono, 25 * 3600)
        fuente = FUENTES["OBRA_EVENTO"]
        event = fuente.modelo.objects.first()
        t = datetime(2026, 9, 7, 2, 59, 59, 999999, tzinfo=utc.utc)
        models.QuerySet(model=fuente.modelo).filter(pk=event.pk).update(creado_en=t)
        result = self.client.get(URL, {"fuente": fuente.nombre, "desde": "2026-09-06", "hasta": "2026-09-06"})
        self.assertEqual([e["evento_id"] for e in result.data["results"]], [event.pk])

    def test_empates_y_cursor_sin_duplicados_orden_total(self):
        t = timezone.now() - timedelta(minutes=1)
        for f in FUENTES.values():
            models.QuerySet(model=f.modelo).update(creado_en=t)
        expected = self.client.get(URL, {"limit": 50}).data["results"]
        first = self.client.get(URL, {"limit": 2})
        result = first
        acumulados = []
        for _ in range(100):
            self.assertEqual(result.status_code, 200, result.data)
            self.assertEqual(result.data["fecha_corte"], first.data["fecha_corte"])
            acumulados += result.data["results"]
            cursor = result.data["next_cursor"]
            if cursor is None:
                break
            result = self.client.get(URL, {"cursor": cursor})
        else:
            self.fail("Cursor no termina")
        self.assertEqual([e["id"] for e in acumulados], [e["id"] for e in expected])
        self.assertEqual(len({e["id"] for e in acumulados}), len(expected))
        self.assertEqual([(e["fuente"], -e["evento_id"]) for e in expected], sorted((e["fuente"], -e["evento_id"]) for e in expected))

    def cursor(self):
        response = self.client.get(URL, {"fuente": "OBRA_EVENTO", "limit": 1})
        self.assertTrue(response.data["has_more"])
        return response.data["next_cursor"]

    def test_cursor_manipulado_otros_parametros_y_duplicados(self):
        token = self.cursor()
        for query in [{"cursor": token + "x"}, {"cursor": ""}, {"cursor": token, "limit": 1}, {"cursor": token, "desconocido": "x"}]:
            response = self.client.get(URL, query)
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.data["code"], "cursor_invalido")
        response = self.client.get(URL, {"cursor": [token, token]})
        self.assertEqual(response.data["code"], "cursor_invalido")

    def test_cursor_expira_sin_renovar_ttl_entre_paginas(self):
        token = self.cursor()
        now = timezone.now()
        with patch("django.core.signing.time.time", return_value=now.timestamp() + 901), patch("apps.auditoria.cursors.timezone.now", return_value=now + timedelta(seconds=901)):
            response = self.client.get(URL, {"cursor": token})
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.data["code"], "cursor_invalido")
        payload = signing.loads(token, salt=SALT)
        payload["corte"] = (now - timedelta(seconds=901)).isoformat()
        response = self.client.get(URL, {"cursor": signing.dumps(payload, salt=SALT)})
        self.assertEqual(response.status_code, 400)

    def test_cursor_identidad_rol_version_y_contenido_malformado(self):
        token = self.cursor()
        self.autenticar(self.supervisor)
        self.assertEqual(self.client.get(URL, {"cursor": token}).status_code, 400)
        self.autenticar(self.gerencia)
        payload = signing.loads(token, salt=SALT)
        for key, value in [("marcas", {"USUARIO_EVENTO": 5}), ("ultima", ["x", "OBRA_EVENTO", 1]), ("filtros", {"limit": 1, "cursor": "x"}), ("identidad", {"id": self.gerencia.pk, "rol": "GERENCIA", "sesion_version": 2})]:
            response = self.client.get(URL, {"cursor": signing.dumps({**payload, key: value}, salt=SALT)})
            self.assertEqual(response.status_code, 400, (key, response.data))

    def test_mismo_rol_otra_identidad_y_misma_identidad_otra_version(self):
        from apps.usuarios.models import Usuario
        token = self.cursor()
        otra = Usuario.objects.create_user(username="otra_g", email="otra_g@example.test", rol="GERENCIA")
        self.autenticar(otra)
        self.assertEqual(self.client.get(URL, {"cursor": token}).data["code"], "cursor_invalido")
        services_usuarios.editar_usuario(self.gerencia, {"email": "nueva_identidad@example.test"}, self.ti)
        self.gerencia.refresh_from_db()
        self.autenticar(self.gerencia)
        self.assertEqual(self.client.get(URL, {"cursor": token}).data["code"], "cursor_invalido")

    def test_claims_no_autorizan_y_recurso_fuera_de_ambito_no_revela_existencia(self):
        token = AccessToken.for_user(self.ti)
        token["rol"] = "GERENCIA"
        token["is_superuser"] = True
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual(self.client.get(URL, {"fuente": "FINANZAS_EVENTO"}).status_code, 403)
        for pk in [self.obra.pk, 9223372036854775807]:
            result = self.client.get(URL, {"recurso_tipo": "OBRA", "recurso_id": str(pk)})
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.data["results"], [])

    def test_openapi_versionado_alineado_con_esquema_y_catalogos(self):
        import json
        from pathlib import Path
        from django.conf import settings
        from apps.auditoria.serializers import RECURSOS, EventoPublicoSerializer
        schema = json.loads((Path(settings.BASE_DIR) / "docs" / "openapi" / "SPEC-008-v1.json").read_text())
        self.assertEqual(schema["openapi"], "3.1.0")
        self.assertEqual(set(schema["components"]["schemas"]["Fuente"]["enum"]), set(FUENTES))
        self.assertEqual(set(schema["components"]["schemas"]["RecursoTipo"]["enum"]), RECURSOS)
        self.assertEqual(set(schema["components"]["schemas"]["Evento"]["required"]), set(EventoPublicoSerializer().fields))
        self.assertEqual({p["name"] for p in schema["paths"][URL]["get"]["parameters"]}, {"modulo", "fuente", "tipo", "actor", "recurso_tipo", "recurso_id", "desde", "hasta", "limit", "cursor"})

    def test_jwt_revocado_expirado_inactivo_y_cambio_rol_real(self):
        token = self.cursor()
        # Mantener una Gerencia activa al ejecutar el cambio autorizado.
        from apps.usuarios.models import Usuario
        Usuario.objects.create_user(username="otra_g", email="otra_g@example.test", rol="GERENCIA")
        services_usuarios.cambiar_rol(self.gerencia, {"rol": "SUPERVISOR_OBRAS", "motivo": "Cambio autorizado"}, self.ti)
        self.assertEqual(self.client.get(URL).status_code, 401)
        self.gerencia.refresh_from_db()
        self.autenticar(self.gerencia)
        self.assertEqual(self.client.get(URL, {"cursor": token}).status_code, 400)
        expired = AccessToken.for_user(self.gerencia)
        expired.set_exp(from_time=timezone.now() - timedelta(days=1), lifetime=timedelta(seconds=1))
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {expired}")
        self.assertEqual(self.client.get(URL).status_code, 401)
        self.autenticar(self.gerencia)
        self.gerencia.is_active = False
        self.gerencia.save()
        self.assertEqual(self.client.get(URL).status_code, 401)

    def test_405_401_head_options_y_no_escrituras_en_get(self):
        for method in ["post", "put", "patch", "delete"]:
            self.assertEqual(getattr(self.client, method)(URL, {}, format="json").status_code, 405)
        head = self.client.head(URL)
        self.assertEqual(head.status_code, 200)
        self.assertEqual(head.content, b"")
        self.assertEqual(self.client.options(URL).status_code, 200)
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(URL)
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.assertFalse(any(q["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE", "CREATE", "ALTER")) for q in queries))
        self.client.credentials()
        self.assertEqual(self.client.get(URL).status_code, 401)

    def test_cursor_solo_lleva_marcas_de_fuentes_autorizadas(self):
        self.autenticar(self.finanzas)
        result = self.client.get(URL, {"limit": 1})
        payload = signing.loads(result.data["next_cursor"], salt=SALT)
        self.assertEqual(set(payload["marcas"]), {"FINANZAS_EVENTO"})
        self.assertEqual(payload["identidad"]["id"], self.finanzas.pk)
        self.assertNotIn("motivo", payload["filtros"])
        self.assertNotIn(self.finanzas.email, str(payload))

    def test_default_25_maximo_50_y_paginacion_vacia_final(self):
        for i in range(51):
            FUENTES["OBRA_EVENTO"].modelo.objects.create(obra=self.obra, tipo="EDICION", estado_anterior="FINALIZADA", estado_nuevo="FINALIZADA", registrado_por=self.supervisor, motivo=f"Registro histórico {i}", datos_nuevos={"estado": "FINALIZADA"})
        first = self.client.get(URL, {"fuente": "OBRA_EVENTO"})
        self.assertEqual(len(first.data["results"]), 25)
        self.assertTrue(first.data["has_more"])
        maximum = self.client.get(URL, {"fuente": "OBRA_EVENTO", "limit": 50})
        self.assertEqual(len(maximum.data["results"]), 50)
        result = self.client.get(URL, {"cursor": maximum.data["next_cursor"]})
        self.assertFalse(result.data["has_more"])
        self.assertIsNone(result.data["next_cursor"])

    def test_ventana_incluye_inicio_y_excluye_inicio_dia_siguiente(self):
        from datetime import date
        inicio = inicio_civil(date(2026, 9, 6))
        fin = inicio_civil(date(2026, 9, 7))
        event = FUENTES["OBRA_EVENTO"].modelo.objects.first()
        for instante, esperado in [(inicio, 1), (inicio.astimezone(utc.utc) - timedelta(microseconds=1), 0), (fin, 0)]:
            models.QuerySet(model=type(event)).filter(pk=event.pk).update(creado_en=instante)
            response = self.client.get(URL, {"fuente": "OBRA_EVENTO", "desde": "2026-09-06", "hasta": "2026-09-06"})
            self.assertEqual(len(response.data["results"]), esperado)

    def test_5xx_correlacion_sin_sql_headers_ni_snapshots_en_respuesta_o_log(self):
        with patch("apps.auditoria.views.consultar", side_effect=DatabaseError("SQL password=SECRETO")), self.assertLogs("apps.auditoria.views", level="ERROR") as captured:
            response = self.client.get(URL)
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response["X-Correlation-ID"], response.data["correlacion"])
        self.assertNotIn("SECRETO", str(response.data) + str(captured.output))

    def test_consultas_acotadas_y_limit_sql_no_n_mas_uno(self):
        for _ in range(60):
            FUENTES["OBRA_EVENTO"].modelo.objects.create(obra=self.obra, tipo="EDICION", estado_anterior="FINALIZADA", estado_nuevo="FINALIZADA", registrado_por=self.supervisor, motivo="Ajuste histórico de prueba", datos_nuevos={"fecha_programada": "2026-11-11"})
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(URL, {"limit": 1})
        self.assertEqual(len(response.data["results"]), 1)
        self.assertLessEqual(len(queries), 16)  # principal, revalidación, 7 MAX + 7 páginas.
        pages = [q["sql"] for q in queries if '"datos_nuevos"' in q["sql"]]
        self.assertTrue(pages)
        self.assertTrue(all("LIMIT 2" in sql for sql in pages))
