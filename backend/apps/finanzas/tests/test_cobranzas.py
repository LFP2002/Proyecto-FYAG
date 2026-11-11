from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

from django.db import connection, models
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from apps.finanzas import services_documentos as documentos, services_pagos as pagos
from apps.finanzas.models import DocumentoCobro
from apps.finanzas.validaciones import hoy_santiago, LIMITE
from .base import FinanzasBase
from .test_pagos import PagosBase


class CobranzasTests(PagosBase, TestCase):
    def setUp(self):
        self.preparar_pagos()

    def nuevo_documento(self, folio, *, vencido=False):
        obra = self.otra_finalizada()
        return documentos.registrar_documento(self.payload(obra=obra.pk, folio_externo=folio,
            fecha_emision=(hoy_santiago() - timedelta(days=5)).isoformat(),
            fecha_vencimiento=(hoy_santiago() - timedelta(days=1) if vencido else hoy_santiago()).isoformat()), self.finanzas)

    def test_estados_agregados_sin_joins_duplicados(self):
        parcial = self.nuevo_documento("20002")
        pagada = self.nuevo_documento("30003")
        vencida = self.nuevo_documento("40004", vencido=True)
        revertida = self.nuevo_documento("50005")
        for doc, monto in [(parcial, "100.13"), (parcial, "100.13"), (pagada, "2180.35"), (vencida, "100.13")]:
            pagos.registrar_pago(doc.pk, self.pago_data(monto=monto), self.finanzas, str(uuid4()))
        documentos.revertir_documento(revertida.pk, {"motivo": "Externo", "referencia_rectificacion_externa": "Respaldo"}, self.finanzas)
        result = self.client.get("/api/finanzas/cobranzas/resumen/")
        self.assertEqual(result.status_code, 200, result.data)
        self.assertEqual(result.data, {"moneda": "CLP", "documentos": 4,
            "conteos": {"PENDIENTE": 1, "PARCIAL": 1, "PAGADA": 1, "VENCIDA": 1},
            "monto_documentado_total": "8721.40", "abonado_total": "2480.74", "saldo_total": "6240.66", "saldo_vencido": "2080.22"})
        result = self.client.get("/api/finanzas/cobranzas/?estado=PARCIAL")
        self.assertEqual(result.data["count"], 1)
        self.assertEqual(result.data["results"][0]["id"], parcial.pk)
        result = self.client.get("/api/finanzas/cobranzas/resumen/?estado=VENCIDA")
        self.assertEqual(result.data["documentos"], 1)
        self.assertEqual(result.data["abonado_total"], "100.13")
        self.assertEqual(result.data["saldo_total"], "2080.22")

    def test_anulaciones_no_se_suman_y_vencimiento_civil(self):
        first = self.pagar()
        self.anular(first.data["id"])
        result = self.client.get("/api/finanzas/cobranzas/resumen/")
        self.assertEqual(result.data["abonado_total"], "0.00")
        self.assertEqual(result.data["saldo_total"], "2180.35")
        self.assertEqual(result.data["saldo_vencido"], "0.00")
        self.assertEqual(result.data["conteos"]["PENDIENTE"], 1)

    def test_cartera_vacia_no_inventa_ingresos_de_revertidos(self):
        documentos.revertir_documento(self.doc.pk, {"motivo": "Externo", "referencia_rectificacion_externa": "Respaldo"}, self.finanzas)
        result = self.client.get("/api/finanzas/cobranzas/")
        self.assertEqual(result.data["count"], 0)
        result = self.client.get("/api/finanzas/cobranzas/resumen/")
        self.assertEqual(result.data["documentos"], 0)
        for field in ["monto_documentado_total", "abonado_total", "saldo_total", "saldo_vencido"]:
            self.assertEqual(result.data[field], "0.00")
        self.assertIsNone(self.cobranza())

    def test_filtros_estrictos_y_mismo_conjunto_en_resumen(self):
        params = f"obra={self.obra.pk}&cliente={self.cliente.pk}&fecha_emision_desde=2020-01-01&fecha_emision_hasta={hoy_santiago()}&fecha_vencimiento_desde={hoy_santiago()}&fecha_vencimiento_hasta={hoy_santiago()}"
        self.assertEqual(self.client.get("/api/finanzas/cobranzas/?" + params).data["count"], 1)
        self.assertEqual(self.client.get("/api/finanzas/cobranzas/resumen/?" + params).data["documentos"], 1)
        for query in ["estado=VIGENTE", "estado=PENDIENTE&estado=PARCIAL", "cliente=true", "obra=0", "otro=x", "page=0", "page=1&page=2", "fecha_vencimiento_hasta=2026-02-30", "fecha_vencimiento_desde=2026-01-01&fecha_vencimiento_hasta=2020-01-01"]:
            for endpoint in ["cobranzas/", "cobranzas/resumen/"]:
                response = self.client.get("/api/finanzas/" + endpoint + "?" + query)
                self.assertEqual(response.status_code, 400, (endpoint, query, response.data))

    def test_paginacion_25_estado_antes_de_conteo_y_sin_n_mas_uno(self):
        for index in range(26):
            self.nuevo_documento(str(20000 + index))
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get("/api/finanzas/cobranzas/?estado=PENDIENTE")
        self.assertEqual(response.data["count"], 27)
        self.assertEqual(len(response.data["results"]), 25)
        self.assertEqual([row["id"] for row in response.data["results"]], sorted(row["id"] for row in response.data["results"]))
        self.assertLessEqual(len(queries), 7)
        self.assertEqual(len(self.client.get("/api/finanzas/cobranzas/?page=2").data["results"]), 2)
        self.assertEqual(self.client.get("/api/finanzas/cobranzas/resumen/").data["monto_documentado_total"], "58869.45")

    def test_aggregate_overflow_controlado_no_float_ni_redondeo(self):
        other = self.nuevo_documento("20002")
        models.QuerySet(model=DocumentoCobro).filter(pk__in=[self.doc.pk, other.pk]).update(monto_neto=LIMITE, monto_impuesto=Decimal("0.00"), monto_total=LIMITE, tipo_documento="FACTURA_EXENTA")
        response = self.client.get("/api/finanzas/cobranzas/resumen/")
        self.assertEqual(response.status_code, 409, response.data)
        self.assertEqual(response.data["code"], "importe_fuera_rango")


class SinCobroCarteraTests(FinanzasBase, TestCase):
    con_cortesia = True

    def setUp(self):
        self.preparar_finanzas()

    def test_sin_cobro_no_crea_pago_saldo_ni_cartera(self):
        documentos.registrar_sin_cobro(self.obra.pk, {"motivo_registro": "Archivo de garantía"}, self.finanzas)
        response = self.client.get(f"/api/finanzas/obras/{self.obra.pk}/estado-financiero/")
        self.assertEqual(response.data["estado_financiero"], "SIN_COBRO")
        self.assertIsNone(response.data["documento_vigente"])
        self.assertNotIn("saldo", str(response.data))
        self.assertEqual(self.client.get("/api/finanzas/cobranzas/").data["count"], 0)
        self.assertEqual(self.client.get("/api/finanzas/cobranzas/resumen/").data["documentos"], 0)
