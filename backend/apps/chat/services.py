from datetime import timedelta
import hashlib

from django.conf import settings
from django.db import connection, transaction, IntegrityError
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from apps.usuarios.acceso import sesion_operativa
from . import almacen, archivos, consultas
from .exceptions import ConflictoChat, NoDisponible
from .models import ConversacionChat as Conversacion, ParticipanteChat as Participante, MensajeChat as Mensaje, ActoChat as Acto, ArchivoChat as Archivo
from .permissions import revalidar
from .validaciones import contrato, identificador, texto, clave, huella


def bloquear(value, namespace=2300):
    digest = int.from_bytes(hashlib.sha256(str(value).encode()).digest()[:4], 'big', signed=True)
    with connection.cursor() as cursor:
        cursor.execute('SELECT pg_advisory_xact_lock(%s,%s)', [namespace, digest])


def replay(actor, accion, key, digest):
    previo = Acto.objects.filter(autor=actor, accion=accion, clave=key).first()
    if previo:
        if previo.caducado:
            raise ConflictoChat('mensaje_caducado')
        if previo.huella != digest:
            raise ConflictoChat('idempotencia_conflictiva')
    return previo


def crear_conversacion(payload, actor):
    revalidar(actor)
    tipo = payload.get('tipo') if type(payload) is dict else None
    requeridos = {'tipo', 'destinatario', 'clave_idempotencia'} if tipo == 'DIRECTA' else {'tipo', 'titulo', 'participantes', 'clave_idempotencia'}
    contrato(payload, requeridos, requeridos)
    if type(tipo) is not str or tipo not in {'DIRECTA', 'GRUPAL'}:
        raise ValidationError({'tipo': ['Use DIRECTA o GRUPAL.']})
    key = clave(payload['clave_idempotencia'])
    titulo = ''
    if tipo == 'DIRECTA':
        miembros = [identificador(payload['destinatario'])]
    else:
        titulo = texto(payload['titulo'], 100)
        if type(payload['participantes']) is not list or not 2 <= len(payload['participantes']) <= 19:
            raise ValidationError({'participantes': ['Entre 2 y 19 destinatarios requeridos.']})
        miembros = [identificador(x) for x in payload['participantes']]
    if actor.pk in miembros or len(set(miembros)) != len(miembros):
        raise ValidationError({'participantes': ['Participantes distintos; el creador se incorpora por servidor.']})
    miembros = sorted([actor.pk, *miembros])
    digest = huella({'tipo': tipo, 'titulo': titulo, 'participantes': miembros})
    try:
        with transaction.atomic():
            bloquear(f'{actor.pk}:CONVERSACION:{key}')
            actual = revalidar(actor)
            previo = replay(actual, 'CONVERSACION', key, digest)
            if previo:
                return consultas.obtener(actor, previo.conversacion_id), False
            usuarios = list(consultas.elegibles().filter(pk__in=miembros))
            if len(usuarios) != len(miembros) or not all(sesion_operativa(u) for u in usuarios):
                raise NotFound('Destinatario no disponible.')
            conv = None
            if tipo == 'DIRECTA':
                bloquear(f'{miembros[0]}:{miembros[1]}', 2301)
                actual = revalidar(actor)
                conv = Conversacion.objects.filter(tipo='DIRECTA', par_menor_id=miembros[0], par_mayor_id=miembros[1]).first()
            nueva = conv is None
            if nueva:
                conv = Conversacion.objects.create(tipo=tipo, titulo=titulo, creador=actual,
                    par_menor_id=miembros[0] if tipo == 'DIRECTA' else None, par_mayor_id=miembros[1] if tipo == 'DIRECTA' else None)
                Participante.objects.bulk_create([Participante(conversacion=conv, usuario_id=i, incorporado_en=conv.creado_en) for i in miembros])
            Acto.objects.create(autor=actual, accion='CONVERSACION', clave=key, huella=digest, conversacion=conv)
            revalidar(actor)
            # Destinatarios releídos después de esperas; sin locks inversos de Usuarios.
            usuarios = list(consultas.elegibles().filter(pk__in=miembros))
            if len(usuarios) != len(miembros) or not all(sesion_operativa(u) for u in usuarios):
                raise NotFound('Destinatario no disponible.')
            return conv, nueva
    except IntegrityError as exc:
        if getattr(getattr(exc.__cause__, 'diag', None), 'constraint_name', '') == 'chat_integridad':
            raise ConflictoChat() from None
        raise


def _publicar(conv_id, contenido, key, digest, actor, archivo=None, metadata=None):
    bloquear(f'{actor.pk}:MENSAJE:{key}')
    actual = revalidar(actor)
    conv = consultas.obtener(actor, conv_id, bloquear=True)
    previo = replay(actual, 'MENSAJE', key, digest)
    if previo:
        if previo.conversacion_id != conv_id:
            raise ConflictoChat('idempotencia_conflictiva')
        mensaje = Mensaje.objects.filter(pk=previo.mensaje_id, vence_en__gt=timezone.now()).select_related('archivo').first()
        if mensaje is None:
            raise ConflictoChat('mensaje_caducado')
        return mensaje, False
    ahora = timezone.now()
    mensaje = Mensaje.objects.create(conversacion=conv, autor=actual, texto=contenido, clave_idempotencia=key, huella=digest,
        creado_en=ahora, vence_en=ahora+timedelta(days=settings.CHAT_RETENCION_DIAS))
    if archivo:
        for campo, valor in metadata.items():
            setattr(archivo, campo, valor)
        archivo.mensaje = mensaje; archivo.estado = 'PUBLICADO'
        archivo.save(update_fields=[*metadata, 'mensaje', 'estado'])
    Acto.objects.create(autor=actual, accion='MENSAJE', clave=key, huella=digest, conversacion=conv, mensaje_id=mensaje.pk)
    revalidar(actor)
    from .eventos import avisar
    transaction.on_commit(lambda conv=conv_id, pk=mensaje.pk: avisar(conv, pk))
    return mensaje, True


def publicar_texto(conv_id, payload, actor):
    revalidar(actor)
    contrato(payload, {'texto', 'clave_idempotencia'}, {'texto', 'clave_idempotencia'})
    contenido = texto(payload['texto'])
    key = clave(payload['clave_idempotencia'])
    digest = huella({'conversacion': conv_id, 'texto': contenido, 'tipo': 'TEXTO'})
    with transaction.atomic():
        return _publicar(conv_id, contenido, key, digest, actor)


def retirar_recibo(pk):
    with transaction.atomic():
        row = Archivo.objects.select_for_update().filter(pk=pk, estado='RETIRAR').first()
        if row:
            almacen.retirar(row.clave_interna)
            row.delete()


def compensar(pk):
    try:
        with transaction.atomic():
            row = Archivo.objects.select_for_update().filter(pk=pk, estado='RESERVADO').first()
            if row:
                row.estado = 'RETIRAR'; row.save(update_fields=['estado'])
        retirar_recibo(pk)
    except (NoDisponible, OSError):
        pass  # Referencia durable conservada; el recolector reintentará.


def publicar_archivo(conv_id, payload, key_value, actor):
    revalidar(actor)
    contrato(payload, {'archivo', 'texto'}, {'archivo'})
    contenido = texto(payload.get('texto', ''), vacio=True)
    key = clave(key_value)
    consultas.obtener(actor, conv_id)
    # Commit independiente ANTES del primer byte: recuperación tras SIGKILL.
    if connection.in_atomic_block:
        raise RuntimeError('La publicación de archivos requiere caller sin transacción externa.')
    reservado = Archivo.objects.create()
    try:
        with transaction.atomic():
            row = Archivo.objects.select_for_update().get(pk=reservado.pk)
            with almacen.Staging(row.clave_interna) as stage:
                metadata, hash_original = archivos.preparar(payload['archivo'], stage)
                digest = huella({'conversacion': conv_id, 'texto': contenido, 'tipo': 'ARCHIVO', 'nombre': metadata['nombre'], 'sha256_original': hash_original})
                mensaje, nuevo = _publicar(conv_id, contenido, key, digest, actor, row, metadata)
                if nuevo:
                    stage.publicar()
        if nuevo:
            try:
                almacen.retirar(row.clave_interna, publicado=False)
            except NoDisponible:
                pass  # Commit confirmado: nunca falsear un error de publicación.
        else:
            compensar(reservado.pk)
        return mensaje, nuevo
    except BaseException as exc:
        # No retirar PUBLICADO incluso si se perdió confirmación de commit.
        compensar(reservado.pk)
        if isinstance(exc, OSError):
            raise NoDisponible() from None
        raise


@transaction.atomic
def leer(conv_id, payload, actor):
    revalidar(actor)
    contrato(payload, {'ultimo_mensaje_id'}, {'ultimo_mensaje_id'})
    pk = identificador(payload['ultimo_mensaje_id'])
    consultas.obtener(actor, conv_id, bloquear=True)
    mensaje = Mensaje.objects.filter(pk=pk, conversacion_id=conv_id, vence_en__gt=timezone.now()).first()
    if mensaje is None:
        raise NotFound('Mensaje no disponible.')
    participante = Participante.objects.select_for_update().get(conversacion_id=conv_id, usuario_id=actor.pk)
    revalidar(actor)
    if pk > (participante.ultimo_leido_mensaje_id or 0):
        participante.ultimo_leido_mensaje_id = pk
        participante.save(update_fields=['ultimo_leido_mensaje_id'])
    revalidar(actor)
    return participante


@transaction.atomic
def descargar(pk, actor):
    revalidar(actor)
    row = Archivo.objects.select_related('mensaje').filter(pk=pk, estado='PUBLICADO', mensaje__vence_en__gt=timezone.now(),
        mensaje__conversacion__participantes__usuario_id=actor.pk).first()
    if row is None:
        raise NotFound('Archivo no disponible.')
    consultas.obtener(actor, row.mensaje.conversacion_id, bloquear=True)
    row = Archivo.objects.select_for_update().filter(pk=pk, estado='PUBLICADO', mensaje__vence_en__gt=timezone.now()).first()
    revalidar(actor)
    if row is None:
        raise NotFound('Archivo no disponible.')
    copia = almacen.copia_verificada(row)
    try:
        revalidar(actor)
        if row.mensaje.vence_en <= timezone.now():
            raise NotFound('Archivo no disponible.')
        return row, copia
    except BaseException:
        copia.close()
        raise
