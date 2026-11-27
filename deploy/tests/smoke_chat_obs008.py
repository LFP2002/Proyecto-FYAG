"""OBS-008: pass the env file of the disposable fyag-aud027-source project."""
import json
from pathlib import Path
from queue import Queue
import subprocess
import sys
from threading import Thread
from time import monotonic

LOCKER = '''
import sys
from datetime import timedelta
from uuid import UUID
import django
from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone
assert settings.DATABASES['default']['NAME'] == 'fyag_aud027_source'
assert settings.FYAG_PRODUCTION_ROLE == 'web'
django.setup()
from apps.chat.models import CanalChat, CupoChat, TicketChat
from apps.usuarios.models import Usuario
with connection.cursor() as cursor:
    cursor.execute('SELECT current_user, current_database()')
    assert cursor.fetchone() == ('fyag_sql_web', 'fyag_aud027_source')
models = (CupoChat, TicketChat, CanalChat)
assert not any(model.objects.exists() for model in models)
user = Usuario.objects.get(username='aud027')
now = timezone.now()
keys = [[], [], []]
for i in range(1, 6):
    keys[0].append(CupoChat.objects.create(clave=f'{i:064x}', ventana=int(now.timestamp())//60-5).pk)
    keys[1].append(TicketChat.objects.create(digest=f'{i:064x}', usuario=user, sesion_version=user.sesion_version,
        creado_en=now-timedelta(seconds=70), vence_en=now-timedelta(seconds=40)).pk)
    keys[2].append(CanalChat.objects.create(id=UUID(int=i), ip_digest=f'{i:064x}',
        creado_en=now-timedelta(seconds=70), vence_en=now-timedelta(seconds=40)).pk)
with transaction.atomic():
    for model, ids in zip(models, keys):
        assert list(model.objects.select_for_update().filter(pk__in=ids[::2][:2]).order_by('pk').values_list('pk', flat=True)) == [ids[0], ids[2]]
    print('locked', flush=True)
    assert sys.stdin.readline().strip() == 'check'
    for model, ids in zip(models, keys):
        assert list(model.objects.order_by('pk').values_list('pk', flat=True)) == [ids[0], ids[2]]
print('released', flush=True)
'''

ACL = '''
from django.db import connection
with connection.cursor() as cursor:
    cursor.execute('SELECT current_user, current_database()')
    assert cursor.fetchone() == ('fyag_sql_chat', 'fyag_aud027_source')
    for table in ('chat_cupochat', 'chat_ticketchat', 'chat_canalchat'):
        cursor.execute("SELECT has_table_privilege(%s, 'SELECT'), has_table_privilege(%s, 'DELETE'), "
                       "has_any_column_privilege(%s, 'UPDATE')", [table, table, table])
        assert cursor.fetchone() == (True, True, False)
'''


def main(env):
    compose = ['docker', 'compose', '-p', 'fyag-aud027-source', '--env-file', str(Path(env).resolve()),
               '-f', 'compose.production.yaml', 'run', '--rm', '--no-deps', '-T']
    subprocess.run([*compose, 'chat_purgador', 'python', 'manage.py', 'shell', '-c', ACL], check=True, timeout=30)
    command = [*compose, 'chat_purgador', 'python', 'manage.py', 'purgar_chat', '--once', '--lote', '2']

    def cycle():
        start = monotonic()
        result = subprocess.run(command, capture_output=True, text=True, timeout=15)
        report, = [json.loads(line) for line in result.stdout.splitlines() if line.startswith('{')]
        return result.returncode, report, monotonic() - start

    with subprocess.Popen([*compose, 'backend', 'python', '-c', LOCKER], text=True,
                          stdin=subprocess.PIPE, stdout=subprocess.PIPE) as blocker:
        ready = Queue()
        Thread(target=lambda: ready.put(blocker.stdout.readline().strip()), daemon=True).start()
        try:
            assert ready.get(timeout=30) == 'locked'
            rc, report, elapsed = cycle()
            assert rc == 1 and report['estado'] == 'pendiente', (rc, report)
            for name in ('cupos', 'tickets', 'canales'):
                assert report['registros'][name] == dict(identificados=5, eliminados=3, pendientes=2, fallidos=0, bloqueados=2), report
            blocker.stdin.write('check\n')
            blocker.stdin.flush()
            out, _ = blocker.communicate(timeout=15)
            assert blocker.returncode == 0 and out.strip() == 'released'
            print(f'OK: ciclo incompleto con locks activos ({elapsed:.2f} s); 3 eliminados y 2 pendientes por entidad.')
        finally:
            if blocker.poll() is None:
                blocker.stdin.close()
                blocker.wait(timeout=15)

    rc, report, elapsed = cycle()
    assert rc == 0 and report['estado'] == 'completo', (rc, report)
    for name in ('cupos', 'tickets', 'canales'):
        assert report['registros'][name] == dict(identificados=2, eliminados=2, pendientes=0, fallidos=0, bloqueados=0), report
    print(f'OK: reintento completo tras liberar locks ({elapsed:.2f} s); sin UPDATE en ninguna de las tres tablas.')


if __name__ == '__main__':
    main(sys.argv[1])
