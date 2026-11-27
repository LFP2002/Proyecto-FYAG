from unittest.mock import patch

from django.db import OperationalError
from django.test import SimpleTestCase


class HealthTests(SimpleTestCase):
    def test_live_does_not_require_sql(self):
        with patch("config.health.connections") as connections:
            response = self.client.get("/health/live/")
        connections.__getitem__.assert_not_called()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})
        self.assertIn("no-store", response["Cache-Control"])

    def test_ready_uses_default_connection(self):
        with patch("config.health.connections") as connections:
            cursor = connections.__getitem__.return_value.cursor.return_value.__enter__.return_value
            response = self.client.get("/health/ready/")
        connections.__getitem__.assert_called_once_with("default")
        cursor.execute.assert_called_once_with("SELECT 1")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_ready_sanitizes_sql_failures(self):
        with patch("config.health.connections") as connections:
            connections.__getitem__.return_value.cursor.side_effect = OperationalError("private test data")
            response = self.client.get("/health/ready/")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json(), {"status": "unavailable"})
        self.assertIn("no-store", response["Cache-Control"])

    def test_health_does_not_accept_writes(self):
        for endpoint in ("live", "ready"):
            self.assertEqual(self.client.post(f"/health/{endpoint}/").status_code, 405)
