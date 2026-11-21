from django.test import TestCase, override_settings
from rest_framework.exceptions import AuthenticationFailed

from apps.usuarios.models import Usuario
from apps.usuarios.tokens import AccessToken
from apps.usuarios.tests.c2_helpers import BaseC2
from apps.inventario.services_materiales import operar
from .test_materiales import RUTAS


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class BloqueosMaterialesTests(BaseC2, TestCase):
    def test_bloqueo_persistido_para_bodega_supervisor_y_finanzas(self):
        for rol, tipo in [('BODEGUERO', 'ENTREGA'), ('SUPERVISOR_OBRAS', 'AUTORIZACION_ENTREGA'), ('ADMINISTRATIVO_FINANZAS', 'VALORIZACION')]:
            u = Usuario.objects.create_user(username='bloqueado_'+rol, email=rol+'@bloqueo.test', rol=rol, password='solo-qa-ficticia')
            token = str(AccessToken.for_user(u))
            self.client.credentials()
            self.fail(u)
            self.client.credentials(HTTP_AUTHORIZATION='Bearer '+token)
            self.assertEqual(self.client.get('/api/inventario/'+RUTAS[tipo]+'/').status_code, 401)
            self.assertEqual(self.client.post('/api/inventario/'+RUTAS[tipo]+'/', {}, format='json').status_code, 401)
            u.refresh_from_db()
            with self.assertRaises(AuthenticationFailed):
                operar(tipo, {}, u)
