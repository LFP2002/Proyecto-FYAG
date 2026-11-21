from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class MigracionC2Tests(TransactionTestCase):
    def test_0008_a_0009_y_reverse_sin_cambiar_estado_historico(self):
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        previous = [(app, "0008_estado_acceso_c1" if app == "usuarios" else name) for app, name in latest]
        executor.migrate(previous)
        try:
            apps = executor.loader.project_state(previous).apps
            User = apps.get_model("usuarios", "Usuario")
            User.objects.create(username="qa_c2_historica", email="qa_c2_historica@example.test", rol="TECNICO", password="!inutilizable")
            names = ("Usuario", "SeguridadCredencial", "EstadoAcceso", "EventoAcceso", "UsuarioEvento")
            before = [list(apps.get_model("usuarios", name).objects.values()) for name in names]
            executor = MigrationExecutor(connection)
            executor.migrate(latest)
            apps = executor.loader.project_state(latest).apps
            self.assertTrue(before == [list(apps.get_model("usuarios", name).objects.values()) for name in names])
            self.assertFalse(apps.get_model("usuarios", "RecuperacionAcceso").objects.exists())
            executor = MigrationExecutor(connection)
            executor.migrate(previous)
            apps = executor.loader.project_state(previous).apps
            self.assertTrue(before == [list(apps.get_model("usuarios", name).objects.values()) for name in names])
        finally:
            MigrationExecutor(connection).migrate(latest)
