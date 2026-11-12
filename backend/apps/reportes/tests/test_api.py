from datetime import date, datetime, timedelta, timezone as utc
from decimal import Decimal, localcontext
from unittest.mock import patch

from django.core.cache import cache
from django.db import connection, models, DatabaseError
from django.test import TransactionTestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.reportes.catalogo import COLUMNAS, TIPOS
from apps.reportes.consistencia import snapshot
from apps.reportes.filtros import inicio_civil, ZONA
from apps.obras.models import Obra, CierreCostosObra
from apps.obras import services_costos as costos
from apps.comercial.models import Cliente
from apps.finanzas.models import DocumentoCobro, PagoDocumento
from apps.finanzas import services_documentos
from apps.finanzas.validaciones import hoy_santiago, LIMITE
from apps.usuarios.models import Usuario
from apps.usuarios.tokens import AccessToken
from .base import ReportesBase, BASE

ENVELOPE = {"count", "next", "previous", "results", "totales", "periodo", "moneda", "fecha_corte"}


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ReportesAPITests(ReportesBase, TransactionTestCase):
    def setUp(self):
        self.preparar_reportes()

    def test_catalogo_exacto_gerencia_y_finanzas(self):
        for actor, tipos in ((self.gerencia, TIPOS), (self.finanzas, ("cobranzas",))):
            self.autenticar(actor)
            r = self.client.get(BASE + "catalogo/")
            self.assertEqual(r.status_code, 200, r.data)
            self.assertEqual(set(r.data), {"moneda", "zona_horaria", "formatos", "reportes"})
            self.assertEqual(r.data["formatos"], ["csv", "xlsx", "pdf"])
            self.assertEqual([x["tipo"] for x in r.data["reportes"]], list(tipos))
            for row in r.data["reportes"]:
                self.assertEqual(set(row), {"tipo", "titulo", "filtros", "formatos"})
            self.assertEqual(self.client.get(BASE + "catalogo/", {"page": 1}).status_code, 400)

    def test_tres_listados_schemas_exactos_totales_y_nullables(self):
        self.documento(folio="00001234")
        for tipo in TIPOS:
            r = self.listado(tipo)
            self.assertEqual(r.status_code, 200, r.data)
            self.assertEqual(set(r.data), ENVELOPE)
            self.assertEqual(r.data["count"], 1)
            self.assertEqual(set(r.data["results"][0]), {key for key, _ in COLUMNAS[tipo]})
            self.assertEqual(r.data["totales"]["documentos" if tipo == "cobranzas" else "obras"], 1)
            self.assertEqual(r.data["moneda"], "CLP")
            self.assertIsNotNone(datetime.fromisoformat(r.data["fecha_corte"]).tzinfo)
        self.assertEqual(self.listado("rentabilidad").data["totales"], {"obras": 1, "presupuesto_neto": "2080.22", "costo_real_neto": "8000.00", "margen_neto": "-5919.78"})
        row = self.listado("cobranzas").data["results"][0]
        self.assertEqual(row["folio_externo"], "00001234")
        self.assertEqual(row["monto_documentado_bruto"], "2180.35")

    def test_default_mes_actual_y_fechas_juntas_futuro_366(self):
        r = self.client.get(BASE + "obras/")
        hoy = hoy_santiago()
        self.assertEqual(r.data["periodo"], {"desde": hoy.replace(day=1).isoformat(), "hasta": hoy.isoformat()})
        for tipo in TIPOS:
            self.assertEqual(self.client.get(BASE + tipo + "/", {"desde": "2024-01-01", "hasta": "2024-12-31"}).status_code, 200)
            for params in ({"desde": hoy.isoformat()}, {"hasta": hoy.isoformat()}, {"desde": "2024-01-01", "hasta": "2025-01-01"}, {"desde": hoy.isoformat(), "hasta": (hoy + timedelta(days=1)).isoformat()}):
                self.assertEqual(self.client.get(BASE + tipo + "/", params).status_code, 400)

    def test_filtros_estrictos_por_tipo_y_duplicados(self):
        comunes = ("otro=1", "format=csv", "format=json", "cliente=0", "cliente=01", "cliente=-1", "cliente=1.0", "cliente=9223372036854775808", "desde=2026-02-30&hasta=2026-03-01", "desde=2026-1-01&hasta=2026-01-31", "desde=2026-02-01&hasta=2026-01-01", "desde=9999-12-31&hasta=9999-12-31", "page=0", "page=01", "page=last", "page=2", "page=", "page=1&page=1", "formato=csv", "cliente=1&cliente=1")
        for tipo in TIPOS:
            for query in comunes:
                r = self.client.get(BASE + tipo + "/?" + query)
                self.assertEqual(r.status_code, 400, (tipo, query, r.data))
        for tipo, query in (("obras", "estado=VIGENTE"), ("obras", "fecha_base=OTRA"), ("obras", "fecha_base=FINALIZACION&estado=EN_PROCESO"), ("rentabilidad", "estado=FINALIZADA"), ("rentabilidad", "fecha_base=FINALIZACION"), ("cobranzas", "estado=FINALIZADA"), ("cobranzas", "fecha_base=CREACION")):
            self.assertEqual(self.client.get(BASE + tipo + "/?" + query).status_code, 400)

    def test_estados_fecha_base_y_cliente(self):
        self.historica(estado="SUSPENDIDA")
        self.historica(estado="EN_PROCESO")
        self.assertEqual(self.listado("obras", estado="SUSPENDIDA").data["count"], 1)
        self.assertEqual(self.listado("obras", fecha_base="FINALIZACION").data["count"], 1)
        self.assertEqual(self.listado("obras", cliente=str(self.cliente.pk)).data["count"], 3)
        self.assertEqual(self.listado("obras", cliente="9223372036854775807").data["count"], 0)

    def test_paginacion_25_totales_todas_filas_y_orden(self):
        instante = timezone.now() - timedelta(days=2)
        for _ in range(28):
            self.historica(estado="EN_PROCESO")
        Obra.objects.filter(estado="EN_PROCESO").update(creado_en=instante)
        with CaptureQueriesContext(connection) as q:
            r = self.listado("obras", estado="EN_PROCESO")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["count"], 28)
        self.assertEqual(len(r.data["results"]), 25)
        self.assertEqual(r.data["totales"], {"obras": 28, "presupuesto_neto": "280.00"})
        self.assertLessEqual(len(q), 12)
        r2 = self.client.get(r.data["next"])
        ids = [x["obra"] for x in r.data["results"] + r2.data["results"]]
        self.assertEqual(ids, sorted(ids, reverse=True))
        self.assertEqual(r2.data["totales"], r.data["totales"])
        self.assertEqual(len(r2.data["results"]), 3)
        self.assertEqual(r2.data["previous"].split("?")[0], "http://testserver/api/reportes/obras/")

    def test_decimal_round_half_up_margenes_y_cierre_faltante(self):
        for costo, margen in (("0.01", "0.01"), ("0.02", "0.00"), ("0.03", "-0.01")):
            obra = self.historica(costo=costo, lineas=(("0.500", "0.01"), ("0.500", "0.01")))
            r = self.listado("rentabilidad")
            row = next(x for x in r.data["results"] if x["obra"] == obra.pk)
            self.assertEqual(row["presupuesto_neto"], "0.02")
            self.assertEqual(row["margen_neto"], margen)
        self.historica(cierre=False)
        r = self.listado("rentabilidad")
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "cierre_costos_inconsistente")
        self.assertEqual(self.listado("obras").status_code, 200)
        for formato in ("csv", "xlsx", "pdf"):
            cache.clear()
            r = self.client.get(BASE + "rentabilidad/exportar/", {**self.filtros_periodo(), "formato": formato})
            self.assertEqual(r.status_code, 409)
            self.assertFalse(r.streaming)

    def test_cortesia_real_no_elimina_costos(self):
        self.obra = self.otra_obra()
        self.completa()
        costos.registrar_cortesia(self.obra, {"justificacion": "Garantía", "motivo": "Decisión"}, self.supervisor)
        self.validar()
        self.finalizar()
        r = self.listado("rentabilidad")
        row = next(x for x in r.data["results"] if x["obra"] == self.obra.pk)
        self.assertTrue(row["tiene_cortesia_sin_cobro"])
        self.assertEqual(row["costo_real_neto"], "8000.00")
        self.assertEqual(row["margen_neto"], "-8000.00")

    def test_cartera_vigente_pagos_parciales_total_anulado_revertido(self):
        doc = self.documento(folio="00001234")
        p = self.pago(doc)
        r = self.listado("cobranzas")
        self.assertEqual(r.data["results"][0]["estado_cobranza"], "PARCIAL")
        self.assertEqual(r.data["totales"]["saldo"], "2080.22")
        p2 = self.pago(doc, "2080.22")
        self.assertEqual(self.listado("cobranzas", estado="PAGADA").data["count"], 1)
        self.anular(doc, p2)
        self.assertEqual(self.listado("cobranzas").data["totales"]["abonado"], "100.13")
        self.anular(doc, p)
        services_documentos.revertir_documento(doc.pk, {"motivo": "Rectificar", "referencia_rectificacion_externa": "Respaldo"}, self.finanzas)
        self.assertEqual(self.listado("cobranzas").data["count"], 0)

    def test_estado_vencido_depende_del_dia_capturado_no_se_recalcula(self):
        ayer = hoy_santiago() - timedelta(days=1)
        self.documento(fecha_emision=ayer.isoformat(), fecha_vencimiento=ayer.isoformat())
        with patch("apps.finanzas.consultas_cobranzas.hoy_santiago", side_effect=AssertionError("No cambiar el día del snapshot")):
            r = self.listado("cobranzas", estado="VENCIDA")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["totales"]["saldo_vencido"], "2180.35")

    def test_cartera_inconsistente_y_agregado_fuera_rango(self):
        doc = self.documento()
        p = self.pago(doc)
        models.QuerySet(model=PagoDocumento).filter(pk=p.pk).update(monto=Decimal("3000.00"))
        self.assertEqual(self.listado("cobranzas").data["code"], "saldo_inconsistente")
        models.QuerySet(model=PagoDocumento).filter(pk=p.pk).update(monto=Decimal("100.13"))
        otro = self.documento(obra=self.otra_finalizada(), folio="1011")
        with localcontext() as ctx:
            ctx.prec = 80
            neto = LIMITE - Decimal("0.01")
        models.QuerySet(model=DocumentoCobro).filter(pk__in=[doc.pk, otro.pk]).update(monto_neto=neto, monto_impuesto=Decimal("0.01"), monto_total=LIMITE)
        self.assertEqual(self.listado("cobranzas").data["code"], "importe_fuera_rango")

    def test_g_y_af_proyeccion_identica_sin_datos_privados(self):
        self.documento()
        g = self.listado("cobranzas").data
        self.autenticar(self.finanzas)
        af = self.listado("cobranzas").data
        for campo in ("results", "totales", "periodo", "count"):
            self.assertEqual(g[campo], af[campo])
        for secreto in ("costo_real_neto", "margen_neto", "tarifa", "referencia_respaldo", "fotos", self.cliente.correo):
            self.assertNotIn(secreto, str(af))

    def test_dst_limites_civiles_y_finalizacion_en_otro_dia_utc(self):
        for dia, siguiente, horas in ((date(2026, 9, 6), date(2026, 9, 7), 23), (date(2026, 4, 4), date(2026, 4, 5), 25)):
            self.assertEqual((inicio_civil(siguiente).astimezone(utc.utc) - inicio_civil(dia).astimezone(utc.utc)).total_seconds(), horas * 3600)
            self.historica(fecha=inicio_civil(dia))
            self.historica(fecha=inicio_civil(siguiente).astimezone(utc.utc) - timedelta(microseconds=1))
            self.historica(fecha=inicio_civil(siguiente))
            r = self.listado("rentabilidad", desde=dia.isoformat(), hasta=dia.isoformat())
            self.assertEqual(r.status_code, 200, r.data)
            self.assertEqual(r.data["count"], 2)

    def test_roles_flags_claims_head_options_y_404_tipo(self):
        ti = Usuario.objects.create_user(username="ti011", email="ti011@example.test", rol="ADMINISTRADOR_TI")
        for user in (self.gerencia, self.finanzas, self.supervisor, self.tecnico, ti):
            user.is_superuser = user.is_staff = True
            user.save()
            token = AccessToken.for_user(user)
            token["rol"] = "GERENCIA"
            self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
            for tipo in TIPOS:
                permitido = user.rol == "GERENCIA" or user.rol == "ADMINISTRATIVO_FINANZAS" and tipo == "cobranzas"
                for method in ("get", "head", "options"):
                    r = getattr(self.client, method)(BASE + tipo + "/")
                    self.assertEqual(r.status_code, 200 if permitido else 403, (user.rol, tipo, method))
                cache.clear()
                r = self.client.head(BASE + tipo + "/exportar/", {"formato": "csv"})
                self.assertEqual(r.status_code, 200 if permitido else 403)
                self.assertEqual(self.client.options(BASE + tipo + "/exportar/").status_code, 200 if permitido else 403)
            esperado = 404 if user.rol in ("GERENCIA", "ADMINISTRATIVO_FINANZAS") else 403
            self.assertEqual(self.client.get(BASE + "inexistente/exportar/", {"formato": "csv"}).status_code, esperado)

    def test_401_sesiones_revocadas_expiradas_inactivas(self):
        self.client.credentials()
        self.assertEqual(self.client.get(BASE + "catalogo/").status_code, 401)
        t = AccessToken.for_user(self.gerencia)
        t.set_exp(from_time=timezone.now() - timedelta(days=1), lifetime=timedelta(seconds=1))
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {t}")
        self.assertEqual(self.client.get(BASE + "obras/").status_code, 401)
        self.autenticar(self.gerencia)
        self.gerencia.sesion_version += 1
        self.gerencia.save()
        self.assertEqual(self.client.get(BASE + "obras/").status_code, 401)
        self.autenticar(self.gerencia)
        self.gerencia.is_active = False
        self.gerencia.save()
        self.assertEqual(self.client.get(BASE + "obras/").status_code, 401)

    def test_405_headers_y_get_sin_writes(self):
        for ruta in (BASE + "catalogo/", BASE + "obras/", BASE + "rentabilidad/", BASE + "cobranzas/", BASE + "obras/exportar/?formato=csv"):
            for metodo in ("post", "put", "patch", "delete"):
                self.assertEqual(getattr(self.client, metodo)(ruta, {}, format="json").status_code, 405)
        with CaptureQueriesContext(connection) as q:
            r = self.listado("obras")
        self.assertEqual(r["Cache-Control"], "private, no-store")
        self.assertIn("Authorization", r["Vary"])
        self.assertEqual(r["X-Content-Type-Options"], "nosniff")
        self.assertFalse(any(x["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE", "CREATE", "ALTER")) for x in q))

    def test_500_generico_sin_excepcion_sql_o_pii(self):
        with patch("apps.reportes.consultas.totales", side_effect=DatabaseError("SQL SECRETO")), self.assertLogs("apps.reportes.views", level="ERROR") as logs:
            r = self.listado("obras")
        self.assertEqual(r.status_code, 500)
        self.assertEqual(r.data["correlacion"], r["X-Correlation-ID"])
        self.assertNotIn("SECRETO", str(r.data) + str(logs.output))

    def test_snapshot_read_only_y_aislamiento_no_global(self):
        with snapshot():
            with connection.cursor() as cur:
                cur.execute("SHOW transaction_isolation")
                self.assertEqual(cur.fetchone()[0], "repeatable read")
                cur.execute("SHOW transaction_read_only")
                self.assertEqual(cur.fetchone()[0], "on")
        with connection.cursor() as cur:
            cur.execute("SHOW transaction_read_only")
            self.assertEqual(cur.fetchone()[0], "off")
            cur.execute("SHOW transaction_isolation")
            self.assertEqual(cur.fetchone()[0], "read committed")

    def test_no_registros_posteriores_corte_aunque_fecha_base_sea_creacion(self):
        self.historica(fecha=timezone.now() + timedelta(days=1))
        self.assertEqual(self.listado("obras").data["count"], 1)
        self.assertEqual(self.listado("rentabilidad").data["count"], 1)

    def test_extension_fecha_opcional_conserva_callers_originales(self):
        from apps.finanzas.consultas_cobranzas import con_cobranza
        doc = self.documento()
        base = DocumentoCobro.objects.filter(pk=doc.pk)
        original = con_cobranza(base).values("abonado_calculado", "saldo_calculado", "estado_cobranza_calculado").get()
        fijada = con_cobranza(base, hoy=hoy_santiago()).values("abonado_calculado", "saldo_calculado", "estado_cobranza_calculado").get()
        self.assertEqual(original, fijada)

    def test_openapi_versionado_rutas_schemas_y_referencias(self):
        import json
        from pathlib import Path
        from django.conf import settings
        from apps.reportes.serializers import SERIALIZERS
        schema = json.loads((Path(settings.BASE_DIR) / "docs/openapi/SPEC-011-v1.json").read_text())
        self.assertEqual(schema["openapi"], "3.1.0")
        self.assertEqual(set(schema["paths"]), {BASE + "catalogo/", BASE + "obras/", BASE + "rentabilidad/", BASE + "cobranzas/", BASE + "{tipo}/exportar/"})
        for tipo, nombre in (("obras", "Obra"), ("rentabilidad", "Rentabilidad"), ("cobranzas", "Cobranza")):
            self.assertEqual(set(schema["components"]["schemas"][nombre]["required"]), set(SERIALIZERS[tipo]().fields))
            self.assertEqual(set(SERIALIZERS[tipo]().fields), {key for key, _ in COLUMNAS[tipo]})
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
