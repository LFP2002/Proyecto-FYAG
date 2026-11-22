import json
import os
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase
from django.urls import resolve

from apps.chat.serializers import ConversacionSerializer, MensajeSerializer, ArchivoSerializer
from config.settings import _chat_entero


class ContratoChatTests(SimpleTestCase):
    def test_openapi_rutas_y_serializers_reales(self):
        spec = json.loads((Path(settings.BASE_DIR)/'docs/openapi/SPEC-023A-v1.json').read_text(encoding='utf-8'))
        self.assertEqual(spec['openapi'], '3.1.0')
        self.assertEqual(len(spec['paths']), 7)
        for ruta, metodos in spec['paths'].items():
            self.assertNotIn('conexion', ruta)
            match = resolve(ruta.replace('{id}', '1'))
            for method in set(metodos)-{'parameters'}:
                self.assertTrue(hasattr(match.func.view_class, method))
        for name, serializer in [('Conversacion', ConversacionSerializer), ('Mensaje', MensajeSerializer), ('Archivo', ArchivoSerializer)]:
            self.assertEqual(set(spec['components']['schemas'][name]['properties']), set(serializer.Meta.fields))

    def test_retencion_rango_seguro_entero_y_default(self):
        for value in ['0', '91', '-1', '1.5', 'abc', '١', ' 30 ']:
            with patch.dict(os.environ, {'FYAG_CHAT_RETENCION_DIAS': value}), self.assertRaises(ImproperlyConfigured):
                _chat_entero('FYAG_CHAT_RETENCION_DIAS', 30, 1, 90)
        for value in ['1', '30', '90']:
            with patch.dict(os.environ, {'FYAG_CHAT_RETENCION_DIAS': value}):
                self.assertEqual(_chat_entero('FYAG_CHAT_RETENCION_DIAS', 30, 1, 90), int(value))
