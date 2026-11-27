from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.db import connection

from apps.obras.models import ControlCostosObra, Obra
from .test_costos import CostosBase


class SupervisionGerencialTests(CostosBase, TestCase):
    url_panel = "/api/obras/supervision-gerencial/"

    def setUp(self):
        self.preparar()

    def test_permiso_y_consulta_sin_escrituras(self):
        for usuario in (self.supervisor, self.finanzas, self.tecnico):
            self.autenticar(usuario)
            self.assertEqual(self.client.get(self.url_panel).status_code, 403)
        self.autenticar(self.gerencia)
        self.assertEqual(self.client.post(self.url_panel, {}, format="json").status_code, 405)
        antes = ControlCostosObra.objects.count()
        respuesta = self.client.get(self.url_panel)
        self.assertEqual(respuesta.status_code, 200, respuesta.data)
        self.assertEqual(respuesta.data["resumen"]["en_ejecucion"], 1)
        self.assertEqual(ControlCostosObra.objects.count(), antes)

    def test_costos_coinciden_con_resumen_y_prioridad(self):
        self.crear_ok()
        self.acreditar()
        self.autenticar(self.gerencia)
        resumen = self.client.get(self.resumen_url).data
        respuesta = self.client.get(self.url_panel, {"atencion": "requiere"})
        self.assertEqual(respuesta.status_code, 200, respuesta.data)
        fila = respuesta.data["results"][0]
        self.assertEqual(fila["costo_total"], resumen["costo_total"])
        self.assertEqual(fila["presupuesto_neto"], format(self.obra.presupuesto.monto_neto, ".2f"))
        self.assertIn("PRESUPUESTO_SUPERADO", fila["alertas"])
        self.assertEqual(respuesta.data["resumen"]["presupuesto_superado"], 1)
        self.assertIsNone(fila["porcentaje_utilizado"])

    def test_paginacion_y_resumen_global_sin_n_mas_uno(self):
        for _ in range(26):
            self.otra_obra()
        self.autenticar(self.gerencia)
        with CaptureQueriesContext(connection) as consultas:
            respuesta = self.client.get(self.url_panel)
        self.assertEqual(respuesta.status_code, 200, respuesta.data)
        self.assertEqual(respuesta.data["count"], 27)
        self.assertEqual(len(respuesta.data["results"]), 25)
        self.assertEqual(respuesta.data["resumen"]["total"], 27)
        self.assertLess(len(consultas), 20)
        pagina = self.client.get(self.url_panel, {"page": 2})
        self.assertEqual(len(pagina.data["results"]), 2)
        self.assertEqual(pagina.data["resumen"], respuesta.data["resumen"])
        filtrada = self.client.get(self.url_panel, {"estado": "PLANIFICADA"})
        self.assertEqual(filtrada.data["count"], 0)
        self.assertEqual(filtrada.data["resumen"], respuesta.data["resumen"])
        for query in ("?estado=INVALIDO", "?atencion=otro", "?prioridad=otro", "?page=1&page=2", "?foo=bar"):
            self.assertEqual(self.client.get(self.url_panel + query).status_code, 400)
