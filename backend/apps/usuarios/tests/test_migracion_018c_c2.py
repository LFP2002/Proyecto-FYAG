from contextlib import contextmanager
from datetime import timedelta

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone


ANTES_C2 = "0008_estado_acceso_c1"
C2 = "0009_recuperacion_acceso_c2"
MODELOS_HISTORICOS = ("Usuario", "SeguridadCredencial", "EstadoAcceso", "EventoAcceso", "UsuarioEvento")


class MigracionC2Tests(TransactionTestCase):
    @contextmanager
    def esquema_historico(self):
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        try:
            yield latest
        finally:
            MigrationExecutor(connection).migrate(latest)
            self.assertEqual(MigrationExecutor(connection).migration_plan(latest), [])

    def destino(self, latest, version):
        return [(app, version if app == "usuarios" else name) for app, name in latest]

    def migrar(self, destino):
        executor = MigrationExecutor(connection)
        executor.migrate(destino)
        return executor.loader.project_state(destino).apps

    def historial(self, apps):
        return {name: list(apps.get_model("usuarios", name).objects.order_by("pk").values())
                for name in MODELOS_HISTORICOS}

    def sembrar_historico(self, apps):
        usuario = apps.get_model("usuarios", "Usuario")
        credencial = apps.get_model("usuarios", "SeguridadCredencial")
        acceso = apps.get_model("usuarios", "EstadoAcceso")
        evento = apps.get_model("usuarios", "UsuarioEvento")
        personal, con_evidencia, sin_evidencia = [
            usuario.objects.create(username=f"historica_{i}", email=f"historica_{i}@qa.test",
                                   rol="TECNICO", password="!inutilizable", sesion_version=7)
            for i in range(3)
        ]
        ahora = timezone.now()
        credencial.objects.filter(usuario_id__in=[con_evidencia.pk, sin_evidencia.pk]).update(
            estado="RECUPERACION", emitida_en=ahora, vence_en=ahora + timedelta(hours=1))
        acceso.objects.filter(usuario_id=personal.pk).update(
            estado="BLOQUEO_TEMPORAL", version=2, actualizado_en=ahora, ciclos_en=[ahora],
            bloqueo_inicio=ahora, bloqueado_hasta=ahora + timedelta(minutes=15))
        apps.get_model("usuarios", "EventoAcceso").objects.create(
            usuario=personal, tipo="BLOQUEO_TEMPORAL", actor_tipo="SISTEMA", version=2,
            cantidad_fallos=5, creado_en=ahora)
        evento.objects.create(usuario_objetivo=con_evidencia, actor=con_evidencia, tipo="CAMBIO_INICIAL")
        evento.objects.create(usuario_objetivo=sin_evidencia, actor=con_evidencia, tipo="REEMISION", motivo="Histórico QA")
        return con_evidencia.pk

    def assert_historial(self, esperado, actual):
        self.assertEqual(set(esperado), set(actual))
        for modelo in esperado:
            # No volcar hashes, desafíos ni snapshots en caso de error.
            self.assertTrue(esperado[modelo] == actual[modelo], f"Filas o columnas inesperadas en {modelo}")

    def test_0008_a_0009_y_reverse_sin_cambiar_estado_historico(self):
        with self.esquema_historico() as latest:
            anterior = self.destino(latest, ANTES_C2)
            apps = self.migrar(anterior)
            self.sembrar_historico(apps)
            esperado = self.historial(apps)

            apps = self.migrar(self.destino(latest, C2))
            self.assert_historial(esperado, self.historial(apps))
            self.assertFalse(apps.get_model("usuarios", "RecuperacionAcceso").objects.exists())

            apps = self.migrar(anterior)
            self.assert_historial(esperado, self.historial(apps))
            self.assertNotIn("usuarios_recuperacionacceso", connection.introspection.table_names())

    def test_0008_al_esquema_vigente_preserva_historico_y_aplica_campos_nuevos(self):
        with self.esquema_historico() as latest:
            apps = self.migrar(self.destino(latest, ANTES_C2))
            con_evidencia = self.sembrar_historico(apps)
            esperado = self.historial(apps)

            esperado["Usuario"] = [dict(row, correo_pendiente="", correo_verificado_en=None)
                                   for row in esperado["Usuario"]]
            esperado["SeguridadCredencial"] = [dict(row, personal_previa=row["usuario_id"] == con_evidencia)
                                               for row in esperado["SeguridadCredencial"]]
            esperado["UsuarioEvento"] = [dict(row, actor_nombre_historico=None, actor_username_historico=None)
                                         for row in esperado["UsuarioEvento"]]

            apps = self.migrar(latest)
            self.assert_historial(esperado, self.historial(apps))
            for modelo in ("RecuperacionAcceso", "DesafioCorreo", "DesafioRecuperacionCorreo",
                           "RecuperacionCorreoEvento", "RecuperacionTIEvento"):
                self.assertFalse(apps.get_model("usuarios", modelo).objects.exists(), modelo)
            instalacion = apps.get_model("usuarios", "InstalacionFYAG").objects.get(pk=1)
            self.assertIsNotNone(instalacion.inicializada_en)
            self.assertEqual((instalacion.clave_digest, instalacion.clave_vence_en), (None, None))
