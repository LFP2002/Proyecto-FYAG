from unittest.mock import patch

from rest_framework.exceptions import PermissionDenied

from apps.documentos import services
from apps.usuarios.models import Usuario
from .base import DocumentosBase


class Metadatos020ATests(DocumentosBase):
    def test_servicio_deniega_gerencia_y_revalida_rol_antes_del_cas(self):
        self.proyectar()
        antes = self.col.find_one()
        with self.assertRaises(PermissionDenied):
            services.editar(self.gerencia, self.evidencia.pk, 0, {'descripcion': 'No autorizado'}, '020a')
        self.assertEqual(self.col.find_one(), antes)
        original = services.validar_documento

        def cambiar_rol(documento, row):
            resultado = original(documento, row)
            Usuario.objects.filter(pk=self.supervisor.pk).update(rol='GERENCIA')
            return resultado

        with patch.object(services, 'validar_documento', side_effect=cambiar_rol):
            with self.assertRaises(PermissionDenied):
                services.editar(self.supervisor, self.evidencia.pk, 0, {'descripcion': 'No autorizado'}, '020a')
        self.assertEqual(self.col.find_one(), antes)
