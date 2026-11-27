import sys

from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError
from django.views.decorators.debug import sensitive_variables
from rest_framework.exceptions import APIException

from apps.usuarios.services_usuarios import emitir_clave_instalacion


class Command(BaseCommand):
    help = 'Emitir o renovar una clave web de instalación de 30 minutos; mostrarla una sola vez.'

    def add_arguments(self, parser):
        parser.add_argument('--operador', required=True, help='Identificador no secreto del operador de infraestructura.')
        parser.add_argument('--referencia', required=True, help='Referencia no secreta de la autorización fuera de banda.')

    @sensitive_variables()
    def handle(self, *args, **options):
        if not sys.stdin.isatty() or not sys.stdout.isatty() or not self.stdout.isatty():
            raise CommandError('Se requiere terminal privada interactiva, sin redirección ni captura.')
        try:
            clave, vence = emitir_clave_instalacion(options['operador'], options['referencia'])
        except APIException as exc:
            raise CommandError(str(exc.detail.get('detail')) if isinstance(exc.detail, dict) else str(exc.detail)) from None
        except DatabaseError:
            raise CommandError('No se pudo emitir la autorización de instalación.') from None
        self.stdout.write(f'Vence: {vence.isoformat()}')
        self.stdout.write(f'Clave de instalación (mostrar una vez): {clave}')
