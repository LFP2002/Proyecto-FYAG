import json
import signal
from threading import Event

from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections

from apps.documentos import mongo, services
from apps.documentos.exceptions import MongoNoDisponible


class Command(BaseCommand):
    help = "Reconciliación completa repetible, sin watermark persistente y sin modificar anotaciones."

    def add_arguments(self, parser):
        parser.add_argument("--continuo", action="store_true")
        parser.add_argument("--intervalo", type=int, default=60)

    def handle(self, *args, **options):
        intervalo = options["intervalo"]
        if not 1 <= intervalo <= 3600:
            raise CommandError("Intervalo permitido: 1-3600 segundos.")
        stop = Event()
        anteriores = {}
        if options["continuo"]:
            for sig in (signal.SIGTERM, signal.SIGINT):
                anteriores[sig] = signal.signal(sig, lambda *_: stop.set())
        backoff = 1
        try:
            while not stop.is_set():
                count = 0
                try:
                    services.fuera_transaccion()
                    col = mongo.coleccion()
                    ultimo = 0
                    # Reiniciar en 0 CADA ciclo. Un PK bajo con commit tardío se
                    # recupera en el siguiente ciclo; jamás marcarlo descartado.
                    while not stop.is_set():
                        lote = list(services.fuentes().filter(pk__gt=ultimo).order_by("pk").values(*services.CAMPOS_SQL)[:200])
                        if not lote:
                            break
                        for row in lote:
                            if stop.is_set():
                                break
                            services.sincronizar(row, col)
                            count += 1
                        ultimo = lote[-1]["id"]
                    self.stdout.write(json.dumps({"resultado": "sincronizado", "cantidad": count}))
                    backoff = 1
                    if not options["continuo"]:
                        break
                    stop.wait(intervalo)
                except MongoNoDisponible:
                    self.stderr.write(json.dumps({"resultado": "no_disponible", "cantidad_confirmada": count}))
                    if not options["continuo"]:
                        raise CommandError("No se completó la reconciliación documental; reintente.") from None
                    stop.wait(backoff)
                    backoff = min(backoff * 2, 60)
                finally:
                    close_old_connections()
        finally:
            mongo.cerrar()
            for sig, handler in anteriores.items():
                signal.signal(sig, handler)
