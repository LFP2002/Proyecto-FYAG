from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

from apps.obras.tests.test_servicios_004a import BaseObras


class MigracionUsuariosTests(BaseObras, TransactionTestCase):
    def test_upgrade_preserva_identidad_hash_y_asociaciones(self):
        self.setUpTestData()
        obra = self.crear(tecnico_responsable=self.tecnico.pk, motivo="Histórico")
        ids = (obra.pk, self.tecnico.pk, self.presupuesto.pk)
        password = self.tecnico.password
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        previous = [(app, "0003_usuario_usuarios_email_no_vacio_and_more" if app == "usuarios" else name) for app, name in latest]
        executor.migrate(previous)
        try:
            old = executor.loader.project_state(previous).apps
            User = old.get_model("usuarios", "Usuario")
            legacy = User.objects.create(username="historico", email="historico@example.test", rol="TECNICO", password=password)
            legacy_pk = legacy.pk
            executor = MigrationExecutor(connection)
            executor.migrate(latest)
            apps = executor.loader.project_state(latest).apps
            User = apps.get_model("usuarios", "Usuario")
            Obra = apps.get_model("obras", "Obra")
            self.assertEqual(User.objects.get(pk=legacy_pk).sesion_version, 1)
            user = User.objects.get(pk=ids[1])
            self.assertEqual(user.password, password)
            self.assertEqual(user.sesion_version, 1)
            saved = Obra.objects.get(pk=ids[0])
            self.assertEqual(saved.tecnico_responsable_id, ids[1])
            self.assertEqual(saved.presupuesto_id, ids[2])
            self.assertEqual(apps.get_model("usuarios", "UsuarioEvento").objects.count(), 0)
        finally:
            MigrationExecutor(connection).migrate(latest)
