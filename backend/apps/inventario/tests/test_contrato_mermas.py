import json
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase
from django.urls import resolve

from apps.inventario.serializers_mermas import MermaSerializer
from apps.inventario.serializers_materiales import AutorizacionDevolucionLecturaSerializer


class ContratoMermasTests(SimpleTestCase):
    def test_rutas_campos_y_contrato_019b_aditivo(self):
        base = Path(settings.BASE_DIR)/'docs/openapi'
        spec = json.loads((base/'SPEC-019C-2-v1.json').read_text(encoding='utf-8'))
        self.assertEqual(spec['openapi'], '3.1.0')
        self.assertEqual(len(spec['paths']), 6)
        for ruta, metodos in spec['paths'].items():
            match = resolve(ruta.replace('{id}', '1'))
            for metodo in set(metodos)-{'parameters'}:
                self.assertTrue(hasattr(match.func.view_class, metodo))
        props = spec['components']['schemas']['MermaBase']['properties']
        self.assertEqual(set(props)-{'historial'}, set(MermaSerializer.Meta.fields))
        anterior = json.loads((base/'SPEC-019B-v1.json').read_text(encoding='utf-8'))
        self.assertEqual(set(anterior['components']['schemas']['AutorizacionRetornable']['properties']),
            set(AutorizacionDevolucionLecturaSerializer.Meta.fields))
