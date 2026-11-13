import json
import signal
from threading import Event

from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections

from apps.documentos import mongo
from apps.documentos.exceptions import MongoNoDisponible
from apps.documentos.services import fuera_transaccion
from apps.adjuntos import metadata
from apps.adjuntos.models import AdjuntoDocumento


class Command(BaseCommand):
    help = "Proyección repetible de adjuntos en su colección independiente; conserva anotaciones."

    def add_arguments(self, parser):
        parser.add_argument("--continuo", action="store_true")
        parser.add_argument("--intervalo", type=int, default=60)

    def handle(self, *args, **options):
        if not 1 <= options["intervalo"] <= 3600:
            raise CommandError("Intervalo permitido: 1-3600 segundos.")
        stop, anteriores = Event(), {}
        if options["continuo"]:
            for sig in (signal.SIGTERM, signal.SIGINT):
                anteriores[sig] = signal.signal(sig, lambda *_: stop.set())
        backoff = 1
        try:
            while not stop.is_set():
                count = 0
                try:
                    fuera_transaccion()
                    col = metadata.coleccion()
                    ultimo = 0
                    while not stop.is_set():
                        lote = list(AdjuntoDocumento.objects.filter(pk__gt=ultimo).order_by("pk")[:200])
                        if not lote:
                            break
                        for adjunto in lote:
                            if stop.is_set():
                                break
                            metadata.sincronizar(adjunto, col)
                            count += 1
                        ultimo = lote[-1].pk
                    self.stdout.write(json.dumps({"resultado": "sincronizado", "cantidad": count}))
                    backoff = 1
                    if not options["continuo"]:
                        break
                    stop.wait(options["intervalo"])
                except MongoNoDisponible:
                    self.stderr.write(json.dumps({"resultado": "no_disponible", "cantidad_confirmada": count}))
                    if not options["continuo"]:
                        raise CommandError("Reconciliación de adjuntos no completada.") from None
                    stop.wait(backoff)
                    backoff = min(backoff*2, 60)
                finally:
                    close_old_connections()
        finally:
            mongo.cerrar()
            for sig, handler in anteriores.items():
                signal.signal(sig, handler)
