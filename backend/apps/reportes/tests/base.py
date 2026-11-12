from datetime import timedelta
from io import BytesIO, StringIO
import csv

from django.core.cache import cache
from openpyxl import load_workbook
from pypdf import PdfReader

from apps.dashboard.tests.base import DashboardBase
from apps.finanzas.validaciones import hoy_santiago
from apps.reportes.catalogo import COLUMNAS

BASE = "/api/reportes/"


class ReportesBase(DashboardBase):
    def preparar_reportes(self):
        cache.clear()
        self.preparar_dashboard()

    def filtros_periodo(self):
        hoy = hoy_santiago()
        return {"desde": (hoy - timedelta(days=365)).isoformat(), "hasta": hoy.isoformat()}

    def listado(self, tipo, **filtros):
        return self.client.get(BASE + tipo + "/", {**self.filtros_periodo(), **filtros})

    def exportacion(self, tipo, formato, **filtros):
        cache.clear()  # Las pruebas de tasa usan requests directos, sin este helper.
        r = self.client.get(BASE + tipo + "/exportar/", {**self.filtros_periodo(), "formato": formato, **filtros})
        self.assertEqual(r.status_code, 200, getattr(r, "data", None))
        try:
            contenido = b"".join(r.streaming_content)
        finally:
            r.close()
        return contenido, r

    def leer_csv(self, data, tipo):
        rows = list(csv.reader(StringIO(data.decode("utf-8-sig"), newline=""), delimiter=";"))
        headers = [label for _, label in COLUMNAS[tipo]]
        indice = rows.index(headers)
        return rows[:indice], rows[indice + 1:]

    def leer_xlsx(self, data):
        return load_workbook(BytesIO(data), read_only=True, data_only=False)

    def leer_pdf(self, data):
        return PdfReader(BytesIO(data))
