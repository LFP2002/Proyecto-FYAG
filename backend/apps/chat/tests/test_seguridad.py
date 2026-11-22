from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.usuarios.models import Usuario
from apps.usuarios.tokens import AccessToken
from apps.usuarios.tests.c2_helpers import BaseC2
from .base import ChatBase, URL


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class ChatBloqueosTests(BaseC2, TestCase):
    def test_bloqueos_persistidos_seis_roles_sin_excepcion_ti(self):
        for rol in Usuario.Rol.values:
            user = Usuario.objects.create_user(username='chat_bloq_'+rol, email=rol+'@chat-bloqueo.test', rol=rol, password='FicticiaSoloQA-2026')
            token = str(AccessToken.for_user(user))
            self.client.credentials()
            self.fail(user)
            self.client.credentials(HTTP_AUTHORIZATION='Bearer '+token)
            self.assertEqual(self.client.get(URL+'usuarios/').status_code, 401)


class ChatErroresTests(ChatBase, TestCase):
    def setUp(self):
        self.preparar()

    def test_error_inesperado_no_registra_texto_token_ni_sql(self):
        c = self.directa()
        from uuid import uuid4
        secreto = 'CONTENIDO_PRIVADO_QA'
        with patch('apps.chat.services.publicar_texto', side_effect=RuntimeError(secreto)), self.assertLogs('apps.chat.views', level='WARNING') as logs:
            r = self.client.post(f'{URL}conversaciones/{c.pk}/mensajes/', {'texto': secreto, 'clave_idempotencia': str(uuid4())}, format='json')
        self.assertEqual(r.status_code, 503)
        self.assertNotIn(secreto, str(r.data))
        self.assertNotIn(secreto, str(logs.output))
        self.assertNotIn('Bearer', str(logs.output))

    def test_fecha_utc_y_contenido_html_solo_texto_plano(self):
        c = self.directa()
        m = self.enviar(c, texto='<b>No renderizar como HTML</b>')
        r = self.client.get(f'{URL}conversaciones/{c.pk}/mensajes/')
        self.assertEqual(r.data['results'][0]['texto'], m.texto)
        self.assertTrue(r.data['results'][0]['creado_en'].endswith('Z'))
        self.assertTrue(r.data['results'][0]['vence_en'].endswith('Z'))
