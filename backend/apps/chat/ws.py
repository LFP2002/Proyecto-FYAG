"""Socket de avisos. Identidad propia, sin suscripciones o escrituras del cliente."""
import asyncio
from collections import deque
import json
import logging

from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.conf import settings

from . import tickets
from .eventos import grupo
from .parsers import _objeto

logger = logging.getLogger(__name__)


class OriginChat:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        origins = [v for k, v in scope.get('headers', []) if k.lower() == b'origin']
        try:
            origin = origins[0].decode('ascii') if len(origins) == 1 else None
        except UnicodeError:
            origin = None
        if (origin not in settings.CHAT_WS_ALLOWED_ORIGINS or scope.get('query_string')
            or scope.get('subprotocols') or scope.get('path') != '/ws/chat/'):
            await send({'type': 'websocket.close', 'code': 4403})
            return
        await self.app(scope, receive, send)


class ChatConsumer(AsyncWebsocketConsumer):
    async def __call__(self, scope, receive, send):
        self.identidad = self.canal_id = self.grupo = None
        self.cerrado = False
        self.tareas = []
        self.candado = asyncio.Lock()
        self.frames = deque()
        try:
            await super().__call__(scope, receive, send)
        except Exception as error:
            logger.warning('chat_ws_no_disponible %s', type(error).__name__)
            try:
                await send({'type': 'websocket.close', 'code': 4503})
            except Exception:
                pass
        finally:
            self.cerrado = True
            for tarea in self.tareas:
                tarea.cancel()
            await asyncio.gather(*self.tareas, return_exceptions=True)
            if self.grupo:
                try:
                    await asyncio.wait_for(self.channel_layer.group_discard(self.grupo, self.channel_name), settings.CHAT_WS_IO_TIMEOUT)
                except Exception:
                    pass
            if self.canal_id:
                try:
                    await self._db(tickets.liberar, self.canal_id)
                except Exception:
                    pass  # Lease caduca; no retener un cupo indefinidamente tras caída.

    async def _db(self, funcion, *args, timeout=None, **kwargs):
        return await asyncio.wait_for(database_sync_to_async(funcion)(*args, **kwargs), timeout or settings.CHAT_WS_IO_TIMEOUT)

    async def _cerrar(self, code):
        if not self.cerrado:
            self.cerrado = True
            await self.close(code=code)

    async def connect(self):
        self.deadline = asyncio.get_running_loop().time()+settings.CHAT_WS_AUTH_TIMEOUT
        ip = str((self.scope.get('client') or ('', 0))[0])
        try:
            self.canal_id = await self._db(tickets.admitir, ip)
        except tickets.CupoAgotado:
            await self._cerrar(4429); return
        except Exception:
            await self._cerrar(4503); return
        await self.accept()
        self.tareas.append(asyncio.create_task(self._autenticacion_timeout()))

    async def _autenticacion_timeout(self):
        await asyncio.sleep(max(0, self.deadline-asyncio.get_running_loop().time()))
        async with self.candado:
            if self.identidad is None:
                await self._cerrar(4408)

    async def _vigente(self, *, renovar=False, conversacion_id=None, mensaje_id=None):
        try:
            return await self._db(tickets.verificar, self.identidad, self.canal_id,
                renovar=renovar, conversacion_id=conversacion_id, mensaje_id=mensaje_id)
        except tickets.Denegado:
            await self._cerrar(4401)
        except Exception as error:
            logger.warning('chat_ws_verificacion_no_disponible %s', type(error).__name__)
            await self._cerrar(4503)
        return False

    async def _autenticar(self, ticket):
        self.identidad = await self._db(tickets.consumir, ticket, self.canal_id)
        self.grupo = grupo(self.identidad.usuario_id)
        await asyncio.wait_for(self.channel_layer.group_add(self.grupo, self.channel_name), settings.CHAT_WS_IO_TIMEOUT)
        if await self._vigente():
            await self.send(text_data=json.dumps({'tipo': 'chat.conectado'}))
            self.tareas.append(asyncio.create_task(self._heartbeat()))

    async def receive(self, text_data=None, bytes_data=None):
        async with self.candado:
            if self.cerrado:
                return
            if text_data is None or len(text_data.encode('utf-8')) > settings.CHAT_WS_MAX_BYTES:
                await self._cerrar(1009 if text_data is not None else 4400); return
            ahora = asyncio.get_running_loop().time()
            while self.frames and self.frames[0] <= ahora-settings.CHAT_WS_LIMITES['ventana_frames']:
                self.frames.popleft()
            self.frames.append(ahora)
            if len(self.frames) > settings.CHAT_WS_LIMITES['frames']:
                await self._cerrar(4429); return
            try:
                data = json.loads(text_data, object_pairs_hook=_objeto)
            except (ValueError, RecursionError):
                await self._cerrar(4400); return
            if self.identidad is None:
                if type(data) is not dict or set(data) != {'tipo', 'ticket'} or data['tipo'] != 'autenticar':
                    await self._cerrar(4400); return
                restante = self.deadline-ahora
                if restante <= 0:
                    await self._cerrar(4408); return
                try:
                    await asyncio.wait_for(self._autenticar(data['ticket']), restante)
                except tickets.Denegado:
                    await self._cerrar(4401)
                except tickets.CupoAgotado:
                    await self._cerrar(4429)
                except asyncio.TimeoutError:
                    await self._cerrar(4408 if asyncio.get_running_loop().time() >= self.deadline else 4503)
                except Exception:
                    await self._cerrar(4503)
            elif data == {'tipo': 'ping'} or data == {'tipo': 'pong'}:
                if await self._vigente() and data['tipo'] == 'ping':
                    await self.send(text_data=json.dumps({'tipo': 'pong'}))
            else:
                await self._cerrar(4400)

    async def _heartbeat(self):
        while not self.cerrado:
            await asyncio.sleep(settings.CHAT_WS_HEARTBEAT)
            async with self.candado:
                if self.cerrado or not await self._vigente(renovar=True):
                    return
                try:
                    await asyncio.wait_for(self.channel_layer.group_add(self.grupo, self.channel_name), settings.CHAT_WS_IO_TIMEOUT)
                except Exception:
                    await self._cerrar(4503); return

    async def chat_mensaje(self, evento):
        async with self.candado:
            if self.cerrado or self.identidad is None:
                return
            conv, mensaje = evento.get('conversacion_id'), evento.get('ultimo_mensaje_id')
            if any(type(pk) is not int or not 0 < pk <= 9223372036854775807 for pk in (conv, mensaje)):
                return
            if await self._vigente(conversacion_id=conv, mensaje_id=mensaje):
                await self.send(text_data=json.dumps({'tipo': 'chat.mensaje', 'conversacion_id': conv, 'ultimo_mensaje_id': mensaje}))
