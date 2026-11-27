from datetime import timedelta
from django.test import TestCase
from django.urls import resolve
from apps.finanzas.validaciones import hoy_santiago
from apps.finanzas import services_egresos as services
from apps.finanzas.views_egresos_gerencia import SupervisionEgresosView
from .test_egresos import EgresosBase


class SupervisionEgresosTests(EgresosBase, TestCase):
    supervision_url = "/api/finanzas/egresos/supervision-gerencial/"

    def setUp(self):
        self.preparar_finanzas()
        self.assertIs(resolve(self.supervision_url).func.cls, SupervisionEgresosView)
        self.period = {"desde": (hoy_santiago()-timedelta(days=7)).isoformat(), "hasta": hoy_santiago().isoformat()}

    def test_roles_y_filtros_invalidos(self):
        for actor in (self.finanzas, self.supervisor, self.tecnico, self.gerencia):
            self.autenticar(actor)
            response = self.client.get(self.supervision_url, self.period)
            self.assertEqual(response.status_code, 200 if actor == self.gerencia else 403, response.data)
        for params in ({}, {**self.period,"vista":"x"}, {**self.period,"categoria":"x"}, {**self.period,"foo":"x"}, {**self.period,"medio":"x"}, {**self.period,"desde":"2026-02-30"}):
            self.assertEqual(self.client.get(self.supervision_url, params).status_code, 400)
        self.assertEqual(self.client.post(self.supervision_url, {}, format="json").status_code, 403)

    def test_resumen_global_y_anulaciones(self):
        self.crear_egreso(monto="100.25", beneficiario="Proveedor A", obra=self.obra.pk)
        self.crear_egreso(monto="200.00", beneficiario="Proveedor A", categoria="TRANSPORTE")
        self.crear_egreso(monto="300.50", beneficiario="Proveedor B")
        e = self.crear_egreso(monto="900.00", beneficiario="Proveedor C")
        services.anular_egreso(e.pk, {"motivo":"Duplicado","referencia_correccion":"R"}, self.finanzas)
        self.crear_egreso(monto="999.00", fecha_pago=(hoy_santiago()-timedelta(days=10)).isoformat())
        self.autenticar(self.gerencia)
        r = self.client.get(self.supervision_url, self.period)
        self.assertEqual(r.status_code, 200, r.data)
        s = r.data["resumen"]
        self.assertEqual((s["total"],s["pagos"],s["beneficiarios"],s["mayor"]), ("600.75",3,2,"300.50"))
        self.assertEqual(s["ranking"][0]["beneficiario"], "Proveedor B")
        self.assertEqual(s["ranking"][1]["monto"], "300.25")
        self.assertEqual(r.data["count"],3)
        for filtros, n in [({"vista":"anulados"},1),({"vista":"todos"},4),({"buscar":self.obra.codigo.lower()},1),({"categoria":"TRANSPORTE"},1),({"buscar":"Proveedor B"},1)]:
            r = self.client.get(self.supervision_url, {**self.period,**filtros})
            self.assertEqual(r.status_code,200,r.data)
            self.assertEqual(r.data["count"],n)
            self.assertEqual(r.data["resumen"],s)

    def test_paginacion_y_periodo_vacio(self):
        for _ in range(26):
            self.crear_egreso(monto="1.01")
        self.autenticar(self.gerencia)
        r = self.client.get(self.supervision_url, self.period)
        self.assertEqual(r.status_code,200,r.data)
        self.assertEqual(len(r.data["results"]),25)
        self.assertEqual(r.data["resumen"]["total"],"26.26")
        siguiente = self.client.get(r.data["next"])
        self.assertEqual(len(siguiente.data["results"]),1)
        self.assertEqual(siguiente.data["resumen"],r.data["resumen"])
        yesterday = (hoy_santiago()-timedelta(days=1)).isoformat()
        r = self.client.get(self.supervision_url, {"desde":yesterday,"hasta":yesterday})
        self.assertEqual(r.data["resumen"]["total"],"0.00")
        self.assertEqual(r.data["resumen"]["ranking"],[])
