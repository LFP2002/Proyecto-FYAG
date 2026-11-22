"""Autenticación/cupos WS en PostgreSQL. Nunca guardar o registrar ticket en claro."""
from dataclasses import dataclass
from datetime import timedelta
import hashlib
import hmac
import re
import secrets

from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone
from django.utils.crypto import constant_time_compare

from apps.usuarios.acceso import sesion_operativa
from apps.usuarios.authentication import validar_sesion
from apps.usuarios.configuracion_c2 import relaciones_seguridad
from apps.usuarios.models import Usuario
from .models import TicketChat, CanalChat, CupoChat, MensajeChat
from .permissions import revalidar


class Denegado(Exception):
    pass


class CupoAgotado(Exception):
    pass


@dataclass(frozen=True)
class Identidad:
    usuario_id: int
    sesion_version: int
    password_firma: str


def _mac(value):
    return hmac.new(settings.SECRET_KEY.encode(), value.encode(), hashlib.sha256).hexdigest()


def _firma(user):
    return _mac('chat-password\0'+user.password)


def _sello(nonce, user):
    return _mac(f'chat-ticket\0{nonce}\0{user.pk}\0{user.sesion_version}\0{_firma(user)}')


def _plazos():
    with connection.cursor() as cursor:
        cursor.execute("SET LOCAL statement_timeout='2000ms'")
        cursor.execute("SET LOCAL lock_timeout='1000ms'")


def _mutex():
    with connection.cursor() as cursor:
        cursor.execute('SELECT pg_advisory_xact_lock(2303,0)')


def _usuario(pk):
    user = Usuario.objects.select_related(*relaciones_seguridad()).filter(pk=pk).first()
    if user is None or not user.is_active or user.rol not in Usuario.Rol.values or not sesion_operativa(user):
        raise Denegado()
    return user


@transaction.atomic
def emitir(actor, token=None):
    _plazos()
    actual = revalidar(actor)
    if token is not None:
        validar_sesion(token, actual)
    nonce = secrets.token_urlsafe(32)  # 256 bits aleatorios, sin claims ni identidad visible.
    ticket = nonce+'.'+_sello(nonce, actual)
    ahora = timezone.now()
    row = TicketChat.objects.create(digest=hashlib.sha256(ticket.encode()).hexdigest(), usuario=actual,
        sesion_version=actual.sesion_version, creado_en=ahora, vence_en=ahora+timedelta(seconds=settings.CHAT_WS_TICKET_TTL))
    ultimo = revalidar(actor)
    if token is not None:
        validar_sesion(token, ultimo)
    if not constant_time_compare(_firma(actual), _firma(ultimo)):
        raise Denegado()
    return ticket, row.vence_en


def admitir(ip):
    ahora = timezone.now()
    limites = settings.CHAT_WS_LIMITES
    ip_hash = _mac('chat-ws-ip\0'+ip)
    ventana = int(ahora.timestamp())//60
    # La cuota persiste también si después se rechaza el cupo/conexión.
    with transaction.atomic():
        _plazos(); _mutex()
        contador, nuevo = CupoChat.objects.get_or_create(clave=_mac('chat-ws-handshake\0'+ip), ventana=ventana)
        if not nuevo and contador.cantidad >= limites['handshakes_ip_minuto']:
            raise CupoAgotado()
        if not nuevo:
            contador.cantidad += 1; contador.save(update_fields=['cantidad'])
    with transaction.atomic():
        _plazos(); _mutex()
        ahora = timezone.now()
        # Filas caducadas no cuentan; nunca mensajes o membresías.
        CanalChat.objects.filter(vence_en__lte=ahora).delete()
        vivos = CanalChat.objects.filter(vence_en__gt=ahora)
        pendientes = vivos.filter(usuario__isnull=True)
        if (vivos.count() >= limites['total'] or vivos.filter(ip_digest=ip_hash).count() >= limites['ip']
            or pendientes.count() >= limites['pendientes'] or pendientes.filter(ip_digest=ip_hash).count() >= limites['pendientes_ip']):
            raise CupoAgotado()
        return CanalChat.objects.create(ip_digest=ip_hash, creado_en=ahora,
            vence_en=ahora+timedelta(seconds=settings.CHAT_WS_AUTH_TIMEOUT+2)).pk


@transaction.atomic
def consumir(ticket, canal_id):
    if type(ticket) is not str or not re.fullmatch(r'[A-Za-z0-9_-]{43}\.[0-9a-f]{64}', ticket):
        raise Denegado()
    _plazos(); _mutex()
    row = TicketChat.objects.select_for_update().filter(digest=hashlib.sha256(ticket.encode()).hexdigest()).first()
    canal = CanalChat.objects.select_for_update().filter(pk=canal_id, usuario__isnull=True).first()
    ahora = timezone.now()
    if row is None or row.usado_en is not None or row.vence_en <= ahora or canal is None or canal.vence_en <= ahora:
        raise Denegado()
    user = _usuario(row.usuario_id)
    nonce, sello = ticket.split('.')
    if user.sesion_version != row.sesion_version or not constant_time_compare(sello, _sello(nonce, user)):
        raise Denegado()
    if CanalChat.objects.filter(usuario=user, vence_en__gt=ahora).count() >= settings.CHAT_WS_LIMITES['usuario']:
        raise CupoAgotado()
    row.usado_en = ahora; row.save(update_fields=['usado_en'])
    canal.usuario = user
    canal.vence_en = ahora+timedelta(seconds=30)
    canal.save(update_fields=['usuario', 'vence_en'])
    return Identidad(user.pk, user.sesion_version, _firma(user))


@transaction.atomic
def verificar(identidad, canal_id, *, renovar=False, conversacion_id=None, mensaje_id=None):
    _plazos()
    user = _usuario(identidad.usuario_id)
    if user.sesion_version != identidad.sesion_version or not constant_time_compare(_firma(user), identidad.password_firma):
        raise Denegado()
    ahora = timezone.now()
    canales = CanalChat.objects.filter(pk=canal_id, usuario=user, vence_en__gt=ahora)
    if renovar:
        if not canales.update(vence_en=ahora+timedelta(seconds=30)):
            raise Denegado()
    elif not canales.exists():
        raise Denegado()
    if conversacion_id is not None:
        return MensajeChat.objects.filter(pk=mensaje_id, conversacion_id=conversacion_id,
            conversacion__participantes__usuario=user, vence_en__gt=ahora).exists()
    return True


@transaction.atomic
def liberar(canal_id):
    _plazos()
    CanalChat.objects.filter(pk=canal_id).delete()
