from concurrent.futures import ThreadPoolExecutor
from threading import Event, current_thread
from time import monotonic
from uuid import uuid4
from unittest.mock import patch

from django.db import connection, transaction, close_old_connections
from django.test import TransactionTestCase, override_settings

from apps.finanzas.tests.test_concurrencia import CarrerasPostgreSQL
from apps.chat import services, almacen
from apps.chat.models import MensajeChat, ArchivoChat, ParticipanteChat, ConversacionChat
from apps.usuarios.models import Usuario
from .base import ChatBase, imagen


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class ConcurrenciaChatTests(ChatBase, CarrerasPostgreSQL, TransactionTestCase):
    def setUp(self):
        self.preparar()

    def test_directa_pareja_inversa_dos_uuid(self):
        a, b = self.entrada_directa(), self.entrada_directa(self.actor)
        one, two = self.race(lambda: services.crear_conversacion(a, self.actor), lambda: services.crear_conversacion(b, self.otro))
        self.assertEqual(one[0].pk, two[0].pk)
        self.assertEqual((one[1], two[1]), (True, False))

    def test_conversacion_misma_uuid_misma_carga(self):
        data = self.entrada_directa()
        action = lambda: services.crear_conversacion(data, self.actor)
        one, two = self.race(action, action)
        self.assertEqual(one[0].pk, two[0].pk)
        self.assertFalse(two[1])

    def test_conversacion_misma_uuid_distinta_carga(self):
        data = self.entrada_directa()
        _, two = self.race(lambda: services.crear_conversacion(data, self.actor),
            lambda: services.crear_conversacion({**data, 'destinatario': self.ajeno.pk}, self.actor))
        self.assertEqual(two.status_code, 409)

    def test_mensaje_misma_uuid_mismo_texto(self):
        c = self.directa(); data = {'texto': 'QA', 'clave_idempotencia': str(uuid4())}
        action = lambda: services.publicar_texto(c.pk, data, self.actor)
        one, two = self.race(action, action)
        self.assertEqual(one[0].pk, two[0].pk)
        self.assertFalse(two[1])
        self.assertEqual(MensajeChat.objects.filter(conversacion=c).count(), 1)

    def test_mensaje_misma_uuid_distinto_texto(self):
        c = self.directa(); data = {'texto': 'QA', 'clave_idempotencia': str(uuid4())}
        _, two = self.race(lambda: services.publicar_texto(c.pk, data, self.actor), lambda: services.publicar_texto(c.pk, {**data, 'texto': 'Otro'}, self.actor))
        self.assertEqual(two.status_code, 409)

    def test_dos_mensajes_distintos_se_serializan_por_conversacion(self):
        c = self.directa()
        one, two = self.race(lambda: self.enviar(c), lambda: self.enviar(c, actor=self.otro))
        self.assertNotEqual(one.pk, two.pk)
        self.assertEqual(MensajeChat.objects.filter(conversacion=c).count(), 2)

    def test_lectura_no_retrocede_durante_carrera(self):
        c = self.directa(); viejo, nuevo = self.enviar(c), self.enviar(c)
        _, two = self.race(lambda: services.leer(c.pk, {'ultimo_mensaje_id': nuevo.pk}, self.actor),
            lambda: services.leer(c.pk, {'ultimo_mensaje_id': viejo.pk}, self.actor))
        self.assertEqual(two.ultimo_leido_mensaje_id, nuevo.pk)

    def test_sesion_revocada_mientras_espera_conversacion(self):
        c = self.directa()
        def revocar():
            ConversacionChat.objects.select_for_update().get(pk=c.pk)
            Usuario.objects.filter(pk=self.actor.pk).update(sesion_version=self.actor.sesion_version+1)
        _, two = self.race(revocar, lambda: self.enviar(c))
        self.assertEqual(two.status_code, 401)
        self.assertFalse(MensajeChat.objects.filter(conversacion=c).exists())

    def test_inactivo_mientras_espera_conversacion(self):
        c = self.directa()
        def revocar():
            ConversacionChat.objects.select_for_update().get(pk=c.pk)
            Usuario.objects.filter(pk=self.actor.pk).update(is_active=False)
        _, two = self.race(revocar, lambda: self.enviar(c))
        self.assertEqual(two.status_code, 401)

    def test_dos_retiros_fisicos_mismo_recibo(self):
        self.storage()
        row = ArchivoChat.objects.create()
        with almacen.Staging(row.clave_interna) as stage:
            stage.file.write(b'QA'); stage.publicar()
        row.estado = 'RETIRAR'; row.save(update_fields=['estado'])
        self.race(lambda: services.retirar_recibo(row.pk), lambda: services.retirar_recibo(row.pk))
        self.assertFalse(ArchivoChat.objects.filter(pk=row.pk).exists())

    def test_dos_uploads_misma_uuid_un_archivo_con_bloqueo_observado(self):
        self.storage(); c = self.directa(); key = str(uuid4())
        ready, release, started = Event(), Event(), Event()
        pids = {}
        original = almacen.Staging.publicar
        def publicar(stage):
            original(stage)
            if current_thread().name.endswith('_0'):
                ready.set()
                if not release.wait(10):
                    raise AssertionError('No se liberó publicación')
        def worker(index):
            close_old_connections()
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SET lock_timeout='10s'")
                    cursor.execute('SELECT pg_backend_pid()'); pids[index] = cursor.fetchone()[0]
                if index == 2:
                    started.set()
                return services.publicar_archivo(c.pk, {'archivo': imagen()}, key, self.actor)
            finally:
                connection.close()
        with patch('apps.chat.archivos.analizar'), patch.object(almacen.Staging, 'publicar', publicar), ThreadPoolExecutor(max_workers=2) as pool:
            one = pool.submit(worker, 1)
            try:
                self.assertTrue(ready.wait(10))
                two = pool.submit(worker, 2)
                self.assertTrue(started.wait(10))
                observado = False; deadline = monotonic()+5
                while monotonic() < deadline:
                    with connection.cursor() as cursor:
                        cursor.execute('SELECT pg_blocking_pids(%s)', [pids[2]])
                        if pids[1] in cursor.fetchone()[0]:
                            observado = True; break
                    if two.done():
                        break
                self.assertTrue(observado)
            finally:
                release.set()
            a, b = one.result(timeout=15), two.result(timeout=15)
        self.assertEqual((a[0].pk, a[1], b[1]), (b[0].pk, True, False))
        self.assertEqual(ArchivoChat.objects.filter(mensaje__conversacion=c).count(), 1)
