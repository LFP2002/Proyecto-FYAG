from django.test import TestCase

from .base import FinanzasBase


class ObrasResumenFinanzasTests(FinanzasBase, TestCase):
    def setUp(self):
        self.preparar_finanzas()
        self.url = "/api/finanzas/obras-resumen/"

    def test_proyeccion_filtros_y_documento(self):
        response = self.client.get(self.url, {"buscar": self.obra.codigo, "situacion_financiera": "PENDIENTE_FACTURACION"})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["count"], 1)
        row = response.data["results"][0]
        self.assertEqual(row["id"], self.obra.pk)
        self.assertEqual(row["monto_neto_aprobado"], "2080.22")
        self.assertNotIn("descripcion", row)
        self.assertNotIn("documento", row)
        self.assertNotIn("costo_total", row)
        self.assertEqual(self.client.get(self.url, {"cliente_nombre": self.cliente.nombre_legal}).data["count"], 1)
        self.assertEqual(self.client.get(self.url, {"estado": "PLANIFICADA"}).data["count"], 0)
        self.assertEqual(self.registrar().status_code, 201)
        detail = self.client.get(f"{self.url}{self.obra.pk}/")
        self.assertEqual(detail.status_code, 200, detail.data)
        self.assertEqual(detail.data["situacion_financiera"], "DOCUMENTADO")
        self.assertEqual(detail.data["documento"]["monto_total"], "2180.35")
        self.assertEqual(detail.data["documento"]["cobranza"]["saldo"], "2180.35")
        self.assertEqual(self.client.get(self.url, {"situacion_financiera": "PENDIENTE_FACTURACION"}).data["count"], 0)

    def test_rol_exclusivo_y_validacion(self):
        for actor in (self.gerencia, self.supervisor, self.tecnico):
            self.autenticar(actor)
            self.assertEqual(self.client.get(self.url).status_code, 403)
            self.assertEqual(self.client.get(f"{self.url}{self.obra.pk}/").status_code, 403)
        self.client.credentials()
        self.assertEqual(self.client.get(self.url).status_code, 401)
        self.autenticar(self.finanzas)
        for query in ("?estado=INVALIDO", "?buscar=", "?cliente=1", "?buscar=a&buscar=b"):
            self.assertEqual(self.client.get(self.url + query).status_code, 400)
        self.assertEqual(self.client.post(self.url, {}, format="json").status_code, 405)
        self.assertEqual(self.client.get(f"{self.url}999999999/").status_code, 404)
