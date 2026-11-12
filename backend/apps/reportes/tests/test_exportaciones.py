import json
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryFile
from time import monotonic
from unittest.mock import patch
from zipfile import ZipFile

from django.core.cache import cache
from django.db import connection, models
from django.test import TransactionTestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from openpyxl.worksheet._writer import ALL_TEMP_FILES

from apps.reportes import catalogo, services
from apps.reportes.catalogo import COLUMNAS, MONETARIOS, TIPOS
from apps.reportes.consistencia import ExportacionGrande, PresupuestoTiempo
from apps.reportes.exportadores.comun import ArchivoLimitado, texto_csv
from apps.finanzas.models import DocumentoCobro
from apps.obras.models import Obra
from apps.comercial.models import Cliente, Presupuesto, PresupuestoItem
from .base import ReportesBase, BASE


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ExportacionesTests(ReportesBase, TransactionTestCase):
    def setUp(self):
        self.preparar_reportes()

    def test_nueve_combinaciones_reales_equivalentes_json(self):
        self.documento(folio="00001234")
        self.historica(estado="EN_PROCESO")
        for tipo in TIPOS:
            datos = self.listado(tipo).data
            for formato in catalogo.FORMATOS:
                with self.subTest(tipo=tipo, formato=formato):
                    binario, response = self.exportacion(tipo, formato)
                    self.assertGreater(len(binario), 50)
                    self.assertEqual(response["Cache-Control"], "private, no-store")
                    self.assertEqual(response["X-Content-Type-Options"], "nosniff")
                    self.assertIn("Authorization", response["Vary"])
                    self.assertRegex(response["Content-Disposition"], rf'^attachment; filename="fyag-{tipo}-[0-9]{{8}}-[0-9]{{6}}\.{formato}"$')
                    if formato == "csv":
                        self.assertTrue(binario.startswith(b"\xef\xbb\xbf"))
                        self.assertFalse(b"\n" in binario.replace(b"\r\n", b""))
                        meta, rows = self.leer_csv(binario, tipo)
                        self.assertEqual(len(rows), datos["count"])
                        for actual, esperado in zip(rows, datos["results"]):
                            for value, (key, _) in zip(actual, COLUMNAS[tipo]):
                                e = esperado[key]
                                self.assertEqual(value, "" if e is None else str(e).lower() if type(e) is bool else str(e))
                        for key, value in datos["totales"].items():
                            self.assertIn(["META", "Total " + key, str(value)], meta)
                    elif formato == "xlsx":
                        self.assertTrue(binario.startswith(b"PK"))
                        libro = self.leer_xlsx(binario)
                        try:
                            self.assertEqual(libro.sheetnames, ["Resultados", "Resumen"])
                            rows = list(libro["Resultados"].values)
                            self.assertEqual(rows[0], tuple(label for _, label in COLUMNAS[tipo]))
                            self.assertEqual(len(rows) - 1, datos["count"])
                            for actual, esperado in zip(rows[1:], datos["results"]):
                                for value, (key, _) in zip(actual, COLUMNAS[tipo]):
                                    e = esperado[key]
                                    self.assertEqual(value, e if e is None or type(e) is bool else str(e))
                            resumen = dict(libro["Resumen"].values)
                            for key, value in datos["totales"].items():
                                self.assertEqual(resumen["Total " + key], str(value))
                        finally:
                            libro.close()
                    else:
                        self.assertTrue(binario.startswith(b"%PDF-"))
                        pdf = self.leer_pdf(binario)
                        self.assertGreaterEqual(len(pdf.pages), 1)
                        text = "\n".join(p.extract_text() for p in pdf.pages)
                        self.assertIn("Reporte de gestión", text)
                        self.assertIn("no es documento tributario ni DTE", text)
                        self.assertIn("Cliente de obra", text)
                        self.assertIn("Total ", text)
                        for fila in datos["results"]:
                            self.assertIn(fila["codigo_obra"], text)
                        for value in datos["totales"].values():
                            self.assertIn(str(value), text)

    def test_cero_filas_json_y_archivos_autenticos_con_cabeceras(self):
        for tipo in TIPOS:
            datos = self.listado(tipo, cliente="9223372036854775807").data
            self.assertEqual(datos["count"], 0)
            for formato in catalogo.FORMATOS:
                data, _ = self.exportacion(tipo, formato, cliente="9223372036854775807")
                if formato == "csv":
                    self.assertEqual(self.leer_csv(data, tipo)[1], [])
                elif formato == "xlsx":
                    libro = self.leer_xlsx(data)
                    self.assertEqual(len(list(libro["Resultados"].values)), 1)
                    libro.close()
                else:
                    self.assertIn("Filas: 0", self.leer_pdf(data).pages[0].extract_text())

    def test_exporta_todo_filtro_mas_de_25_no_solo_primera_pagina(self):
        for _ in range(28):
            self.historica(estado="EN_PROCESO")
        for formato in ("csv", "xlsx", "pdf"):
            data, _ = self.exportacion("obras", formato, estado="EN_PROCESO")
            if formato == "csv":
                self.assertEqual(len(self.leer_csv(data, "obras")[1]), 28)
            elif formato == "xlsx":
                libro = self.leer_xlsx(data)
                self.assertEqual(len(list(libro["Resultados"].values)) - 1, 28)
                libro.close()
            else:
                self.assertIn("Filas: 28", "\n".join(p.extract_text() for p in self.leer_pdf(data).pages))

    def test_csv_formulas_acentos_comillas_y_margen_negativo_real(self):
        nombre = '=SUM("Árbol";1)'
        Cliente.objects.filter(pk=self.cliente.pk).update(nombre_legal=nombre)
        data, _ = self.exportacion("rentabilidad", "csv")
        meta, rows = self.leer_csv(data, "rentabilidad")
        self.assertEqual(rows[0][3], "'" + nombre)
        self.assertEqual(rows[0][8], "-5919.78")
        self.assertIn(["META", "Total margen_neto", "-5919.78"], meta)
        for peligro in ("=1+1", "+1+1", "-1+1", "@SUM(A1)", " \t=1+1", "\u200b=1+1", "\ufeff \u200d@SUM(A1)", "\r\n-2+3", "\u00a0\u200b+1+1"):
            protegido = texto_csv(peligro)
            self.assertTrue(protegido.startswith("'"), repr(peligro))
            self.assertNotIn("\n", protegido)
            self.assertNotIn("\t", protegido)

    def test_xlsx_folio_y_grandes_decimales_textuales_sin_formulas_links(self):
        doc = self.documento(folio="00001234")
        models.QuerySet(model=DocumentoCobro).filter(pk=doc.pk).update(monto_neto=Decimal("123456789012345678901234567890123456.78"), monto_impuesto=Decimal("0.01"), monto_total=Decimal("123456789012345678901234567890123456.79"))
        malicioso = '=HYPERLINK("https://example.invalid","Árbol")'
        Cliente.objects.filter(pk=self.cliente.pk).update(nombre_legal=malicioso)
        data, _ = self.exportacion("cobranzas", "xlsx")
        libro = self.leer_xlsx(data)
        try:
            rows = list(libro["Resultados"].rows)
            self.assertEqual(rows[1][6].value, "00001234")
            self.assertEqual(rows[1][6].data_type, "s")
            self.assertEqual(rows[1][10].value, "123456789012345678901234567890123456.79")
            self.assertEqual(rows[1][4].value, malicioso)
            self.assertTrue(all(c.data_type != "f" for hoja in libro for row in hoja for c in row))
        finally:
            libro.close()
        with ZipFile(BytesIO(data)) as archive:
            self.assertFalse(any("externalLinks" in name or "vbaProject" in name for name in archive.namelist()))
            for name in archive.namelist():
                if name.endswith(".xml"):
                    self.assertNotIn(b"<f>", archive.read(name))
                    self.assertNotIn(b"<hyperlink ", archive.read(name))

    def test_pdf_legible_paginado_acentos_encabezados_y_montos_grandes(self):
        Cliente.objects.filter(pk=self.cliente.pk).update(nombre_legal=("Refrigeración Ñandú " * 10).strip())
        for _ in range(65):
            self.historica(estado="EN_PROCESO", lineas=(("999999999.999", "9999999999999.99"),))
        data, _ = self.exportacion("obras", "pdf", estado="EN_PROCESO")
        pdf = self.leer_pdf(data)
        self.assertGreater(len(pdf.pages), 1)
        total_texto = "\n".join(page.extract_text() for page in pdf.pages)
        self.assertIn("Refrigeración Ñandú", total_texto)
        self.assertIn("Filas: 65", total_texto)
        for indice, pagina in enumerate(pdf.pages, 1):
            text = pagina.extract_text()
            self.assertIn(f"Página {indice}", text)
            self.assertIn("Código obra", text)
            self.assertIn("Presupuesto neto", text)
            self.assertGreater(float(pagina.mediabox.width), float(pagina.mediabox.height))
        # La cadena de dígitos de un importe grande se conserva aun envuelta.
        limpio = "".join(total_texto.split())
        self.assertIn("9999999999989990000000.00", limpio)

    def test_pdf_conserva_importes_38_digitos_sin_recortar_columnas(self):
        doc = self.documento(folio="0000001")
        importe = "123456789012345678901234567890123456.79"
        models.QuerySet(model=DocumentoCobro).filter(pk=doc.pk).update(monto_neto=Decimal("123456789012345678901234567890123456.78"), monto_impuesto=Decimal("0.01"), monto_total=Decimal(importe))
        data, _ = self.exportacion("cobranzas", "pdf")
        pdf = self.leer_pdf(data)
        texto = "".join("\n".join(p.extract_text() for p in pdf.pages).split())
        cuerpo = texto.split("Estadocobranza", 1)[1]
        self.assertIn(importe, cuerpo)
        self.assertIn("0000001", cuerpo)

    def test_normalizacion_xml_y_controles_no_rompe_archivos(self):
        Cliente.objects.filter(pk=self.cliente.pk).update(nombre_legal="Árbol\ufffe\uffff\ufdd0\u200b\tSeguro")
        for formato in catalogo.FORMATOS:
            data, _ = self.exportacion("obras", formato)
            if formato == "xlsx":
                libro = self.leer_xlsx(data)
                filas = list(libro["Resultados"].values)
                self.assertEqual(filas[1][3], "Árbol Seguro")
                libro.close()
            elif formato == "csv":
                self.assertEqual(self.leer_csv(data, "obras")[1][0][3], "Árbol Seguro")
            else:
                self.assertIn("Árbol Seguro", self.leer_pdf(data).pages[0].extract_text())

    def test_head_valida_sin_renderizar_y_sin_archivo(self):
        for formato in catalogo.FORMATOS:
            cache.clear()
            with patch("apps.reportes.services.TemporaryFile", side_effect=AssertionError("No generar archivo en HEAD")):
                r = self.client.head(BASE + "obras/exportar/", {"formato": formato})
            self.assertEqual(r.status_code, 200)
            self.assertEqual(b"".join(r.streaming_content), b"")
            self.assertIn("attachment", r["Content-Disposition"])
            self.assertNotIn("Content-Length", r)

    def test_accept_binario_valido_no_produce_406_y_errores_siguen_json(self):
        from apps.reportes.views import MIMES
        for formato in catalogo.FORMATOS:
            cache.clear()
            r = self.client.get(BASE + "obras/exportar/", {"formato": formato}, HTTP_ACCEPT=MIMES[formato])
            self.assertEqual(r.status_code, 200, getattr(r, "data", None))
            self.assertEqual(r["Content-Type"], MIMES[formato])
            self.assertTrue(b"".join(r.streaming_content))
            r.close()
        cache.clear()
        r = self.client.get(BASE + "obras/exportar/", {"formato": "zip"}, HTTP_ACCEPT="application/pdf")
        self.assertEqual(r.status_code, 400)
        self.assertIn("application/json", r["Content-Type"])

    def test_exportacion_rechaza_query_y_page(self):
        for tipo in TIPOS:
            for params in ({}, {"formato": "CSV"}, {"formato": "zip"}, {"formato": ""}, {"formato": "csv", "page": 1}, {"formato": "csv", "limit": 1}):
                cache.clear()
                r = self.client.get(BASE + tipo + "/exportar/", params)
                self.assertEqual(r.status_code, 400, (tipo, params, r.data))
            cache.clear()
            self.assertEqual(self.client.get(BASE + tipo + "/exportar/?formato=csv&formato=pdf").status_code, 400)

    def test_throttle_5_por_minuto_429_con_retry_after_y_usuario_independiente(self):
        for _ in range(5):
            r = self.client.head(BASE + "cobranzas/exportar/", {"formato": "csv"})
            self.assertEqual(r.status_code, 200)
            r.close()
        r = self.client.get(BASE + "cobranzas/exportar/", {"formato": "csv"})
        self.assertEqual(r.status_code, 429)
        self.assertIn("Retry-After", r)
        self.autenticar(self.finanzas)
        self.assertEqual(self.client.head(BASE + "cobranzas/exportar/", {"formato": "csv"}).status_code, 200)

    def test_temporal_cerrado_en_exito_y_desconexion(self):
        creados = []
        def crear(*args, **kwargs):
            f = TemporaryFile(*args, **kwargs)
            creados.append(f)
            return f
        for formato in catalogo.FORMATOS:
            cache.clear()
            with patch("apps.reportes.services.TemporaryFile", side_effect=crear):
                r = self.client.get(BASE + "obras/exportar/", {"formato": formato})
            self.assertEqual(r.status_code, 200, getattr(r, "data", None))
            self.assertFalse(creados[-1].closed)
            next(iter(r.streaming_content))
            r.close()  # equivale al cierre del iterable WSGI por desconexión
            self.assertTrue(creados[-1].closed)
        self.assertTrue(all(f.closed for f in creados))

    def test_error_generacion_no_entrega_200_parcial_y_elimina_temporal(self):
        creados = []
        def crear(*args, **kwargs):
            f = TemporaryFile(*args, **kwargs)
            creados.append(f)
            return f
        def fallar(tipo, filas, info, archivo, tiempo):
            archivo.write(b"parcial")
            raise RuntimeError("DATOS_SECRETOS")
        with patch("apps.reportes.services.TemporaryFile", side_effect=crear), patch("apps.reportes.exportadores.csv.generar", side_effect=fallar), self.assertLogs("apps.reportes.views", level="ERROR"):
            r = self.client.get(BASE + "obras/exportar/", {"formato": "csv"})
        self.assertEqual(r.status_code, 500)
        self.assertFalse(r.streaming)
        self.assertNotIn("DATOS_SECRETOS", str(r.data))
        self.assertTrue(creados[0].closed)

    def test_limite_bytes_http_y_limpieza_xml_xlsx_tambien_en_error(self):
        antes = set(ALL_TEMP_FILES)
        for formato in catalogo.FORMATOS:
            cache.clear()
            with patch("apps.reportes.catalogo.MAX_BYTES", 128):
                r = self.client.get(BASE + "obras/exportar/", {"formato": formato})
            self.assertEqual(r.status_code, 413, (formato, getattr(r, "data", None)))
            self.assertEqual(r.data["code"], "exportacion_demasiado_grande")
            self.assertFalse(r.streaming)
        self.assertEqual(set(ALL_TEMP_FILES), antes)

    def test_limite_real_50_mib_proxy_no_escribe_byte_que_excede(self):
        self.assertEqual(catalogo.MAX_BYTES, 50 * 1024 * 1024)
        with TemporaryFile("w+b") as archivo:
            writer = ArchivoLimitado(archivo, PresupuestoTiempo(monotonic()))
            bloque = b"x" * (1024 * 1024)
            for _ in range(50):
                writer.write(bloque)
            with self.assertRaises(ExportacionGrande):
                writer.write(b"x")
            self.assertEqual(archivo.tell(), catalogo.MAX_BYTES)

    def test_file_response_no_consulta_sql_fuera_snapshot(self):
        for formato in catalogo.FORMATOS:
            cache.clear()
            r = self.client.get(BASE + "rentabilidad/exportar/", {"formato": formato})
            self.assertEqual(r.status_code, 200, getattr(r, "data", None))
            with CaptureQueriesContext(connection) as q:
                data = b"".join(r.streaming_content)
                r.close()
            self.assertEqual(len(q), 0)
            self.assertTrue(data)

    def test_logs_estructurados_no_pii_tokens_folios_importes(self):
        self.documento(folio="00001234")
        with self.assertLogs("apps.reportes.services", level="INFO") as logs:
            self.exportacion("cobranzas", "csv")
        eventos = [json.loads(record.getMessage()) for record in logs.records]
        self.assertEqual(eventos[0]["resultado"], "solicitud")
        self.assertEqual(eventos[-1]["resultado"], "archivo_generado_no_confirma_descarga")
        self.assertEqual(eventos[-1]["cantidad_filas"], 1)
        self.assertEqual(eventos[-1]["actor_id"], self.gerencia.pk)
        for value in (self.cliente.nombre_legal, self.cliente.correo, "00001234", "2180.35", "Bearer", "cookie"):
            self.assertNotIn(value, str(logs.output))

    def test_limite_10000_real_postgres_y_10001_rechazado_antes_render(self):
        # Carga contractual temporal, no datos demostrativos en desarrollo.
        presupuestos = Presupuesto.objects.bulk_create([Presupuesto(cliente=self.cliente, creado_por=self.finanzas, descripcion="Límite QA", estado="APROBADO_CLIENTE") for _ in range(10_000)], batch_size=500)
        PresupuestoItem.objects.bulk_create([PresupuestoItem(presupuesto=p, descripcion="Servicio QA", unidad="unidad", cantidad=Decimal("1.000"), precio_unitario=Decimal("1.00"), orden=1) for p in presupuestos], batch_size=500)
        Obra.objects.bulk_create([Obra(presupuesto=p, categoria_servicio=self.categoria, creado_por=self.supervisor, descripcion="Obra QA") for p in presupuestos], batch_size=500)
        data, _ = self.exportacion("obras", "csv", estado="PLANIFICADA")
        self.assertEqual(len(self.leer_csv(data, "obras")[1]), 10_000)
        self.historica(estado="PLANIFICADA")
        for formato in catalogo.FORMATOS:
            cache.clear()
            with patch("apps.reportes.services.TemporaryFile", side_effect=AssertionError("No renderizar")):
                r = self.client.get(BASE + "obras/exportar/", {**self.filtros_periodo(), "formato": formato, "estado": "PLANIFICADA"})
            self.assertEqual(r.status_code, 413)
            self.assertEqual(r.data["code"], "exportacion_demasiado_grande")
        cache.clear()
        self.assertEqual(self.client.head(BASE + "obras/exportar/", {**self.filtros_periodo(), "formato": "csv", "estado": "PLANIFICADA"}).status_code, 413)

    @override_settings(CORS_ALLOWED_ORIGINS=["https://ui.example.test"])
    def test_frontend_separado_puede_leer_nombre_y_correlacion_sin_nuevos_origenes(self):
        r = self.client.get(BASE + "obras/exportar/", {"formato": "csv"}, HTTP_ORIGIN="https://ui.example.test")
        self.assertEqual(r.status_code, 200, getattr(r, "data", None))
        self.assertEqual(r["Access-Control-Allow-Origin"], "https://ui.example.test")
        for header in ("Content-Disposition", "X-Correlation-ID", "Retry-After"):
            self.assertIn(header, r["Access-Control-Expose-Headers"])
        r.close()
        cache.clear()
        r = self.client.get(BASE + "obras/exportar/", {"formato": "csv"}, HTTP_ORIGIN="https://ajeno.example.test")
        self.assertNotIn("Access-Control-Allow-Origin", r)
        r.close()
