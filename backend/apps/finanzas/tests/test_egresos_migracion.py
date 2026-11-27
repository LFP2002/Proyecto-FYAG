"""Instalación aditiva desde 0002 con historia real; runner instala desde cero."""
from importlib import import_module
from uuid import uuid4

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.exceptions import IrreversibleError
from django.test import TransactionTestCase

from apps.finanzas import services_pagos as pagos
from apps.finanzas.models import DocumentoCobro, PagoDocumento, FinanzasEvento
from apps.inventario.models import ArticuloInventario, ExistenciaInventario, MovimientoInventario
from apps.obras.models import GastoObra, CierreCostosObra, CostoObraEvento, ObraEvento
from apps.usuarios.models import Usuario
from .test_egresos import EgresosBase
from .test_pagos import PagosBase


class MigracionEgresosTests(EgresosBase, PagosBase, TransactionTestCase):
    def test_desde_0002_preserva_filas_y_bloquea_reversion_con_historia(self):
        executor = MigrationExecutor(connection)
        hojas = executor.loader.graph.leaf_nodes()
        try:
            # Los servicios actuales requieren el esquema vigente. Generar la
            # historia real antes de retroceder; usar modelos históricos para
            # inspeccionar las filas en 0002, nunca servicios actuales allí.
            self.setUpTestData()
            self.preparar_pagos()
            pagos.registrar_pago(self.doc.pk, self.pago_data(), self.finanzas, str(uuid4()))
            bodeguero = Usuario.objects.create_user(username='bodega_migracion_021', rol='BODEGUERO', email='bodega021@example.test')
            a = ArticuloInventario.objects.create(codigo='qa-021', nombre='Material histórico', unidad='unidad',
                creado_por=bodeguero, actualizado_por=bodeguero)
            MovimientoInventario.objects.create(articulo=a, cantidad='5.000', saldo_anterior='0.000',
                saldo_posterior='5.000', clave_idempotencia=uuid4(), actor=bodeguero)
            modelos = [DocumentoCobro, PagoDocumento, FinanzasEvento, GastoObra, CierreCostosObra,
                       CostoObraEvento, ObraEvento, ArticuloInventario, ExistenciaInventario, MovimientoInventario]
            antes = {m: list(m.objects.order_by('pk').values()) for m in modelos}
            self.assertTrue(antes[FinanzasEvento])
            self.assertTrue(all(fila['actor_username_historico'] == self.finanzas.username
                                for fila in antes[FinanzasEvento]))
            self.assertTrue(antes[PagoDocumento])
            self.assertTrue(antes[CierreCostosObra])
            self.assertTrue(antes[MovimientoInventario])
            anterior = ('finanzas', '0002_pagos_cobranzas')
            executor = MigrationExecutor(connection)
            executor.migrate([anterior])
            historicos = executor.loader.project_state([anterior]).apps
            for m in (DocumentoCobro, PagoDocumento, FinanzasEvento):
                viejo = historicos.get_model('finanzas', m.__name__)
                campos = [f.attname for f in viejo._meta.concrete_fields]
                self.assertEqual(list(viejo.objects.order_by('pk').values(*campos)),
                                 [{k: fila[k] for k in campos} for fila in antes[m]], m.__name__)
            executor = MigrationExecutor(connection)
            executor.migrate(hojas)
            for m, filas in antes.items():
                if m is FinanzasEvento:
                    # 0002 no tenía identidad histórica. 0004 agrega columnas
                    # anulables sin backfill; no inventar nombres del pasado.
                    # Todos los campos que sí existían se comparan íntegros.
                    filas = [dict(fila, actor_nombre_historico=None,
                                  actor_username_historico=None) for fila in filas]
                self.assertEqual(list(m.objects.order_by('pk').values()), filas, m.__name__)
            e = self.crear_egreso()
            migration = import_module('apps.finanzas.migrations.0003_egresos_flujo_dinero')
            estado = executor.loader.project_state(hojas)
            with self.assertRaises(IrreversibleError), connection.schema_editor() as editor:
                migration.comprobar_reversion(estado.apps, editor)
            self.assertEqual(e.eventos.count(), 1)
        finally:
            MigrationExecutor(connection).migrate(hojas)
