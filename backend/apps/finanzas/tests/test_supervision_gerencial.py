from datetime import timedelta

from django.db import models
from django.test import TestCase
from django.urls import resolve
from apps.finanzas.models import DocumentoCobro
from apps.finanzas.validaciones import hoy_santiago
from apps.finanzas.views_supervision import SupervisionCobranzasView
from apps.finanzas import services_documentos as documentos
from .test_pagos import PagosBase


class SupervisionCobranzasTests(PagosBase, TestCase):
    supervision_url = "/api/finanzas/cobranzas/supervision-gerencial/"

    def setUp(self):
        self.preparar_pagos()
        # GastosBase asigna self.url a la ruta de gastos de obra.
        # La ruta de supervisión debe permanecer independiente de ese fixture.
        self.assertIs(resolve(self.supervision_url).func.cls, SupervisionCobranzasView)

    def test_roles_y_validacion(self):
        for user in (self.finanzas, self.supervisor, self.tecnico, self.gerencia):
            self.autenticar(user)
            r = self.client.get(self.supervision_url)
            self.assertEqual(r.status_code, 200 if user == self.gerencia else 403, (user.rol, r.data))
            if user == self.gerencia:
                self.assertIn('resumen', r.data)
        self.assertEqual(self.client.post(self.supervision_url, {}, format="json").status_code, 405)
        for query in ("?vista=x", "?desde=2026-01-01", "?desde=2026-02-30&hasta=2026-03-01", "?page=1&page=2", "?foo=x"):
            self.assertEqual(self.client.get(self.supervision_url+query).status_code, 400)

    def test_vencida_pago_parcial_y_resumen_global(self):
        self.assertEqual(self.pagar().status_code, 201)
        models.QuerySet(model=DocumentoCobro).filter(pk=self.doc.pk).update(fecha_vencimiento=hoy_santiago()-timedelta(days=2))
        self.autenticar(self.gerencia)
        r = self.client.get(self.supervision_url)
        self.assertEqual(r.status_code, 200, r.data)
        s = r.data["resumen"]
        self.assertEqual((s["total"], s["cobrado"], s["saldo"], s["vencido"], s["no_vencido"]), ("2180.35", "100.13", "2080.22", "2080.22", "0.00"))
        self.assertEqual(s["clientes_vencidos"], 1)
        self.assertEqual(r.data["results"][0]["dias_atraso"], 2)
        self.assertEqual(r.data["results"][0]["obra"], self.obra.codigo)
        por_codigo = self.client.get(self.supervision_url, {"buscar": self.obra.codigo.lower()})
        self.assertEqual(por_codigo.status_code, 200, por_codigo.data)
        self.assertEqual(por_codigo.data["count"], 1)
        self.assertEqual(por_codigo.data["results"][0]["obra"], self.obra.codigo)
        self.assertEqual(self.client.get(self.supervision_url, {"buscar":"no existe"}).data["resumen"], s)
        self.assertEqual(self.client.get(self.supervision_url, {"desde":hoy_santiago().isoformat(),"hasta":hoy_santiago().isoformat()}).data["resumen"]["documentos"], 0)

    def test_revertido_solo_historico(self):
        documentos.revertir_documento(self.doc.pk, {"motivo":"Corrección", "referencia_rectificacion_externa":"Respaldo"}, self.finanzas)
        self.autenticar(self.gerencia)
        vigentes = self.client.get(self.supervision_url, {"vista":"vigentes"})
        self.assertEqual(vigentes.status_code, 200, vigentes.data)
        self.assertEqual(vigentes.data["count"], 0)
        r = self.client.get(self.supervision_url, {"vista":"documentos"})
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["count"], 1)
        self.assertIsNone(r.data["results"][0]["saldo"])
        self.assertEqual(r.data["resumen"]["total"], "0.00")
