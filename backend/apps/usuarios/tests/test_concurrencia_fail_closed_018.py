"""Ausencia sobre fixtures QA frente a autenticación: PostgreSQL real, sin sleeps."""
from django.core.cache import cache
from django.db import transaction
from django.test import TransactionTestCase, override_settings
from rest_framework.exceptions import APIException

from apps.usuarios import credenciales
from apps.usuarios.models import SeguridadCredencial, Usuario, UsuarioEvento
from apps.usuarios.serializers import LoginSerializer, VersionedRefreshSerializer
from apps.usuarios.tokens import RefreshToken
from . import test_concurrencia_006 as concurrencia
from .test_administracion import NEW_PASSWORD, PASSWORD
from .test_credenciales_018 import CredencialesBase


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ConcurrenciaEstadoAusenteTests(CredencialesBase, TransactionTestCase):
    race = concurrencia.ConcurrenciaTests.race

    def setUp(self):
        self.setUpTestData()
        cache.clear()

    def retirar_fixture(self, user=None):
        user = user or self.target
        with transaction.atomic():
            Usuario.objects.select_for_update().get(pk=user.pk)
            SeguridadCredencial.objects.filter(usuario=user).delete()

    def login(self):
        return LoginSerializer().validate({"email": self.target.email, "password": PASSWORD})

    def test_ausencia_confirma_antes_de_login_no_emite_tokens(self):
        one, two = self.race(self.retirar_fixture, self.login)
        self.assertIsInstance(two, APIException)
        self.assertEqual(two.status_code, 401)
        self.assertFalse(SeguridadCredencial.objects.filter(usuario=self.target).exists())

    def test_login_anterior_a_ausencia_sus_tokens_tambien_se_denegan(self):
        one, two = self.race(self.login, self.retirar_fixture)
        self.assert_old_tokens_denied(one["access"], one["refresh"])

    def test_ausencia_antes_de_refresh_no_rota(self):
        token = str(RefreshToken.for_user(self.target))
        one, two = self.race(self.retirar_fixture, lambda: VersionedRefreshSerializer().validate({"refresh": token}))
        self.assertIsInstance(two, APIException)
        self.assertEqual(two.status_code, 401)

    def test_ausencia_antes_de_primer_cambio_no_modifica_hash_ni_eventos(self):
        issued = self.emit()
        challenge = self.challenge(issued)["desafio"]
        before = (issued.usuario.password, issued.usuario.sesion_version, UsuarioEvento.objects.count())
        one, two = self.race(lambda: self.retirar_fixture(issued.usuario),
                             lambda: credenciales.primer_cambio({"desafio": challenge, "nueva_clave": NEW_PASSWORD}))
        self.assertIsInstance(two, APIException)
        self.assertEqual(two.status_code, 401)
        issued.usuario.refresh_from_db()
        self.assertTrue((issued.usuario.password, issued.usuario.sesion_version, UsuarioEvento.objects.count()) == before)

    def test_ausencia_antes_de_reset_no_repara_estado_desconocido(self):
        before = (self.target.password, self.target.sesion_version, UsuarioEvento.objects.count())
        one, two = self.race(self.retirar_fixture, self.reset)
        self.assertIsInstance(two, APIException)
        self.assertEqual(two.status_code, 409)
        self.target.refresh_from_db()
        self.assertTrue((self.target.password, self.target.sesion_version, UsuarioEvento.objects.count()) == before)
        self.assertFalse(SeguridadCredencial.objects.filter(usuario=self.target).exists())
