"""Carreras reales PostgreSQL con barreras/pg_blocking_pids y conexiones distintas."""
from django.core.cache import cache
from django.test import TransactionTestCase, override_settings
from rest_framework.exceptions import APIException

from apps.usuarios import credenciales, services_usuarios as services
from apps.usuarios.authentication import validar_sesion
from apps.usuarios.models import SeguridadCredencial, Usuario
from apps.usuarios.serializers import LoginSerializer, VersionedRefreshSerializer
from apps.usuarios.tokens import AccessToken, RefreshToken
from .test_administracion import NEW_PASSWORD, PASSWORD
from . import test_concurrencia_006 as concurrencia
from .test_credenciales_018 import CredencialesBase


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ConcurrenciaCredencialesTests(CredencialesBase, TransactionTestCase):
    race = concurrencia.ConcurrenciaTests.race

    def setUp(self):
        self.setUpTestData()
        cache.clear()

    def normal_login(self):
        return LoginSerializer().validate({"email": self.target.email, "password": PASSWORD})

    def refresh(self, token):
        return VersionedRefreshSerializer().validate({"refresh": str(token)})

    def assert_revoked(self, data):
        self.target.refresh_from_db()
        with self.assertRaises(APIException):
            validar_sesion(AccessToken(data["access"]), self.target)
        with self.assertRaises(APIException):
            self.refresh(data["refresh"])

    def test_dos_primeros_cambios_un_solo_consumo_evento_y_version(self):
        issued = self.emit()
        challenge = self.challenge(issued)["desafio"]
        version = issued.usuario.sesion_version
        action = lambda: credenciales.primer_cambio({"desafio": challenge, "nueva_clave": NEW_PASSWORD})
        one, two = self.race(action, action)
        self.assertIsNone(one)
        self.assertIsInstance(two, APIException)
        self.assertEqual(two.status_code, 401)
        user = Usuario.objects.get(pk=issued.usuario.pk)
        self.assertEqual(user.sesion_version, version + 1)
        self.assertEqual(user.eventos_administrativos.filter(tipo="CAMBIO_INICIAL").count(), 1)

    def test_dos_logins_temporales_solo_ultimo_desafio_valido(self):
        issued = self.emit()
        one, two = self.race(lambda: self.challenge(issued), lambda: self.challenge(issued))
        with self.assertRaises(APIException):
            credenciales.primer_cambio({"desafio": one["desafio"], "nueva_clave": NEW_PASSWORD})
        credenciales.primer_cambio({"desafio": two["desafio"], "nueva_clave": NEW_PASSWORD})

    def test_reset_antes_de_login_clave_antigua_rechazada(self):
        one, two = self.race(self.reset, self.normal_login)
        self.assertIsInstance(one, credenciales.CredencialEmitida)
        self.assertIsInstance(two, APIException)

    def test_login_antes_de_reset_tokens_resultantes_revocados(self):
        one, two = self.race(self.normal_login, self.reset)
        self.assertIsInstance(two, credenciales.CredencialEmitida)
        self.assert_revoked(one)

    def test_reset_antes_de_refresh_no_emite(self):
        token = RefreshToken.for_user(self.target)
        one, two = self.race(self.reset, lambda: self.refresh(token))
        self.assertIsInstance(one, credenciales.CredencialEmitida)
        self.assertIsInstance(two, APIException)

    def test_refresh_antes_de_reset_rotados_tambien_revocados(self):
        token = RefreshToken.for_user(self.target)
        one, two = self.race(lambda: self.refresh(token), self.reset)
        self.assertIsInstance(two, credenciales.CredencialEmitida)
        self.assert_revoked(one)

    def test_dos_resets_solo_ultima_credencial_utilizable(self):
        one, two = self.race(self.reset, self.reset)
        self.target.refresh_from_db()
        self.assertEqual(self.target.sesion_version, 3)
        self.assertFalse(self.target.check_password(one.credencial_temporal))
        self.assertTrue(self.target.check_password(two.credencial_temporal))
        self.assertEqual(self.target.eventos_administrativos.filter(tipo="REEMISION").count(), 2)

    def test_reset_antes_de_consumo_invalida_desafio(self):
        issued = self.emit()
        challenge = self.challenge(issued)["desafio"]
        one, two = self.race(lambda: self.reset(issued.usuario), lambda: credenciales.primer_cambio({"desafio": challenge, "nueva_clave": NEW_PASSWORD}))
        self.assertIsInstance(two, APIException)
        self.assertEqual(SeguridadCredencial.objects.get(usuario=issued.usuario).estado, "RECUPERACION")

    def test_consumo_antes_de_reset_vuelve_a_recuperacion(self):
        issued = self.emit()
        challenge = self.challenge(issued)["desafio"]
        one, two = self.race(lambda: credenciales.primer_cambio({"desafio": challenge, "nueva_clave": NEW_PASSWORD}), lambda: self.reset(issued.usuario))
        self.assertIsNone(one)
        self.assertIsInstance(two, credenciales.CredencialEmitida)
        user = Usuario.objects.get(pk=issued.usuario.pk)
        self.assertFalse(user.check_password(NEW_PASSWORD))
        self.assertEqual(user.eventos_administrativos.filter(tipo="CAMBIO_INICIAL").count(), 1)

    def test_reset_antes_de_cambio_personal_no_sortea_revocacion(self):
        one, two = self.race(self.reset, lambda: services.cambiar_clave_propia({"clave_actual": PASSWORD, "nueva_clave": NEW_PASSWORD}, self.target))
        self.assertIsInstance(two, APIException)

    def test_cambio_personal_antes_de_reset_termina_temporal(self):
        one, two = self.race(lambda: services.cambiar_clave_propia({"clave_actual": PASSWORD, "nueva_clave": NEW_PASSWORD}, self.target), self.reset)
        self.assertIsInstance(one, Usuario)
        self.target.refresh_from_db()
        self.assertFalse(self.target.check_password(NEW_PASSWORD))
        self.assertEqual(credenciales.estado_credencial(self.target), "RECUPERACION")

    def test_correo_antes_de_consumo_revoca_desafio(self):
        issued = self.emit()
        challenge = self.challenge(issued)["desafio"]
        one, two = self.race(lambda: services.editar_usuario(issued.usuario, {"email": "otro@example.test"}, self.manager),
                             lambda: credenciales.primer_cambio({"desafio": challenge, "nueva_clave": NEW_PASSWORD}))
        self.assertIsInstance(two, APIException)

    def test_consumo_antes_de_correo_preserva_hash_y_revoca_version(self):
        issued = self.emit()
        challenge = self.challenge(issued)["desafio"]
        version = issued.usuario.sesion_version
        one, two = self.race(lambda: credenciales.primer_cambio({"desafio": challenge, "nueva_clave": NEW_PASSWORD}),
                             lambda: services.editar_usuario(issued.usuario, {"email": "otro@example.test"}, self.manager))
        user = Usuario.objects.get(pk=issued.usuario.pk)
        self.assertTrue(user.check_password(NEW_PASSWORD))
        self.assertEqual(user.sesion_version, version + 2)

    def test_desactivacion_antes_de_consumo_impide_cambio(self):
        issued = self.emit()
        challenge = self.challenge(issued)["desafio"]
        one, two = self.race(lambda: services.actividad_usuario(issued.usuario, {"motivo": "Baja QA"}, self.manager, activo=False),
                             lambda: credenciales.primer_cambio({"desafio": challenge, "nueva_clave": NEW_PASSWORD}))
        self.assertIsInstance(two, APIException)
