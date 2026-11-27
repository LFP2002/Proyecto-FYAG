from time import sleep

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError, close_old_connections
from django.utils import timezone

from apps.usuarios.models import DesafioCorreo
from apps.usuarios.throttles import LimitesNoDisponibles
from apps.usuarios.verificacion import procesar_reenvio


class Command(BaseCommand):
    help = 'Procesar reenvíos de verificación sin guardar enlaces en cola.'

    def add_arguments(self, parser):
        parser.add_argument('--continuo', action='store_true')

    def handle(self, *args, **options):
        if settings.FYAG_EMAIL_PROFILE == 'deshabilitado':
            if options['continuo']:
                self.stdout.write('verificacion_correo_deshabilitada')
                return
            raise CommandError('El perfil de correo está deshabilitado.')
        while True:
            try:
                for _ in range(20):
                    if not procesar_reenvio():
                        break
                ids = list(DesafioCorreo.objects.filter(vence_en__lte=timezone.now())
                           .order_by('vence_en').values_list('pk', flat=True)[:200])
                DesafioCorreo.objects.filter(pk__in=ids).delete()
            except (DatabaseError, LimitesNoDisponibles):
                if not options['continuo']:
                    raise CommandError('No se pudo procesar la verificación de correo.') from None
                self.stderr.write('verificacion_procesamiento_no_disponible')
            finally:
                close_old_connections()
            if not options['continuo']:
                return
            sleep(2)
