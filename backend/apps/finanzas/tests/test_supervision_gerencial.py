from datetime import timedelta

from django.db import models
from django.test import TestCase
from apps.finanzas.models import DocumentoCobro
from apps.finanzas.validaciones import hoy_santiago
from apps.finanzas import services_documentos as documentos
from .test_pagos import PagosBase


class SupervisionCobranzasTests(PagosBase, TestCase):
    url = "/api/finanzas/cobranzas/supervision-gerencial/"

    def setUp(self):
        self.preparar_pagos()

    def test_roles_y_validacion(self):
        for user in (self.finanzas, self.supervisor, self.tecnico, self.gerencia):
            self.autenticar(user)
            self.assertEqual(self.client.get(self.url).status_code, 200 if user == self.gerencia else 403)
        self.assertEqual(self.client.post(self.url, {}, format="json").status_code, 405)
        for query in ("?vista=x", "?desde=2026-01-01", "?desde=2026-02-30&hasta=2026-03-01", "?page=1&page=2", "?foo=x"):
            self.assertEqual(self.client.get(self.url+query).status_code, 400)

    def test_vencida_pago_parcial_y_resumen_global(self):
        self.assertEqual(self.pagar().status_code, 201)
        models.QuerySet(model=DocumentoCobro).filter(pk=self.doc.pk).update(fecha_vencimiento=hoy_santiago()-timedelta(days=2))
        self.autenticar(self.gerencia)
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200, r.data)
        s = r.data["resumen"]
        self.assertEqual((s["total"], s["cobrado"], s["saldo"], s["vencido"], s["no_vencido"]), ("2180.35", "100.13", "2080.22", "2080.22", "0.00"))
        self.assertEqual(s["clientes_vencidos"], 1)
        self.assertEqual(r.data["results"][0]["dias_atraso"], 2)
        self.assertEqual(self.client.get(self.url, {"buscar":"no existe"}).data["resumen"], s)
        self.assertEqual(self.client.get(self.url, {"desde":hoy_santiago().isoformat(),"hasta":hoy_santiago().isoformat()}).data["resumen"]["documentos"], 0)

    def test_revertido_solo_historico(self):
        documentos.revertir_documento(self.doc.pk, {"motivo":"Corrección", "referencia_rectificacion_externa":"Respaldo"}, self.finanzas)
        self.autenticar(self.gerencia)
        self.assertEqual(self.client.get(self.url, {"vista":"vigentes"}).data["count"], 0)
        r = self.client.get(self.url, {"vista":"documentos"})
        self.assertEqual(r.data["count"], 1)
        self.assertIsNone(r.data["results"][0]["saldo"])
        self.assertEqual(r.data["resumen"]["total"], "0.00")
