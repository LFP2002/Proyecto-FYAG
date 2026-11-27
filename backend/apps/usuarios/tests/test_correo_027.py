from smtplib import SMTPException
from unittest.mock import patch

from django.core import mail
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, TestCase, override_settings

from apps.usuarios.correo import enviar_desafio_despues_commit
from apps.usuarios.correo_config import configurar_correo


class MailConfigTests(SimpleTestCase):
    def test_refuses_incoherent_tls_and_insecure_public_origin(self):
        smtp = {'FYAG_EMAIL_PROFILE': 'smtp', 'EMAIL_BACKEND': 'django.core.mail.backends.smtp.EmailBackend',
                'EMAIL_HOST': 'smtp.example.test', 'EMAIL_USE_TLS': 'True', 'EMAIL_HOST_USER': 'qa',
                'EMAIL_HOST_PASSWORD': 'valor-sintetico', 'DEFAULT_FROM_EMAIL': 'qa@example.test'}
        for base in ['http://fyag.test', 'https://user@fyag.test', 'https://fyag.test/path']:
            with self.subTest(base=base), self.assertRaises(ImproperlyConfigured):
                configurar_correo({**smtp, 'FYAG_PUBLIC_BASE_URL': base})
        with self.assertRaises(ImproperlyConfigured):
            configurar_correo({**smtp, 'FYAG_PUBLIC_BASE_URL': 'https://fyag.test', 'EMAIL_USE_SSL': 'True'})
        self.assertTrue(configurar_correo({**smtp, 'FYAG_PUBLIC_BASE_URL': 'https://fyag.test'})['EMAIL_USE_TLS'])


@override_settings(FYAG_EMAIL_PROFILE='mailpit', EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
                   FYAG_PUBLIC_BASE_URL='http://localhost:5173', DEFAULT_FROM_EMAIL='avisos@fyag.test')
class MailDeliveryTests(TestCase):
    def test_sends_after_commit_with_fragment_and_effective_lifetime(self):
        with self.captureOnCommitCallbacks(execute=True):
            enviar_desafio_despues_commit('recuperacion', 'titular@qa.test', 'token-sintetico', 15)
            self.assertEqual(len(mail.outbox), 0)
        mensaje, = mail.outbox
        self.assertIn('http://localhost:5173/restablecer-clave#token=token-sintetico', mensaje.body)
        self.assertIn('15 minutos', mensaje.body)
        self.assertEqual(mensaje.alternatives[0].mimetype, 'text/html')

    def test_mailpit_refuses_non_synthetic_recipient(self):
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            enviar_desafio_despues_commit('verificacion', 'nadie@example.org', 'token-sintetico', 15)
        self.assertEqual(callbacks, [])

    def test_smtp_failure_is_opaque(self):
        with patch('apps.usuarios.correo.EmailMultiAlternatives.send', side_effect=SMTPException('dato privado')):
            with self.assertLogs('apps.usuarios.correo', 'WARNING') as events:
                with self.captureOnCommitCallbacks(execute=True):
                    enviar_desafio_despues_commit('verificacion', 'titular@qa.test', 'token-sintetico', 15)
        self.assertEqual(events.output, ['WARNING:apps.usuarios.correo:correo_seguridad_no_aceptado'])
