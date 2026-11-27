from datetime import datetime, timezone
from types import SimpleNamespace

from django.test import SimpleTestCase, override_settings
from django.utils.crypto import salted_hmac

from apps.usuarios.recuperacion_correo import _vinculo


class RecuperacionHMACTests(SimpleTestCase):
    def setUp(self):
        self.user = SimpleNamespace(pk=1, email='cuenta@qa.test', sesion_version=2, rol='TECNICO',
                                    password='hash-sintetico', correo_verificado_en=datetime(2026, 1, 1, tzinfo=timezone.utc))
        self.state = SimpleNamespace(estado='PERSONAL', personal_previa=False)

    @override_settings(FYAG_RECUPERACION_HMAC_KEY=None, SECRET_KEY='qa-legacy')
    def test_compatibilidad_con_vinculos_de_desarrollo_y_qa(self):
        datos = (1, 'cuenta@qa.test', '2026-01-01T00:00:00+00:00', 2, 'TECNICO', 'hash-sintetico', 'PERSONAL', False)
        legacy = salted_hmac('fyag.027.recuperacion.v1', repr(datos), secret='qa-legacy', algorithm='sha256')
        self.assertEqual(_vinculo(self.user, self.state), legacy.hexdigest())

    @override_settings(FYAG_RECUPERACION_HMAC_KEY='ab' * 32, SECRET_KEY='qa-worker')
    def test_vinculo_independiente_compartido_y_rotacion(self):
        emitido = _vinculo(self.user, self.state)
        with override_settings(SECRET_KEY='qa-web'):
            self.assertEqual(_vinculo(self.user, self.state), emitido)
        with override_settings(FYAG_RECUPERACION_HMAC_KEY='cd' * 32):
            self.assertNotEqual(_vinculo(self.user, self.state), emitido)
        self.user.sesion_version += 1
        self.assertNotEqual(_vinculo(self.user, self.state), emitido)
