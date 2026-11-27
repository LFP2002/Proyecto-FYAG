"""Contrato sobre TCP real, dos procesos Daphne, PostgreSQL y Redis (sin mocks).

Runner: python manage.py test apps.chat.tests.test_ws_real --noinput
Usar exclusivamente Compose QA efímero; nunca una base institucional.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import ExitStack
from datetime import timedelta
import json
import os
import socket
import subprocess
import sys
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.db import connection, transaction
from django.test import TransactionTestCase
from django.utils import timezone
from websockets.sync.client import connect
from websockets.exceptions import ConnectionClosed, InvalidStatus

from apps.chat import services, tickets
from apps.chat.eventos import grupo
from apps.chat.models import MensajeChat, TicketChat
from apps.usuarios.models import Usuario, SeguridadCredencial, EstadoAcceso
from apps.usuarios.tokens import AccessToken
from .base import ChatBase, URL

ORIGIN = 'http://localhost:5173'


class WebSocketReal(ChatBase, TransactionTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        if not connection.settings_dict['NAME'].startswith('test_'):
            raise RuntimeError('Runner exige base test aislada.')
        cls.procesos = []
        cls.puertos = []
        cls.logs = []
        cls.prohibidos = []
        cls.addClassCleanup(cls.detener)
        for roto in (False, False, True):
            with socket.socket() as reserva:
                reserva.bind(('127.0.0.1', 0))
                port = reserva.getsockname()[1]
            env = {**os.environ, 'POSTGRES_DB': connection.settings_dict['NAME'],
                   'FYAG_CHAT_WS_HEARTBEAT': '1', 'PYTHONDONTWRITEBYTECODE': '1',
                   'FYAG_BLOQUEOS_C2': 'QA_AISLADO_C2', 'FYAG_C2_TI_QA_IDS': '900001,900002',
                   'FYAG_C2_RECUPERACION_QA': 'CONFIRMADA', 'FYAG_C2_RIESGO_DOS_QA': 'ACEPTADO',
                   'FYAG_C2_RESPUESTAS': '401_GENERICO', 'FYAG_C2_SESIONES_TEMPORALES': 'REVOCAR_TODAS_QA'}
            if roto:
                env['FYAG_CHAT_REDIS_PORT'] = '1'
            from tempfile import TemporaryFile
            log = TemporaryFile()
            cls.logs.append(log)
            proc = subprocess.Popen([sys.executable, '-m', 'daphne', '-b', '127.0.0.1', '-p', str(port),
                '--verbosity', '0', '--websocket_connect_timeout', '5',
                '--websocket-max-message-size', '1024', '--websocket-max-frame-size', '1024',
                'config.asgi:application'], env=env, stdout=log, stderr=log)
            cls.procesos.append(proc); cls.puertos.append(port)
            deadline = time.monotonic()+20
            while True:
                if proc.poll() is not None or time.monotonic() > deadline:
                    log.seek(0)
                    raise RuntimeError('Daphne no disponible: '+log.read().decode(errors='replace'))
                try:
                    with socket.create_connection(('127.0.0.1', port), timeout=.2):
                        break
                except OSError:
                    time.sleep(.1)

    @classmethod
    def detener(cls):
        for proc in cls.procesos:
            proc.terminate()
        for proc in cls.procesos:
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill(); proc.wait(timeout=5)
        for log in cls.logs:
            log.seek(0)
            contenido = log.read()
            log.close()
            if any(value.encode() in contenido for value in cls.prohibidos):
                raise AssertionError('Log ASGI contiene credencial o contenido privado de QA.')

    def setUp(self):
        self.preparar()
        for pk in (900001, 900002):
            Usuario.objects.create_user(pk=pk, username=f'ti_ws_qa_{pk}', email=f'ti{pk}@ws.test', rol='ADMINISTRADOR_TI')

    def http(self, path, user=None, data=None, proceso=0):
        token = str(AccessToken.for_user(user or self.actor))
        self.prohibidos.append(token)
        headers = {'Authorization': 'Bearer '+token}
        raw = None
        if data is not None:
            headers['Content-Type'] = 'application/json'; raw = json.dumps(data).encode()
            if data.get('texto'):
                self.prohibidos.append(data['texto'])
        req = Request(f'http://127.0.0.1:{self.puertos[proceso]}'+path, data=raw, headers=headers)
        try:
            response = urlopen(req, timeout=10)
        except HTTPError as error:
            response = error
        with response:
            contenido = json.loads(response.read())
            if 'ticket' in contenido:
                self.prohibidos.append(contenido['ticket'])
            return response.status, contenido

    def abrir(self, proceso=0, **kwargs):
        return connect(f'ws://127.0.0.1:{self.puertos[proceso]}/ws/chat/', origin=ORIGIN,
                       open_timeout=5, close_timeout=1, proxy=None, **kwargs)

    def autenticar_socket(self, ws, user=None):
        status, data = self.http(URL+'conexion/', user, {})
        self.assertEqual(status, 201)
        ws.send(json.dumps({'tipo': 'autenticar', 'ticket': data['ticket']}))
        self.assertEqual(json.loads(ws.recv(timeout=5)), {'tipo': 'chat.conectado'})

    def silencio(self, ws):
        with self.assertRaises(TimeoutError):
            ws.recv(timeout=.25)

    def cerrado(self, ws, code):
        with self.assertRaises(ConnectionClosed) as error:
            ws.recv(timeout=7)
        self.assertEqual(error.exception.rcvd.code, code)

    def test_http_ws_dos_procesos_y_usuarios_replay_y_ajeno(self):
        conv = self.directa()
        with self.abrir() as a, self.abrir(1) as b, self.abrir(1) as ajeno:
            self.autenticar_socket(a); self.autenticar_socket(b, self.otro); self.autenticar_socket(ajeno, self.ajeno)
            payload = {'texto': 'Privado solo PostgreSQL', 'clave_idempotencia': str(uuid4())}
            path = URL+f'conversaciones/{conv.pk}/mensajes/'
            status, data = self.http(path, data=payload)
            self.assertEqual(status, 201)
            esperado = {'tipo': 'chat.mensaje', 'conversacion_id': conv.pk, 'ultimo_mensaje_id': data['id']}
            self.assertEqual(json.loads(a.recv(timeout=5)), esperado)
            self.assertEqual(json.loads(b.recv(timeout=5)), esperado)
            self.silencio(ajeno)
            self.assertEqual(self.http(path, data=payload)[0], 200)
            self.silencio(a); self.silencio(b)
            self.assertEqual(MensajeChat.objects.filter(conversacion=conv).count(), 1)
            self.assertEqual(self.http(path, self.ajeno)[0], 404)
            self.assertEqual(self.http(path, self.otro)[1]['results'][0]['texto'], payload['texto'])

    def test_commit_y_rollback_sin_avisos_prematuros(self):
        conv = self.directa()
        with self.abrir(1) as ws:
            self.autenticar_socket(ws, self.otro)
            with transaction.atomic():
                mensaje = self.enviar(conv)
                self.silencio(ws)
            self.assertEqual(json.loads(ws.recv(timeout=5))['ultimo_mensaje_id'], mensaje.pk)
            try:
                with transaction.atomic():
                    self.enviar(conv)
                    raise ValueError('rollback QA')
            except ValueError:
                pass
            self.silencio(ws)
            self.assertEqual(MensajeChat.objects.count(), 1)

    def test_ticket_concurrente_multiproceso(self):
        status, data = self.http(URL+'conexion/', data={})
        self.assertEqual(status, 201)
        with self.abrir() as a, self.abrir(1) as b:
            frame = json.dumps({'tipo': 'autenticar', 'ticket': data['ticket']})
            def intentar(ws):
                ws.send(frame)
                try:
                    return json.loads(ws.recv(timeout=5))['tipo']
                except ConnectionClosed as error:
                    return error.rcvd.code
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(intentar, (a, b)))
            self.assertCountEqual(results, ['chat.conectado', 4401])

    def test_origin_query_subprotocolo_ausente_y_ajeno(self):
        base = f'ws://127.0.0.1:{self.puertos[0]}/ws/chat/'
        for origin, suffix, protocols in [(None, '', None), ('http://ajeno.test', '', None),
                (ORIGIN, '?token=no-secreto-qa', None), (ORIGIN, '', ['jwt-no-secreto-qa'])]:
            with self.subTest(origin=origin, suffix=suffix, protocols=protocols), self.assertRaises(InvalidStatus):
                with connect(base+suffix, origin=origin, subprotocols=protocols, proxy=None):
                    self.fail('Origin/opciones no autorizados')

    def test_timeout_y_frames_invalidos(self):
        with self.abrir() as ws:
            self.cerrado(ws, 4408)
        for frame in ('{', '{"tipo":"ping"}', '{"tipo":"autenticar","ticket":"falso"}', b'binario'):
            with self.subTest(frame=frame), self.abrir() as ws:
                ws.send(frame)
                self.cerrado(ws, 4401 if 'falso' in str(frame) else 4400)

    def test_tamano_frecuencia_y_cupo_usuario(self):
        with self.abrir() as ws:
            ws.send('x'*1025)
            # Autobahn puede abortar transporte antes de entregar frame a ASGI.
            with self.assertRaises(ConnectionClosed) as error:
                ws.recv(timeout=7)
            self.assertIn(error.exception.rcvd.code if error.exception.rcvd else 1006, (1009, 1006))
        with self.abrir() as ws:
            self.autenticar_socket(ws)
            for _ in range(9):
                ws.send('{"tipo":"ping"}')
                self.assertEqual(json.loads(ws.recv(timeout=5)), {'tipo': 'pong'})
            ws.send('{"tipo":"ping"}'); self.cerrado(ws, 4429)
        with ExitStack() as stack:
            sockets = [stack.enter_context(self.abrir(i % 2)) for i in range(4)]
            for ws in sockets[:3]:
                self.autenticar_socket(ws)
            status, data = self.http(URL+'conexion/', data={})
            self.assertEqual(status, 201)
            sockets[3].send(json.dumps({'tipo': 'autenticar', 'ticket': data['ticket']}))
            self.cerrado(sockets[3], 4429)

    def test_revocacion_periodica_sesion_password_e_inactivo(self):
        for campo in ('sesion_version', 'password', 'is_active'):
            with self.subTest(campo=campo):
                self.actor.refresh_from_db()
                with self.abrir() as ws:
                    self.autenticar_socket(ws)
                    value = {'sesion_version': self.actor.sesion_version+1, 'password': '!revocado', 'is_active': False}[campo]
                    Usuario.objects.filter(pk=self.actor.pk).update(**{campo: value})
                    self.cerrado(ws, 4401)

    def test_recuperacion_correo_revoca_socket_y_ticket_pendiente(self):
        from secrets import token_urlsafe
        from apps.usuarios.models import DesafioRecuperacionCorreo
        from apps.usuarios.recuperacion_correo import _digest, _vinculo, confirmar

        self.actor.correo_verificado_en = timezone.now()
        self.actor.save(update_fields=['correo_verificado_en'])
        secret = token_urlsafe(32)
        clave = 'Nueva-clave-qa-WebSocket-981!'
        self.prohibidos.extend([secret, clave])
        DesafioRecuperacionCorreo.objects.create(usuario=self.actor, digest=_digest(secret),
            vinculo=_vinculo(self.actor, SeguridadCredencial.objects.get(usuario=self.actor)),
            vence_en=timezone.now() + timedelta(minutes=15))
        with self.abrir() as ws:
            self.autenticar_socket(ws)
            status, data = self.http(URL + 'conexion/', data={})
            self.assertEqual(status, 201)
            confirmar(secret, clave)
            self.cerrado(ws, 4401)
            with self.abrir(1) as nuevo:
                nuevo.send(json.dumps({'tipo': 'autenticar', 'ticket': data['ticket']}))
                self.cerrado(nuevo, 4401)

    def test_evento_inyectado_ajeno_no_autoriza(self):
        conv = self.directa(); mensaje = self.enviar(conv)
        with self.abrir(1) as ws:
            self.autenticar_socket(ws, self.ajeno)
            async_to_sync(get_channel_layer().group_send)(grupo(self.ajeno.pk),
                {'type': 'chat.mensaje', 'conversacion_id': conv.pk, 'ultimo_mensaje_id': mensaje.pk})
            self.silencio(ws)

    def test_redis_inaccesible_http_201_reconexion_recupera(self):
        conv = self.directa()
        path = URL+f'conversaciones/{conv.pk}/mensajes/'
        payload = {'texto': 'Persistido sin Redis', 'clave_idempotencia': str(uuid4())}
        status, data = self.http(path, data=payload, proceso=2)
        self.assertEqual(status, 201)
        with self.abrir(1) as ws:
            self.autenticar_socket(ws, self.otro)
            self.assertEqual(self.http(path, self.otro)[1]['results'][0]['id'], data['id'])
            self.assertEqual(self.http(path, data=payload)[0], 200)
            self.silencio(ws)
        self.assertEqual(MensajeChat.objects.count(), 1)

    def test_ticket_expirado_reutilizado_y_credencial_temporal(self):
        # Ticket expirado genuino, sin modificar reloj ni SQL existente.
        ahora = timezone.now()
        nonce = 'e'*43
        falso_expirado = nonce+'.'+'a'*64
        import hashlib
        TicketChat.objects.create(digest=hashlib.sha256(falso_expirado.encode()).hexdigest(),
            usuario=self.actor, sesion_version=self.actor.sesion_version,
            creado_en=ahora-timedelta(seconds=60), vence_en=ahora-timedelta(seconds=30))
        with self.abrir() as ws:
            ws.send(json.dumps({'tipo': 'autenticar', 'ticket': falso_expirado}))
            self.cerrado(ws, 4401)
        status, data = self.http(URL+'conexion/', data={})
        self.assertEqual(status, 201)
        frame = json.dumps({'tipo': 'autenticar', 'ticket': data['ticket']})
        with self.abrir() as ws:
            ws.send(frame)
            self.assertEqual(json.loads(ws.recv(timeout=5)), {'tipo': 'chat.conectado'})
        with self.abrir(1) as ws:
            ws.send(frame); self.cerrado(ws, 4401)
        # La credencial cambia con socket abierto: revalidación periódica real.
        with self.abrir() as ws:
            self.autenticar_socket(ws)
            SeguridadCredencial.objects.filter(usuario=self.actor).update(estado='INICIAL',
                emitida_en=ahora, vence_en=ahora+timedelta(hours=1))
            self.cerrado(ws, 4401)
        self.assertEqual(self.http(URL+'conexion/', data={})[0], 401)

    def test_bloqueo_operativo_c2_revoca_socket(self):
        from apps.usuarios.politica_bloqueos import DURACIONES
        with self.abrir() as ws:
            self.autenticar_socket(ws)
            ahora = timezone.now()
            EstadoAcceso.objects.filter(usuario=self.actor).update(estado='BLOQUEO_TEMPORAL',
                bloqueo_inicio=ahora, bloqueado_hasta=ahora+DURACIONES[0],
                ciclos_en=[ahora], actualizado_en=ahora)
            self.cerrado(ws, 4401)
        self.assertEqual(self.http(URL+'conexion/', data={})[0], 401)

    def test_cupo_pendientes_real_compartido(self):
        with ExitStack() as stack:
            for i in range(8):
                stack.enter_context(self.abrir(i % 2))
            with self.assertRaises(InvalidStatus):
                with self.abrir(1):
                    self.fail('Noveno pendiente de la misma IP fue admitido')

    def test_ti_superusuario_sin_privilegios_y_sin_grupos_cliente(self):
        conv = self.directa()
        ti = next(user for user in self.users if user.rol == 'ADMINISTRADOR_TI')
        ti.is_superuser = True; ti.save(update_fields=['is_superuser'])
        with self.abrir(1) as ws:
            self.autenticar_socket(ws, ti)
            self.enviar(conv)
            self.silencio(ws)
            self.assertEqual(self.http(URL+f'conversaciones/{conv.pk}/mensajes/', ti)[0], 404)
            ws.send(json.dumps({'tipo': 'suscribir', 'grupo': grupo(self.actor.pk)}))
            self.cerrado(ws, 4400)

    def test_redis_pausado_conserva_publicacion(self):
        # Pausa solo Redis efímero QA; se recupera automáticamente, sin Docker API.
        from django.conf import settings
        from redis import Redis
        config = settings.CHANNEL_LAYERS['default']['CONFIG']['hosts'][0]
        redis = Redis(**config)
        conv = self.directa()
        path = URL+f'conversaciones/{conv.pk}/mensajes/'
        payload = {'texto': 'QA pausa Redis sin perder mensaje', 'clave_idempotencia': str(uuid4())}
        try:
            redis.client_pause(3500)
            status, data = self.http(path, data=payload)
            self.assertEqual(status, 201)
            self.assertTrue(MensajeChat.objects.filter(pk=data['id']).exists())
            self.assertTrue(redis.ping())  # Espera recuperación automática de la pausa.
            self.assertEqual(self.http(path, data=payload)[0], 200)
            self.assertEqual(self.http(path, self.otro)[1]['results'][0]['id'], data['id'])
            self.assertEqual(MensajeChat.objects.count(), 1)
        finally:
            redis.close()
