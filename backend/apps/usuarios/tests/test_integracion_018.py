"""Contrato documental y recorrido HTTP de las peticiones Postman (no Runner)."""
import json
import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase, override_settings
from django.urls import resolve
from rest_framework.test import APIClient, APITestCase

from .test_administracion import AdminBase, NEW_PASSWORD, PASSWORD


DOCS = Path(settings.BASE_DIR) / "docs"


def collection():
    return json.loads((DOCS / "postman/SPEC-018.postman_collection.json").read_text(encoding="utf-8"))


class ContratoConsumoTests(SimpleTestCase):
    def test_openapi_referencias_y_rutas_resueltas(self):
        schema = json.loads((DOCS / "openapi/SPEC-018A-v1.json").read_text(encoding="utf-8"))

        def walk(value):
            if isinstance(value, dict):
                if "$ref" in value:
                    target = schema
                    self.assertTrue(value["$ref"].startswith("#/"))
                    for part in value["$ref"][2:].split("/"):
                        target = target[part]
                for item in value.values():
                    walk(item)
            elif isinstance(value, list):
                for item in value:
                    walk(item)

        walk(schema)
        for path in schema["paths"]:
            resolve(path.replace("{id}", "1"))
        for item in collection()["item"]:
            request = item["request"]
            path = request["url"].replace("{{base_url}}", "").replace("{{target_id}}", "{id}")
            self.assertIn(request["method"].lower(), schema["paths"][path])

    def test_coleccion_sin_secretos_exportados_y_con_guardas(self):
        data = collection()
        self.assertTrue(all(variable["value"] == "" for variable in data["variable"]))
        self.assertFalse(data["protocolProfileBehavior"]["followRedirects"])
        scripts = "\n".join("\n".join(event["script"]["exec"]) for event in data["event"])
        for forbidden in ("pm.environment.set", "pm.globals.set", "pm.collectionVariables.set", "console."):
            self.assertNotIn(forbidden, scripts)
        for required in ("pm.variables.get('base_url')", "SOLO_QA_AISLADO_SPEC018", "pm.vault.get", "pm.execution.skipRequest()", "pm.execution.setNextRequest(null)"):
            self.assertIn(required, scripts)
        self.assertEqual([int(item["name"][:2]) for item in data["item"]], list(range(18)))


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class RecorridoConsumoTests(AdminBase, APITestCase):
    def test_peticiones_coleccion_con_csrf_real_y_revocacion(self):
        client = APIClient(enforce_csrf_checks=True)
        values = {"base_url": "", "ti_email": self.manager.email, "ti_password": PASSWORD,
                  "target_email": "spec018-recorrido@example.test", "new_password": NEW_PASSWORD,
                  "reset_password": NEW_PASSWORD + "-Reset"}

        def render(text):
            return re.sub(r"\{\{(\w+)\}\}", lambda match: str(values[match[1]]), text)

        for step, item in enumerate(collection()["item"]):
            with self.subTest(step=step):
                req = item["request"]
                headers = {"HTTP_" + h["key"].upper().replace("-", "_"): render(h["value"])
                           for h in req.get("header", []) if h["key"] != "Content-Type"}
                payload = json.loads(render(req.get("body", {}).get("raw", "{}")))
                response = getattr(client, req["method"].lower())(render(req["url"]), payload, format="json", **headers)
                expected = 201 if step == 2 else 401 if step in (10, 11) else 204 if step == 17 else 200
                # No incluir responses/payloads secretos en mensajes de aserción.
                self.assertEqual(response.status_code, expected)
                data = response.data or {}
                if "csrfToken" in data:
                    values["csrf"] = data["csrfToken"]
                if step == 1:
                    values["ti_access"] = data["access"]
                if step in (2, 9):
                    values["temporary"] = data["credencial_temporal"]
                    self.assertEqual(data["estado_credencial"], "INICIAL" if step == 2 else "RECUPERACION")
                    self.assertIn("no-store", response["Cache-Control"])
                    if step == 2:
                        values["target_id"] = data["id"]
                        self.assertFalse(data["is_active"])
                if step == 3:
                    self.assertNotIn("credencial_temporal", data)
                    self.assertNotIn("desafio", data)
                if step in (5, 12):
                    self.assertEqual(set(data), {"estado", "desafio", "desafio_vence_en", "csrfToken"})
                    self.assertEqual(data["estado"], "CAMBIO_OBLIGATORIO")
                    values["challenge"] = data["desafio"]
                if step in (6, 13):
                    self.assertEqual(data, {"estado": "CLAVE_PERSONAL_CONFIRMADA", "login_requerido": True})
                if step in (7, 14):
                    values["target_access"] = data["access"]
                    self.assertEqual(data["user"]["email"], values["target_email"])
                if step == 15:
                    self.assertIn("access", data)
                    self.assertNotIn("refresh", data)
                if step == 16:
                    self.assertFalse(data["is_active"])
