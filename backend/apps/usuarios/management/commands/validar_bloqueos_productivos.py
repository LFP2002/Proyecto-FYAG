from django.core.exceptions import ImproperlyConfigured
from django.core.management.base import BaseCommand, CommandError

from apps.usuarios.preflight_bloqueos import preflight_activacion, registrar_activacion


class Command(BaseCommand):
    help = 'Valida la activación inicial de bloqueos productivos sin enviar correo ni cambiar cuentas.'
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument('--registrar', action='store_true', help='Registra explícitamente la activación autorizada.')

    def handle(self, *args, **options):
        try:
            if options['registrar']:
                constancia = registrar_activacion()
                self.stdout.write(f'Constancia de activación vigente: #{constancia.pk}.')
            else:
                preflight_activacion()
                self.stdout.write('Preflight de activación correcto; no se registró ninguna constancia.')
        except ImproperlyConfigured as exc:
            raise CommandError(str(exc)) from None
