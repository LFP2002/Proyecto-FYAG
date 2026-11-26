"""Ascenso 0005 -> 0006 solo en BD de test, nunca en datos de desarrollo."""
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class MigracionCredencialesTests(TransactionTestCase):
    def test_conserva_hashes_versiones_roles_actividad_e_historial(self):
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        previous = [(app, "0005_administrador_ti" if app == "usuarios" else name) for app, name in latest]
        executor.migrate(previous)
        try:
            apps = executor.loader.project_state(previous).apps
            User = apps.get_model("usuarios", "Usuario")
            Event = apps.get_model("usuarios", "UsuarioEvento")
            from django.contrib.auth.hashers import make_password
            import secrets
            # Valor sintético generado solo en memoria; jamás documentar ni imprimir.
            password_hash = make_password(secrets.token_urlsafe(32))
            active = User.objects.create(email="historica@example.test", username="historica", rol="ADMINISTRADOR_TI", password=password_hash, sesion_version=9)
            inactive = User.objects.create(email="inactiva@example.test", username="inactiva", rol="GERENCIA", password=password_hash, is_active=False)
            Event.objects.create(usuario_objetivo=active, actor=active, tipo="ESTABLECER_CLAVE")
            before = list(User.objects.order_by("pk").values())
            events = list(Event.objects.values())
            executor = MigrationExecutor(connection)
            executor.migrate(latest)
            apps = executor.loader.project_state(latest).apps
            self.assertTrue(list(apps.get_model("usuarios", "Usuario").objects.order_by("pk").values()) == before)
            # 0011 agrega atribución histórica nula a las filas anteriores.
            expected_events = [{**event, "actor_nombre_historico": None, "actor_username_historico": None} for event in events]
            self.assertEqual(list(apps.get_model("usuarios", "UsuarioEvento").objects.values()), expected_events)
            states = apps.get_model("usuarios", "SeguridadCredencial").objects
            self.assertEqual(states.count(), 2)
            for pk in [active.pk, inactive.pk]:
                state = states.get(usuario_id=pk)
                self.assertEqual(state.estado, "PERSONAL")
                self.assertIsNone(state.vence_en)
                self.assertIsNone(state.desafio_digest)
        finally:
            MigrationExecutor(connection).migrate(latest)

    def test_0007_preserva_filas_y_no_repara_ausencias_previas(self):
        import secrets
        from datetime import timedelta
        from django.contrib.auth.hashers import make_password
        from django.utils import timezone
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        previous = [(app, "0006_seguridad_credenciales" if app == "usuarios" else name) for app, name in latest]
        executor.migrate(previous)
        try:
            apps = executor.loader.project_state(previous).apps
            User = apps.get_model("usuarios", "Usuario")
            State = apps.get_model("usuarios", "SeguridadCredencial")
            Event = apps.get_model("usuarios", "UsuarioEvento")
            hashed = make_password(secrets.token_urlsafe(32))
            temporary = User.objects.create(email="qa_temporal@example.test", username="qa_temporal", rol="TECNICO", password=hashed, sesion_version=8)
            absent = User.objects.create(email="qa_ausente@example.test", username="qa_ausente", rol="GERENCIA", password=hashed)
            now = timezone.now()
            State.objects.create(usuario_id=temporary.pk, estado="INICIAL", emitida_en=now, vence_en=now + timedelta(days=1))
            Event.objects.create(usuario_objetivo=temporary, actor=temporary, tipo="CREACION_CREDENCIAL_TEMPORAL")
            before = (list(User.objects.order_by("pk").values()), list(State.objects.values()), list(Event.objects.values()))
            executor = MigrationExecutor(connection)
            executor.migrate(latest)
            apps = executor.loader.project_state(latest).apps
            User = apps.get_model("usuarios", "Usuario")
            State = apps.get_model("usuarios", "SeguridadCredencial")
            Event = apps.get_model("usuarios", "UsuarioEvento")
            after = (list(User.objects.order_by("pk").values()), list(State.objects.values()), list(Event.objects.values()))
            expected = (*before[:2], [{**event, "actor_nombre_historico": None, "actor_username_historico": None} for event in before[2]])
            self.assertTrue(after == expected)
            self.assertFalse(State.objects.filter(usuario_id=absent.pk).exists())
            new = User.objects.create(email="qa_nueva@example.test", username="qa_nueva", rol="TECNICO", password=hashed)
            self.assertEqual(State.objects.get(usuario_id=new.pk).estado, "PERSONAL")
        finally:
            MigrationExecutor(connection).migrate(latest)
