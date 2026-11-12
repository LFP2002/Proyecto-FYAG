"""Proceso independiente: ciclo inicial y espera interrumpible, sin web threads."""
import json
import logging
import signal
from threading import Event
from time import monotonic
from uuid import uuid4

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections, connection

from apps.alertas.services import reconciliar

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Reconcilia alertas; --once ejecuta un ciclo y termina."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--interval", type=int, default=settings.ALERTAS_INTERVALO_SEGUNDOS)

    def handle(self, *args, **options):
        intervalo = options["interval"]
        if not 1 <= intervalo <= 3600:
            raise CommandError("El intervalo debe estar entre 1 y 3600 segundos.")
        parada = Event()
        anteriores = {}
        if not options["once"]:
            for sig in (signal.SIGTERM, signal.SIGINT):
                anteriores[sig] = signal.signal(sig, lambda *_: parada.set())
        try:
            while not parada.is_set():
                inicio = monotonic()
                if not connection.in_atomic_block:
                    close_old_connections()
                try:
                    resultado = reconciliar()
                except Exception as exc:
                    correlacion = str(uuid4())
                    logger.error("alertas_reconciliacion_error correlacion=%s clase=%s", correlacion, type(exc).__name__)
                    if options["once"]:
                        raise CommandError(f"Reconciliación fallida; correlacion={correlacion}") from None
                else:
                    self.stdout.write(json.dumps({"reconciliacion": "correcta", **resultado}))
                    self.stdout.flush()
                finally:
                    if not connection.in_atomic_block:
                        close_old_connections()
                if options["once"]:
                    break
                # Cadencia de inicio a inicio; nunca ciclos solapados en un proceso.
                parada.wait(max(0, intervalo - (monotonic() - inicio)))
        finally:
            for sig, handler in anteriores.items():
                signal.signal(sig, handler)
