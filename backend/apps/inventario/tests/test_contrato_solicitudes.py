import json
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase
from django.urls import resolve

from apps.inventario.serializers_solicitudes import SolicitudSerializer, SolicitudDetalleSerializer, ArticuloSolicitableSerializer


class ContratoSolicitudesTests(SimpleTestCase):
    def test_openapi_refleja_rutas_campos_y_proyecciones_cerradas(self):
        spec = json.loads((Path(settings.BASE_DIR)/'docs/openapi/SPEC-019C-1-v1.json').read_text(encoding='utf-8'))
        self.assertEqual(spec['openapi'], '3.1.0')
        self.assertEqual(len(spec['paths']), 4)
        for path, metodos in spec['paths'].items():
            match = resolve(path.replace('{id}', '1'))
            for metodo in set(metodos)-{'parameters'}:
                self.assertTrue(hasattr(match.func.view_class, metodo))
        for schema, serializer in [('Solicitud', SolicitudSerializer), ('SolicitudDetalle', SolicitudDetalleSerializer), ('ArticuloSolicitable', ArticuloSolicitableSerializer)]:
            self.assertEqual(set(spec['components']['schemas'][schema]['properties']), set(serializer.Meta.fields))
            self.assertFalse(spec['components']['schemas'][schema]['additionalProperties'])
