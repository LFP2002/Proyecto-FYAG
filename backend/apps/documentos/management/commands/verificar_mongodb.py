from django.core.management.base import BaseCommand, CommandError
from pymongo.errors import PyMongoError

from apps.documentos import mongo
from apps.documentos.exceptions import MongoNoDisponible


class Command(BaseCommand):
    help = "Comprueba conexión autenticada, esquema e índice documental, sin exponer secretos."

    def handle(self, *args, **options):
        try:
            mongo.cliente().admin.command("ping")
            mongo.coleccion()
            self.stdout.write("MongoDB documental: autenticación, esquema e índice correctos.")
        except (MongoNoDisponible, PyMongoError):
            raise CommandError("MongoDB documental no disponible o bootstrap incompatible.") from None
        finally:
            mongo.cerrar()
