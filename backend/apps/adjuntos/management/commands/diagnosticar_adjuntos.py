import json
import os
from uuid import UUID

from django.core.management.base import BaseCommand

from apps.adjuntos import almacen
from apps.adjuntos.exceptions import AlmacenNoDisponible, ConflictoAdjunto
from apps.adjuntos.models import AdjuntoDocumento


class Command(BaseCommand):
    help = "Solo diagnóstico (dry-run permanente): nunca borra o repara archivos existentes."

    def handle(self, *args, **options):
        faltantes_corruptos, filas = 0, 0
        for adjunto in AdjuntoDocumento.objects.order_by("pk").iterator(chunk_size=200):
            filas += 1
            try:
                almacen.copia_verificada(adjunto).close()
            except ConflictoAdjunto:
                faltantes_corruptos += 1
        huerfanos = 0
        desconocidos = 0
        disponible = True
        staging = None
        try:
            with almacen.directorio("archivos", crear=False) as fd:
                for entry in os.listdir(fd):
                    try:
                        key = UUID(hex=entry)
                        if key.hex != entry:
                            raise ValueError()
                    except ValueError:
                        desconocidos += 1
                        continue
                    if not AdjuntoDocumento.objects.filter(clave_interna=key).exists():
                        huerfanos += 1
            with almacen.directorio("staging", crear=False) as fd:
                staging = len(os.listdir(fd))
        except AlmacenNoDisponible:
            disponible = False
        self.stdout.write(json.dumps({"dry_run": True, "registros": filas, "faltantes_o_corruptos": faltantes_corruptos,
            "archivos_huerfanos": huerfanos if disponible else None, "entradas_desconocidas": desconocidos,
            "staging_pendiente": staging, "directorios_disponibles": disponible}))
