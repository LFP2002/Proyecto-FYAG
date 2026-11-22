"""Avisos mínimos best-effort, siempre después del commit, sin contenido ni secretos."""
import asyncio
import logging

from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from channels.layers import get_channel_layer
from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone

from apps.usuarios.acceso import sesion_operativa
from .consultas import elegibles
from .models import MensajeChat

logger = logging.getLogger(__name__)


def grupo(usuario_id):
    return f'chat.usuario.{usuario_id}'


@database_sync_to_async
@transaction.atomic
def _destinatarios(conversacion_id, mensaje_id):
    with connection.cursor() as cursor:
        cursor.execute("SET LOCAL statement_timeout='2000ms'")
        cursor.execute("SET LOCAL lock_timeout='1000ms'")
    if not MensajeChat.objects.filter(pk=mensaje_id, conversacion_id=conversacion_id, vence_en__gt=timezone.now()).exists():
        return []
    return [u.pk for u in elegibles().filter(chats__conversacion_id=conversacion_id) if sesion_operativa(u)]


async def _avisar(conversacion_id, mensaje_id):
    usuarios = await _destinatarios(conversacion_id, mensaje_id)
    layer = get_channel_layer()
    evento = {'type': 'chat.mensaje', 'conversacion_id': conversacion_id, 'ultimo_mensaje_id': mensaje_id}
    await asyncio.gather(*(layer.group_send(grupo(pk), evento) for pk in usuarios))


def avisar(conversacion_id, mensaje_id):
    async def acotado():
        await asyncio.wait_for(_avisar(conversacion_id, mensaje_id), timeout=settings.CHAT_WS_IO_TIMEOUT)
    try:
        async_to_sync(acotado)()
    except Exception:
        # Commit ya confirmado: jamás convertir fallo de aviso en fallo de escritura.
        logger.warning('chat_ws_aviso_no_disponible')
