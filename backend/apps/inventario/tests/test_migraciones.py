from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class Migracion019ATests(TransactionTestCase):
    def test_upgrade_preserva_usuarios_y_no_inventa_stock(self):
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        previous = [(app, "0009_recuperacion_acceso_c2" if app == "usuarios" else name)
                    for app, name in latest if app != "inventario"] + [("inventario", None)]
        executor.migrate(previous)
        try:
            targets = [x for x in previous if x[1] is not None]
            apps = MigrationExecutor(connection).loader.project_state(targets).apps
            User = apps.get_model("usuarios", "Usuario")
            for i, role in enumerate(("GERENCIA", "ADMINISTRATIVO_FINANZAS", "SUPERVISOR_OBRAS", "TECNICO", "ADMINISTRADOR_TI")):
                User.objects.create(username=f"qa_pre019_{i}", email=f"qa_pre019_{i}@example.test", rol=role,
                                    password="!sintetica_inutilizable", sesion_version=7, is_active=i != 3)
            names = ("Usuario", "SeguridadCredencial", "EstadoAcceso", "EventoAcceso", "UsuarioEvento")
            before = {name: list(apps.get_model("usuarios", name).objects.order_by("pk").values()) for name in names}
            MigrationExecutor(connection).migrate(latest)
            apps = MigrationExecutor(connection).loader.project_state(latest).apps
            for name in names:
                self.assertEqual(list(apps.get_model("usuarios", name).objects.order_by("pk").values()), before[name])
            for name in ("ArticuloInventario", "ExistenciaInventario", "MovimientoInventario"):
                self.assertEqual(apps.get_model("inventario", name).objects.count(), 0)
            User = apps.get_model("usuarios", "Usuario")
            user = User.objects.create(username="qa_nueva_bodega", email="qa_nueva_bodega@example.test", rol="BODEGUERO", password="!sintetica")
            self.assertEqual(user.rol, "BODEGUERO")
            self.assertTrue(apps.get_model("usuarios", "SeguridadCredencial").objects.filter(usuario_id=user.pk).exists())
            self.assertTrue(apps.get_model("usuarios", "EstadoAcceso").objects.filter(usuario_id=user.pk).exists())
        finally:
            MigrationExecutor(connection).migrate(latest)
