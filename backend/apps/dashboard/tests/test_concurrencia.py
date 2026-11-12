"""Snapshot HTTP real contra commits concurrentes. Sin sleeps ni datos simulados."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import patch

from django.db import close_old_connections, connection
from django.test import TransactionTestCase, override_settings
from rest_framework.test import APIClient

from apps.dashboard import consultas
from apps.finanzas import services_documentos as documentos
from apps.usuarios.tokens import AccessToken
from .base import DashboardBase, RESUMEN


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class SnapshotDashboardTests(DashboardBase, TransactionTestCase):
    def setUp(self):
        self.preparar_dashboard()

    def intercalar(self, mutacion):
        observado, continuar = Event(), Event()
        original = consultas.operacion_actual
        token = str(AccessToken.for_user(self.gerencia))
        def pausa():
            datos = original()
            observado.set()
            if not continuar.wait(15):
                raise AssertionError("No se liberó la lectura")
            return datos
        def leer():
            close_old_connections()
            try:
                cliente = APIClient()
                cliente.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
                return cliente.get(RESUMEN)
            finally:
                connection.close()
        with patch("apps.dashboard.consultas.operacion_actual", side_effect=pausa), ThreadPoolExecutor(max_workers=1) as pool:
            futuro = pool.submit(leer)
            try:
                self.assertTrue(observado.wait(15))
                # La escritura debe confirmar mientras el lector está detenido;
                # un bloqueo inverso haría fallar por timeout, no pasar la prueba.
                with connection.cursor() as cursor:
                    cursor.execute("SET statement_timeout = '8s'")
                mutacion()
            finally:
                continuar.set()
                with connection.cursor() as cursor:
                    cursor.execute("SET statement_timeout = DEFAULT")
            anterior = futuro.result(timeout=15)
        posterior = self.client.get(RESUMEN)
        self.assertEqual(anterior.status_code, 200, anterior.data)
        self.assertEqual(posterior.status_code, 200, posterior.data)
        return anterior.data, posterior.data

    def test_pago_confirmado_entre_agregados_no_se_mezcla(self):
        doc = self.documento()
        antes, despues = self.intercalar(lambda: self.pago(doc))
        self.assertEqual(antes["cobranza_actual"]["abonado"], "0.00")
        self.assertEqual(antes["cobranza_actual"]["saldo"], "2180.35")
        self.assertEqual(despues["cobranza_actual"]["abonado"], "100.13")
        self.assertEqual(despues["cobranza_actual"]["saldo"], "2080.22")

    def test_anulacion_confirmada_no_mezcla_abonado_y_saldo(self):
        doc = self.documento()
        pago = self.pago(doc)
        antes, despues = self.intercalar(lambda: self.anular(doc, pago))
        self.assertEqual(antes["cobranza_actual"]["abonado"], "100.13")
        self.assertEqual(despues["cobranza_actual"]["abonado"], "0.00")
        self.assertEqual(despues["cobranza_actual"]["saldo"], "2180.35")

    def test_documento_registrado_no_entra_al_snapshot_iniciado(self):
        antes, despues = self.intercalar(self.documento)
        self.assertEqual(antes["cobranza_actual"]["documentos_vigentes"], 0)
        self.assertEqual(despues["cobranza_actual"]["documentos_vigentes"], 1)

    def test_documento_revertido_se_conserva_en_snapshot_anterior(self):
        doc = self.documento()
        antes, despues = self.intercalar(lambda: documentos.revertir_documento(doc.pk, {"motivo": "Rectificar", "referencia_rectificacion_externa": "Respaldo"}, self.finanzas))
        self.assertEqual(antes["cobranza_actual"]["documentos_vigentes"], 1)
        self.assertEqual(despues["cobranza_actual"]["documentos_vigentes"], 0)

    def test_finalizacion_cierre_y_conteos_son_del_mismo_snapshot(self):
        self.obra = self.otra_obra()
        self.completa()
        antes, despues = self.intercalar(self.finalizar)
        self.assertEqual(antes["operacion"]["obras_por_estado_actual"]["FINALIZADA"], 1)
        self.assertEqual(antes["rentabilidad_cerrada_periodo"]["obras_con_cierre"], 1)
        self.assertEqual(antes["rentabilidad_cerrada_periodo"]["costo_real_neto"], "8000.00")
        self.assertEqual(despues["operacion"]["obras_por_estado_actual"]["FINALIZADA"], 2)
        self.assertEqual(despues["rentabilidad_cerrada_periodo"]["obras_con_cierre"], 2)
        self.assertEqual(despues["rentabilidad_cerrada_periodo"]["costo_real_neto"], "16000.00")
