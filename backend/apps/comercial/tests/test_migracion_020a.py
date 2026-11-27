from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.exceptions import IrreversibleError
from django.test import TransactionTestCase


class Historia020AMigracionTests(TransactionTestCase):
    def test_reversion_con_datos_financieros_se_rechaza_sin_perder_filas(self):
        from apps.comercial.models import Cliente, Presupuesto
        from apps.usuarios.models import Usuario
        actor = Usuario.objects.create_user(username='finanzas_rollback', email='rollback@example.test', rol='ADMINISTRATIVO_FINANZAS')
        cliente = Cliente.objects.create(tipo_cliente='PERSONA', tipo_identificacion='SIN_IDENTIFICACION', nombre_legal='Cliente', correo='cliente@example.test')
        p = Presupuesto.objects.create(cliente=cliente, creado_por=actor, descripcion='Conservar')
        antes = Presupuesto.objects.values().get(pk=p.pk)
        hojas = MigrationExecutor(connection).loader.graph.leaf_nodes()
        try:
            with self.assertRaises(IrreversibleError):
                MigrationExecutor(connection).migrate([('comercial', '0005_remove_presupuesto_presupuesto_gerencia_coherente_and_more')])
        finally:
            MigrationExecutor(connection).migrate(hojas)
        self.assertEqual(Presupuesto.objects.values().get(pk=p.pk), antes)

    def test_backfill_conserva_cabeceras_items_y_eventos_exactos(self):
        anterior = ('comercial', '0005_remove_presupuesto_presupuesto_gerencia_coherente_and_more')
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
            actuales = executor.loader.project_state(hojas).apps
            Obra = actuales.get_model('obras', 'Obra')
            Categoria = actuales.get_model('obras', 'CategoriaServicio')
            actor = Usuario.objects.create(username='gerencia_historica', email='historia@example.test', rol='GERENCIA')
            cliente = Cliente.objects.create(tipo_cliente='PERSONA', tipo_identificacion='SIN_IDENTIFICACION', nombre_legal='Cliente histórico', correo='cliente@example.test')
            estados = ['BORRADOR', 'PENDIENTE_GERENCIA', 'APROBADO_GERENCIA', 'RECHAZADO_GERENCIA',
                       'ENVIADO_CLIENTE', 'APROBADO_CLIENTE', 'RECHAZADO_CLIENTE', 'ANULADO']
            for estado in estados:
                p = Presupuesto.objects.create(cliente=cliente, creado_por_id=actor.pk, descripcion=estado,
                                               requiere_aprobacion_gerencia=True, estado=estado)
                Item.objects.create(presupuesto=p, descripcion='Servicio histórico', cantidad='1.000', precio_unitario='2.00', unidad='unidad', orden=1)
                Evento.objects.create(presupuesto=p, registrado_por_id=actor.pk, estado_nuevo='BORRADOR')
                if estado != 'BORRADOR':
                    Evento.objects.create(presupuesto=p, registrado_por_id=actor.pk, estado_anterior='BORRADOR', estado_nuevo=estado, motivo='Historia exacta')
                if estado == 'APROBADO_CLIENTE':
                    categoria = Categoria.objects.create(nombre='Categoría histórica')
                    Obra.objects.create(presupuesto_id=p.pk, categoria_servicio=categoria, descripcion='Vínculo histórico', creado_por_id=actor.pk)
            cabeceras = list(Presupuesto.objects.order_by('pk').values())
            items = list(Item.objects.order_by('pk').values())
            eventos = list(Evento.objects.order_by('pk').values())
            obras = list(Obra.objects.order_by('pk').values())
        finally:
            MigrationExecutor(connection).migrate(hojas)
        from apps.comercial.models import Presupuesto, PresupuestoItem, PresupuestoEvento
        self.assertEqual(list(Presupuesto.objects.order_by('pk').values()), [dict(p, politica_aprobacion='GERENCIA_LEGADA') for p in cabeceras])
        self.assertEqual(list(PresupuestoItem.objects.order_by('pk').values()), [dict(i, articulo_id=None, codigo_articulo='') for i in items])
        self.assertEqual(list(PresupuestoEvento.objects.order_by('pk').values()),
                         [dict(e, actor_nombre_historico=None, actor_username_historico=None) for e in eventos])
        from apps.obras.models import Obra
        self.assertEqual(list(Obra.objects.order_by('pk').values()), obras)
