"""Retiro recuperable: primero SQL conserva tumba, después bytes, finalmente recibo."""
from datetime import timedelta

from django.db import connection, transaction
from django.utils import timezone

from . import almacen
from .exceptions import NoDisponible
from .models import ConversacionChat, MensajeChat, ArchivoChat, CupoChat
from .services import retirar_recibo


def purgar(*, dry_run=False, lote=250):
    ahora = timezone.now()
    viejos = ahora-timedelta(hours=1)
    conteo = {'mensajes': MensajeChat.objects.filter(vence_en__lte=ahora).count(),
              'reservas': ArchivoChat.objects.filter(estado='RESERVADO', creado_en__lte=viejos).count(),
              'retiros': ArchivoChat.objects.filter(estado='RETIRAR').count(), 'fallos': 0}
    if dry_run:
        return conteo
    # Un paso acotado; root conversación antes de mensajes/archivos.
    conv_ids = list(MensajeChat.objects.filter(vence_en__lte=ahora).order_by('conversacion_id').values_list('conversacion_id', flat=True).distinct()[:lote])
    for conv_id in conv_ids:
        with transaction.atomic():
            conv = ConversacionChat.objects.select_for_update(skip_locked=True).filter(pk=conv_id).first()
            if conv is None:
                continue
            ids = list(MensajeChat.objects.filter(conversacion=conv, vence_en__lte=ahora).values_list('pk', flat=True)[:lote])
            if ids:
                with connection.cursor() as cursor:
                    # BEFORE DELETE conserva referencias de objetos y recibos UUID
                    # mínimos; no recolectar via Collector que opera antes del trigger.
                    cursor.execute('DELETE FROM chat_mensajechat WHERE id=ANY(%s)', [ids])
    with transaction.atomic():
        abandonados = list(ArchivoChat.objects.select_for_update(skip_locked=True).filter(estado='RESERVADO', creado_en__lte=viejos).order_by('pk')[:lote])
        for row in abandonados:
            row.estado = 'RETIRAR'; row.save(update_fields=['estado'])
    retiros = list(ArchivoChat.objects.filter(estado='RETIRAR').order_by('pk').values_list('pk', flat=True)[:lote])
    for pk in retiros:
        try:
            retirar_recibo(pk)
        except NoDisponible:
            conteo['fallos'] += 1
    # Un crash tras commit de publicación puede dejar también un hardlink staging.
    with transaction.atomic():
        for row in ArchivoChat.objects.select_for_update(skip_locked=True).filter(estado='PUBLICADO').order_by('pk')[:lote]:
            try:
                almacen.retirar(row.clave_interna, publicado=False)
            except NoDisponible:
                conteo['fallos'] += 1
    CupoChat.objects.filter(ventana__lt=int(ahora.timestamp())//60-2).delete()
    return conteo
