import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from hashlib import sha256
from io import StringIO
from secrets import token_urlsafe
from threading import Barrier
from unittest import skipUnless
from unittest.mock import patch
from urllib.request import urlopen
from uuid import uuid4

from django.conf import settings
from django.core.management import CommandError, call_command
from django.db import close_old_connections, connection
from django.test import TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.usuarios.models import EventoInstalacionFYAG, InstalacionFYAG, Usuario
from apps.usuarios.services_usuarios import ConflictoUsuario, aprovisionar_primera_ti, emitir_clave_instalacion


class SetupWebTests(TransactionTestCase):
    def setUp(self):
        InstalacionFYAG.objects.get_or_create(pk=1)
        conf = override_settings(FYAG_SECURITY_REDIS_PREFIX=f'qa:setup:{uuid4().hex}')
        conf.enable()
        self.addCleanup(conf.disable)
        self.client = self.browser()
        self.data = {'first_name': 'Nombre QA', 'last_name': 'Apellido QA', 'username': 'soporte_qa',
                     'email': f'setup-{uuid4().hex}@qa.test', 'password': 'Clave-Sintetica-95+Fortaleza!'}

    def browser(self):
        client = APIClient(enforce_csrf_checks=True)
        client.csrf = client.get('/api/auth/csrf/').data['csrfToken']
        return client

    def post(self, key, *, client=None, **overrides):
        client = client or self.client
        body = {**self.data, 'password_confirm': self.data['password'], 'clave_instalacion': key, **overrides}
        return client.post('/api/auth/setup/', body, format='json', HTTP_X_CSRFTOKEN=client.csrf)

    def emit(self):
        return emitir_clave_instalacion('operador-qa', 'QA-027')[0]

    def state(self, client=None):
        return (client or self.client).get('/api/auth/setup/estado/')

    def test_autorizacion_uniforme_caducidad_renovacion_y_consumo(self):
        self.assertEqual(self.state().data, {'pendiente': True})
        wrong = self.post(token_urlsafe(32))
        old = self.emit()
        self.assertEqual(self.state().data, {'pendiente': True})
        valid = self.emit()
        stored = InstalacionFYAG.objects.get(pk=1)
        self.assertTrue(stored.clave_digest == sha256(valid.encode()).hexdigest())
        expired = timezone.now() - timedelta(seconds=1)
        InstalacionFYAG.objects.update(clave_vence_en=expired)
        for key in (old, valid):
            rejected = self.post(key)
            self.assertEqual((rejected.status_code, rejected.data), (wrong.status_code, wrong.data))
        self.assertEqual(wrong.status_code, 409)
        self.assertFalse(Usuario.objects.exists())
        valid = self.emit()
        success = self.post(valid)
        self.assertEqual(success.status_code, 201)
        self.assertTrue('no-store' in success['Cache-Control'])
        self.assertFalse(success.cookies)
        self.assertEqual(set(success.data), {'detail'})
        reused = self.post(valid)
        self.assertEqual((reused.status_code, reused.data), (wrong.status_code, wrong.data))
        self.assertEqual(self.state().data, {'pendiente': False})
        stored.refresh_from_db()
        self.assertIsNotNone(stored.inicializada_en)
        self.assertIsNone(stored.clave_digest)
        self.assertIsNone(stored.clave_vence_en)
        user = Usuario.objects.get()
        self.assertTrue(user.is_active and user.check_password(self.data['password']))
        self.assertFalse(user.is_staff or user.is_superuser or user.groups.exists() or user.user_permissions.exists())
        self.assertIsNone(user.correo_verificado_en)
        self.assertEqual((user.rol, user.seguridad_credencial.estado), ('ADMINISTRADOR_TI', 'PERSONAL'))
        self.assertEqual(self.client.get('/api/auth/me/').status_code, 401)
        events = list(EventoInstalacionFYAG.objects.order_by('pk').values())
        self.assertEqual([event['tipo'] for event in events], ['EMISION', 'RENOVACION', 'RENOVACION', 'INICIALIZACION_WEB'])
        self.assertTrue(all(secret not in str(events) for secret in (valid, old, self.data['password'])))
        self.assertEqual(events[0]['referencia'], 'QA-027')
        with self.assertRaises(ConflictoUsuario):
            self.emit()

    def test_csrf_validacion_estricta_y_redis_cerrado(self):
        key = self.emit()
        self.assertEqual(self.client.post('/api/auth/setup/', {}, format='json').status_code, 403)
        self.assertEqual(self.post(key, rol='GERENCIA').status_code, 400)
        self.assertEqual(self.post(key, password_confirm='distinta').status_code, 400)
        with override_settings(FYAG_SECURITY_REDIS_URL=''):
            self.assertEqual(self.state().status_code, 503)
            self.assertEqual(self.post(key).status_code, 503)
        self.assertFalse(Usuario.objects.exists())
        for _ in range(3):
            self.assertEqual(self.post('').status_code, 409)
        r = self.post(key)
        self.assertEqual(r.status_code, 429)
        self.assertIn('Retry-After', r)

    def test_rollback_no_consume_clave(self):
        key = self.emit()
        with patch('apps.usuarios.services_usuarios._event', side_effect=RuntimeError('fallo sintético')):
            with self.assertRaises(RuntimeError):
                aprovisionar_primera_ti(self.data, clave_instalacion=key)
        self.assertFalse(Usuario.objects.exists())
        self.assertEqual(self.state().data, {'pendiente': True})
        self.assertEqual(self.post(key).status_code, 201)

    def test_alta_externa_invalida_clave_aunque_se_borre_el_usuario(self):
        key = self.emit()
        Usuario.objects.bulk_create([Usuario(username='externa', email='externa@qa.test', rol='TECNICO')])
        self.assertIsNone(InstalacionFYAG.objects.get(pk=1).clave_digest)
        Usuario.objects.filter(username='externa').delete()
        self.assertEqual(self.state().data, {'pendiente': False})
        self.assertEqual(self.post(key).status_code, 409)

    def test_emision_cli_no_permite_redireccion(self):
        with self.assertRaises(CommandError):
            call_command('emitir_clave_instalacion', operador='operador-qa', referencia='QA-027', stdout=StringIO())
        self.assertFalse(EventoInstalacionFYAG.objects.exists())

    def test_emision_cli_interactiva_emite_clave_utilizable(self):
        class Terminal(StringIO):
            def isatty(self):
                return True

        tty = Terminal()
        with patch('apps.usuarios.management.commands.emitir_clave_instalacion.sys.stdin', tty), \
                patch('apps.usuarios.management.commands.emitir_clave_instalacion.sys.stdout', tty):
            call_command('emitir_clave_instalacion', operador='operador-qa', referencia='QA-027', stdout=tty)
        key = tty.getvalue().splitlines()[-1].rsplit(' ', 1)[-1]
        self.assertEqual(self.post(key).status_code, 201)

    def race(self, *, cli):
        key = self.emit()
        barrier = Barrier(2)

        def run(index):
            close_old_connections()
            try:
                client = self.browser()
                barrier.wait(timeout=8)
                if cli and index == 0:
                    try:
                        aprovisionar_primera_ti({**self.data, 'email': 'cli-setup@qa.test', 'username': 'cli_setup'})
                        return 201
                    except ConflictoUsuario:
                        return 409
                return self.post(key, client=client, username=f'qa_concurrente_{index}').status_code
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(run, i) for i in range(2)]
            self.assertEqual(sorted(f.result(timeout=15) for f in futures), [201, 409])
        self.assertEqual(Usuario.objects.count(), 1)
        self.assertIsNone(InstalacionFYAG.objects.get(pk=1).clave_digest)

    def test_concurrencia_dos_navegadores(self):
        self.race(cli=False)

    def test_concurrencia_cli_y_web(self):
        self.race(cli=True)

    @skipUnless(os.environ.get('FYAG_QA_SETUP_MAILPIT') == '1', 'requiere Mailpit privado y explícito')
    @override_settings(EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend')
    def test_mailpit_confirmacion_y_login_manual(self):
        self.assertEqual((settings.FYAG_EMAIL_PROFILE, settings.EMAIL_HOST), ('mailpit', 'mailpit'))
        self.assertTrue(connection.settings_dict['NAME'].startswith('test_fyag_setup027'))
        self.assertEqual(self.post(self.emit()).status_code, 201)
        self.assertFalse(self.client.cookies.get(settings.JWT_REFRESH_COOKIE_NAME))
        with urlopen('http://mailpit:8025/api/v1/messages', timeout=4) as response:
            messages = json.load(response)['messages']
        items = [item for item in messages if any(to['Address'] == self.data['email'] for to in item['To'])]
        self.assertEqual(len(items), 1)
        with urlopen(f"http://mailpit:8025/api/v1/message/{items[0]['ID']}", timeout=4) as response:
            message = json.load(response)
        value = message['Text'].split('#token=', 1)[1].split()[0]
        self.assertTrue(self.data['password'] not in message['Text'])
        confirmed = self.client.post('/api/auth/correo/verificar/', {'token': value}, format='json', HTTP_X_CSRFTOKEN=self.client.csrf)
        self.assertEqual(confirmed.status_code, 204)
        self.assertIsNotNone(Usuario.objects.get().correo_verificado_en)
        login = self.client.post('/api/auth/login/', {k: self.data[k] for k in ('email', 'password')},
                                 format='json', HTTP_X_CSRFTOKEN=self.client.csrf)
        self.assertEqual(login.status_code, 200)

    @override_settings(FYAG_EMAIL_PROFILE='mailpit', EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend',
                       EMAIL_HOST='127.0.0.1', EMAIL_PORT=1, FYAG_PUBLIC_BASE_URL='http://localhost:5173')
    def test_fallo_conexion_smtp_no_deshace_alta(self):
        key = self.emit()
        with self.assertLogs('apps.usuarios.correo', 'WARNING') as logs:
            self.assertEqual(self.post(key).status_code, 201)
        self.assertTrue(all(secret not in str(logs.output) for secret in (key, self.data['password'], self.data['email'])))
        self.assertTrue(Usuario.objects.exists())
        self.assertEqual(self.post(key).status_code, 409)
