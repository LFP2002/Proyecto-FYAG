from datetime import timedelta
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from apps.comercial.models import Presupuesto, PresupuestoEvento
from apps.usuarios.models import Usuario
from .test_presupuesto_api import PresupuestoAPIBase, G


class SeguimientoComercialTests(PresupuestoAPIBase):
    panel = "/api/presupuestos/seguimiento-comercial/"

    def test_roles_y_lectura(self):
        antes = PresupuestoEvento.objects.count()
        for rol in Usuario.Rol:
            self.autenticar(rol)
            self.assertEqual(self.client.get(self.panel).status_code, 200 if rol == G else 403)
        self.autenticar(G)
        self.assertEqual(self.client.post(self.panel, {}, format="json").status_code, 405)
        self.assertEqual(PresupuestoEvento.objects.count(), antes)

    def test_resumen_decimal_legados_y_cohorte(self):
        aceptado = self.preparar("APROBADO_CLIENTE")
        self.preparar("RECHAZADO_CLIENTE")
        legado = self.preparar("PENDIENTE_GERENCIA")
        self.preparar("PENDIENTE_FINANZAS")
        antiguo = self.preparar("APROBADO_CLIENTE")
        Presupuesto.objects.filter(pk=antiguo.pk).update(creado_en=timezone.now()-timedelta(days=30))
        Presupuesto.objects.filter(pk=legado.pk).update(actualizado_en=timezone.now()-timedelta(days=8))
        self.autenticar(G)
        hoy = timezone.localdate().isoformat()
        r = self.client.get(self.panel, {"desde": hoy, "hasta": hoy, "estado": "PENDIENTE_FINANZAS"})
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["count"], 2)
        self.assertEqual(r.data["results"][0]["id"], legado.pk)
        self.assertEqual(r.data["resumen"]["total"], 5)
        self.assertEqual(r.data["resumen"]["estados"]["PENDIENTE_FINANZAS"]["monto_neto"], "501.26")
        self.assertEqual(r.data["resumen"]["tasa_aceptacion"], "50.0")
        self.assertEqual(r.data["resumen"]["estados"]["APROBADO_CLIENTE"]["monto_neto"], format(aceptado.monto_neto, ".2f"))
        self.assertEqual(r.data["resumen"]["sin_actualizar"], 1)

    def test_paginacion_global_y_validacion(self):
        for _ in range(26):
            self.preparar("ENVIADO_CLIENTE")
        self.autenticar(G)
        with CaptureQueriesContext(connection) as consultas:
            r = self.client.get(self.panel)
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(len(r.data["results"]), 25)
        self.assertEqual(r.data["resumen"]["total"], 27)
        self.assertIsNone(r.data["resumen"]["tasa_aceptacion"])
        self.assertLess(len(consultas), 20)
        p = self.client.get(self.panel, {"page": 2})
        self.assertEqual(len(p.data["results"]), 2)
        self.assertEqual(p.data["resumen"], r.data["resumen"])
        for query in ("?desde=2026-02-30", "?desde=2026-11-25&hasta=2026-11-24", "?estado=INVALIDO", "?page=1&page=2", "?foo=x"):
            self.assertEqual(self.client.get(self.panel+query).status_code, 400)
