from django.contrib.auth.hashers import make_password
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class MigracionC1Tests(TransactionTestCase):
    def test_0007_a_0008_preserva_historicos_y_no_repara_credenciales(self):
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        previous = [(app, "0007_estado_seguridad_al_insertar" if app == "usuarios" else name) for app, name in latest]
        executor.migrate(previous)
        try:
            apps = executor.loader.project_state(previous).apps
            User = apps.get_model("usuarios", "Usuario")
            Credential = apps.get_model("usuarios", "SeguridadCredencial")
            Event = apps.get_model("usuarios", "UsuarioEvento")
            for index, role in enumerate(("TECNICO", "GERENCIA")):
                user = User.objects.create(username=f"qa_hist_c1_{index}", email=f"qa_hist_c1_{index}@example.test",
                                           password=make_password(None), rol=role, sesion_version=7, is_active=bool(index))
                Event.objects.create(usuario_objetivo=user, actor=user, tipo="CREACION")
            Credential.objects.filter(usuario_id=user.pk).delete()
            before = (list(User.objects.order_by("pk").values()), list(Credential.objects.values()), list(Event.objects.values()))
            executor = MigrationExecutor(connection)
            executor.migrate(latest)
            apps = executor.loader.project_state(latest).apps
            after = tuple(list(apps.get_model("usuarios", name).objects.order_by("pk").values()) for name in ("Usuario", "SeguridadCredencial", "UsuarioEvento"))
            expected = ([dict(row, correo_verificado_en=None, correo_pendiente='') for row in before[0]], before[1],
                        [{**event, "actor_nombre_historico": None, "actor_username_historico": None} for event in before[2]])
            self.assertTrue(expected == after)  # No imprimir hashes ni snapshots.
            State = apps.get_model("usuarios", "EstadoAcceso")
            self.assertEqual(State.objects.count(), 2)
            self.assertEqual(set(State.objects.values_list("estado", flat=True)), {"NORMAL"})
            self.assertFalse(apps.get_model("usuarios", "SeguridadCredencial").objects.filter(usuario_id=user.pk).exists())
            NewUser = apps.get_model("usuarios", "Usuario")
            new = NewUser.objects.create(username="qa_post_c1", email="qa_post_c1@example.test", rol="TECNICO")
            self.assertEqual(State.objects.get(usuario_id=new.pk).estado, "NORMAL")
        finally:
            MigrationExecutor(connection).migrate(latest)
