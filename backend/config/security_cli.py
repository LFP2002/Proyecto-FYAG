"""One-off production operator; never an ASGI service."""
import sys

from django.conf import settings
from django.core.management import execute_from_command_line

COMMANDS = {'crear_primera_ti', 'emitir_clave_instalacion', 'recuperar_acceso_ti', 'validar_bloqueos_productivos'}

if __name__ == '__main__':
    if settings.FYAG_PRODUCTION_ROLE != 'security' or len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        raise SystemExit('Use un comando autorizado de seguridad con docker compose run --rm operaciones_seguridad.')
    execute_from_command_line(sys.argv)
