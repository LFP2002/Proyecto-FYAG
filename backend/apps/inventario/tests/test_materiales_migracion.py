from importlib import import_module
from uuid import uuid4

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.exceptions import IrreversibleError
from django.test import TransactionTestCase
from rest_framework.exceptions import APIException

from apps.finanzas import services_pagos, services_egresos
from apps.finanzas.tests.test_egresos import payload
from apps.finanzas.tests.test_pagos import PagosBase
from apps.inventario import services, services_materiales
from apps.inventario.models import EstadoValoracion, ExistenciaInventario, MovimientoInventario
from apps.usuarios.models import Usuario


class Upgrade019BTests(PagosBase, TransactionTestCase):
    def test_corte_historico_upgrade_y_regularizacion_explicita(self):
        self.setUpTestData()
        self.preparar_pagos()
        services_pagos.registrar_pago(self.doc.pk, self.pago_data(), self.finanzas, str(uuid4()))
        services_egresos.registrar_egreso(payload(), self.finanzas, str(uuid4()))
        b = Usuario.objects.create_user(username='upgradeb', email='upgradeb@example.test', rol='BODEGUERO')
        a = services.crear_articulo({'codigo': 'historico019a', 'nombre': 'Existencia histórica', 'unidad': 'kg'}, b)
        m, _ = services.registrar_ingreso({'articulo': a.pk, 'cantidad': '5.000', 'clave_idempotencia': str(uuid4())}, b)
        executor = MigrationExecutor(connection)
        hojas = executor.loader.graph.leaf_nodes()
        previo = [('inventario', '0002_integridad_libro'), ('obras', '0011_cierre_costos_finalizacion')]
        try:
            executor.migrate(previo)
            apps = MigrationExecutor(connection).loader.project_state(previo + [('finanzas', '0003_egresos_flujo_dinero')]).apps
            nombres = [('inventario', 'MovimientoInventario'), ('inventario', 'ExistenciaInventario'),
                ('obras', 'Obra'), ('obras', 'GastoObra'), ('obras', 'CostoObraEvento'), ('obras', 'CierreCostosObra'),
                ('finanzas', 'DocumentoCobro'), ('finanzas', 'PagoDocumento'), ('finanzas', 'Egreso')]
            antes = {x: list(apps.get_model(*x).objects.order_by('pk').values()) for x in nombres}
            self.assertTrue(antes[('finanzas', 'Egreso')])
            self.assertTrue(antes[('obras', 'CierreCostosObra')])
            MigrationExecutor(connection).migrate(hojas)
            actuales = MigrationExecutor(connection).loader.project_state(hojas).apps
            for x, filas in antes.items():
                columnas = list(filas[0]) if filas else ['pk']
                resultado = list(actuales.get_model(*x).objects.order_by('pk').values(*columnas))
                self.assertEqual(resultado, filas, x)
            v = EstadoValoracion.objects.get(articulo=a)
            self.assertEqual(v.saldo_historico, 5)
            self.assertEqual(v.ultimo_movimiento_historico, m.pk)
            self.assertEqual(v.saldo_valorado, 0)
            self.assertIsNone(v.promedio)
            operativa = self.otra_obra()
            autorizacion, _ = services_materiales.operar('AUTORIZACION_ENTREGA', {'obra': operativa.pk, 'articulo': a.pk,
                'cantidad': '1.000', 'clave_idempotencia': str(uuid4())}, self.supervisor)
            with self.assertRaises(APIException) as error:
                services_materiales.operar('ENTREGA', {'autorizacion': autorizacion.pk, 'cantidad': '1.000',
                    'clave_idempotencia': str(uuid4())}, b)
            self.assertEqual(error.exception.detail['code'], 'valoracion_pendiente')
            n, _ = services.registrar_ingreso({'articulo': a.pk, 'cantidad': '1.000', 'clave_idempotencia': str(uuid4())}, b)
            data = {'ingreso': n.pk, 'costo_unitario_neto': '200.00', 'referencia': 'RESPALDO', 'clave_idempotencia': str(uuid4())}
            with self.assertRaises(APIException):
                services_materiales.operar('VALORIZACION', data, self.finanzas)
            reg = {'articulo': a.pk, 'costo_unitario_neto': '100.00', 'referencia': 'CORTE-VERIFICADO',
                   'motivo': 'Precio neto histórico respaldado', 'clave_idempotencia': str(uuid4())}
            op, _ = services_materiales.operar('REGULARIZACION', reg, self.finanzas)
            self.assertEqual(op.cantidad, 5)
            replay, creado = services_materiales.operar('REGULARIZACION', reg, self.finanzas)
            self.assertFalse(creado)
            self.assertEqual(replay.pk, op.pk)
            with self.assertRaises(APIException):
                services_materiales.operar('REGULARIZACION', {**reg, 'clave_idempotencia': str(uuid4())}, self.finanzas)
            self.assertEqual(ExistenciaInventario.objects.get(articulo=a).saldo, 6)
            self.assertEqual(MovimientoInventario.objects.filter(articulo=a).count(), 2)
            services_materiales.operar('VALORIZACION', data, self.finanzas)
            self.assertEqual(str(EstadoValoracion.objects.get(articulo=a).promedio), '116.67')
            migration = import_module('apps.inventario.migrations.0004_integridad_materiales')
            with self.assertRaises(IrreversibleError), connection.schema_editor() as editor:
                migration.impedir_reversion(actuales, editor)
        finally:
            MigrationExecutor(connection).migrate(hojas)
