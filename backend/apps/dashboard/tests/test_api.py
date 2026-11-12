from datetime import date, datetime, timedelta, timezone as utc
from decimal import Decimal, localcontext
from unittest.mock import patch

from django.db import connection, DatabaseError, models
from django.test import TransactionTestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.dashboard.consultas import ESTADOS
from apps.dashboard.filtros import desplazar_mes, inicio_civil, ZONA
from apps.dashboard.consistencia import lectura_estable
from apps.comercial.models import Presupuesto, PresupuestoItem
from apps.usuarios.models import Usuario
from apps.usuarios.tokens import AccessToken
from apps.obras.models import Obra, CierreCostosObra
from apps.obras import services_costos as costos
from apps.finanzas import services_documentos as documentos
from apps.finanzas.models import DocumentoCobro, PagoDocumento
from apps.finanzas.validaciones import hoy_santiago, LIMITE
from .base import DashboardBase, BASE, RESUMEN, SERIE, ACTIVAS

PUBLICOS = {"id", "codigo", "cliente", "cliente_nombre", "categoria_nombre", "estado", "tecnico_responsable", "tecnico_nombre", "fecha_programada", "presupuesto_neto"}


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class DashboardAPITests(DashboardBase, TransactionTestCase):
    def setUp(self):
        self.preparar_dashboard()

    def test_resumen_esquema_tipos_y_fuentes_exactas(self):
        r = self.client.get(RESUMEN)
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(set(r.data), {"generado_en", "zona_horaria", "moneda", "periodo", "operacion", "rentabilidad_cerrada_periodo", "cobranza_actual"})
        self.assertEqual(set(r.data["operacion"]), {"obras_por_estado_actual", "presupuestos_pendientes_gerencia_actual", "obras_finalizadas_periodo"})
        self.assertEqual(set(r.data["operacion"]["obras_por_estado_actual"]), set(ESTADOS))
        self.assertEqual(r.data["operacion"]["obras_finalizadas_periodo"], 1)
        self.assertEqual(r.data["rentabilidad_cerrada_periodo"], {"obras_con_cierre": 1, "presupuesto_neto": "2080.22", "costo_real_neto": "8000.00", "margen_real_neto": "-5919.78"})
        self.assertEqual(r.data["cobranza_actual"], {"documentos_vigentes": 0, "monto_documentado_bruto": "0.00", "abonado": "0.00", "saldo": "0.00", "saldo_vencido": "0.00"})
        self.assertEqual(r.data["zona_horaria"], "America/Santiago")
        self.assertEqual(r.data["moneda"], "CLP")
        self.assertIsNotNone(datetime.fromisoformat(r.data["generado_en"]).tzinfo)

    def test_periodo_default_seis_meses_calendario_mes_actual_parcial(self):
        for corte, inicio, fin in [(datetime(2026, 11, 12, 20, tzinfo=utc.utc), "2026-06-01", "2026-11-12"), (datetime(2026, 1, 1, 2, tzinfo=utc.utc), "2025-07-01", "2025-12-31"), (datetime(2026, 1, 1, 4, tzinfo=utc.utc), "2025-08-01", "2026-01-01")]:
            with patch("apps.dashboard.consistencia.timezone.now", return_value=corte):
                r = self.client.get(RESUMEN)
            self.assertEqual(r.status_code, 200, r.data)
            self.assertEqual(r.data["periodo"], {"desde": inicio, "hasta": fin})

    def test_cinco_estados_actuales_y_pendientes_no_se_filtran_por_periodo(self):
        for estado in ESTADOS:
            self.historica(estado=estado)
        Presupuesto.objects.create(cliente=self.cliente, creado_por=self.finanzas, descripcion="Pendiente", estado="PENDIENTE_GERENCIA")
        r = self.client.get(RESUMEN, {"desde": "2020-01-01", "hasta": "2020-01-31"})
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["operacion"]["obras_por_estado_actual"], {"PLANIFICADA": 1, "EN_PROCESO": 1, "SUSPENDIDA": 1, "FINALIZADA": 2, "CANCELADA": 1})
        self.assertEqual(r.data["operacion"]["presupuestos_pendientes_gerencia_actual"], 1)
        self.assertEqual(r.data["operacion"]["obras_finalizadas_periodo"], 0)
        self.assertEqual(r.data["rentabilidad_cerrada_periodo"]["margen_real_neto"], "0.00")

    def test_rangos_validos_366_inclusivos_y_fecha_no_futura(self):
        self.assertEqual(self.client.get(RESUMEN, {"desde": "2024-01-01", "hasta": "2024-12-31"}).status_code, 200)
        manana = hoy_santiago() + timedelta(days=1)
        self.assertEqual(self.client.get(RESUMEN, {"desde": manana.isoformat(), "hasta": manana.isoformat()}).status_code, 400)

    def test_query_estricta_resumen(self):
        for query in ["x=1", "desde=", "desde=2026-01-01", "hasta=2026-01-01", "desde=2026-02-30&hasta=2026-03-01", "desde=2026-1-01&hasta=2026-01-02", "desde=2026-02-01&hasta=2026-01-01", "desde=2024-01-01&hasta=2025-01-01", "desde=2026-01-01&desde=2026-01-02&hasta=2026-01-31", "page=1", "meses=1", "desde=0000-01-01&hasta=0000-01-01", "desde=9999-12-31&hasta=9999-12-31"]:
            r = self.client.get(RESUMEN + "?" + query)
            self.assertEqual(r.status_code, 400, (query, r.data))

    def test_mes_query_estricto_y_extremos(self):
        for valor in ("0", "13", "-1", "+1", "01", "1.0", "", "true", "99999999999999999999"):
            self.assertEqual(self.client.get(SERIE, {"meses": valor}).status_code, 400, valor)
        self.assertEqual(self.client.get(SERIE + "?meses=1&meses=2").status_code, 400)
        self.assertEqual(self.client.get(SERIE, {"page": 1}).status_code, 400)
        for valor in (1, 12):
            r = self.client.get(SERIE, {"meses": valor})
            self.assertEqual(r.status_code, 200, r.data)
            self.assertEqual(len(r.data["puntos"]), valor)

    def test_serie_mes_local_huecos_estados_y_futuro(self):
        corte = datetime(2026, 11, 12, 20, tzinfo=utc.utc)
        # 1 de septiembre UTC, todavía agosto en Santiago.
        self.historica(fecha=datetime(2026, 9, 1, 2, tzinfo=utc.utc))
        self.historica(fecha=datetime(2026, 9, 1, 5, tzinfo=utc.utc))
        self.historica(fecha=datetime(2026, 11, 11, 10, tzinfo=utc.utc))
        self.historica(fecha=corte + timedelta(minutes=1))
        self.historica(estado="CANCELADA", fecha=datetime(2026, 10, 5, 10, tzinfo=utc.utc))
        # Excluir la finalización de la preparación del periodo histórico elegido.
        Obra.objects.filter(pk=self.obra.pk).update(creado_en=corte - timedelta(days=3), iniciado_en=corte - timedelta(days=2), finalizado_en=corte + timedelta(days=1))
        with patch("apps.dashboard.consistencia.timezone.now", return_value=corte):
            r = self.client.get(SERIE, {"meses": 3})
        self.assertEqual(r.data, {"metrica": "OBRAS_FINALIZADAS", "zona_horaria": "America/Santiago", "puntos": [{"mes": "2026-09", "cantidad": 1}, {"mes": "2026-10", "cantidad": 0}, {"mes": "2026-11", "cantidad": 1}]})

    def test_fronteras_civiles_y_dst_23_25_horas(self):
        for dia, siguiente, horas in [(date(2026, 9, 6), date(2026, 9, 7), 23), (date(2026, 4, 4), date(2026, 4, 5), 25)]:
            self.assertEqual((inicio_civil(siguiente).astimezone(utc.utc) - inicio_civil(dia).astimezone(utc.utc)).total_seconds(), horas * 3600)
            self.historica(fecha=inicio_civil(dia))
            self.historica(fecha=inicio_civil(siguiente).astimezone(utc.utc) - timedelta(microseconds=1))
            self.historica(fecha=inicio_civil(siguiente))
            r = self.client.get(RESUMEN, {"desde": dia.isoformat(), "hasta": dia.isoformat()})
            self.assertEqual(r.status_code, 200, r.data)
            self.assertEqual(r.data["operacion"]["obras_finalizadas_periodo"], 2)

    def test_redondeo_oficial_por_linea_no_sum_productos(self):
        obra = self.historica(estado="EN_PROCESO", lineas=(("0.500", "0.01"), ("0.500", "0.01")))
        r = self.client.get(ACTIVAS)
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["results"][0]["presupuesto_neto"], "0.02")
        self.assertEqual(obra.presupuesto.monto_neto, Decimal("0.02"))
        Obra.objects.filter(pk=obra.pk).update(estado="FINALIZADA", finalizado_en=timezone.now())
        CierreCostosObra.objects.create(obra=obra, materiales_total=Decimal("0.00"), otros_total=Decimal("0.00"), mano_obra_total=Decimal("0.01"), costo_total=Decimal("0.01"), version_validada=1, validado_por=self.supervisor, finalizado_por=self.supervisor)
        r = self.client.get(RESUMEN)
        self.assertEqual(r.data["rentabilidad_cerrada_periodo"]["presupuesto_neto"], "2080.24")

    def test_margenes_positivo_cero_negativo_solo_cierres_del_mismo_conjunto(self):
        for costo, esperado in (("1.00", "9.00"), ("10.00", "0.00"), ("11.00", "-1.00")):
            dia = date(2020, 1, int(Decimal(costo)))
            self.historica(fecha=inicio_civil(dia), costo=costo)
            r = self.client.get(RESUMEN, {"desde": dia.isoformat(), "hasta": dia.isoformat()})
            self.assertEqual(r.data["rentabilidad_cerrada_periodo"]["margen_real_neto"], esperado)
            self.assertEqual(r.data["rentabilidad_cerrada_periodo"]["obras_con_cierre"], 1)
        self.historica(estado="EN_PROCESO", costo="999.00")
        self.assertEqual(self.client.get(RESUMEN).data["rentabilidad_cerrada_periodo"]["obras_con_cierre"], 1)

    def test_finalizada_sin_cierre_409_no_silenciar_ni_cero_y_log_saneado(self):
        self.historica(cierre=False)
        with self.assertLogs("apps.dashboard.consultas", level="WARNING") as logs:
            r = self.client.get(RESUMEN)
        self.assertEqual(r.status_code, 409, r.data)
        self.assertEqual(set(r.data), {"code", "detail"})
        self.assertEqual(r.data["code"], "cierre_costos_inconsistente")
        self.assertNotIn(self.cliente.correo, str(logs.output))
        self.assertEqual(self.client.get(SERIE).status_code, 200)
        self.assertEqual(self.client.get(ACTIVAS).status_code, 200)

    def test_cierre_ausente_fuera_periodo_no_impide_periodo_integro(self):
        self.historica(fecha=inicio_civil(date(2020, 1, 1)), cierre=False)
        self.assertEqual(self.client.get(RESUMEN).status_code, 200)

    def test_activa_esquema_exacto_reutiliza_nombres_y_codigo_sin_pii(self):
        self.tecnico.first_name, self.tecnico.last_name = "Nombre", "Laboral"
        self.tecnico.save()
        obra = self.historica(estado="EN_PROCESO")
        self.historica(estado="SUSPENDIDA")
        r = self.client.get(ACTIVAS)
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(set(r.data), {"count", "next", "previous", "results"})
        self.assertEqual(r.data["count"], 1)
        row = r.data["results"][0]
        self.assertEqual(set(row), PUBLICOS)
        self.assertEqual(row["codigo"], obra.codigo)
        self.assertEqual(row["cliente"], self.cliente.pk)
        self.assertEqual(row["tecnico_nombre"], "Nombre Laboral")
        for privado in ("descripcion", "email", "rut", "costo_hora_neto", "margen_proyectado", "fotos", self.cliente.correo):
            self.assertNotIn(privado, str(r.data))

    def test_paginacion_25_orden_empates_y_prefetch_solo_pagina(self):
        for _ in range(28):
            self.historica(estado="EN_PROCESO")
        instante = timezone.now() - timedelta(days=5)
        # Para mantener CHECK inicio >= creado, se retrofecha solo creado_en.
        Obra.objects.filter(estado="EN_PROCESO").update(creado_en=instante)
        with CaptureQueriesContext(connection) as q:
            r = self.client.get(ACTIVAS)
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["count"], 28)
        self.assertEqual(len(r.data["results"]), 25)
        self.assertLessEqual(len(q), 11)
        items = [row["sql"] for row in q if 'FROM "comercial_presupuestoitem"' in row["sql"]]
        self.assertEqual(len(items), 1)
        r2 = self.client.get(r.data["next"])
        ids = [row["id"] for row in r.data["results"] + r2.data["results"]]
        self.assertEqual(ids, sorted(ids, reverse=True))
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(r2.data["results"]), 3)
        self.assertTrue(r.data["next"].startswith("http://testserver/api/dashboard/obras-activas/"))

    def test_page_invalida_y_fuera_rango_400(self):
        for query in ("page=0", "page=-1", "page=1.0", "page=01", "page=last", "page=", "page=2", "page=9999999999999999999999", "page=1&page=2", "limit=25", "estado=EN_PROCESO"):
            r = self.client.get(ACTIVAS + "?" + query)
            self.assertEqual(r.status_code, 400, (query, r.data))
            if query.startswith("page=") and "&" not in query:
                self.assertIn("page", r.data)

    def test_cinco_roles_flags_claims_y_options(self):
        ti = Usuario.objects.create_user(username="ti010", email="ti010@example.test", rol="ADMINISTRADOR_TI")
        for user in (self.gerencia, self.finanzas, self.supervisor, self.tecnico, ti):
            user.is_staff = user.is_superuser = True
            user.save()
            token = AccessToken.for_user(user)
            token["rol"] = "GERENCIA"
            self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
            esperado = 200 if user.rol == "GERENCIA" else 403
            for ruta in (RESUMEN, SERIE, ACTIVAS):
                self.assertEqual(self.client.get(ruta).status_code, esperado, user.rol)
                self.assertEqual(self.client.options(ruta).status_code, esperado)
                self.assertEqual(self.client.head(ruta).status_code, esperado)

    def test_jwt_ausente_expirado_revocado_inactivo(self):
        self.client.credentials()
        self.assertEqual(self.client.get(RESUMEN).status_code, 401)
        token = AccessToken.for_user(self.gerencia)
        token.set_exp(from_time=timezone.now() - timedelta(days=1), lifetime=timedelta(seconds=1))
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual(self.client.get(RESUMEN).status_code, 401)
        self.autenticar(self.gerencia)
        self.gerencia.sesion_version += 1
        self.gerencia.save()
        self.assertEqual(self.client.get(RESUMEN).status_code, 401)
        self.autenticar(self.gerencia)
        self.gerencia.is_active = False
        self.gerencia.save()
        self.assertEqual(self.client.get(RESUMEN).status_code, 401)

    def test_metodos_405_cache_y_get_head_options_sin_writes(self):
        for ruta in (RESUMEN, SERIE, ACTIVAS):
            with CaptureQueriesContext(connection) as q:
                r = self.client.get(ruta)
                h = self.client.head(ruta)
                o = self.client.options(ruta)
            self.assertEqual((r.status_code, h.status_code, o.status_code), (200, 200, 200))
            self.assertEqual(h.content, b"")
            self.assertEqual(r["Cache-Control"], "private, no-store")
            self.assertIn("Authorization", r["Vary"])
            self.assertFalse(any(row["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE", "CREATE", "ALTER")) for row in q))
            for metodo in ("post", "put", "patch", "delete"):
                self.assertEqual(getattr(self.client, metodo)(ruta, {}, format="json").status_code, 405)

    def test_error_500_saneado_con_correlacion_y_aislamiento_restaurado(self):
        with patch("apps.dashboard.consultas.operacion_actual", side_effect=DatabaseError("SQL SECRETO")), self.assertLogs("apps.dashboard.views", level="ERROR") as logs:
            r = self.client.get(RESUMEN)
        self.assertEqual(r.status_code, 500)
        self.assertEqual(r["X-Correlation-ID"], r.data["correlacion"])
        self.assertNotIn("SECRETO", str(r.data) + str(logs.output))
        with connection.cursor() as cursor:
            cursor.execute("SHOW transaction_read_only")
            self.assertEqual(cursor.fetchone()[0], "off")
            cursor.execute("SHOW transaction_isolation")
            self.assertEqual(cursor.fetchone()[0], "read committed")

    def test_snapshot_read_only_real_y_no_modifica_configuracion_global(self):
        with lectura_estable():
            with connection.cursor() as cursor:
                cursor.execute("SHOW transaction_read_only")
                self.assertEqual(cursor.fetchone()[0], "on")
                cursor.execute("SHOW transaction_isolation")
                self.assertEqual(cursor.fetchone()[0], "repeatable read")
            with self.assertRaises(DatabaseError):
                Usuario.objects.filter(pk=self.gerencia.pk).update(first_name="No permitido")
        self.gerencia.refresh_from_db()
        self.assertNotEqual(self.gerencia.first_name, "No permitido")

    def test_presupuestos_fraccionarios_y_maximos_coinciden_propiedad_oficial(self):
        muestras = (("0.001", "0.01"), ("0.500", "0.01"), ("1.125", "1234.56"), ("999999999.999", "9999999999999.99"))
        for c, p in muestras:
            obra = self.historica(estado="EN_PROCESO", lineas=((c, p), (c, p)))
            r = self.client.get(ACTIVAS)
            row = next(row for row in r.data["results"] if row["id"] == obra.pk)
            self.assertEqual(row["presupuesto_neto"], format(obra.presupuesto.monto_neto, ".2f"))
            origen = self.client.get(f"/api/presupuestos/{obra.presupuesto_id}/")
            self.assertEqual(origen.status_code, 200, origen.data)
            self.assertEqual(row["presupuesto_neto"], origen.data["monto_neto"])

    def test_explain_y_consultas_resumen_sin_n_mas_uno(self):
        for _ in range(8):
            self.historica()
        with CaptureQueriesContext(connection) as q:
            r = self.client.get(RESUMEN)
        self.assertEqual(r.status_code, 200, r.data)
        self.assertLessEqual(len(q), 12)
        plan = Obra.objects.filter(estado="EN_PROCESO").order_by("-creado_en", "-id").explain()
        self.assertTrue(plan)

    def test_rentabilidad_por_lotes_conserva_importes_y_no_consulta_por_obra(self):
        for _ in range(6):
            self.historica()
        with patch("apps.dashboard.consultas.LOTE", 2), CaptureQueriesContext(connection) as queries:
            r = self.client.get(RESUMEN)
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["rentabilidad_cerrada_periodo"], {"obras_con_cierre": 7, "presupuesto_neto": "2140.22", "costo_real_neto": "8060.00", "margen_real_neto": "-5919.78"})
        self.assertEqual(sum('FROM "comercial_presupuestoitem"' in q["sql"] for q in queries), 4)

    def test_suma_cierres_mayor_38_digitos_no_redondea_margen(self):
        self.historica(costo=str(LIMITE))
        self.historica(costo=str(LIMITE))
        with localcontext() as ctx:
            ctx.prec = 80
            costo = Decimal("8000.00") + LIMITE * 2
            margen = Decimal("2100.22") - costo
        r = self.client.get(RESUMEN)
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["rentabilidad_cerrada_periodo"]["costo_real_neto"], format(costo, ".2f"))
        self.assertEqual(r.data["rentabilidad_cerrada_periodo"]["margen_real_neto"], format(margen, ".2f"))

    def test_perfil_sql_postgresql_con_varias_paginas(self):
        import json
        from time import perf_counter
        from apps.dashboard import consultas
        for _ in range(28):
            self.historica(estado="EN_PROCESO")
        metricas = {}
        for nombre, ruta in (("resumen", RESUMEN), ("serie", SERIE), ("activas", ACTIVAS)):
            inicio = perf_counter()
            with CaptureQueriesContext(connection) as queries:
                response = self.client.get(ruta)
            self.assertEqual(response.status_code, 200, response.data)
            metricas[nombre] = {"queries": len(queries), "ms": round((perf_counter() - inicio) * 1000, 3)}
        with lectura_estable():
            plan = json.loads(consultas.obras_activas()[:25].explain(analyze=True, buffers=True, format="json"))[0]
        metricas["explain_activas"] = {"nodo": plan["Plan"]["Node Type"], "filas": plan["Plan"]["Actual Rows"], "planning_ms": plan["Planning Time"], "execution_ms": plan["Execution Time"]}
        self.assertEqual(plan["Plan"]["Actual Rows"], 25)
        self.assertLessEqual(metricas["activas"]["queries"], 11)
        self.assertLessEqual(metricas["resumen"]["queries"], 12)
        print("PERFIL_DASHBOARD_POSTGRESQL=" + json.dumps(metricas, sort_keys=True))

    def test_openapi_versionado_rutas_campos_y_referencias(self):
        import json
        from pathlib import Path
        from django.conf import settings
        from apps.dashboard.serializers import ResumenSerializer
        schema = json.loads((Path(settings.BASE_DIR) / "docs/openapi/SPEC-010-v1.json").read_text())
        self.assertEqual(schema["openapi"], "3.1.0")
        self.assertEqual(set(schema["paths"]), {RESUMEN, SERIE, ACTIVAS})
        self.assertEqual(set(schema["components"]["schemas"]["ObraActiva"]["required"]), PUBLICOS)
        self.assertEqual(set(schema["components"]["schemas"]["Resumen"]["required"]), set(ResumenSerializer().fields))
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


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class FinanzasDashboardTests(DashboardBase, TransactionTestCase):
    def setUp(self):
        self.preparar_dashboard()

    def cartera(self):
        r = self.client.get(RESUMEN)
        self.assertEqual(r.status_code, 200, r.data)
        return r.data["cobranza_actual"]

    def test_documentos_pagos_parciales_total_anulacion_coinciden_resumen_origen(self):
        doc = self.documento()
        for monto in (None, "100.13", "2080.22"):
            if monto:
                ultimo = self.pago(doc, monto)
            actual = self.cartera()
            origen = self.client.get("/api/finanzas/cobranzas/resumen/").data
            self.assertEqual(actual, {"documentos_vigentes": origen["documentos"], "monto_documentado_bruto": origen["monto_documentado_total"], "abonado": origen["abonado_total"], "saldo": origen["saldo_total"], "saldo_vencido": origen["saldo_vencido"]})
        self.anular(doc, ultimo)
        self.assertEqual(self.cartera()["abonado"], "100.13")
        for p in doc.pagos.filter(activo=True):
            self.anular(doc, p)
        documentos.revertir_documento(doc.pk, {"motivo": "Rectificación", "referencia_rectificacion_externa": "Respaldo"}, self.finanzas)
        self.assertEqual(self.cartera()["documentos_vigentes"], 0)

    def test_vencido_saldo_positivo_actual_no_filtrado_periodo(self):
        ayer = hoy_santiago() - timedelta(days=1)
        doc = self.documento(fecha_emision=ayer.isoformat(), fecha_vencimiento=ayer.isoformat())
        self.pago(doc)
        r = self.client.get(RESUMEN, {"desde": "2020-01-01", "hasta": "2020-01-02"})
        self.assertEqual(r.data["cobranza_actual"]["saldo_vencido"], "2080.22")
        self.assertEqual(r.data["rentabilidad_cerrada_periodo"]["obras_con_cierre"], 0)

    def test_documento_pagado_no_se_cuenta_como_documentos_extra(self):
        doc = self.documento()
        for _ in range(3):
            self.pago(doc, "10.00")
        actual = self.cartera()
        self.assertEqual(actual["documentos_vigentes"], 1)
        self.assertEqual(actual["monto_documentado_bruto"], "2180.35")
        self.assertEqual(actual["abonado"], "30.00")

    def test_documento_grande_y_contexto_decimal_pequeno_no_pierden_precision(self):
        doc = self.documento()
        importe = Decimal("123456789012345678901234567890123456.78")
        models.QuerySet(model=DocumentoCobro).filter(pk=doc.pk).update(monto_neto=importe, monto_impuesto=Decimal("0.01"), monto_total=Decimal("123456789012345678901234567890123456.79"))
        self.pago(doc, "0.01")
        with localcontext() as ctx:
            ctx.prec = 10
            actual = self.cartera()
        self.assertEqual(actual["saldo"], str(importe))
        self.assertEqual(actual["monto_documentado_bruto"], "123456789012345678901234567890123456.79")

    def test_saldos_individuales_corruptos_409_aunque_sumatoria_no_negativa(self):
        doc = self.documento()
        p = self.pago(doc)
        models.QuerySet(model=PagoDocumento).filter(pk=p.pk).update(monto=Decimal("3000.00"))
        with self.assertLogs("apps.dashboard.consultas", level="WARNING"):
            r = self.client.get(RESUMEN)
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "saldo_inconsistente")

    def test_limite_agregado_financiero_igual_origen_no_silencia_overflow(self):
        doc = self.documento()
        otro = self.documento(obra=self.otra_finalizada(), folio="1011")
        with localcontext() as ctx:
            ctx.prec = 80
            neto = LIMITE - Decimal("0.01")
        models.QuerySet(model=DocumentoCobro).filter(pk__in=[doc.pk, otro.pk]).update(monto_neto=neto, monto_impuesto=Decimal("0.01"), monto_total=LIMITE)
        with self.assertLogs("apps.dashboard.consultas", level="WARNING"):
            r = self.client.get(RESUMEN)
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "importe_fuera_rango")

    def test_cortesia_sin_cobro_conserva_costo_y_margen_no_ingreso(self):
        # Preparar una segunda obra a través del flujo operativo, con cortesía.
        obra = self.otra_obra()
        self.obra = obra
        self.completa()
        costos.registrar_cortesia(obra, {"justificacion": "Garantía", "motivo": "Decisión autorizada"}, self.supervisor)
        self.validar()
        self.finalizar()
        actual = self.client.get(RESUMEN)
        self.assertEqual(actual.status_code, 200, actual.data)
        self.assertEqual(actual.data["rentabilidad_cerrada_periodo"]["costo_real_neto"], "16000.00")
        self.assertEqual(actual.data["cobranza_actual"]["monto_documentado_bruto"], "0.00")
