import json
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase
from django.urls import resolve


class ContratoC2Tests(SimpleTestCase):
    def test_openapi_y_coleccion_sin_423_o_rutas_inventadas(self):
        root = Path(settings.BASE_DIR) / "docs"
        schema = json.loads((root / "openapi/SPEC-018C-C2-v1.json").read_text(encoding="utf-8"))
        base = json.loads((root / "openapi/SPEC-018A-v1.json").read_text(encoding="utf-8"))
        collection = json.loads((root / "postman/SPEC-018C-C2.postman_collection.json").read_text(encoding="utf-8"))
        self.assertEqual(schema["openapi"], "3.1.0")
        for path, methods in schema["paths"].items():
            resolve(path.replace("{id}", "1"))
            for method, operation in methods.items():
                if method != "parameters":
                    self.assertNotIn("423", operation["responses"])
        self.assertEqual(len(collection["item"]), 20)
        for item in collection["item"]:
            path = item["request"]["url"].replace("{{base_url}}", "").replace("{{target_id}}", "{id}")
            methods = schema["paths"].get(path, {}) | base["paths"].get(path, {})
            self.assertIn(item["request"]["method"].lower(), methods)

    def test_coleccion_opt_in_local_sin_secretos_persistidos(self):
        root = Path(settings.BASE_DIR) / "docs"
        data = json.loads((root / "postman/SPEC-018C-C2.postman_collection.json").read_text(encoding="utf-8"))
        self.assertTrue(all(v["value"] == "" for v in data["variable"]))
        self.assertFalse(data["protocolProfileBehavior"]["followRedirects"])
        text = "\n".join("\n".join(e["script"]["exec"]) for e in data["event"])
        for forbidden in ("pm.environment.set", "pm.globals.set", "pm.collectionVariables.set", "console."):
            self.assertNotIn(forbidden, text)
        for required in ("pm.variables.get('base_url')", "pm.vault.get", "16000", "JSON.stringify(body)", "pm.execution.skipRequest()"):
            self.assertIn(required, text)
