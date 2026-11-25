from django.db import connection, IntegrityError, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

class AprobacionObligatoriaMigracionTests(TransactionTestCase):
    def test_normaliza_datos_historicos_sin_perder_contenido(self):
        anterior = ('comercial', '0004_presupuesto_presupuestoevento_presupuestoitem_and_more')
        executor = MigrationExecutor(connection)
        migraciones_originales = executor.loader.graph.leaf_nodes()
        executor.migrate([anterior])
        try:
            apps = executor.loader.project_state([anterior]).apps
            Presupuesto = apps.get_model('comercial', 'Presupuesto')
            Usuario = executor.loader.project_state(migraciones_originales).apps.get_model('usuarios', 'Usuario')
            usuario = Usuario.objects.create(username='migracion', email='migracion@example.test', rol='ADMINISTRATIVO_FINANZAS')
            Cliente = apps.get_model('comercial', 'Cliente')
            cliente = Cliente.objects.create(tipo_cliente='PERSONA', tipo_identificacion='SIN_IDENTIFICACION', nombre_legal='Cliente', correo='cliente@example.test')
            presupuesto = Presupuesto.objects.create(cliente=cliente, creado_por_id=usuario.pk, descripcion='Histórico', requiere_aprobacion_gerencia=False)
            cabecera = Presupuesto.objects.values().get(pk=presupuesto.pk)
            Item = apps.get_model('comercial', 'PresupuestoItem')
            Evento = apps.get_model('comercial', 'PresupuestoEvento')
            Item.objects.create(presupuesto=presupuesto, descripcion='Servicio', cantidad='1.000', unidad='unidad', precio_unitario='10.00', orden=1)
            Evento.objects.create(presupuesto=presupuesto, registrado_por_id=usuario.pk, estado_nuevo='BORRADOR')
            items = list(Item.objects.values())
            eventos = list(Evento.objects.values())
        finally:
            MigrationExecutor(connection).migrate(migraciones_originales)
        cabecera['requiere_aprobacion_gerencia'] = True
        self.assertEqual(Presupuesto.objects.values().get(pk=presupuesto.pk), cabecera)
        self.assertEqual(list(Item.objects.values()), items)
        from apps.comercial.models import PresupuestoItem
        self.assertTrue(all(x.articulo_id is None and x.codigo_articulo == '' for x in PresupuestoItem.objects.all()))
        self.assertEqual(list(Evento.objects.values()), eventos)
        with self.assertRaises(IntegrityError) as error:
            with transaction.atomic():
                Presupuesto.objects.filter(pk=presupuesto.pk).update(
                    requiere_aprobacion_gerencia=False
                )
        self.assertEqual(error.exception.__cause__.diag.constraint_name,
                         'presupuesto_politica_coherente')
