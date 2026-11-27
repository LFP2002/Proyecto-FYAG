import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from secrets import token_urlsafe
from threading import Barrier
from unittest import skipUnless
from urllib.request import urlopen
from uuid import uuid4

from django.conf import settings
from django.core.management import call_command
from django.db import connection
from django.test import TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.usuarios import credenciales, services_usuarios as services
from apps.usuarios.models import DesafioRecuperacionCorreo, EstadoAcceso, RecuperacionAcceso, RecuperacionCorreoEvento, Usuario
from .c2_helpers import BaseC2
from .test_administracion import PASSWORD, NEW_PASSWORD


class QARecuperacion:
    def preparar_correo(self):
        self.assertEqual(connection.settings_dict['NAME'], 'test_fyag_spec018c_c2_qa')
        self.assertEqual((settings.FYAG_EMAIL_PROFILE, settings.EMAIL_HOST), ('mailpit', 'mailpit'))
        config = override_settings(EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend',
                                   FYAG_SECURITY_REDIS_PREFIX=f'qa:recuperacion:{uuid4().hex}')
        config.enable()
        self.addCleanup(config.disable)

    def cuenta(self, rol='TECNICO', verificada=True, activa=True):
        uid = uuid4().hex
        return Usuario.objects.create_user(username=uid, email=f'{uid}@qa.test', rol=rol, password=PASSWORD,
            is_active=activa, correo_verificado_en=timezone.now() if verificada else None)

    def post(self, action, **data):
        client = APIClient(enforce_csrf_checks=True)
        csrf = client.get('/api/auth/csrf/').data['csrfToken']
        return client.post(f'/api/auth/recuperacion/{action}/', data, format='json', HTTP_X_CSRFTOKEN=csrf)

    def confirmar(self, key, password=NEW_PASSWORD):
        return self.post('confirmar', token=key, nueva_clave=password, confirmacion=password)

    def buzon(self, email):
        with urlopen('http://mailpit:8025/api/v1/messages', timeout=4) as response:
            return [m for m in json.load(response)['messages'] if any(t['Address'] == email for t in m['To'])]

    def emitir(self, user):
        prev = {m['ID'] for m in self.buzon(user.email)}
        self.assertEqual(self.post('solicitar', email=user.email).status_code, 202)
        call_command('procesar_verificacion_correo')
        [item] = [m for m in self.buzon(user.email) if m['ID'] not in prev]
        with urlopen(f"http://mailpit:8025/api/v1/message/{item['ID']}", timeout=4) as response:
            msg = json.load(response)
        self.assertTrue('#token=' in msg['HTML'] and PASSWORD not in msg['Text'])
        return msg['Text'].split('#token=', 1)[1].split()[0]


@skipUnless(os.getenv('FYAG_QA_RECUPERACION_MAILPIT') == '1', 'requiere laboratorio C2 y Mailpit explícitos')
class RecuperacionCorreoQA(QARecuperacion, TransactionTestCase):
    def setUp(self):
        self.preparar_correo()

    def test_seis_roles_unica_ti_y_revocacion_http(self):
        from apps.usuarios.tokens import AccessToken, RefreshToken
        for rol in Usuario.Rol.values:
            user = self.cuenta(rol)
            if rol == 'ADMINISTRADOR_TI':
                self.assertEqual(Usuario.objects.filter(rol=rol).count(), 1)
            access, refresh = AccessToken.for_user(user), RefreshToken.for_user(user)
            key = self.emitir(user)
            self.assertTrue(key not in str(list(DesafioRecuperacionCorreo.objects.values())))
            self.assertEqual(self.post('solicitar', email=user.email).status_code, 202)
            call_command('procesar_verificacion_correo')
            self.assertEqual(len(self.buzon(user.email)), 1)
            response = self.confirmar(key)
            self.assertEqual(response.status_code, 204)
            self.assertFalse(response.cookies)
            self.assertEqual(self.confirmar(key).status_code, 400)
            self.assertEqual(len(self.buzon(user.email)), 2)
            user.refresh_from_db()
            self.assertTrue(user.check_password(NEW_PASSWORD) and user.is_active)
            self.assertEqual(user.rol, rol)
            self.assertFalse(RecuperacionAcceso.objects.filter(usuario=user).exists())
            event = RecuperacionCorreoEvento.objects.filter(usuario=user).values().get()
            self.assertTrue(key not in str(event) and NEW_PASSWORD not in str(event))
            client = APIClient()
            self.assertEqual(client.get('/api/auth/me/', HTTP_AUTHORIZATION=f'Bearer {access}').status_code, 401)
            client.cookies[settings.JWT_REFRESH_COOKIE_NAME] = str(refresh)
            self.assertEqual(client.post('/api/auth/refresh/').status_code, 401)

    def test_respuestas_opacas_limites_y_fallo_redis(self):
        emails = [self.cuenta().email, self.cuenta(verificada=False).email, self.cuenta(activa=False).email, 'ausente@qa.test']
        replies = [self.post('solicitar', email=email) for email in emails]
        self.assertTrue(all(r.status_code == 202 and r.data == replies[0].data for r in replies))
        self.assertFalse(DesafioRecuperacionCorreo.objects.exists())
        call_command('procesar_verificacion_correo')
        self.assertEqual([len(self.buzon(e)) for e in emails], [1, 0, 0, 0])
        for _ in range(2):
            self.assertEqual(self.post('solicitar', email=emails[-1].upper()).status_code, 202)
        self.assertEqual(self.post('solicitar', email=emails[-1]).status_code, 429)
        with override_settings(FYAG_SECURITY_REDIS_URL='redis://127.0.0.1:1/0'):
            self.assertEqual(self.post('solicitar', email=emails[0]).status_code, 503)
            self.assertEqual(self.confirmar(token_urlsafe(32)).status_code, 503)

    def test_caducidad_manipulacion_proposito_y_rollback(self):
        from unittest.mock import patch
        user = self.cuenta()
        key = self.emitir(user)
        client = APIClient()
        self.assertEqual(client.post('/api/auth/correo/verificar/', {'token': key}, format='json').status_code, 400)
        wrong = ('A' if key[0] != 'A' else 'B') + key[1:]
        self.assertEqual(self.confirmar(wrong).status_code, 400)
        self.assertEqual(self.confirmar(key, '123').status_code, 400)
        with patch('apps.usuarios.recuperacion_correo.RecuperacionCorreoEvento.objects.create', side_effect=RuntimeError('QA')):
            with self.assertRaises(RuntimeError):
                self.confirmar(key)
        self.assertTrue(Usuario.objects.get(pk=user.pk).check_password(PASSWORD))
        DesafioRecuperacionCorreo.objects.update(vence_en=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.confirmar(key).status_code, 400)
        self.assertEqual(self.confirmar(self.emitir(user)).status_code, 204)

    def test_concurrencia_y_cambios_incompatibles(self):
        for changes in ({'sesion_version': 2}, {'rol': 'BODEGUERO'}, {'email': 'cambiado@qa.test'},
                        {'is_active': False}, {'password': '!otro'}):
            user = self.cuenta()
            key = self.emitir(user)
            Usuario.objects.filter(pk=user.pk).update(**changes)
            self.assertEqual(self.confirmar(key).status_code, 400)
        user = self.cuenta()
        key = self.emitir(user)
        gate = Barrier(2)

        def attempt():
            try:
                gate.wait(timeout=5)
                return self.confirmar(key).status_code
            finally:
                connection.close()

        with ThreadPoolExecutor(2) as pool:
            attempts = [pool.submit(attempt) for _ in range(2)]
            self.assertCountEqual([a.result(timeout=10) for a in attempts], [204, 400])
        self.assertEqual(RecuperacionCorreoEvento.objects.filter(usuario=user).count(), 1)

    def test_temporales_y_fallo_smtp(self):
        ti = self.cuenta('ADMINISTRADOR_TI')
        personal = self.cuenta()
        credenciales.restablecer_clave(personal, {'motivo': 'QA'}, ti)
        self.assertEqual(self.confirmar(self.emitir(personal)).status_code, 204)
        for reemision in (False, True):
            uid = uuid4().hex
            initial = services.crear_usuario({'email': f'{uid}@qa.test', 'username': uid, 'rol': 'TECNICO'}, ti).usuario
            Usuario.objects.filter(pk=initial.pk).update(correo_verificado_en=timezone.now())
            services.actividad_usuario(initial, {'motivo': 'QA'}, ti, activo=True)
            if reemision:
                credenciales.restablecer_clave(initial, {'motivo': 'QA'}, ti)
            self.assertEqual(self.post('solicitar', email=initial.email).status_code, 202)
            call_command('procesar_verificacion_correo')
            self.assertFalse(DesafioRecuperacionCorreo.objects.filter(usuario=initial).exists())
        user = self.cuenta()
        with override_settings(EMAIL_PORT=1), self.assertLogs('apps.usuarios.correo', 'WARNING') as logs:
            self.assertEqual(self.post('solicitar', email=user.email).status_code, 202)
            call_command('procesar_verificacion_correo')
        self.assertTrue(user.email not in str(logs.output))
        self.assertEqual(len(self.buzon(user.email)), 0)


@skipUnless(os.getenv('FYAG_QA_RECUPERACION_MAILPIT') == '1', 'requiere laboratorio C2 y Mailpit explícitos')
class RecuperacionBloqueosQA(QARecuperacion, BaseC2, TransactionTestCase):
    def setUp(self):
        super().setUp()
        self.preparar_correo()

    def test_temporal_y_requiere_ti(self):
        for user, estado in ((self.target, 'BLOQUEO_TEMPORAL'), (self.manager, 'REQUIERE_TI')):
            # El histórico sigue intacto; solo cambia el estado operativo.
            user.email = f'{uuid4().hex}@qa.test'
            user.correo_verificado_en = self.now
            user.save(update_fields=['email', 'correo_verificado_en'])
            if estado == 'REQUIERE_TI':
                self.four_cycles(user)
            else:
                self.fail(user)
            self.assertEqual(EstadoAcceso.objects.get(usuario=user).estado, estado)
            self.assertEqual(self.confirmar(self.emitir(user)).status_code, 204)
            self.assertEqual(EstadoAcceso.objects.get(usuario=user).estado, 'NORMAL')
            self.assertEqual(RecuperacionCorreoEvento.objects.get(usuario=user).acceso_anterior, estado)
            self.assertEqual(self.login(user, NEW_PASSWORD).status_code, 200)
