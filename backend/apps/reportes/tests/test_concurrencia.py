from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import patch

from django.core.cache import cache
from django.db import close_old_connections, connection
from django.test import TransactionTestCase, override_settings
from rest_framework.test import APIClient

from apps.reportes import consultas
from apps.reportes.catalogo import COLUMNAS
from apps.finanzas import services_documentos
from apps.usuarios.tokens import AccessToken
from .base import ReportesBase, BASE


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class SnapshotReportesTests(ReportesBase, TransactionTestCase):
    def setUp(self):
        self.preparar_reportes()

    def intercalar(self, tipo, formato, mutacion):
        antes = self.listado(tipo).data
        listo, continuar = Event(), Event()
        original = consultas.totales
        token = str(AccessToken.for_user(self.gerencia))
        def pausa(*args):
            resultado = original(*args)
            listo.set()
            if not continuar.wait(15):
                raise AssertionError("No se liberó el reporte")
            return resultado
        def leer():
            close_old_connections()
            try:
                client = APIClient()
                client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
                params = self.filtros_periodo()
                ruta = BASE + tipo + "/"
                if formato:
                    params["formato"] = formato
                    ruta += "exportar/"
                return client.get(ruta, params)
            finally:
                connection.close()
        cache.clear()
        with patch("apps.reportes.consultas.totales", side_effect=pausa), ThreadPoolExecutor(max_workers=1) as pool:
            futuro = pool.submit(leer)
            try:
                self.assertTrue(listo.wait(15))
                with connection.cursor() as cur:
                    cur.execute("SET statement_timeout = '8s'")
                mutacion()  # Debe confirmar ANTES de liberar al lector.
            finally:
                continuar.set()
                with connection.cursor() as cur:
                    cur.execute("SET statement_timeout = DEFAULT")
            respuesta = futuro.result(timeout=15)
        self.assertEqual(respuesta.status_code, 200, getattr(respuesta, "data", None))
        if formato is None:
            for key in ("count", "results", "totales"):
                self.assertEqual(respuesta.data[key], antes[key])
        else:
            try:
                data = b"".join(respuesta.streaming_content)
            finally:
                respuesta.close()
            if formato == "csv":
                meta, filas = self.leer_csv(data, tipo)
                esperado = [["" if row[k] is None else str(row[k]).lower() if type(row[k]) is bool else str(row[k]) for k, _ in COLUMNAS[tipo]] for row in antes["results"]]
                self.assertEqual(filas, esperado)
                for k, v in antes["totales"].items():
                    self.assertIn(["META", "Total " + k, str(v)], meta)
            elif formato == "xlsx":
                libro = self.leer_xlsx(data)
                try:
                    filas = list(libro["Resultados"].values)[1:]
                    esperado = [tuple(row[k] if row[k] is None or type(row[k]) is bool else str(row[k]) for k, _ in COLUMNAS[tipo]) for row in antes["results"]]
                    self.assertEqual(filas, esperado)
                    resumen = dict(libro["Resumen"].values)
                    for k, v in antes["totales"].items():
                        self.assertEqual(resumen["Total " + k], str(v))
                finally:
                    libro.close()
            else:
                text = "".join("\n".join(p.extract_text() for p in self.leer_pdf(data).pages).split())
                ultimo_header = "".join(COLUMNAS[tipo][-1][1].split())
                cuerpo = text.split(ultimo_header, 1)[1]
                for row in antes["results"]:
                    esperado = "".join("" if row[k] is None else str(row[k]).lower() if type(row[k]) is bool else str(row[k]) for k, _ in COLUMNAS[tipo])
                    self.assertIn("".join(esperado.split()), cuerpo)
        despues = self.listado(tipo).data
        return antes, despues

    def test_pagos_entre_totales_y_filas_json_y_tres_binarios(self):
        doc = self.documento()
        for formato in (None, "csv", "xlsx", "pdf"):
            antes, despues = self.intercalar("cobranzas", formato, lambda: self.pago(doc))
            self.assertNotEqual(antes["totales"]["abonado"], despues["totales"]["abonado"])

    def test_anulaciones_entre_totales_y_filas_json_y_tres_binarios(self):
        doc = self.documento()
        for formato in (None, "csv", "xlsx", "pdf"):
            pago = self.pago(doc)
            antes, despues = self.intercalar("cobranzas", formato, lambda: self.anular(doc, pago))
            self.assertNotEqual(antes["totales"]["abonado"], despues["totales"]["abonado"])

    def test_registro_documento_entre_totales_y_filas_json_y_tres_binarios(self):
        for indice, formato in enumerate((None, "csv", "xlsx", "pdf")):
            obra = self.otra_finalizada()
            antes, despues = self.intercalar("cobranzas", formato, lambda: self.documento(obra=obra, folio=str(3200 + indice)))
            self.assertEqual(despues["count"], antes["count"] + 1)

    def test_reversion_documento_entre_totales_y_filas_json_y_tres_binarios(self):
        for indice, formato in enumerate((None, "csv", "xlsx", "pdf")):
            doc = self.documento(obra=self.otra_finalizada(), folio=str(3300 + indice))
            antes, despues = self.intercalar("cobranzas", formato, lambda: services_documentos.revertir_documento(doc.pk, {"motivo": "Rectificar", "referencia_rectificacion_externa": "Respaldo"}, self.finanzas))
            self.assertEqual(despues["count"], antes["count"] - 1)

    def test_finalizacion_con_cierre_json_y_tres_binarios(self):
        for formato in (None, "csv", "xlsx", "pdf"):
            self.obra = self.otra_obra()
            self.completa()
            antes, despues = self.intercalar("rentabilidad", formato, self.finalizar)
            self.assertEqual(despues["count"], antes["count"] + 1)
