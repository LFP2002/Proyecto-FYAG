from decimal import Decimal
from django.test import TestCase, override_settings
from django.db import connection
from django.test.utils import CaptureQueriesContext
from apps.inventario.models import ExistenciaInventario, EstadoValoracion, MovimientoInventario
from apps.inventario import services
from .test_inventario import BaseInventario
from .test_mermas import MermasBase


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class SupervisionInventarioTests(BaseInventario, TestCase):
    url = "/api/inventario/supervision-gerencial/"

    def test_roles_y_consulta_sin_escrituras(self):
        for role, user in self.users.items():
            self.auth(user)
            self.assertEqual(self.client.get(self.url).status_code, 200 if role == "GERENCIA" else 403)
        self.auth(self.users["GERENCIA"])
        r = self.client.get(self.url)
        self.assertEqual(r.data["resumen"]["sin_stock"], 1)
        self.assertEqual(r.data["resumen"]["valor_stock_valorado"], "0.00")
        self.assertFalse(MovimientoInventario.objects.exists())
        self.assertFalse(EstadoValoracion.objects.exists() and EstadoValoracion.objects.get(articulo=self.article).saldo_valorado)
        for q in ("?seccion=otro", "?filtro=otro", "?foo=1", "?page=1&page=2"):
            self.assertEqual(self.client.get(self.url+q).status_code, 400)

    def test_stock_fisico_no_valorado_y_paginacion_global(self):
        self.ingreso()
        for i in range(26):
            services.crear_articulo({"codigo": f"mat-{i+2:03}", "nombre": f"Material {i+2}", "unidad": "u"}, self.bodega)
        self.auth(self.users["GERENCIA"])
        with CaptureQueriesContext(connection) as consultas:
            r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["resumen"]["sin_stock"], 26)
        self.assertEqual(r.data["resumen"]["pendientes_valoracion"], 1)
        self.assertEqual(r.data["resumen"]["valor_stock_valorado"], "0.00")
        self.assertLess(len(consultas), 20)
        r2 = self.client.get(self.url, {"filtro": "pendiente"})
        self.assertEqual(r2.data["count"], 1)
        self.assertEqual(r2.data["results"][0]["saldo"], "1.250")
        self.assertEqual(r2.data["resumen"], r.data["resumen"])
        self.assertEqual(self.client.get(self.url, {"page": 2}).data["count"], 27)

class SupervisionMermasTests(MermasBase, TestCase):
    def setUp(self):
        self.preparar_mermas()

    def test_valor_real_y_mermas_separadas(self):
        self.preparar_entrega()
        self.resolver(self.informar("BODEGA"))
        self.resolver(self.informar("OBRA"))
        self.informar("OBRA", cantidad="1.000")
        self.autenticar(self.gerencia)
        url = "/api/inventario/supervision-gerencial/"
        r = self.client.get(url, {"seccion": "mermas"})
        self.assertEqual(r.status_code, 200, r.data)
        s = r.data["resumen"]
        self.assertEqual(s["valor_stock_valorado"], "200.00")
        self.assertEqual(s["mermas_bodega_neto"], "200.00")
        self.assertEqual(s["mermas_obra_informativo"], "200.00")
        self.assertEqual(s["mermas_pendientes"], 1)
        self.assertEqual(r.data["count"], 2)
        bodega = self.client.get(url, {"seccion": "mermas", "filtro": "bodega"})
        self.assertEqual(bodega.data["count"], 1)
        self.assertEqual(bodega.data["resumen"], s)
