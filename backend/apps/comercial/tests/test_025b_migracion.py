"""Migración aditiva SPEC-025B: mantener íntegra la cotización anterior."""
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class MigracionMateriales025B(TransactionTestCase):
    def test_upgrade_preserva_lineas_libres_y_montos(self):
        anterior = ('comercial', '0006_flujo_finanzas_020a')
        executor = MigrationExecutor(connection)
        hojas = executor.loader.graph.leaf_nodes()
        executor.migrate([anterior])
        try:
            apps = executor.loader.project_state([anterior]).apps
            Usuario = executor.loader.project_state(hojas).apps.get_model('usuarios', 'Usuario')
            Cliente = apps.get_model('comercial', 'Cliente')
            Presupuesto = apps.get_model('comercial', 'Presupuesto')
            Item = apps.get_model('comercial', 'PresupuestoItem')
            Evento = apps.get_model('comercial', 'PresupuestoEvento')
            actor = Usuario.objects.create(username='upgrade25', email='upgrade25@example.test',
                                           rol='ADMINISTRATIVO_FINANZAS')
            cliente = Cliente.objects.create(tipo_cliente='PERSONA',
                tipo_identificacion='SIN_IDENTIFICACION', nombre_legal='Cliente anterior',
                correo='cliente25@example.test')
            presupuesto = Presupuesto.objects.create(cliente=cliente, creado_por_id=actor.pk,
                descripcion='Histórico', estado='BORRADOR', politica_aprobacion='FINANZAS',
                requiere_aprobacion_gerencia=False)
            item = Item.objects.create(presupuesto=presupuesto, descripcion='Material libre anterior',
                cantidad='2.500', unidad='m', precio_unitario='8500.00', orden=1)
            Evento.objects.create(presupuesto=presupuesto, registrado_por_id=actor.pk,
                                  estado_nuevo='BORRADOR')
            cabecera = Presupuesto.objects.values().get(pk=presupuesto.pk)
            linea = Item.objects.values().get(pk=item.pk)
            historial = list(Evento.objects.filter(presupuesto=presupuesto).values())
        finally:
            MigrationExecutor(connection).migrate(hojas)
        from apps.comercial.models import Presupuesto, PresupuestoItem, PresupuestoEvento
        from decimal import Decimal
        self.assertEqual(Presupuesto.objects.values().get(pk=presupuesto.pk), cabecera)
        self.assertEqual(PresupuestoItem.objects.values().get(pk=item.pk),
                         dict(linea, articulo_id=None, codigo_articulo=''))
        self.assertEqual(list(PresupuestoEvento.objects.filter(presupuesto_id=presupuesto.pk).values()),
                         [dict(e, actor_nombre_historico=None, actor_username_historico=None) for e in historial])
        self.assertEqual(PresupuestoItem.objects.get(pk=item.pk).subtotal, Decimal('21250.00'))

    def test_upgrade_0008_preserva_precios_vinculados_incluido_cero(self):
        from decimal import Decimal
        from apps.comercial.models import PresupuestoItem, PresupuestoPrecioEvento
        from apps.comercial.tests.test_presupuesto_api import datos_item
        from apps.comercial.tests.test_025b import MaterialesPresupuesto025B

        # Crear antes del downgrade solo datos compatibles con 0008, sin fijaciones nuevas.
        fixture = MaterialesPresupuesto025B()
        fixture.setUpTestData()
        presupuesto = fixture.preparar()
        articulo = fixture.material()
        lineas = []
        for orden, precio in ((2, '0.00'), (3, '8500.00')):
            lineas.append(PresupuestoItem.objects.create(
                presupuesto=presupuesto, articulo=articulo, codigo_articulo=articulo.codigo,
                descripcion=articulo.nombre, cantidad=Decimal(datos_item()['cantidad']),
                unidad=articulo.unidad, precio_unitario=Decimal(precio), orden=orden,
            ).pk)
        executor = MigrationExecutor(connection)
        hojas = executor.loader.graph.leaf_nodes()
        anterior = [('comercial', '0008_merge_identidad_articulo')]
        try:
            executor.migrate(anterior)
            modelo = executor.loader.project_state(anterior).apps.get_model('comercial', 'PresupuestoItem')
            antes = list(modelo.objects.filter(pk__in=lineas).values())
        finally:
            MigrationExecutor(connection).migrate(hojas)
        self.assertEqual(list(PresupuestoItem.objects.filter(pk__in=lineas).values()), antes)
        self.assertEqual(list(PresupuestoItem.objects.filter(pk__in=lineas).values_list('precio_unitario', flat=True)),
                         [Decimal('0.00'), Decimal('8500.00')])
        self.assertFalse(PresupuestoPrecioEvento.objects.exists())
