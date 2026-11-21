from django.test import TransactionTestCase, override_settings
from rest_framework.exceptions import APIException

from apps.usuarios.autenticacion_c2 import verificar_acceso
from apps.usuarios.authentication import validar_sesion
from apps.usuarios import credenciales
from apps.usuarios.models import EstadoAcceso, EventoAcceso, RecuperacionAcceso, Usuario
from apps.usuarios.serializers import LoginSerializer, VersionedRefreshSerializer
from apps.usuarios.tokens import AccessToken, RefreshToken
from . import test_concurrencia_006 as concurrencia
from .c2_helpers import BaseC2
from .test_administracion import PASSWORD


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ConcurrenciaC2Tests(BaseC2, TransactionTestCase):
    race = concurrencia.ConcurrenciaTests.race

    def wrong(self, user=None):
        return verificar_acceso((user or self.target).email, "incorrecta-sintetica", None)

    def test_quinto_y_login_correcto_no_emite_tras_bloqueo(self):
        self.fail(count=4)
        one, two = self.race(self.wrong, lambda: verificar_acceso(self.target.email, PASSWORD, None))
        self.assertIsNone(one)
        self.assertIsNone(two)
        self.assertEqual(EventoAcceso.objects.filter(tipo="BLOQUEO_TEMPORAL").count(), 1)
        self.target.refresh_from_db()
        self.assertEqual(self.target.sesion_version, 2)

    def test_dos_quintos_un_solo_ciclo_y_revocacion(self):
        self.fail(count=4)
        self.race(self.wrong, self.wrong)
        self.assertEqual(len(EstadoAcceso.objects.get(usuario=self.target).ciclos_en), 1)
        self.target.refresh_from_db()
        self.assertEqual(self.target.sesion_version, 2)

    def test_refresh_antes_de_bloqueo_sus_tokens_tambien_revocados(self):
        self.fail(count=4)
        token = str(RefreshToken.for_user(self.target))
        one, two = self.race(lambda: VersionedRefreshSerializer().validate({"refresh": token}), self.wrong)
        self.assertIsNone(two)
        self.target.refresh_from_db()
        with self.assertRaises(APIException):
            validar_sesion(AccessToken(one["access"]), self.target)
        with self.assertRaises(APIException):
            VersionedRefreshSerializer().validate({"refresh": one["refresh"]})

    def test_bloqueo_antes_de_refresh_no_emite(self):
        self.fail(count=4)
        token = str(RefreshToken.for_user(self.target))
        one, two = self.race(self.wrong, lambda: VersionedRefreshSerializer().validate({"refresh": token}))
        self.assertIsNone(one)
        self.assertIsInstance(two, APIException)

    def test_reset_antes_de_verificacion_no_cuenta_snapshot_obsoleto(self):
        one, two = self.race(lambda: credenciales.restablecer_clave(self.target, {"motivo": "QA recuperación"}, self.manager), self.wrong)
        self.assertIsInstance(one, credenciales.CredencialEmitida)
        self.assertIsNone(two)
        self.assertEqual(EstadoAcceso.objects.get(usuario=self.target).intentos, 0)
        self.assertEqual(RecuperacionAcceso.objects.count(), 1)

    def test_dos_ti_concurrentes_no_pierden_ultima_recuperadora(self):
        self.fail(self.manager, count=4)
        self.fail(self.other, count=4)
        self.race(lambda: self.wrong(self.manager), lambda: self.wrong(self.other))
        states = EstadoAcceso.objects.filter(usuario__in=[self.manager, self.other])
        self.assertEqual(states.filter(estado="BLOQUEO_TEMPORAL").count(), 1)
        self.assertEqual(states.filter(estado="NORMAL").count(), 1)

    def test_login_antes_de_reset_tokens_no_reutilizables(self):
        one, two = self.race(lambda: LoginSerializer().validate({"email": self.target.email, "password": PASSWORD}),
                             lambda: credenciales.restablecer_clave(self.target, {"motivo": "QA recuperación"}, self.manager))
        self.target.refresh_from_db()
        with self.assertRaises(APIException):
            validar_sesion(AccessToken(one["access"]), self.target)

    def test_dos_resets_solo_ultima_temporal_utilizable(self):
        action = lambda: credenciales.restablecer_clave(self.target, {"motivo": "QA recuperación"}, self.manager)
        one, two = self.race(action, action)
        self.target.refresh_from_db()
        self.assertFalse(self.target.check_password(one.credencial_temporal))
        self.assertTrue(self.target.check_password(two.credencial_temporal))
        self.assertEqual(RecuperacionAcceso.objects.count(), 2)
