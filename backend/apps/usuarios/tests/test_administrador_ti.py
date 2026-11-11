from io import StringIO
from unittest.mock import patch

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase, override_settings
from rest_framework.test import APITestCase
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.obras.tests.test_servicios_004a import BaseObras
from apps.usuarios import services_usuarios as services
from apps.usuarios.models import Usuario, UsuarioEvento
from apps.usuarios.tokens import AccessToken, RefreshToken
from .test_administracion import AdminBase, PASSWORD
from . import test_concurrencia_006 as concurrencia


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class AdministradorTITests(AdminBase, APITestCase):
    def test_ti_no_tiene_acceso_negocio_ni_con_flags(self):
        self.manager.is_staff = self.manager.is_superuser = True
        self.manager.save()
        self.authenticate()
        for path in ["/api/clientes/", "/api/presupuestos/", "/api/obras/", "/api/obras/mis-obras/", "/api/categorias-servicio/", "/api/finanzas/documentos/", "/api/finanzas/obras-elegibles/", "/api/finanzas/cobranzas/", "/api/finanzas/cobranzas/resumen/"]:
            for method in ["get", "post", "options"]:
                response = getattr(self.client, method)(path, {}, format="json")
                self.assertEqual(response.status_code, 403, (method, path, response.data))

    def test_gerencia_conserva_negocio_sin_administrar_cuentas(self):
        gerencia = self.users[Usuario.Rol.GERENCIA]
        token = AccessToken.for_user(gerencia)
        token["rol"] = "ADMINISTRADOR_TI"
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        for path in ["/api/clientes/", "/api/presupuestos/", "/api/obras/", "/api/finanzas/documentos/"]:
            self.assertEqual(self.client.get(path).status_code, 200, path)
        for path in ["/api/usuarios/", self.url, self.url + "historial/"]:
            self.assertEqual(self.client.get(path).status_code, 403)
            self.assertEqual(self.client.options(path).status_code, 403)
        with self.assertRaises(PermissionDenied) as caught:
            services.crear_usuario(self.new_data(), gerencia)
        self.assertEqual(caught.exception.status_code, 403)

    def test_ultima_gerencia_independiente_de_dos_ti(self):
        gerencia = self.users[Usuario.Rol.GERENCIA]
        for action, data in [("desactivar", {"motivo": "Cambio"}), ("cambiar-rol", {"motivo": "Cambio", "rol": "ADMINISTRADOR_TI"})]:
            result = self.client.post(f"/api/usuarios/{gerencia.pk}/{action}/", data, format="json")
            self.assertEqual(result.status_code, 409, result.data)
            self.assertEqual(result.data["code"], "ultima_gerencia")
        Usuario.objects.create_user(username="segunda_g", email="segunda_g@example.test", rol="GERENCIA")
        result = self.client.post(f"/api/usuarios/{gerencia.pk}/desactivar/", {"motivo": "Hay relevo"}, format="json")
        self.assertEqual(result.status_code, 200, result.data)
        self.assertEqual(Usuario.objects.filter(rol="GERENCIA", is_active=True).count(), 1)
        self.assertEqual(Usuario.objects.filter(rol="ADMINISTRADOR_TI", is_active=True).count(), 2)

    def test_cambios_hacia_y_desde_ti_revocan_access_y_refresh(self):
        target = self.users[Usuario.Rol.ADMINISTRATIVO_FINANZAS]
        for role in ["ADMINISTRADOR_TI", "ADMINISTRATIVO_FINANZAS"]:
            target.refresh_from_db()
            access, refresh = AccessToken.for_user(target), RefreshToken.for_user(target)
            services.cambiar_rol(target, {"rol": role, "motivo": "Cambio autorizado de función"}, self.manager)
            self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
            self.assertEqual(self.client.get("/api/auth/me/").status_code, 401)
            self.client.cookies[settings.JWT_REFRESH_COOKIE_NAME] = str(refresh)
            self.assertEqual(self.client.post("/api/auth/refresh/").status_code, 401)
            target.refresh_from_db()
            self.authenticate(target)
            self.assertEqual(self.client.get("/api/usuarios/").status_code, 200 if role == "ADMINISTRADOR_TI" else 403)
            self.assertEqual(self.client.get("/api/clientes/").status_code, 403 if role == "ADMINISTRADOR_TI" else 200)
        self.assertEqual(target.eventos_administrativos.count(), 2)

    def test_ultimo_ti_inactivo_no_es_relevo_y_gerencia_no_lo_es(self):
        self.other_manager.is_active = False
        self.other_manager.save()
        response = self.client.post(f"/api/usuarios/{self.manager.pk}/desactivar/", {"motivo": "Sin relevo TI"}, format="json")
        self.assertEqual(response.data["code"], "ultima_ti")
        self.assertEqual(Usuario.objects.filter(rol="GERENCIA", is_active=True).count(), 1)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class AprovisionamientoTests(TestCase):
    def data(self, **changes):
        return {"email": " TI@EXAMPLE.TEST ", "username": "administracion_ti", "password": PASSWORD, **changes}

    def test_primera_ti_activa_hash_auditoria_sin_flags(self):
        obj = services.aprovisionar_primera_ti(self.data())
        self.assertTrue(obj.is_active)
        self.assertEqual(obj.rol, "ADMINISTRADOR_TI")
        self.assertEqual(obj.email, "ti@example.test")
        self.assertTrue(obj.check_password(PASSWORD))
        self.assertFalse(obj.is_staff or obj.is_superuser)
        event = obj.eventos_administrativos.get()
        self.assertEqual(event.actor_id, obj.pk)
        self.assertEqual(event.tipo, "CREACION")
        self.assertTrue(event.datos_nuevos["is_active"])
        self.assertNotIn(PASSWORD, str(event.datos_nuevos))
        with self.assertRaises(services.ConflictoUsuario):
            services.aprovisionar_primera_ti(self.data(email="otra@example.test", username="otra"))
        obj.is_active = False
        obj.save()
        with self.assertRaises(services.ConflictoUsuario):
            services.aprovisionar_primera_ti(self.data(email="otra@example.test", username="otra"))
        self.assertEqual(Usuario.objects.count(), 1)

    def test_validadores_rollback_y_no_promover_cuenta_existente(self):
        gerencia = Usuario.objects.create_user(username="g", email="g@example.test", rol="GERENCIA")
        with self.assertRaises(ValidationError):
            services.aprovisionar_primera_ti(self.data(password="123"))
        with self.assertRaises(ValidationError):
            services.aprovisionar_primera_ti(self.data(email=gerencia.email))
        with patch("apps.usuarios.services_usuarios._event", side_effect=RuntimeError("controlado")):
            with self.assertRaises(RuntimeError):
                services.aprovisionar_primera_ti(self.data())
        self.assertEqual(Usuario.objects.count(), 1)
        gerencia.refresh_from_db()
        self.assertEqual(gerencia.rol, "GERENCIA")
        self.assertFalse(UsuarioEvento.objects.exists())

    def test_comando_interactivo_sin_secretos_y_no_repetible(self):
        output = StringIO()
        with patch("apps.usuarios.management.commands.crear_primera_ti.sys.stdin.isatty", return_value=True), patch("apps.usuarios.management.commands.crear_primera_ti.getpass", return_value=PASSWORD):
            call_command("crear_primera_ti", email="ti@example.test", username="ti", stdout=output)
            with self.assertRaises(CommandError):
                call_command("crear_primera_ti", email="otra@example.test", username="otra", stdout=output)
        self.assertNotIn(PASSWORD, output.getvalue())
        self.assertNotIn(Usuario.objects.get().password, output.getvalue())

    def test_comando_rechaza_no_tty_confirmacion_y_fallback_con_eco(self):
        with patch("apps.usuarios.management.commands.crear_primera_ti.sys.stdin.isatty", return_value=False):
            with self.assertRaises(CommandError):
                call_command("crear_primera_ti", email="ti@example.test", username="ti")
        from getpass import GetPassWarning
        for values in [[PASSWORD, "distinta"], GetPassWarning("sin terminal segura")]:
            with patch("apps.usuarios.management.commands.crear_primera_ti.sys.stdin.isatty", return_value=True), patch("apps.usuarios.management.commands.crear_primera_ti.getpass", side_effect=values):
                with self.assertRaises(CommandError):
                    call_command("crear_primera_ti", email="ti@example.test", username="ti")
        self.assertFalse(Usuario.objects.exists())

    def test_comando_no_imprime_detalles_sql_que_podrian_contener_hashes(self):
        with patch("apps.usuarios.management.commands.crear_primera_ti.sys.stdin.isatty", return_value=True), patch("apps.usuarios.management.commands.crear_primera_ti.getpass", return_value=PASSWORD), patch("apps.usuarios.management.commands.crear_primera_ti.aprovisionar_primera_ti", side_effect=IntegrityError("detalle_sql_sensible")):
            with self.assertRaises(CommandError) as caught:
                call_command("crear_primera_ti", email="ti@example.test", username="ti")
        self.assertNotIn("detalle_sql_sensible", str(caught.exception))
        self.assertNotIn(PASSWORD, str(caught.exception))
        self.assertFalse(Usuario.objects.exists())


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ProteccionesConcurrenciaTests(BaseObras, TransactionTestCase):
    race = concurrencia.ConcurrenciaTests.race

    def setUp(self):
        self.setUpTestData()

    def test_dos_ti_no_desactivan_dos_gerencias(self):
        ti1 = Usuario.objects.create_user(username="ti1", email="ti1@example.test", rol="ADMINISTRADOR_TI")
        ti2 = Usuario.objects.create_user(username="ti2", email="ti2@example.test", rol="ADMINISTRADOR_TI")
        g2 = Usuario.objects.create_user(username="g2", email="g2@example.test", rol="GERENCIA")
        one, two = self.race(lambda: services.actividad_usuario(self.gerencia, {"motivo": "Relevo"}, ti1, activo=False),
                             lambda: services.actividad_usuario(g2, {"motivo": "Relevo"}, ti2, activo=False))
        self.assertIsInstance(one, Usuario)
        self.assertEqual(two.detail["code"], "ultima_gerencia")
        self.assertEqual(Usuario.objects.filter(rol="GERENCIA", is_active=True).count(), 1)

    def test_dos_ti_no_degradan_dos_gerencias(self):
        ti = Usuario.objects.create_user(username="ti", email="ti@example.test", rol="ADMINISTRADOR_TI")
        g2 = Usuario.objects.create_user(username="g2", email="g2@example.test", rol="GERENCIA")
        one, two = self.race(lambda: services.cambiar_rol(self.gerencia, {"motivo": "Relevo", "rol": "SUPERVISOR_OBRAS"}, ti),
                             lambda: services.cambiar_rol(g2, {"motivo": "Relevo", "rol": "SUPERVISOR_OBRAS"}, ti))
        self.assertIsInstance(one, Usuario)
        self.assertEqual(two.detail["code"], "ultima_gerencia")

    def test_comandos_concurrentes_solo_crean_una_primera_ti(self):
        def run(suffix):
            try:
                call_command("crear_primera_ti", email=f"ti{suffix}@example.test", username=f"ti{suffix}", stdout=StringIO())
            except CommandError as exc:
                return exc
            return Usuario.objects.get(username=f"ti{suffix}")
        with patch("apps.usuarios.management.commands.crear_primera_ti.sys.stdin.isatty", return_value=True), patch("apps.usuarios.management.commands.crear_primera_ti.getpass", return_value=PASSWORD):
            one, two = self.race(lambda: run("1"), lambda: run("2"))
        self.assertIsInstance(one, Usuario)
        self.assertIsInstance(two, CommandError)
        self.assertEqual(Usuario.objects.filter(rol="ADMINISTRADOR_TI").count(), 1)
        self.assertEqual(UsuarioEvento.objects.count(), 1)


class MigracionTITests(BaseObras, TransactionTestCase):
    def test_0004_0005_conserva_usuarios_roles_hashes_y_asociaciones(self):
        self.setUpTestData()
        obra = self.crear(tecnico_responsable=self.tecnico.pk, motivo="Histórico")
        before = list(Usuario.objects.order_by("pk").values())
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        previous = [(app, "0004_usuarios_roles_sesiones_auditoria" if app == "usuarios" else name) for app, name in latest]
        executor.migrate(previous)
        try:
            old = executor.loader.project_state(previous).apps
            self.assertEqual(list(old.get_model("usuarios", "Usuario").objects.order_by("pk").values()), before)
            executor = MigrationExecutor(connection)
            executor.migrate(latest)
            self.assertEqual(list(Usuario.objects.order_by("pk").values()), before)
            obra.refresh_from_db()
            self.assertEqual(obra.tecnico_responsable_id, self.tecnico.pk)
            self.assertFalse(Usuario.objects.filter(rol="ADMINISTRADOR_TI").exists())
            Usuario.objects.create_user(username="ti", email="ti@example.test", rol="ADMINISTRADOR_TI")
            with self.assertRaises(IntegrityError), transaction.atomic():
                Usuario.objects.filter(pk=self.tecnico.pk).update(rol="OTRO")
        finally:
            MigrationExecutor(connection).migrate(latest)


@override_settings(CORS_ALLOWED_ORIGINS=["https://app.example.test"], CSRF_TRUSTED_ORIGINS=["https://app.example.test"])
class CorsSeparacionTests(TestCase):
    def test_origen_permitido_credenciales_y_desconocido_cerrado(self):
        response = self.client.options("/api/usuarios/", HTTP_ORIGIN="https://app.example.test", HTTP_ACCESS_CONTROL_REQUEST_METHOD="GET", HTTP_ACCESS_CONTROL_REQUEST_HEADERS="authorization")
        self.assertEqual(response["access-control-allow-origin"], "https://app.example.test")
        self.assertEqual(response["access-control-allow-credentials"], "true")
        rejected = self.client.options("/api/usuarios/", HTTP_ORIGIN="https://evil.example", HTTP_ACCESS_CONTROL_REQUEST_METHOD="GET")
        self.assertNotIn("access-control-allow-origin", rejected)
