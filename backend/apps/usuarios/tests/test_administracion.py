from unittest.mock import patch

from django.conf import settings

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.core.exceptions import ValidationError as DjangoValidationError
from django.test import override_settings
from rest_framework.test import APITestCase
from rest_framework.exceptions import ValidationError

from apps.usuarios import services_usuarios as services
from apps.usuarios.models import UsuarioEvento
from apps.usuarios.serializers_usuarios import UsuarioEventoSerializer
from apps.usuarios.tokens import AccessToken, RefreshToken

Usuario = get_user_model()
PASSWORD = "Clave-Inicial-9X!"
NEW_PASSWORD = "Otra-Clave-Segura-8Y!"


class AdminBase:
    @classmethod
    def setUpTestData(cls):
        cls.users = {role: Usuario.objects.create_user(username=f"cuenta_{index}", email=f"cuenta{index}@example.test", password=PASSWORD, rol=role)
                     for index, role in enumerate(Usuario.Rol.values)}
        cls.manager = cls.users[Usuario.Rol.ADMINISTRADOR_TI]
        cls.other_manager = Usuario.objects.create_user(username="otra_ti", email="otra@example.test", password=PASSWORD, rol=Usuario.Rol.ADMINISTRADOR_TI)
        cls.target = cls.users[Usuario.Rol.TECNICO]

    def authenticate(self, user=None):
        user = user or self.manager
        user.refresh_from_db()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(user)}")

    def setUp(self):
        cache.clear()
        self.authenticate()
        self.url = f"/api/usuarios/{self.target.pk}/"

    def new_data(self, **changes):
        return {"email": " NUEVA@EXAMPLE.TEST ", "username": "alias_nuevo", "rol": Usuario.Rol.TECNICO, "password": PASSWORD, **changes}


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class AdministracionAPITests(AdminBase, APITestCase):
    def test_alta_inactiva_normalizada_hash_y_activacion_explicita(self):
        result = self.client.post("/api/usuarios/", self.new_data(), format="json")
        self.assertEqual(result.status_code, 201, result.data)
        user = Usuario.objects.get(pk=result.data["id"])
        self.assertFalse(user.is_active)
        self.assertEqual(user.email, "nueva@example.test")
        self.assertTrue(user.check_password(PASSWORD))
        self.assertNotEqual(user.password, PASSWORD)
        self.assertEqual(user.sesion_version, 1)
        self.assertEqual(set(result.data), {"id", "username", "email", "first_name", "last_name", "rol", "is_active", "date_joined"})
        self.assertEqual(user.eventos_administrativos.get().tipo, "CREACION")
        login = self.client.post("/api/auth/login/", {"email": user.email, "password": PASSWORD}, format="json")
        self.assertEqual(login.status_code, 401)
        active = self.client.post(f"/api/usuarios/{user.pk}/activar/", {"motivo": "Cuenta preparada"}, format="json")
        self.assertEqual(active.status_code, 200, active.data)
        self.assertTrue(active.data["is_active"])
        self.assertEqual(self.client.post("/api/auth/login/", {"email": user.email, "password": PASSWORD}, format="json").status_code, 200)

    def test_alta_cinco_roles_sin_privilegios_django(self):
        for index, role in enumerate(Usuario.Rol.values):
            result = self.client.post("/api/usuarios/", self.new_data(email=f"alta{index}@example.test", username=f"alta{index}", rol=role), format="json")
            self.assertEqual(result.status_code, 201, result.data)
            user = Usuario.objects.get(pk=result.data["id"])
            self.assertFalse(user.is_active or user.is_staff or user.is_superuser)

    def test_creacion_estricta_password_validadores_y_tipos(self):
        for field, value in [("rol", "ADMIN"), ("email", 3), ("username", True), ("first_name", []), ("password", 123), ("password", "123"), ("password", "12345678"), ("is_active", True), ("is_staff", True), ("is_superuser", True), ("groups", []), ("user_permissions", []), ("sesion_version", 9), ("id", 22), ("otro", "x")]:
            with self.subTest(field=field, value=value):
                result = self.client.post("/api/usuarios/", self.new_data(**{field: value}), format="json")
                self.assertEqual(result.status_code, 400, result.data)
        self.assertEqual(UsuarioEvento.objects.count(), 0)

    def test_duplicados_email_username_y_alias_invalido(self):
        for changes in [{"email": self.manager.email.upper()}, {"username": self.manager.username}, {"username": "alias con espacios"}, {"email": "correo-invalido"}]:
            result = self.client.post("/api/usuarios/", self.new_data(**changes), format="json")
            self.assertEqual(result.status_code, 400, result.data)

    def test_lista_25_filtros_estrictos_y_orden_id(self):
        for index in range(26):
            Usuario.objects.create_user(username=f"lista{index}", email=f"lista{index}@example.test", rol=Usuario.Rol.TECNICO, is_active=False)
        result = self.client.get("/api/usuarios/")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(len(result.data["results"]), 25)
        self.assertEqual(result.data["count"], 32)
        self.assertEqual([user["id"] for user in result.data["results"]], sorted(user["id"] for user in result.data["results"]))
        self.assertEqual(len(self.client.get("/api/usuarios/?page=2").data["results"]), 7)
        result = self.client.get("/api/usuarios/?rol=TECNICO&activo=false")
        self.assertEqual(result.data["count"], 26)
        for query in ["rol=admin", "activo=True", "activo=1", "rol=TECNICO&rol=GERENCIA", "page=1&page=2", "email=x", "ordering=email", "activo="]:
            self.assertEqual(self.client.get("/api/usuarios/?" + query).status_code, 400, query)
        self.assertEqual(self.client.get("/api/usuarios/?page=999").status_code, 404)

    def test_roles_no_ti_denegados_antes_de_revelar_cuentas(self):
        for role in [Usuario.Rol.GERENCIA, Usuario.Rol.ADMINISTRATIVO_FINANZAS, Usuario.Rol.SUPERVISOR_OBRAS, Usuario.Rol.TECNICO]:
            user = self.users[role]
            user.is_superuser = True
            user.is_staff = True
            user.save()
            self.authenticate(user)
            for path, method in [("/api/usuarios/", "get"), ("/api/usuarios/", "post"), (self.url, "get"), (self.url, "patch"), (self.url + "activar/", "post"), (self.url + "desactivar/", "post"), (self.url + "cambiar-rol/", "post"), (self.url + "establecer-clave/", "post"), (self.url + "historial/", "get"), ("/api/usuarios/999999/", "get")]:
                result = getattr(self.client, method)(path, {}, format="json")
                self.assertEqual(result.status_code, 403, (role, path, result.data))

    def test_anonimo_y_cookie_no_autentican_administracion(self):
        self.client.credentials()
        self.assertEqual(self.client.get("/api/usuarios/").status_code, 401)
        self.assertEqual(self.client.post("/api/auth/cambiar-clave/", {}, format="json").status_code, 401)
        self.assertEqual(self.client.post("/api/usuarios/", self.new_data(), format="json").status_code, 401)

    def test_patch_acotado_noop_y_evento_solo_cambios(self):
        old_joined = self.target.date_joined
        result = self.client.patch(self.url, {"first_name": " Nombre ", "username": "nuevo_alias"}, format="json")
        self.assertEqual(result.status_code, 200, result.data)
        event = self.target.eventos_administrativos.get()
        self.assertEqual(event.datos_nuevos, {"first_name": "Nombre", "username": "nuevo_alias"})
        self.assertEqual(self.client.patch(self.url, {"first_name": "Nombre"}, format="json").status_code, 200)
        self.assertEqual(self.target.eventos_administrativos.count(), 1)
        self.target.refresh_from_db()
        self.assertEqual(self.target.sesion_version, 1)
        self.assertEqual(self.target.date_joined, old_joined)
        for field in ["rol", "password", "is_active", "is_staff", "is_superuser", "groups", "user_permissions", "sesion_version", "date_joined", "last_login"]:
            self.assertEqual(self.client.patch(self.url, {field: 1}, format="json").status_code, 400, field)

    def test_editar_correo_propio_ti_normaliza_revoca_tokens_y_audita(self):
        """La respuesta PATCH confirma el cambio, pero toda credencial anterior queda obsoleta."""
        target = self.manager
        own_url = f"/api/usuarios/{target.pk}/"
        original_email = target.email
        access = AccessToken.for_user(target)
        refresh = RefreshToken.for_user(target)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        unchanged = self.client.patch(own_url, {"email": original_email.upper()}, format="json")
        self.assertEqual(unchanged.status_code, 200, unchanged.data)
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 200)
        self.assertFalse(target.eventos_administrativos.exists())

        changed = self.client.patch(own_url, {"email": " NUEVO.TI@EXAMPLE.TEST "}, format="json")
        self.assertEqual(changed.status_code, 200, changed.data)
        self.assertEqual(changed.data["email"], "nuevo.ti@example.test")
        target.refresh_from_db()
        self.assertEqual(target.sesion_version, 2)
        evento = target.eventos_administrativos.get()
        self.assertEqual(evento.tipo, "EDICION")
        self.assertEqual(evento.actor_id, target.pk)
        self.assertEqual(evento.datos_anteriores, {"email": original_email})
        self.assertEqual(evento.datos_nuevos, {"email": "nuevo.ti@example.test"})
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 401)
        self.client.cookies[settings.JWT_REFRESH_COOKIE_NAME] = str(refresh)
        self.assertEqual(self.client.post("/api/auth/refresh/", {}, format="json").status_code, 401)
        self.client.credentials()
        self.assertEqual(self.client.post("/api/auth/login/", {"email": original_email, "password": PASSWORD}, format="json").status_code, 401)
        self.assertEqual(self.client.post("/api/auth/login/", {"email": target.email, "password": PASSWORD}, format="json").status_code, 200)

    def test_activar_desactivar_idempotentes_exigen_motivo(self):
        self.assertEqual(self.client.post(self.url + "desactivar/", {}, format="json").status_code, 400)
        for action, expected in [("desactivar", False), ("activar", True)]:
            for _ in range(2):
                result = self.client.post(self.url + action + "/", {"motivo": "Decisión motivada"}, format="json")
                self.assertEqual(result.status_code, 200, result.data)
                self.assertEqual(result.data["is_active"], expected)
        self.target.refresh_from_db()
        self.assertEqual(self.target.sesion_version, 3)
        self.assertEqual(self.target.eventos_administrativos.count(), 2)

    def test_cambiar_rol_separado_y_sin_bypass_flags(self):
        result = self.client.post(self.url + "cambiar-rol/", {"rol": "GERENCIA", "motivo": "Nueva función"}, format="json")
        self.assertEqual(result.status_code, 200, result.data)
        self.target.refresh_from_db()
        self.assertFalse(self.target.is_staff or self.target.is_superuser)
        self.assertEqual(self.target.sesion_version, 2)
        result = self.client.post(self.url + "cambiar-rol/", {"rol": "GERENCIA", "motivo": "Repetido"}, format="json")
        self.assertEqual(result.status_code, 409)
        self.assertEqual(result.data["code"], "sin_cambios")

    def test_autooperaciones_protegidas_y_ultima_ti(self):
        url = f"/api/usuarios/{self.manager.pk}/"
        for action, data in [("desactivar", {"motivo": "Propia"}), ("cambiar-rol", {"rol": "TECNICO", "motivo": "Propia"}), ("establecer-clave", {"nueva_clave": NEW_PASSWORD, "motivo": "Propia"})]:
            self.assertEqual(self.client.post(url + action + "/", data, format="json").status_code, 409)
        self.other_manager.is_active = False
        self.other_manager.save()
        result = self.client.post(url + "desactivar/", {"motivo": "Última"}, format="json")
        self.assertEqual(result.status_code, 409)
        self.assertEqual(result.data["code"], "ultima_ti")
        result = self.client.post(url + "cambiar-rol/", {"rol": "TECNICO", "motivo": "Última"}, format="json")
        self.assertEqual(result.data["code"], "ultima_ti")
        self.assertEqual(UsuarioEvento.objects.count(), 0)

    def test_clave_administrativa_y_snapshots_sin_secretos(self):
        result = self.client.post(self.url + "establecer-clave/", {"nueva_clave": NEW_PASSWORD, "motivo": "Restablecimiento interno"}, format="json")
        self.assertEqual(result.status_code, 200, result.data)
        self.target.refresh_from_db()
        self.assertTrue(self.target.check_password(NEW_PASSWORD))
        event = self.target.eventos_administrativos.get()
        self.assertEqual(event.datos_anteriores, {})
        self.assertEqual(event.datos_nuevos, {})
        result = self.client.get(self.url + "historial/")
        for secret in [PASSWORD, NEW_PASSWORD, self.target.password, "sesion_version", "nueva_clave", "clave_actual"]:
            self.assertNotIn(secret, str(result.data))
        self.assertEqual(event.actor_id, self.manager.pk)

    def test_cambio_propio_todos_roles_exige_clave_actual_y_valida_nueva(self):
        for role, user in self.users.items():
            self.authenticate(user)
            for data in [{"clave_actual": "incorrecta", "nueva_clave": NEW_PASSWORD}, {"clave_actual": PASSWORD, "nueva_clave": "123"}, {"clave_actual": PASSWORD, "nueva_clave": NEW_PASSWORD, "usuario": self.target.pk}]:
                self.assertEqual(self.client.post("/api/auth/cambiar-clave/", data, format="json").status_code, 400)
            result = self.client.post("/api/auth/cambiar-clave/", {"clave_actual": PASSWORD, "nueva_clave": NEW_PASSWORD}, format="json")
            self.assertEqual(result.status_code, 204, (role, result.data))
            self.assertEqual(self.client.get("/api/auth/me/").status_code, 401)
            self.assertEqual(user.eventos_administrativos.get().tipo, "CAMBIO_CLAVE_PROPIA")

    def test_historial_paginado_metodos_prohibidos_y_ids(self):
        for i in range(26):
            services.editar_usuario(self.target, {"first_name": f"Nombre {i}"}, self.manager)
        result = self.client.get(self.url + "historial/")
        self.assertEqual(result.data["count"], 26)
        self.assertEqual(len(result.data["results"]), 25)
        self.assertEqual(len(self.client.get(self.url + "historial/?page=2").data["results"]), 1)
        self.assertEqual(self.client.get(self.url + "historial/?rol=TECNICO").status_code, 400)
        for method in ["put", "delete"]:
            self.assertEqual(getattr(self.client, method)(self.url, {}, format="json").status_code, 405)
        for identifier in ["0", "-1", "abc", "99999999999999999999999999999", "9223372036854775808", "999999"]:
            self.assertEqual(self.client.get(f"/api/usuarios/{identifier}/").status_code, 404)
        self.assertEqual(self.client.patch(self.url + "historial/", {}, format="json").status_code, 405)

    def test_rollback_cuenta_y_evento_tambien_revocacion(self):
        before = Usuario.objects.count()
        with patch("apps.usuarios.services_usuarios._event", side_effect=RuntimeError("fallo controlado")):
            with self.assertRaises(RuntimeError):
                services.crear_usuario(self.new_data(), self.manager)
            with self.assertRaises(RuntimeError):
                services.editar_usuario(self.target, {"email": "cambiado@example.test"}, self.manager)
            with self.assertRaises(RuntimeError):
                services.establecer_clave(self.target, {"nueva_clave": NEW_PASSWORD, "motivo": "Cambio"}, self.manager)
        self.assertEqual(Usuario.objects.count(), before)
        self.target.refresh_from_db()
        self.assertEqual(self.target.sesion_version, 1)
        self.assertTrue(self.target.check_password(PASSWORD))
        self.assertEqual(UsuarioEvento.objects.count(), 0)

    def test_historial_inmutable_y_version_positiva_en_db(self):
        services.editar_usuario(self.target, {"first_name": "Cambio"}, self.manager)
        event = self.target.eventos_administrativos.get()
        for operation in [lambda: event.save(), lambda: event.delete(), lambda: UsuarioEvento.objects.filter(pk=event.pk).update(motivo="Reescrito"), lambda: UsuarioEvento.objects.filter(pk=event.pk).delete()]:
            with self.assertRaises(DjangoValidationError):
                operation()
        with self.assertRaises(ProtectedError):
            self.target.delete()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Usuario.objects.filter(pk=self.target.pk).update(sesion_version=0)

    def test_evento_rechaza_secretos_y_lectura_filtra_snapshots(self):
        with self.assertRaises(DjangoValidationError):
            UsuarioEvento.objects.create(usuario_objetivo=self.target, actor=self.manager, tipo="ESTABLECER_CLAVE", datos_nuevos={"password": "secreto"})
        event = UsuarioEvento(usuario_objetivo=self.target, actor=self.manager, tipo="EDICION", datos_nuevos={"email": "publico@example.test", "password": "NO MOSTRAR", "sesion_version": 99})
        self.assertEqual(UsuarioEventoSerializer(event).data["datos_nuevos"], {"email": "publico@example.test"})

    def test_colisiones_db_conocidas_no_ocultan_errores_inesperados(self):
        # El chequeo previo puede perder una carrera; la constraint debe traducirse.
        with patch("apps.usuarios.services_usuarios._unique"):
            for changes in [{"email": self.manager.email}, {"username": self.manager.username}]:
                with self.assertRaisesMessage(ValidationError, "Ya existe una cuenta"):
                    services.crear_usuario(self.new_data(**changes), self.manager)
        with patch("apps.usuarios.services_usuarios._event", side_effect=IntegrityError("error inesperado")):
            with self.assertRaisesMessage(IntegrityError, "error inesperado"):
                services.crear_usuario(self.new_data(), self.manager)
        self.assertEqual(UsuarioEvento.objects.count(), 0)
