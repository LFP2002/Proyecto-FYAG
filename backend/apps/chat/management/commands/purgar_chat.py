import json
import signal
from time import sleep

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import close_old_connections

from apps.chat.purga import purgar


class DetenerPurga(BaseException):
    """Interrumpe también sleep/operaciones, sin adquirir locks en signal handler."""


class Command(BaseCommand):
    help = 'Purgar exclusivamente chat temporal. Requiere --once, --dry-run o --continuo explícito.'

    def add_arguments(self, parser):
        modo = parser.add_mutually_exclusive_group(required=True)
        modo.add_argument('--once', action='store_true')
        modo.add_argument('--dry-run', action='store_true')
        modo.add_argument('--continuo', action='store_true')

    def handle(self, *args, **options):
        if not options['continuo']:
            self.stdout.write(json.dumps(purgar(dry_run=options['dry_run'])))
            return
        def terminar(*_):
            raise DetenerPurga()
        previos = {s: signal.signal(s, terminar) for s in (signal.SIGTERM, signal.SIGINT)}
        try:
            while True:
                try:
                    self.stdout.write(json.dumps(purgar()))
                except Exception:
                    # No datos, rutas ni traceback. Referencias durables quedan intactas.
                    self.stderr.write('chat_purga_no_disponible')
                finally:
                    close_old_connections()
                sleep(settings.CHAT_PURGA_INTERVALO)
        except DetenerPurga:
            pass
        finally:
            close_old_connections()
            for s, previo in previos.items():
                signal.signal(s, previo)
