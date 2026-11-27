"""No acepta datos por argumentos ni entrega la credencial via stdout/return."""
import os
import re
import sys
import warnings
from getpass import GetPassWarning, getpass

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError, connection
from django.views.decorators.debug import sensitive_variables
from rest_framework.exceptions import APIException

from apps.usuarios.models import Usuario
from apps.usuarios.recuperacion_ti import cuenta_elegible, metadatos, recuperar
from apps.usuarios.services_usuarios import ConflictoUsuario


def abrir_terminal(command):
    # Solo terminal controladora POSIX, nunca pipes, archivos ni fallback.
    if os.name != 'posix' or not all(s.isatty() for s in (sys.stdin, sys.stdout, sys.stderr, command.stdout, command.stderr)):
        raise CommandError('Se requiere una terminal privada e interactiva sin redirecciones.')
    terminal = open('/dev/tty', 'w', encoding='utf-8')
    try:
        if not terminal.isatty() or os.tcgetpgrp(terminal.fileno()) != os.getpgrp():
            raise CommandError('Se requiere una terminal controladora en primer plano.')
    except BaseException:
        terminal.close()
        raise
    return terminal


class Command(BaseCommand):
    help = 'Recuperar una cuenta TI activa mediante infraestructura con autorización humana fuera de banda.'
    requires_system_checks = []

    @sensitive_variables()
    def handle(self, *args, **options):
        try:
            with abrir_terminal(self) as tty, warnings.catch_warnings():
                if settings.DEBUG or connection.force_debug_cursor:
                    raise CommandError('Desactive la depuración y el registro de consultas antes de recuperar el acceso.')
                if connection.in_atomic_block or not connection.get_autocommit():
                    raise CommandError('Ejecute el comando fuera de una transacción existente.')
                warnings.simplefilter('error', GetPassWarning)
                pk = getpass('ID numérico de la cuenta TI: ', stream=tty)
                if not re.fullmatch(r'[1-9][0-9]{0,18}', pk):
                    raise CommandError('Se requiere un ID numérico válido.')
                cuenta = cuenta_elegible(Usuario.objects, int(pk))
                operador, referencia, motivo = metadatos(
                    getpass('Identificador institucional del operador: ', stream=tty),
                    getpass('Referencia de autorización de dos personas: ', stream=tty),
                    getpass('Motivo (no incluya secretos): ', stream=tty),
                )
                confirmacion = f'RECUPERAR {cuenta.pk}'
                if getpass(f'Cuenta #{cuenta.pk} ({cuenta.username!r}). Tras verificar identidad y autorización, '
                           f'escriba {confirmacion}: ', stream=tty) != confirmacion:
                    raise CommandError('Recuperación cancelada; no se realizaron cambios.')
                # Verificar que la salida sigue disponible antes de modificar la cuenta.
                tty.flush()
                try:
                    emitida = recuperar(cuenta.pk, cuenta.sesion_version, operador=operador, referencia=referencia, motivo=motivo)
                except ConflictoUsuario as error:
                    if error.detail['code'] == 'recuperacion_qa_protegida':
                        raise CommandError('Recuperación no realizada: debe permanecer otra TI QA con contraseña personal y acceso operativo.') from None
                    raise
                try:
                    tty.write(f'Credencial temporal (se muestra una vez): {emitida.credencial_temporal}\n'
                              f'Vence: {emitida.vence_en.isoformat()}. Requiere cambio al ingresar.\n')
                    tty.flush()
                except OSError:
                    raise CommandError('La recuperación se confirmó, pero falló la entrega en terminal; no se puede volver a mostrar.') from None
        except (EOFError, KeyboardInterrupt, GetPassWarning, OSError):
            raise CommandError('No se pudo completar la interacción en una terminal segura.') from None
        except (APIException, DatabaseError):
            raise CommandError('Recuperación no realizada: revise la autorización, cuenta, estado de seguridad y base de datos.') from None
