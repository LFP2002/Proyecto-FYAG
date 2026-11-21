from uuid import uuid4

from django.test import TestCase, override_settings
from rest_framework.exceptions import AuthenticationFailed

from apps.finanzas import services_egresos, consultas_egresos
from apps.finanzas.models import Egreso
from apps.usuarios.models import Usuario
from apps.usuarios.tests.c2_helpers import BaseC2
from apps.usuarios.tokens import AccessToken
from .test_egresos import URL, RESUMEN, payload


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class BloqueosEgresosTests(BaseC2, TestCase):
    def test_bloqueo_persistido_deniega_endpoints_y_servicios_aun_con_version_actual(self):
        Usuario.objects.filter(pk=self.target.pk).update(rol='ADMINISTRATIVO_FINANZAS')
        self.target.refresh_from_db()
        token = str(AccessToken.for_user(self.target))
        self.fail(self.target)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        for ruta in [URL, URL + '999999/', URL + '999999/historial/', RESUMEN]:
            self.assertEqual(self.client.get(ruta).status_code, 401)
        self.assertEqual(self.client.post(URL, payload(), format='json', HTTP_IDEMPOTENCY_KEY=str(uuid4())).status_code, 401)
        self.target.refresh_from_db()
        with self.assertRaises(AuthenticationFailed):
            services_egresos.registrar_egreso(payload(), self.target, str(uuid4()))
        with self.assertRaises(AuthenticationFailed):
            consultas_egresos.listado(self.target, {})
        self.assertFalse(Egreso.objects.exists())
