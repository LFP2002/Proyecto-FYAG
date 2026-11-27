"""Feed to backend `python - seed|partial|repair|verify` in the disposable AUD-027 projects."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
import sys
from threading import Event
from unittest.mock import patch
from uuid import uuid4

import django
from django.conf import settings
from django.db import connection, connections, transaction
from django.utils import timezone

action = sys.argv[1]
assert action in {'seed', 'partial', 'repair', 'verify'}
assert settings.DATABASES['default']['NAME'] in ({'fyag_aud027_source', 'fyag_aud027_target'} if action == 'verify' else {'fyag_aud027_source'})
assert settings.FYAG_PRODUCTION_ROLE == 'web'
django.setup()

from apps.chat import almacen, services
from apps.chat.consultas import mensajes
from apps.chat.exceptions import ConflictoChat
from apps.chat.models import ActoChat, ArchivoChat, ConversacionChat, MensajeChat
from apps.chat.purga import purgar
from apps.usuarios.models import Usuario

ROOT = Path(settings.CHAT_ARCHIVOS_ROOT)
DATA = b'AUD-027 archivo sintetico'


def path(row):
    return ROOT / 'archivos' / row.clave_interna.hex


def seed():
    from hashlib import sha256

    assert not Usuario.objects.exists() and settings.CHAT_RETENCION_DIAS == 30
    author = Usuario.objects.create_user(username='aud027', email='aud027@example.test', rol='TECNICO')
    old = timezone.now() - timedelta(days=31)

    def publish(conv, instant):
        file = ArchivoChat.objects.create()
        with almacen.Staging(file.clave_interna) as stage, transaction.atomic():
            stage.file.write(DATA)
            stage.publicar()
            with patch('apps.chat.services.timezone.now', return_value=instant):
                services._publicar(conv.pk, '', uuid4(), sha256(DATA).hexdigest(), author, archivo=file,
                    metadata={'nombre': 'aud027.png', 'mime': 'image/png', 'tamano_bytes': len(DATA), 'sha256': sha256(DATA).hexdigest()})

    for i, count in enumerate((4, 1, 1, 1)):
        other = Usuario.objects.create_user(username=f'aud027_{i}', email=f'aud027_{i}@example.test', rol='TECNICO')
        conv, _ = services.crear_conversacion({'tipo': 'DIRECTA', 'destinatario': other.pk,
                                              'clave_idempotencia': str(uuid4())}, author)
        for _ in range(count):
            publish(conv, old)
        if i == 0:
            publish(conv, timezone.now())
    orphan = ArchivoChat.objects.create(creado_en=timezone.now()-timedelta(hours=2))
    with almacen.Staging(orphan.clave_interna) as stage:
        stage.file.write(DATA)
    conv = ConversacionChat.objects.order_by('pk').first()
    assert mensajes(author, conv.pk, {}).count() == 1
    print('OK: siete mensajes caducados, un vigente y una reserva antigua; historial oculta caducados.')


def partial():
    dry = purgar(dry_run=True, lote=2)
    assert dry['estado'] == 'dry_run' and dry['registros']['mensajes']['pendientes'] == 7
    assert MensajeChat.objects.count() == 8 and len(list((ROOT/'archivos').iterdir())) == 8
    convs = list(ConversacionChat.objects.order_by('pk'))
    fail = path(ArchivoChat.objects.get(mensaje__conversacion=convs[1]))
    fail.rename(fail.with_suffix('.fixture'))
    fail.mkdir()  # unlink on a directory fails in the real store, only for this receipt.
    acquired, release = Event(), Event()

    def lock():
        try:
            with transaction.atomic():
                ConversacionChat.objects.select_for_update().get(pk=convs[0].pk)
                acquired.set()
                assert release.wait(timeout=25)
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=1) as pool:
        task = pool.submit(lock)
        try:
            assert acquired.wait(timeout=15)
            result = purgar(lote=2)
            assert result['estado'] == 'fallido', result
            assert result['registros']['mensajes']['pendientes'] == 4, result
            assert result['registros']['retiros']['eliminados'] == 3, result
            assert result['registros']['retiros']['fallidos'] == 1, result
        finally:
            release.set()
        task.result()
    print('OK: lote bloqueado omitido, fallo real aislado, retiros posteriores avanzaron.')


def repair():
    row = ArchivoChat.objects.get(estado='RETIRAR')
    failed = path(row)
    assert failed.is_dir()
    failed.rmdir()
    failed.with_suffix('.fixture').rename(failed)
    print('OK: obstrucción sintética retirada; el próximo proceso reintentará la tumba.')


def verify():
    assert MensajeChat.objects.count() == ArchivoChat.objects.count() == 1
    assert not MensajeChat.objects.filter(vence_en__lte=timezone.now()).exists()
    row = ArchivoChat.objects.get(estado='PUBLICADO')
    assert list((ROOT/'archivos').iterdir()) == [path(row)]
    assert list((ROOT/'staging').iterdir()) == []
    assert path(row).read_bytes() == DATA
    expired = ActoChat.objects.filter(accion='MENSAJE', caducado=True, mensaje_id=None, huella='')
    assert expired.count() == 7
    receipt = expired.first()
    try:
        services.replay(receipt.autor, 'MENSAJE', receipt.clave, 'a'*64)
    except ConflictoChat as exc:
        assert exc.status_code == 409 and exc.detail['code'] == 'mensaje_caducado'
    else:
        raise AssertionError('Un acto caducado no debe republicarse.')
    print('OK: siete caducados eliminados con sus archivos; recibos mínimos y contenido vigente intactos.')


{'seed': seed, 'partial': partial, 'repair': repair, 'verify': verify}[action]()
