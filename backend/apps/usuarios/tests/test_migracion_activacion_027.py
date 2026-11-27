from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class MigracionActivacionTests(TransactionTestCase):
    def test_0017_0018_reversible_sin_alterar_cuentas_ni_crear_autorizacion(self):
        executor = MigrationExecutor(connection)
        vigente = executor.loader.graph.leaf_nodes()
        anterior = [(app, '0017_recuperacion_ti_infraestructura' if app == 'usuarios' else nombre)
                    for app, nombre in vigente]
        tabla = 'usuarios_activacionbloqueos'
        try:
            executor.migrate(anterior)
            modelos = executor.loader.project_state(anterior).apps
            usuarios = modelos.get_model('usuarios', 'Usuario').objects
            usuario = usuarios.create(username='qa18', email='qa18@qa.test', rol='TECNICO')
            antes = usuarios.values().get(pk=usuario.pk)
            self.assertNotIn(tabla, connection.introspection.table_names())
            executor = MigrationExecutor(connection)
            executor.migrate(vigente)
            constancias = executor.loader.project_state(vigente).apps.get_model('usuarios', 'ActivacionBloqueos').objects
            self.assertFalse(constancias.exists())
            self.assertEqual(usuarios.values().get(pk=usuario.pk), antes)
            constancias.create(autorizacion='QA-0018', entrega_smtp='SMTP-QA', autorizacion_remitente='FROM-QA',
                              huella_configuracion='a' * 64)
            MigrationExecutor(connection).migrate(anterior)
            self.assertNotIn(tabla, connection.introspection.table_names())
            self.assertEqual(usuarios.values().get(pk=usuario.pk), antes)
            MigrationExecutor(connection).migrate(vigente)
            self.assertFalse(constancias.exists())
        finally:
            MigrationExecutor(connection).migrate(vigente)
