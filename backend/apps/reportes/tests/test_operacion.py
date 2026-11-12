import json
from decimal import Decimal
from time import perf_counter
import tracemalloc
from unittest.mock import patch

from django.core.cache import cache
from django.db import connection
from django.test import TransactionTestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.reportes import consultas
from apps.reportes.consistencia import snapshot
from apps.comercial.models import Presupuesto, PresupuestoItem
from apps.obras.models import Obra
from .base import ReportesBase, BASE


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class OperacionReportesTests(ReportesBase, TransactionTestCase):
    def setUp(self):
        self.preparar_reportes()

    def test_presupuesto_tiempo_controlado_sin_archivo_parcial(self):
        with patch("apps.reportes.catalogo.MAX_SEGUNDOS", -1), self.assertLogs("apps.reportes.views", level="WARNING"):
            r = self.client.get(BASE + "obras/exportar/", {"formato": "csv"})
        self.assertEqual(r.status_code, 500)
        self.assertEqual(r.data["code"], "reporte_tiempo_excedido")
        self.assertFalse(r.streaming)

    def test_perfil_postgres_mil_filas_tres_formatos_y_memoria(self):
        presupuestos = Presupuesto.objects.bulk_create([Presupuesto(cliente=self.cliente, creado_por=self.finanzas, descripcion="Perfil QA", estado="APROBADO_CLIENTE") for _ in range(1000)], batch_size=200)
        PresupuestoItem.objects.bulk_create([PresupuestoItem(presupuesto=p, descripcion="Servicio QA", unidad="unidad", cantidad=Decimal("1.125"), precio_unitario=Decimal("1234.56"), orden=1) for p in presupuestos], batch_size=200)
        Obra.objects.bulk_create([Obra(presupuesto=p, categoria_servicio=self.categoria, creado_por=self.supervisor, descripcion="Perfil de exportación") for p in presupuestos], batch_size=200)
        metricas = {}
        for formato in ("json", "csv", "xlsx", "pdf"):
            cache.clear()
            inicio = perf_counter()
            tracemalloc.start()
            try:
                with CaptureQueriesContext(connection) as queries:
                    if formato == "json":
                        r = self.listado("obras", estado="PLANIFICADA")
                        self.assertEqual(r.status_code, 200, r.data)
                        self.assertEqual(r.data["count"], 1000)
                        self.assertEqual(r.data["totales"]["presupuesto_neto"], "1388880.00")
                        data = r.content
                    else:
                        data, _ = self.exportacion("obras", formato, estado="PLANIFICADA")
                _, peak = tracemalloc.get_traced_memory()
            finally:
                tracemalloc.stop()
            metricas[formato] = {"queries": len(queries), "bytes": len(data), "segundos": round(perf_counter() - inicio, 3), "peak_python_bytes": peak}
            self.assertLessEqual(len(queries), 25)
            self.assertLess(peak, 150 * 1024 * 1024)
            if formato == "pdf":
                metricas[formato]["paginas"] = len(self.leer_pdf(data).pages)
        with snapshot() as (corte, _):
            qs = consultas.queryset("obras", {"desde": corte.date().replace(day=1), "hasta": corte.date(), "fecha_base": "CREACION", "estado": "PLANIFICADA"}, corte)
            plan = json.loads(qs[:25].explain(analyze=True, buffers=True, format="json"))[0]
        metricas["explain"] = {"nodo": plan["Plan"]["Node Type"], "filas": plan["Plan"]["Actual Rows"], "planning_ms": plan["Planning Time"], "execution_ms": plan["Execution Time"]}
        print("PERFIL_REPORTES_POSTGRESQL=" + json.dumps(metricas, sort_keys=True))
