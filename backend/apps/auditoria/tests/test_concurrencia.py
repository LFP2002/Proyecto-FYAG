"""Conexiones reales y confirmaciones tardías. GET nunca bloquea al escritor."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event

from django.db import close_old_connections, connection, models, transaction
from django.test import TransactionTestCase, override_settings
from django.utils import timezone

from apps.obras.models import ObraEvento
from .base import AuditoriaBase, URL


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ConcurrenciaAuditoriaTests(AuditoriaBase, TransactionTestCase):
    def setUp(self):
        self.setUpTestData()
        self.preparar_auditoria()

    def evento(self, fecha=None):
        obj = ObraEvento.objects.create(obra=self.obra, tipo="EDICION", estado_anterior="FINALIZADA", estado_nuevo="FINALIZADA", registrado_por=self.supervisor, motivo="Hecho de prueba concurrente", datos_nuevos={"estado": "FINALIZADA"})
        if fecha:
            models.QuerySet(model=ObraEvento).filter(pk=obj.pk).update(creado_en=fecha)
        return obj

    def recorrer(self, result):
        rows = []
        for _ in range(100):
            self.assertEqual(result.status_code, 200, result.data)
            rows += result.data["results"]
            if result.data["next_cursor"] is None:
                break
            result = self.client.get(URL, {"cursor": result.data["next_cursor"]})
        else:
            self.fail("Navegación no termina")
        return rows

    def test_nuevos_eventos_no_entran_a_navegacion_iniciada(self):
        first = self.client.get(URL, {"fuente": "OBRA_EVENTO", "limit": 1})
        self.assertTrue(first.data["has_more"])

        def escribir():
            close_old_connections()
            try:
                normal = self.evento()
                anterior_al_corte = self.evento(timezone.now() - timedelta(days=1))
                return normal.pk, anterior_al_corte.pk
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=1) as pool:
            nuevos = pool.submit(escribir).result(timeout=10)
        rows = self.recorrer(first)
        self.assertFalse(set(nuevos) & {e["evento_id"] for e in rows})
        self.assertEqual(len(rows), len({e["id"] for e in rows}))
        fresh = self.client.get(URL, {"fuente": "OBRA_EVENTO", "limit": 50})
        self.assertTrue(set(nuevos) <= {e["evento_id"] for e in fresh.data["results"]})

    def tardia(self, delante):
        t0 = timezone.now() - timedelta(minutes=1)
        models.QuerySet(model=ObraEvento).update(creado_en=t0)
        reservado, liberar = Event(), Event()
        info = {}

        def escritor():
            close_old_connections()
            try:
                with transaction.atomic():
                    obj = self.evento(t0 + timedelta(seconds=4 if delante else 2))
                    info["pk"] = obj.pk
                    reservado.set()
                    if not liberar.wait(10):
                        raise AssertionError("No se liberó la confirmación tardía")
                return obj.pk
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(escritor)
            try:
                self.assertTrue(reservado.wait(10))
                visible = self.evento(t0 + timedelta(seconds=3))
                self.assertLess(info["pk"], visible.pk)
                first = self.client.get(URL, {"fuente": "OBRA_EVENTO", "limit": 1})
                self.assertEqual(first.data["results"][0]["evento_id"], visible.pk)
            finally:
                liberar.set()
            pk = future.result(timeout=10)
        rows = self.recorrer(first)
        self.assertEqual(len(rows), len({e["id"] for e in rows}))
        if delante:
            self.assertNotIn(pk, {e["evento_id"] for e in rows})
        else:
            self.assertIn(pk, {e["evento_id"] for e in rows})
        fresh = self.client.get(URL, {"fuente": "OBRA_EVENTO", "limit": 50})
        self.assertIn(pk, {e["evento_id"] for e in fresh.data["results"]})

    def test_pk_reservada_confirmada_tarde_detras_puede_aparecer(self):
        self.tardia(delante=False)

    def test_pk_reservada_confirmada_tarde_delante_puede_omitirse(self):
        self.tardia(delante=True)
