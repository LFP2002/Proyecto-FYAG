from django.test import TestCase

from apps.inventario.models import MovimientoInventario, OperacionMaterial
from .test_materiales import MaterialesBase


URL = "/api/inventario/finanzas/"


class FinanzasInventarioTests(MaterialesBase, TestCase):
    def setUp(self):
        self.preparar_materiales()
        self.autenticar(self.finanzas)

    def test_proyeccion_totales_busqueda_y_lectura(self):
        self.recibir("10.000", "100.00")
        self.recibir("2.000", None)
        response = self.client.get(URL)
        self.assertEqual(response.status_code, 200, response.data)
        row = response.data["results"][0]
        self.assertEqual(row["nombre"], self.article.nombre)
        self.assertEqual(row["saldo"], "12.000")
        self.assertEqual(row["valor_neto"], "1000.00")
        self.assertTrue(row["pendiente"])
        self.assertEqual(response.data["resumen"], {"materiales": 1, "sin_stock": 0, "pendientes": 1, "valor_neto": "1000.00"})
        filtered = self.client.get(URL, {"buscar": "inexistente"})
        self.assertEqual(filtered.data["count"], 0)
        self.assertEqual(filtered.data["resumen"], response.data["resumen"])
        filtered = self.client.get(URL, {"buscar": "MAT019B", "filtro": "pendiente"})
        self.assertEqual(filtered.data["count"], 1)
        self.assertEqual(self.client.get(URL, {"filtro": "sin_stock"}).data["count"], 0)
        movements = self.client.get(URL, {"seccion": "movimientos", "tipo": "INGRESO", "buscar": "019B"})
        self.assertEqual(movements.data["count"], 2)
        self.assertTrue(all(r["nombre"] == self.article.nombre for r in movements.data["results"]))
        self.assertEqual(self.client.get(URL, {"seccion": "valoraciones"}).data["count"], 1)
        self.assertEqual(self.client.get(URL, {"seccion": "regularizaciones"}).data["count"], 0)
        self.assertEqual(MovimientoInventario.objects.count(), 2)
        self.assertEqual(OperacionMaterial.objects.count(), 1)

    def test_ingresos_elegibles_respetan_orden_y_no_reofrecen_valorizados(self):
        first = self.recibir("2.000", None)
        second = self.recibir("3.000", None)
        params = {"seccion": "ingresos"}
        def ids():
            response = self.client.get(URL, params)
            self.assertEqual(response.status_code, 200, response.data)
            return [r["id"] for r in response.data["results"]]
        self.assertEqual(ids(), [first.pk])
        self.op("VALORIZACION", ingreso=first.pk, costo_unitario_neto="100.00", referencia="R")
        self.assertEqual(ids(), [second.pk])
        self.op("VALORIZACION", ingreso=second.pk, costo_unitario_neto="100.00", referencia="R")
        self.assertEqual(ids(), [])
        self.assertEqual(self.client.get(URL, {"seccion": "historicos"}).data["count"], 0)
        self.assertEqual(self.saldo(), 5)

    def test_permisos_y_filtros_estrictos(self):
        for actor in (self.bodega, self.supervisor, self.gerencia):
            self.autenticar(actor)
            self.assertEqual(self.client.get(URL).status_code, 403)
        self.autenticar(self.finanzas)
        for q in ("?seccion=otro", "?buscar=%20", "?buscar=a&buscar=b", "?filtro=otro",
                  "?seccion=valoraciones&tipo=INGRESO", "?seccion=movimientos&desde=2026-11-01",
                  "?seccion=movimientos&desde=2026-11-30&hasta=2026-11-01"):
            self.assertEqual(self.client.get(URL + q).status_code, 400, q)
        # DRF comprueba permisos antes de resolver el método HTTP.
        # Finanzas no tiene permiso de escritura en la proyección de inventario.
        self.assertEqual(self.client.post(URL, {}, format="json").status_code, 403)
        self.assertFalse(MovimientoInventario.objects.exists())
        self.assertFalse(OperacionMaterial.objects.exists())
