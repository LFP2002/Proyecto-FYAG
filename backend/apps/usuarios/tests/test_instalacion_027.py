from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

from apps.usuarios.models import InstalacionFYAG, Usuario
from apps.usuarios.services_usuarios import ConflictoUsuario, aprovisionar_primera_ti


class InstalacionTests(TransactionTestCase):
    def test_alta_externa_y_borrado_posterior_no_reabren_bootstrap(self):
        Usuario.objects.bulk_create([Usuario(username='historico', email='historico@qa.test', rol='TECNICO')])
        self.assertIsNotNone(InstalacionFYAG.objects.get(pk=1).inicializada_en)
        Usuario.objects.filter(username='historico').delete()
        with self.assertRaises(ConflictoUsuario):
            aprovisionar_primera_ti({'email': 'primera@qa.test', 'username': 'primera', 'password': 'Clave-qa-sintetica-527!'})
        self.assertFalse(Usuario.objects.exists())

    def test_upgrade_desde_0011_no_modifica_cuentas(self):
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        previous = [(app, '0011_identidad_evento' if app == 'usuarios' else name) for app, name in latest]
        executor.migrate(previous)
        try:
            user = executor.loader.project_state(previous).apps.get_model('usuarios', 'Usuario')
            user.objects.create(username='hist', email='hist@qa.test', rol='BODEGUERO', is_active=False)
            before = list(user.objects.values())
            MigrationExecutor(connection).migrate(latest)
            self.assertTrue([dict(row, correo_verificado_en=None, correo_pendiente='') for row in before] == list(Usuario.objects.values()))
            self.assertIsNotNone(InstalacionFYAG.objects.get(pk=1).inicializada_en)
        finally:
            MigrationExecutor(connection).migrate(latest)
