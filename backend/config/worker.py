"""Run existing one-shot commands sequentially; health reflects a completed cycle."""
import os
from pathlib import Path
import signal
import subprocess
import sys
from threading import Event
from time import monotonic, time


JOBS = {
    'alerts': ('FYAG_ALERTAS_INTERVALO_SEGUNDOS', 60, ['reconciliar_alertas', '--once']),
    'documents': ('FYAG_DOCUMENTOS_INTERVALO', 60, ['reconciliar_documentos_mongodb']),
    'attachments': ('FYAG_ADJUNTOS_INTERVALO', 60, ['reconciliar_adjuntos_mongodb']),
    'chat': ('FYAG_CHAT_PURGA_INTERVALO', 3600, ['purgar_chat', '--once']),
    'mail': ('FYAG_MAIL_INTERVALO', 2, ['procesar_verificacion_correo']),
}
HEARTBEAT = Path('/tmp/fyag-worker-ok')


def main():
    role = os.environ['FYAG_PROD_ROLE']
    env, default, command = JOBS[role]
    interval = int(os.getenv(env, default))
    timeout = int(os.getenv('FYAG_WORKER_TIMEOUT', '900'))
    if not (1 <= interval <= 86400 and 10 <= timeout <= 7200):
        raise SystemExit('Cadencia o timeout de worker fuera de rango.')
    if sys.argv[1:] == ['health']:
        try:
            return int(time() - HEARTBEAT.stat().st_mtime > interval + timeout + 5)
        except OSError:
            return 1
    HEARTBEAT.unlink(missing_ok=True)
    stop = Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    while not stop.is_set():
        with subprocess.Popen([sys.executable, 'manage.py', *command]) as job:
            deadline = monotonic() + timeout
            while job.poll() is None and monotonic() < deadline and not stop.wait(0.25):
                pass
            if job.poll() is None:
                job.terminate()
                try:
                    job.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    job.kill()
                    job.wait()
            if stop.is_set():
                break
            if job.returncode:
                HEARTBEAT.unlink(missing_ok=True)
                print(f'worker_cycle_failed role={role}', file=sys.stderr)
                return 1  # Docker restarts with backoff; dependencias no reinician el web.
        HEARTBEAT.touch()
        stop.wait(interval)
    return 0


if __name__ == '__main__':
    sys.exit(main())
