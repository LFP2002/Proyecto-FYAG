"""Hallazgo de revisión 018: solo fixtures de BD QA; nunca reparar ausencias al leer."""
import secrets
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.hashers import make_password
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import RequestFactory, override_settings
from django.utils import timezone
from rest_framework.exceptions import APIException
from rest_framework.test import APITestCase

from apps.usuarios import credenciales, services_usuarios as services
from apps.usuarios.authentication import validar_sesion
from apps.usuarios.backends import CredencialesModelBackend
from apps.usuarios.models import SeguridadCredencial, Usuario, UsuarioEvento
from apps.usuarios.serializers import LoginSerializer, VersionedRefreshSerializer
from apps.usuarios.tokens import AccessToken, RefreshToken
from .test_administracion import NEW_PASSWORD, PASSWORD
from .test_credenciales_018 import CredencialesBase, FIRST, login_request


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class FailClosedTests(CredencialesBase, APITestCase):
    def retirar_estado_fixture(self, user):
        # Simula inconsistencia únicamente en una cuenta sintética del test aislado.
        SeguridadCredencial.objects.filter(usuario=user).delete()
        user.refresh_from_db()

    def test_personal_sin_estado_login_jwt_refresh_y_django_denegados(self):
        access, refresh = AccessToken.for_user(self.target), RefreshToken.for_user(self.target)
        self.retirar_estado_fixture(self.target)
        before = (self.target.password, self.target.rol, self.target.sesion_version, UsuarioEvento.objects.count())
        result = self.client.post("/api/auth/login/", {"email": self.target.email, "password": PASSWORD}, format="json")
        self.assertEqual(result.status_code, 401)
        self.assertEqual(result.data, {"detail": "Credenciales inválidas."})
        self.assert_old_tokens_denied(access, refresh)
        self.assertIsNone(authenticate(email=self.target.email, password=PASSWORD))
        self.assertIsNone(CredencialesModelBackend().get_user(self.target.pk))
        self.target.refresh_from_db()
        self.assertTrue((self.target.password, self.target.rol, self.target.sesion_version, UsuarioEvento.objects.count()) == before)
        self.assertFalse(SeguridadCredencial.objects.filter(usuario=self.target).exists())

    def test_temporal_sin_estado_nunca_se_convierte_en_login_normal(self):
        issued = self.emit()
        challenge = self.challenge(issued)["desafio"]
        access, refresh = AccessToken.for_user(issued.usuario), RefreshToken.for_user(issued.usuario)
        self.retirar_estado_fixture(issued.usuario)
        with self.assertRaises(APIException):
            self.challenge(issued)
        self.assert_old_tokens_denied(access, refresh)
        self.assertEqual(self.client.post(FIRST, {"desafio": challenge, "nueva_clave": NEW_PASSWORD}, format="json").status_code, 401)
        self.assertFalse(SeguridadCredencial.objects.filter(usuario=issued.usuario).exists())

    def test_ausencia_precargada_y_sin_cache_ambas_fail_closed(self):
        self.retirar_estado_fixture(self.target)
        uncached = Usuario.objects.get(pk=self.target.pk)
        self.assertEqual(credenciales.estado_credencial(uncached), "NO_DISPONIBLE")
        cached = Usuario.objects.select_related("seguridad_credencial").get(pk=self.target.pk)
        self.assertTrue(Usuario._meta.get_field("seguridad_credencial").is_cached(cached))
        with self.assertNumQueries(0):
            self.assertEqual(credenciales.estado_credencial(cached), "NO_DISPONIBLE")
            self.assertFalse(credenciales.es_personal(cached))

    def test_guardar_existente_y_get_or_create_no_reparan_ausencia(self):
        self.retirar_estado_fixture(self.target)
        self.target.save(update_fields=["password"])
        user, created = Usuario.objects.get_or_create(pk=self.target.pk)
        self.assertFalse(created)
        self.assertFalse(SeguridadCredencial.objects.filter(usuario=user).exists())

    def test_cambio_propio_y_reset_no_reconstruyen_personal_implicitamente(self):
        self.retirar_estado_fixture(self.target)
        before = (self.target.password, self.target.sesion_version, UsuarioEvento.objects.count())
        with self.assertRaises(APIException) as caught:
            services.cambiar_clave_propia({"clave_actual": PASSWORD, "nueva_clave": NEW_PASSWORD}, self.target)
        self.assertEqual(caught.exception.status_code, 401)
        result = self.client.post(self.url + "restablecer-clave/", {"motivo": "Revisión QA"}, format="json")
        self.assertEqual(result.status_code, 409)
        self.assertEqual(result.data["code"], "seguridad_no_disponible")
        self.target.refresh_from_db()
        self.assertTrue((self.target.password, self.target.sesion_version, UsuarioEvento.objects.count()) == before)
        self.assertFalse(SeguridadCredencial.objects.filter(usuario=self.target).exists())

    def test_actor_ti_sin_estado_no_administra_aunque_se_invoque_servicio(self):
        self.retirar_estado_fixture(self.manager)
        for action in [lambda: services.crear_usuario(self.new_data(), self.manager),
                       lambda: self.reset(),
                       lambda: services.editar_usuario(self.target, {"first_name": "QA"}, self.manager)]:
            with self.assertRaises(APIException) as caught:
                action()
            self.assertEqual(caught.exception.status_code, 401)

    def test_detalle_ti_muestra_no_disponible_sin_reparar_ni_exponer_secretos(self):
        self.retirar_estado_fixture(self.target)
        result = self.client.get(self.url)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data["estado_credencial"], "NO_DISPONIBLE")
        self.assertTrue(result.data["cambio_obligatorio"])
        self.assertNotIn("password", result.data)
        self.assertFalse(SeguridadCredencial.objects.filter(usuario=self.target).exists())

    def test_backend_django_temporal_solo_admite_flujo_restringido(self):
        issued = self.emit()
        data = {"email": issued.usuario.email, "password": issued.credencial_temporal}
        request = login_request()
        self.assertIsNotNone(authenticate(request, **data))
        self.assertIsNone(authenticate(RequestFactory().post("/admin/login/"), **data))
        self.assertIsNone(CredencialesModelBackend().get_user(issued.usuario.pk))

    def test_hash_antiguo_no_se_reescribe_si_falta_estado(self):
        # Hash sintético MD5 leído con PBKDF2 preferido: no debe migrarse al denegar.
        self.retirar_estado_fixture(self.target)
        before = self.target.password
        with override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.PBKDF2PasswordHasher", "django.contrib.auth.hashers.MD5PasswordHasher"]):
            self.assertIsNone(authenticate(email=self.target.email, password=PASSWORD))
        self.target.refresh_from_db()
        self.assertTrue(self.target.password == before)

    def test_incoherencia_personal_denegada_en_todos_los_caminos(self):
        access, refresh = AccessToken.for_user(self.target), RefreshToken.for_user(self.target)
        original = SeguridadCredencial.from_db

        def inconsistente(*args, **kwargs):
            state = original(*args, **kwargs)
            if state.usuario_id == self.target.pk:
                state.emitida_en = timezone.now()  # PERSONAL no admite fechas temporales.
            return state

        # Simula una lectura corrupta sin deshabilitar constraints ni alterar filas.
        with patch.object(SeguridadCredencial, "from_db", side_effect=inconsistente):
            self.assert_old_tokens_denied(access, refresh)
            with self.assertRaises(APIException):
                LoginSerializer().validate({"email": self.target.email, "password": PASSWORD})
            with self.assertRaises(APIException):
                services.cambiar_clave_propia({"clave_actual": PASSWORD, "nueva_clave": NEW_PASSWORD}, self.target)
            self.assertIsNone(CredencialesModelBackend().get_user(self.target.pk))

    def test_estado_incoherente_temporal_no_produce_500_ni_desafio(self):
        issued = self.emit()
        original = SeguridadCredencial.from_db

        def inconsistente(*args, **kwargs):
            state = original(*args, **kwargs)
            if state.usuario_id == issued.usuario.pk:
                state.vence_en = None
            return state

        with patch.object(SeguridadCredencial, "from_db", side_effect=inconsistente):
            with self.assertRaises(APIException):
                self.challenge(issued)
            with self.assertRaises(APIException):
                with transaction.atomic():
                    credenciales.iniciar_cambio(issued.usuario)

    def test_otras_revalidaciones_no_aceptan_ausencia_sin_token(self):
        from apps.documentos.permissions import revalidar
        from apps.adjuntos.permissions import actor_actual
        for role in [Usuario.Rol.GERENCIA, Usuario.Rol.SUPERVISOR_OBRAS]:
            user = self.users[role]
            self.retirar_estado_fixture(user)
            for action in [revalidar, actor_actual]:
                with self.assertRaises(APIException) as caught:
                    action(user)  # No JWT: también debe validar el estado SQL.
                self.assertEqual(caught.exception.status_code, 401)

    def test_coherencia_valida_todos_los_campos_y_la_identidad(self):
        state = SeguridadCredencial(usuario=self.target, estado="PERSONAL")
        self.assertTrue(credenciales.estado_coherente(state))
        for values in [{"estado": "OTRO"}, {"emitida_en": timezone.now()}, {"desafio_version": 1}]:
            invalid = SeguridadCredencial(usuario=self.target, estado="PERSONAL")
            for name, value in values.items():
                setattr(invalid, name, value)
            self.assertFalse(credenciales.estado_coherente(invalid))
        now = timezone.now()
        for values in [{"desafio_digest": "x"}, {"desafio_version": True},
                       {"desafio_vence_en": now + timedelta(days=2)}, {"vence_en": now},
                       {"emitida_en": now.replace(tzinfo=None)}]:
            invalid = SeguridadCredencial(usuario=self.target, estado="INICIAL", emitida_en=now, vence_en=now + timedelta(days=1))
            for name, value in values.items():
                setattr(invalid, name, value)
            self.assertFalse(credenciales.estado_coherente(invalid))
        user = Usuario.objects.get(pk=self.target.pk)
        Usuario._meta.get_field("seguridad_credencial").set_cached_value(user, self.manager.seguridad_credencial)
        self.assertEqual(credenciales.estado_credencial(user), "NO_DISPONIBLE")

    def test_altas_internas_save_manager_superuser_y_bulk_tienen_estado(self):
        password = secrets.token_urlsafe(32)
        first = Usuario.objects.create_user(username="qa_interno", email="qa_interno@example.test", password=password, rol="TECNICO")
        second = Usuario.objects.create_superuser(username="qa_super", email="qa_super@example.test", password=password, rol="GERENCIA")
        third = Usuario(username="qa_save", email="qa_save@example.test", rol="TECNICO")
        third.set_password(password)
        third.save()
        bulk = [Usuario(username=f"qa_bulk_{i}", email=f"qa_bulk_{i}@example.test", rol="TECNICO", password=make_password(password)) for i in range(2)]
        Usuario.objects.bulk_create(bulk)
        for user in [first, second, third, *bulk]:
            state = SeguridadCredencial.objects.get(usuario=user)
            self.assertTrue(credenciales.estado_coherente(state))
            self.assertEqual(state.estado, "PERSONAL")

    def test_rollback_incluye_estado_y_no_deja_huerfanos(self):
        before = (Usuario.objects.count(), SeguridadCredencial.objects.count())
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                user = Usuario.objects.create_user(username="qa_rollback", email="qa_rollback@example.test", rol="TECNICO")
                self.assertTrue(SeguridadCredencial.objects.filter(usuario=user).exists())
                raise RuntimeError("Rollback sintético QA")
        self.assertEqual((Usuario.objects.count(), SeguridadCredencial.objects.count()), before)

    def test_fallo_de_trigger_impide_insertar_usuario(self):
        pk = 900000000
        with self.assertRaises(IntegrityError), transaction.atomic():
            # FK diferida permite simular conflicto de estado dentro de esta tx QA.
            SeguridadCredencial.objects.create(usuario_id=pk)
            Usuario.objects.create(pk=pk, username="qa_conflicto", email="qa_conflicto@example.test", rol="TECNICO", password=make_password(secrets.token_urlsafe(32)))
        self.assertFalse(Usuario.objects.filter(pk=pk).exists())
        self.assertFalse(SeguridadCredencial.objects.filter(usuario_id=pk).exists())


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class BootstrapFailClosedTests(APITestCase):
    def test_comando_primera_ti_estado_personal_y_login_operativo(self):
        password = secrets.token_urlsafe(32)
        output = StringIO()
        with patch("apps.usuarios.management.commands.crear_primera_ti.sys.stdin.isatty", return_value=True), patch("apps.usuarios.management.commands.crear_primera_ti.getpass", return_value=password):
            call_command("crear_primera_ti", email="qa_ti@example.test", username="qa_ti", stdout=output)
        user = Usuario.objects.get()
        self.assertEqual(credenciales.estado_credencial(user), "PERSONAL")
        self.assertTrue(user.check_password(password))
        self.assertFalse(password in output.getvalue())
        self.assertIn("access", LoginSerializer().validate({"email": user.email, "password": password}))

    def test_bootstrap_sin_estado_confirmado_revierte_cuenta_y_evento(self):
        with patch("apps.usuarios.credenciales.es_personal", return_value=False):
            with self.assertRaises(APIException):
                services.aprovisionar_primera_ti({"email": "qa_ti@example.test", "username": "qa_ti", "password": secrets.token_urlsafe(32)})
        self.assertFalse(Usuario.objects.exists())
        self.assertFalse(SeguridadCredencial.objects.exists())
        self.assertFalse(UsuarioEvento.objects.exists())

    def test_no_rebootstrap_ti_existente_sin_estado(self):
        user = Usuario.objects.create_user(username="qa_ti", email="qa_ti@example.test", rol="ADMINISTRADOR_TI")
        SeguridadCredencial.objects.filter(usuario=user).delete()  # Solo fixture QA.
        with self.assertRaises(APIException) as caught:
            services.aprovisionar_primera_ti({"email": "otra@example.test", "username": "otra", "password": secrets.token_urlsafe(32)})
        self.assertEqual(caught.exception.detail["code"], "ti_ya_aprovisionada")
        self.assertEqual(Usuario.objects.count(), 1)
        self.assertFalse(SeguridadCredencial.objects.exists())
