from django.core.management.base import BaseCommand
from apps.usuarios.autenticacion_c2 import preflight_qa


class Command(BaseCommand):
    help = "Preflight C2 exclusivamente QA; no crea ni recupera cuentas."

    def handle(self, *args, **options):
        preflight_qa()
        self.stdout.write("Precondiciones C2 QA comprobadas. No autoriza producción.")
