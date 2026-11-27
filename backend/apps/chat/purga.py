"""Retiro recuperable: primero SQL conserva tumba, después bytes y finalmente recibo."""
from datetime import timedelta
from itertools import batched

from django.db import connection, transaction
from django.utils import timezone

from . import almacen
from .exceptions import NoDisponible
from .models import ArchivoChat, CanalChat, ConversacionChat, CupoChat, MensajeChat, TicketChat


def paginas(qs, field, lote):
    ordenado = qs.order_by(field).values_list(field, flat=True).distinct()
    ultimo = ordenado.last()
    if ultimo is None:
        return
    qs = ordenado.filter(**{f'{field}__lte': ultimo})
    while ids := list(qs[:lote]):
        yield ids
        qs = ordenado.filter(**{f'{field}__gt': ids[-1], f'{field}__lte': ultimo})


def purgar(*, dry_run=False, lote=250):
    if not 1 <= lote <= 1000:
        raise ValueError('Lote de purga fuera de rango.')
    corte = timezone.now()
    mensajes = MensajeChat.objects.filter(vence_en__lte=corte)
    reservas = ArchivoChat.objects.filter(estado='RESERVADO', creado_en__lte=corte-timedelta(hours=1))
    retiros = ArchivoChat.objects.filter(estado='RETIRAR')
    efimeros = {'cupos': CupoChat.objects.filter(ventana__lt=int(corte.timestamp())//60-2),
                'tickets': TicketChat.objects.filter(vence_en__lte=corte),
                'canales': CanalChat.objects.filter(vence_en__lte=corte)}
    fuentes = {'mensajes': mensajes, 'reservas': reservas, 'retiros': retiros, **efimeros}
    # «reservas» cuenta transiciones; «retiros» cuenta archivos finalizados con recibo borrado.
    filas = {nombre: dict(identificados=qs.count(), eliminados=0, pendientes=0, fallidos=0)
             for nombre, qs in fuentes.items()}
    filas['reservas']['transferidas'] = 0
    resultado = {'corte': corte.isoformat(), 'estado': 'dry_run', 'registros': filas}
    if dry_run:
        for fila in filas.values():
            fila['pendientes'] = fila['identificados']
        return resultado  # ni locks ni acceso al filesystem

    for conversaciones in paginas(mensajes, 'conversacion_id', lote):
        for conv_id in conversaciones:
            for ids in paginas(mensajes.filter(conversacion_id=conv_id), 'id', lote):
                with transaction.atomic(), connection.cursor() as cursor:
                    if not ConversacionChat.objects.select_for_update(skip_locked=True).filter(pk=conv_id).first():
                        break  # no impedir que otras conversaciones avancen
                    # El trigger transfiere el archivo a RETIRAR y minimiza el recibo de idempotencia.
                    cursor.execute('DELETE FROM chat_mensajechat WHERE id=ANY(%s)', [ids])
                    filas['mensajes']['eliminados'] += cursor.rowcount

    for ids in paginas(reservas, 'id', lote):
        with transaction.atomic():
            for row in reservas.select_for_update(skip_locked=True).filter(pk__in=ids).order_by('id'):
                row.estado = 'RETIRAR'
                row.save(update_fields=['estado'])
                filas['reservas']['transferidas'] += 1

    filas['retiros']['identificados'] = retiros.count()
    for ids in paginas(retiros, 'id', lote):
        for pk in ids:
            try:
                with transaction.atomic():
                    row = retiros.select_for_update(skip_locked=True).filter(pk=pk).first()
                    if row:
                        almacen.retirar(row.clave_interna)
                        row.delete()
                        filas['retiros']['eliminados'] += 1
            except NoDisponible:
                filas['retiros']['fallidos'] += 1

    # Solo staging realmente presente. No retirar reservas activas ni archivos sin recibo.
    staging = filas['staging'] = dict(identificados=0, eliminados=0, pendientes=0, fallidos=0)
    try:
        for claves in batched(almacen.claves_staging(), lote):
            publicados = ArchivoChat.objects.filter(estado='PUBLICADO', clave_interna__in=claves)
            for pk in publicados.values_list('pk', flat=True):
                staging['identificados'] += 1
                try:
                    with transaction.atomic():
                        row = publicados.select_for_update(skip_locked=True).filter(pk=pk).first()
                        if row is None:
                            staging['pendientes'] += 1
                            continue
                        almacen.retirar(row.clave_interna, publicado=False)
                        staging['eliminados'] += 1
                except NoDisponible:
                    staging['fallidos'] += 1
                    staging['pendientes'] += 1
    except NoDisponible:
        resultado['staging_no_disponible'] = True

    for nombre, qs in efimeros.items():
        # Separar selección y borrado, acotando locks; no tocar nuevas filas.
        for ids in paginas(qs, 'id', lote):
            filas[nombre]['eliminados'] += qs.filter(pk__in=ids).delete()[0]
    for nombre, qs in fuentes.items():
        filas[nombre]['pendientes'] = qs.count()
    resultado['estado'] = (
        'fallido' if resultado.get('staging_no_disponible') or any(f['fallidos'] for f in filas.values()) else
        'pendiente' if any(f['pendientes'] for f in filas.values()) else 'completo')
    return resultado
