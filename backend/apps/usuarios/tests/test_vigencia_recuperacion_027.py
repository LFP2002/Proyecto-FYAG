from datetime import timedelta

from django.core import mail
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from apps.usuarios.correo_config import configurar_vigencia_recuperacion
from apps.usuarios.models import DesafioRecuperacionCorreo, Usuario
from apps.usuarios.recuperacion_correo import emitir


class ConfiguracionVigenciaTests(SimpleTestCase):
    def test_default_limites_y_rechazos(self):
        self.assertEqual(configurar_vigencia_recuperacion({}), 15)
        for minutos in ('5', '17', '30'):
            self.assertEqual(configurar_vigencia_recuperacion({'FYAG_RECUPERACION_MINUTOS': minutos}), int(minutos))
        for invalido in ('', '0', '4', '31', '-5', '15.5', 'no', '1_5'):
            with self.subTest(valor=invalido), self.assertRaises(ImproperlyConfigured):
                configurar_vigencia_recuperacion({'FYAG_RECUPERACION_MINUTOS': invalido})


@override_settings(FYAG_EMAIL_PROFILE='mailpit', FYAG_PUBLIC_BASE_URL='https://fyag.test',
    EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend', FYAG_RECUPERACION_MINUTOS=23)
class EmisionVigenciaTests(TestCase):
    def test_vigencia_coincide_en_persistencia_y_ambas_plantillas(self):
        usuario = Usuario.objects.create_user(username='ttl', email='ttl@qa.test', rol='TECNICO', correo_verificado_en=timezone.now())
        antes = timezone.now()
        with self.captureOnCommitCallbacks(execute=True):
            emitir(usuario.email)
        vence = DesafioRecuperacionCorreo.objects.get(usuario=usuario).vence_en
        self.assertLessEqual(antes + timedelta(minutes=23), vence)
        self.assertLessEqual(vence, timezone.now() + timedelta(minutes=23))
        mensaje, = mail.outbox
        self.assertIn('23 minutos', mensaje.body)
        self.assertIn('23 minutos', mensaje.alternatives[0].content)
