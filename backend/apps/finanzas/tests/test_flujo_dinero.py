from datetime import timedelta
from decimal import Decimal, localcontext
from uuid import uuid4

from django.db import connection, models
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.exceptions import APIException

from apps.finanzas import consultas_egresos as consultas, services_egresos as egresos
from apps.finanzas import services_documentos as documentos, services_pagos as pagos
from apps.finanzas.models import DocumentoCobro, PagoDocumento, FinanzasEvento
from apps.finanzas.validaciones import hoy_santiago, LIMITE
from apps.obras.models import GastoObra, CierreCostosObra, CostoObraEvento
from apps.inventario.models import MovimientoInventario, ExistenciaInventario
from .test_egresos import EgresosBase, payload, RESUMEN
from .test_pagos import PagosBase


def periodo(dia=None):
    return {'desde': str(dia or hoy_santiago()), 'hasta': str(dia or hoy_santiago())}


class FlujoDineroTests(EgresosBase, PagosBase, TestCase):
    def setUp(self):
        self.preparar_pagos()

    def pagar_directo(self, **changes):
        return pagos.registrar_pago(self.doc.pk, self.pago_data(**changes), self.finanzas, str(uuid4()))[0]

    def test_solo_movimientos_efectivos_no_documentos_costos_ni_inventario(self):
        self.assertGreater(self.doc.monto_total, 0)
        self.assertTrue(CierreCostosObra.objects.exists())
        r = self.client.get(RESUMEN, periodo())
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data['ingresos_recibidos'], '0.00')
        self.assertEqual(r.data['egresos_pagados'], '0.00')
        pago = self.pagar_directo()
        antes = {m: list(m.objects.order_by('pk').values()) for m in [DocumentoCobro, PagoDocumento, FinanzasEvento,
            GastoObra, CierreCostosObra, CostoObraEvento, MovimientoInventario, ExistenciaInventario]}
        e = self.crear_egreso(monto='150.25', obra=self.obra.pk)
        r = self.client.get(RESUMEN, periodo())
        self.assertEqual(r.data, {'periodo': periodo(), 'moneda': 'CLP', 'ingresos_recibidos': '100.13',
            'egresos_pagados': '150.25', 'flujo_neto_registrado': '-50.12', 'naturaleza': 'REGISTROS_ADMINISTRATIVOS_NO_CONCILIADOS'})
        egresos.anular_egreso(e.pk, {'motivo': 'Registro incorrecto', 'referencia_correccion': 'R'}, self.finanzas)
        for m, estado in antes.items():
            self.assertEqual(list(m.objects.order_by('pk').values()), estado, m.__name__)
        r = self.client.get(RESUMEN, periodo())
        self.assertEqual(r.data['flujo_neto_registrado'], '100.13')
        pagos.anular_pago(self.doc.pk, pago.pk, {'motivo': 'Error', 'referencia_reversion_externa': 'R'}, self.finanzas)
        self.assertEqual(self.client.get(RESUMEN, periodo()).data['flujo_neto_registrado'], '0.00')

    def test_invariante_007_documento_revertido_con_pago_activo_no_se_oculta(self):
        self.pagar_directo()
        with self.assertRaises(APIException) as error:
            documentos.revertir_documento(self.doc.pk, {'motivo': 'No válido', 'referencia_rectificacion_externa': 'R'}, self.finanzas)
        self.assertEqual(error.exception.detail['code'], 'pagos_pendientes_de_resolver')
        # Simula corrupción preexistente eludiendo servicios, solo en BD de tests.
        models.QuerySet(model=DocumentoCobro).filter(pk=self.doc.pk).update(estado='REVERTIDO',
            revertido_por_id=self.finanzas.pk, revertido_en=timezone.now(), motivo_reversion='Corrupción de prueba', referencia_rectificacion_externa='R')
        r = self.client.get(RESUMEN, periodo())
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data['code'], 'origen_inconsistente')

    def test_inconsistencias_fecha_y_sobrepago_devuelven_conflicto(self):
        p = self.pagar_directo()
        models.QuerySet(model=PagoDocumento).filter(pk=p.pk).update(monto=Decimal('3000.00'))
        self.assertEqual(self.client.get(RESUMEN, periodo()).status_code, 409)
        models.QuerySet(model=PagoDocumento).filter(pk=p.pk).update(monto=Decimal('100.00'), fecha_pago=self.doc.fecha_emision - timedelta(days=1))
        self.assertEqual(self.client.get(RESUMEN, periodo(self.doc.fecha_emision - timedelta(days=1))).status_code, 409)

    def test_fechas_del_pago_no_de_registro_ni_emision_y_rango_inclusivo(self):
        ayer = hoy_santiago() - timedelta(days=1)
        self.pagar_directo(fecha_pago=ayer.isoformat())
        self.crear_egreso(fecha_pago=ayer.isoformat())
        self.assertEqual(self.client.get(RESUMEN, periodo()).data['ingresos_recibidos'], '0.00')
        r = self.client.get(RESUMEN, periodo(ayer))
        self.assertEqual(r.data['ingresos_recibidos'], '100.13')
        self.assertEqual(r.data['egresos_pagados'], '100.25')
        self.assertEqual(r.data['flujo_neto_registrado'], '-0.12')
        self.assertEqual(self.client.get(RESUMEN, {'desde': '2024-01-01', 'hasta': '2024-12-31'}).status_code, 200)
        for query in [{}, {'desde': str(ayer)}, {'desde': '2026-02-30', 'hasta': '2026-03-01'},
                      {'desde': '2024-01-01', 'hasta': '2025-01-01'}, {'desde': str(ayer), 'hasta': str(ayer), 'page': 1}]:
            self.assertEqual(self.client.get(RESUMEN, query).status_code, 400)
        self.assertEqual(self.client.get(RESUMEN + '?desde=2026-01-01&desde=2026-01-02&hasta=2026-01-31').status_code, 400)

    def test_agregado_mayor_que_movimiento_individual_decimal_exacto(self):
        for _ in range(2):
            self.crear_egreso(monto=format(LIMITE, '.2f'))
        r = self.client.get(RESUMEN, periodo())
        self.assertEqual(r.status_code, 200, r.data)
        with localcontext() as ctx:
            ctx.prec = 80
            self.assertEqual(r.data['egresos_pagados'], format(LIMITE * 2, '.2f'))
            self.assertEqual(r.data['flujo_neto_registrado'], format(-LIMITE * 2, '.2f'))

    def test_resumen_un_solo_select_de_agregados_sin_escrituras(self):
        with CaptureQueriesContext(connection) as queries:
            consultas.resumen(self.finanzas, periodo())
        self.assertEqual(sum('SPEC-021 snapshot' in q['sql'] for q in queries), 1)
        self.assertFalse(any(q['sql'].lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE')) for q in queries))

    def test_uuid_del_pago_no_colisiona_con_dominio_egreso(self):
        key = str(uuid4())
        p, _ = pagos.registrar_pago(self.doc.pk, self.pago_data(), self.finanzas, key)
        e, nuevo = egresos.registrar_egreso(payload(), self.finanzas, key)
        self.assertTrue(nuevo)
        self.assertEqual(PagoDocumento.objects.get(pk=p.pk).monto, Decimal('100.13'))
        self.assertEqual(e.monto, Decimal('100.25'))
