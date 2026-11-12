from concurrent.futures import ThreadPoolExecutor
from threading import Event

from datetime import timedelta
from uuid import uuid4

from django.db import close_old_connections, connection, transaction
from django.test import TransactionTestCase, override_settings
from rest_framework.test import APIClient

from apps.alertas import services
from apps.alertas.models import Alerta, AlertaEvento
from apps.obras import services as obras
from apps.obras.models import Obra
from apps.finanzas.tests.test_concurrencia import CarrerasPostgreSQL
from apps.finanzas.tests.base import FinanzasBase
from apps.finanzas import services_documentos, services_pagos
from apps.finanzas.validaciones import hoy_santiago
from apps.usuarios.tokens import AccessToken
from apps.usuarios.models import Usuario
from .base import AlertasBase, URL


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ConcurrenciaAlertasTests(AlertasBase, CarrerasPostgreSQL, TransactionTestCase):
    def setUp(self):
        self.setUpTestData()
        self.preparar_alertas()

    def suspender_sin_callback(self):
        # Fixture de estado persistido: la reconciliación recupera callbacks perdidas.
        Obra.objects.filter(pk=self.obra.pk).update(estado="SUSPENDIDA")

    def test_dos_proyectores_creacion_no_duplican_generacion_ni_eventos(self):
        self.suspender_sin_callback()
        action = lambda: services.reconciliar_recurso("OBRA_SUSPENDIDA", self.obra.pk)
        one, two = self.race(action, action)
        self.assertEqual((one, two), (2, 0))
        self.assertEqual(Alerta.objects.count(), 2)
        self.assertEqual(AlertaEvento.objects.count(), 2)
        self.assertEqual(set(Alerta.objects.values_list("generacion", flat=True)), {1})

    def test_dos_ciclos_completos_idempotentes(self):
        self.suspender_sin_callback()
        self.race(services.reconciliar, services.reconciliar)
        self.assertEqual(Alerta.objects.count(), 2)
        self.assertEqual(AlertaEvento.objects.count(), 2)

    def test_doble_post_http_un_200_un_409_y_un_evento(self):
        a = self.suspender()
        token = str(AccessToken.for_user(self.gerencia))
        def atender():
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
            return client.post(f"{URL}{a.pk}/atender/", {"motivo": "Coordinación"}, format="json")
        one, two = self.race(atender, atender)
        self.assertEqual((one.status_code, two.status_code), (200, 409))
        self.assertEqual(two.data["code"], "alerta_ya_atendida")
        self.assertEqual(a.eventos.filter(tipo="ATENCION").count(), 1)

    def test_atencion_y_reconciliacion_comparten_lock(self):
        a = self.suspender()
        self.race(lambda: services.atender(self.gerencia, a.pk, "Coordinado"),
                  lambda: services.reconciliar_recurso(a.tipo, a.recurso_id))
        self.assertEqual(a.eventos.filter(tipo="ATENCION").count(), 1)
        a.refresh_from_db()
        self.assertEqual(a.estado, "ATENDIDA")

    def test_revalida_condicion_tras_esperar_lock_no_usa_candidato_viejo(self):
        self.suspender_sin_callback()
        def cambiar():
            services.bloquear("OBRA_SUSPENDIDA", self.obra.pk)
            Obra.objects.filter(pk=self.obra.pk).update(estado="EN_PROCESO")
        one, two = self.race(cambiar, lambda: services.reconciliar_recurso("OBRA_SUSPENDIDA", self.obra.pk))
        self.assertEqual(two, 0)
        self.assertFalse(Alerta.objects.exists())

    def test_resolucion_concurrente_evento_unico_por_rol(self):
        self.suspender()
        Obra.objects.filter(pk=self.obra.pk).update(estado="EN_PROCESO")
        action = lambda: services.reconciliar_recurso("OBRA_SUSPENDIDA", self.obra.pk)
        self.assertEqual(self.race(action, action), (2, 0))
        self.assertEqual(AlertaEvento.objects.filter(tipo="RESOLUCION").count(), 2)

    def test_otra_clave_no_espera_un_mutex_global(self):
        self.suspender_sin_callback()
        otra = self.otra_obra()
        Obra.objects.filter(pk=otra.pk).update(estado="SUSPENDIDA")
        listo, liberar = Event(), Event()
        def primero():
            from django.db import transaction
            close_old_connections()
            try:
                with transaction.atomic():
                    services.bloquear("OBRA_SUSPENDIDA", self.obra.pk)
                    listo.set()
                    if not liberar.wait(10):
                        raise AssertionError("No se liberó el lock")
            finally:
                connection.close()
        def segundo():
            close_old_connections()
            try:
                return services.reconciliar_recurso("OBRA_SUSPENDIDA", otra.pk)
            finally:
                connection.close()
        with ThreadPoolExecutor(max_workers=2) as pool:
            uno = pool.submit(primero)
            try:
                self.assertTrue(listo.wait(10))
                self.assertEqual(pool.submit(segundo).result(timeout=5), 2)
            finally:
                liberar.set()
            uno.result(timeout=10)

    def test_cambio_sesion_mientras_espera_lock_impide_atencion(self):
        a = self.suspender()
        def cambiar():
            services.bloquear(a.tipo, a.recurso_id)
            Usuario.objects.filter(pk=self.gerencia.pk).update(sesion_version=self.gerencia.sesion_version + 1)
        _, resultado = self.race(cambiar, lambda: services.atender(self.gerencia, a.pk, "Coordinado"))
        self.assertEqual(resultado.status_code, 401)
        self.assertFalse(a.eventos.filter(tipo="ATENCION").exists())


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class LocksFinanzasAlertasTests(FinanzasBase, TransactionTestCase):
    def setUp(self):
        self.setUpTestData()
        self.preparar_finanzas()
        ayer = hoy_santiago() - timedelta(days=1)
        self.doc = services_documentos.registrar_documento(self.payload(fecha_emision=ayer.isoformat(), fecha_vencimiento=ayer.isoformat()), self.finanzas)

    def test_atencion_no_invierte_locks_con_pago_en_curso(self):
        a = Alerta.objects.get(tipo="COBRANZA_VENCIDA")
        listo, liberar = Event(), Event()
        def pagar():
            close_old_connections()
            try:
                with transaction.atomic():
                    services_pagos.documento_bloqueado(self.doc.pk)
                    listo.set()
                    if not liberar.wait(10):
                        raise AssertionError("No se liberó el pago")
                    return services_pagos.registrar_pago(self.doc.pk, {"monto": "2180.35", "fecha_pago": hoy_santiago().isoformat(), "medio": "EFECTIVO", "referencia_respaldo": "Respaldo"}, self.finanzas, str(uuid4()))
            finally:
                connection.close()
        with ThreadPoolExecutor(max_workers=1) as pool:
            futuro = pool.submit(pagar)
            try:
                self.assertTrue(listo.wait(10))
                atendida = services.atender(self.gerencia, a.pk, "Pago en coordinación")
                self.assertEqual(atendida.estado, "ATENDIDA")
            finally:
                liberar.set()
            futuro.result(timeout=10)
        a.refresh_from_db()
        self.assertEqual(a.estado, "RESUELTA")
        self.assertEqual(a.eventos.count(), 3)
