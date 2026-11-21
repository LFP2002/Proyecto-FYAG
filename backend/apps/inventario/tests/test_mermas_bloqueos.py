from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed

from apps.usuarios.models import Usuario, SeguridadCredencial
from apps.usuarios.tokens import AccessToken
from apps.usuarios.tests.c2_helpers import BaseC2
from apps.inventario.permissions_mermas import revalidar
from .test_mermas import URLS


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class MermasBloqueadasTests(BaseC2, TestCase):
    def test_bloqueo_persistido_en_cuatro_actores(self):
        for rol, ambito in [('BODEGUERO', 'BODEGA'), ('ADMINISTRATIVO_FINANZAS', 'BODEGA'), ('TECNICO', 'OBRA'), ('SUPERVISOR_OBRAS', 'OBRA')]:
            usuario = Usuario.objects.create_user(username='c2_bloq_'+rol, email=rol+'@c2-bloqueo.test', rol=rol, password='ficticia-solo-qa')
            token = str(AccessToken.for_user(usuario))
            self.client.credentials()
            self.fail(usuario)
            self.client.credentials(HTTP_AUTHORIZATION='Bearer '+token)
            self.assertEqual(self.client.get(URLS[ambito]).status_code, 401)
            with self.assertRaises(AuthenticationFailed):
                revalidar(usuario, ambito)

    def test_credencial_no_personal_en_cuatro_actores(self):
        for rol, ambito in [('BODEGUERO', 'BODEGA'), ('ADMINISTRATIVO_FINANZAS', 'BODEGA'), ('TECNICO', 'OBRA'), ('SUPERVISOR_OBRAS', 'OBRA')]:
            usuario = Usuario.objects.create_user(username='c2_cred_'+rol, email=rol+'@c2-cred.test', rol=rol, password='ficticia-solo-qa')
            token = str(AccessToken.for_user(usuario))
            ahora = timezone.now()
            SeguridadCredencial.objects.filter(usuario=usuario).update(estado='INICIAL', emitida_en=ahora, vence_en=ahora+timedelta(hours=1))
            self.client.credentials(HTTP_AUTHORIZATION='Bearer '+token)
            self.assertEqual(self.client.get(URLS[ambito]).status_code, 401)
            with self.assertRaises(AuthenticationFailed):
                revalidar(usuario, ambito)
