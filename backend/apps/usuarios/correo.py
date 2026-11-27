import logging
from smtplib import SMTPException
from urllib.parse import urlencode

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.template.loader import render_to_string
from django.views.decorators.debug import sensitive_variables


_logger = logging.getLogger(__name__)
_DESAFIOS = {
    'verificacion': ('Verificación de correo — FYAG', '/verificar-correo', 'Verificar correo'),
    'recuperacion': ('Solicitud de recuperación de contraseña — FYAG', '/restablecer-clave', 'Restablecer contraseña'),
}


@sensitive_variables('token')
def enviar_desafio_despues_commit(proposito, destinatario, token, minutos):
    """Registrar solo el envío en memoria; ningún log incluye enlace ni destino."""
    subject, path, action = _DESAFIOS[proposito]
    if settings.FYAG_EMAIL_PROFILE == 'deshabilitado':
        return
    if settings.FYAG_EMAIL_PROFILE == 'mailpit' and not destinatario.lower().endswith('.test'):
        return
    enlace = f'{settings.FYAG_PUBLIC_BASE_URL}{path}#{urlencode({"token": token})}'
    contexto = {'enlace': enlace, 'minutos': minutos, 'accion': action, 'proposito': proposito}

    @sensitive_variables()
    def enviar():
        try:
            mensaje = EmailMultiAlternatives(subject, render_to_string('seguridad/desafio.txt', contexto), to=[destinatario])
            mensaje.attach_alternative(render_to_string('seguridad/desafio.html', contexto), 'text/html')
            if mensaje.send(fail_silently=False) != 1:
                _logger.warning('correo_seguridad_no_aceptado')
        except (SMTPException, OSError, ValueError):
            _logger.warning('correo_seguridad_no_aceptado')

    transaction.on_commit(enviar, robust=False)
