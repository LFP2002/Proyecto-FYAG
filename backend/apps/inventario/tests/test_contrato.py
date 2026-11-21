import json
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase
from django.urls import resolve

from apps.usuarios.models import Usuario


class Contrato019ATests(SimpleTestCase):
    def test_openapi_rutas_y_roles_reales(self):
        data = json.loads((Path(settings.BASE_DIR) / "docs/openapi/SPEC-019A-v1.json").read_text(encoding="utf-8"))
        self.assertEqual(data["openapi"], "3.1.0")
        self.assertEqual(data["components"]["schemas"]["Rol019A"]["enum"], list(Usuario.Rol.values))
        self.assertEqual(len(data["paths"]), 5)
        for path, methods in data["paths"].items():
            match = resolve(path.replace("{id}", "1"))
            for method in set(methods) - {"parameters"}:
                self.assertIn(method, {"get", "post", "patch"})
                if hasattr(match.func, "actions"):
                    self.assertIn(method, match.func.actions)
                else:
                    self.assertTrue(hasattr(match.func.view_class, method))
