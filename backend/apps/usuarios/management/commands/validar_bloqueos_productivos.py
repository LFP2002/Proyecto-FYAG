from django.core.exceptions import ImproperlyConfigured
from django.core.management.base import BaseCommand, CommandError

from apps.usuarios.preflight_bloqueos import preflight_si_productivo


class Command(BaseCommand):
    help = 'Valida los prerrequisitos de bloqueos productivos sin enviar correo ni cambiar cuentas.'
    requires_system_checks = []

    def handle(self, *args, **options):
        try:
            if not preflight_si_productivo():
                raise CommandError('El perfil productivo no está seleccionado.')
        except ImproperlyConfigured as exc:
            raise CommandError(str(exc)) from None
        self.stdout.write('Preflight de bloqueos productivos correcto.')
