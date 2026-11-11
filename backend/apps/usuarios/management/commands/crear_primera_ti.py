"""Sin contraseña en argumentos, entorno o stdin redirigido."""
from getpass import getpass, GetPassWarning
import sys
import warnings

from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError
from rest_framework.exceptions import APIException

from apps.usuarios.services_usuarios import aprovisionar_primera_ti


class Command(BaseCommand):
    help = "Crear interactivamente la primera cuenta TI activa, sin privilegios Django heredados."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True)
        parser.add_argument("--username", required=True)
        parser.add_argument("--first-name", default="")
        parser.add_argument("--last-name", default="")

    def handle(self, *args, **options):
        if not sys.stdin.isatty():
            raise CommandError("Se requiere una terminal interactiva segura; no se admite contraseña por argumentos, entorno o entrada redirigida.")
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", GetPassWarning)
                password = getpass("Contraseña de la primera TI: ")
                confirm = getpass("Confirmar contraseña: ")
        except (EOFError, KeyboardInterrupt, GetPassWarning):
            raise CommandError("Aprovisionamiento cancelado.") from None
        if password != confirm:
            raise CommandError("Las contraseñas no coinciden.")
        try:
            user = aprovisionar_primera_ti({"email": options["email"], "username": options["username"],
                "first_name": options["first_name"], "last_name": options["last_name"], "password": password})
        except (APIException, DatabaseError):
            # Nunca imprimir datos de entrada, hashes ni el objeto de excepción.
            raise CommandError("No se creó la cuenta: revise migraciones/conexión, unicidad, formato, validadores de contraseña o existencia previa de TI.") from None
        finally:
            password = confirm = None
        self.stdout.write(self.style.SUCCESS(f"Cuenta TI inicial creada (ID {user.pk}); auditoría registrada. Inicie sesión por el flujo habitual."))
