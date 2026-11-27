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
            # La migración abarca también las SPEC posteriores a 019A. Exigir
            # igualdad de todas las columnas históricas y los defaults nuevos,
            # sin proyectar solo un subconjunto que oculte cambios de esquema.
            before["Usuario"] = [dict(row, correo_pendiente="", correo_verificado_en=None)
                                 for row in before["Usuario"]]
            # La fixture solo contiene credenciales originales sin evidencia
            # de recuperación personal previa (migración 0016).
            before["SeguridadCredencial"] = [dict(row, personal_previa=False)
                                             for row in before["SeguridadCredencial"]]
            before["UsuarioEvento"] = [dict(row, actor_nombre_historico=None, actor_username_historico=None)
                                       for row in before["UsuarioEvento"]]
            MigrationExecutor(connection).migrate(latest)
            apps = MigrationExecutor(connection).loader.project_state(latest).apps
            for name in names:
                actual = list(apps.get_model("usuarios", name).objects.order_by("pk").values())
                self.assertTrue(actual == before[name], f"Filas o columnas inesperadas en {name}")
            instalacion = apps.get_model("usuarios", "InstalacionFYAG").objects.get(pk=1)
            self.assertIsNotNone(instalacion.inicializada_en)
            self.assertEqual((instalacion.clave_digest, instalacion.clave_vence_en), (None, None))
            for name in ("DesafioCorreo", "DesafioRecuperacionCorreo", "RecuperacionCorreoEvento",
                         "RecuperacionTIEvento", "ActivacionBloqueos"):
                self.assertFalse(apps.get_model("usuarios", name).objects.exists(), name)
            for name in ("ArticuloInventario", "ExistenciaInventario", "MovimientoInventario"):
                self.assertEqual(apps.get_model("inventario", name).objects.count(), 0)
            User = apps.get_model("usuarios", "Usuario")
            user = User.objects.create(username="qa_nueva_bodega", email="qa_nueva_bodega@example.test", rol="BODEGUERO", password="!sintetica")
            self.assertEqual(user.rol, "BODEGUERO")
            self.assertTrue(apps.get_model("usuarios", "SeguridadCredencial").objects.filter(usuario_id=user.pk).exists())
            self.assertTrue(apps.get_model("usuarios", "EstadoAcceso").objects.filter(usuario_id=user.pk).exists())
        finally:
            MigrationExecutor(connection).migrate(latest)
