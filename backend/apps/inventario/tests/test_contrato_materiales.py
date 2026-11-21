import json
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase
from django.urls import resolve

from apps.inventario.serializers_materiales import OperacionSerializer, OperacionCostoSerializer
from .test_materiales import RUTAS


class Contrato019BTests(SimpleTestCase):
    def test_openapi_publica_solo_rutas_y_campos_reales(self):
        spec = json.loads((Path(settings.BASE_DIR)/'docs/openapi/SPEC-019B-v1.json').read_text(encoding='utf-8'))
        self.assertEqual(spec['openapi'], '3.1.0')
        self.assertEqual(set(spec['paths']), {'/api/inventario/'+x+'/' for x in [*RUTAS.values(), 'estados-valorizacion']})
        for path, metodos in spec['paths'].items():
            match = resolve(path)
            self.assertEqual(set(match.func.actions)-{'head'}, set(metodos))
        schemas = spec['components']['schemas']
        self.assertEqual(set(schemas['OperacionPublica']['properties']), set(OperacionSerializer.Meta.fields))
        self.assertEqual(set(schemas['OperacionCosto']['properties']), set(OperacionCostoSerializer.Meta.fields))
        self.assertTrue(schemas['OperacionPublica']['additionalProperties'] is False)
