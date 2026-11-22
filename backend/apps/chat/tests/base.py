from io import BytesIO
from tempfile import TemporaryDirectory
from uuid import uuid4
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from PIL import Image
from rest_framework.test import APIClient

from apps.usuarios.models import Usuario
from apps.usuarios.tokens import AccessToken
from apps.chat import services

URL = '/api/chat/'


def imagen(nombre='imagen.png', size=(32, 24), formato='PNG'):
    file = BytesIO()
    Image.new('RGB', size, 'blue').save(file, format=formato)
    return SimpleUploadedFile(nombre, file.getvalue(), content_type='application/octet-stream')


class ChatBase:
    def preparar(self):
        self.users = [Usuario.objects.create_user(username=f'chat_{rol}', email=f'{rol}@chat.test', rol=rol) for rol in Usuario.Rol.values]
        self.actor, self.otro, self.ajeno = self.users[:3]
        self.client = APIClient()
        self.autenticar(self.actor)

    def autenticar(self, user):
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {AccessToken.for_user(user)}')

    def entrada_directa(self, destinatario=None, **cambios):
        value = destinatario or self.otro
        return {'tipo': 'DIRECTA', 'destinatario': value.pk if hasattr(value, 'pk') else value, 'clave_idempotencia': str(uuid4()), **cambios}

    def directa(self, **cambios):
        return services.crear_conversacion(self.entrada_directa(**cambios), self.actor)[0]

    def enviar(self, conv, actor=None, **cambios):
        return services.publicar_texto(conv.pk, {'texto': ' Mensaje de QA ', 'clave_idempotencia': str(uuid4()), **cambios}, actor or self.actor)[0]

    def storage(self):
        root = TemporaryDirectory(prefix='fyag-chat-qa-')
        self.addCleanup(root.cleanup)
        contexto = override_settings(CHAT_ARCHIVOS_ROOT=root.name)
        contexto.enable(); self.addCleanup(contexto.disable)
        return root

    def subir(self, conv, *, real=False, upload=None, key=None, texto='', actor=None):
        data = {'archivo': upload or imagen(), 'texto': texto}
        if real:
            return services.publicar_archivo(conv.pk, data, key or str(uuid4()), actor or self.actor)
        with patch('apps.chat.archivos.analizar'):
            return services.publicar_archivo(conv.pk, data, key or str(uuid4()), actor or self.actor)
