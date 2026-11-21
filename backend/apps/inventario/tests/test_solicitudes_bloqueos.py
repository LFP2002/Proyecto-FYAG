from django.test import TestCase, override_settings
from rest_framework.exceptions import AuthenticationFailed

from apps.usuarios.models import Usuario
from apps.usuarios.tokens import AccessToken
from apps.usuarios.tests.c2_helpers import BaseC2
from apps.inventario import services_solicitudes
from .test_solicitudes import URL, CATALOGO


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class SolicitudesBloqueadasTests(BaseC2, TestCase):
    def test_sesion_bloqueada_tecnico_y_supervisor(self):
        for rol in ['TECNICO', 'SUPERVISOR_OBRAS']:
            usuario = Usuario.objects.create_user(username='c1_bloq_'+rol, email=rol+'@c1-bloqueo.test', rol=rol, password='ficticia-solo-qa')
            token = str(AccessToken.for_user(usuario))
            self.client.credentials()
            self.fail(usuario)
            self.client.credentials(HTTP_AUTHORIZATION='Bearer '+token)
            self.assertEqual(self.client.get(URL).status_code, 401)
            self.assertEqual(self.client.get(CATALOGO).status_code, 401)
            self.assertEqual(self.client.post(URL, {}, format='json').status_code, 401)
            usuario.refresh_from_db()
            with self.assertRaises(AuthenticationFailed):
                services_solicitudes.crear_solicitud({}, usuario)
            with self.assertRaises(AuthenticationFailed):
                services_solicitudes.decidir_solicitud(usuario.pk, {}, usuario)
