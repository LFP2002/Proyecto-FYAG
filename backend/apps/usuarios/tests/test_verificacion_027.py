from concurrent.futures import ThreadPoolExecutor
import json
import os
from datetime import timedelta
from hashlib import sha256
from smtplib import SMTPException
from threading import Barrier
from unittest.mock import patch
from unittest import skipUnless
from urllib.request import urlopen

from django.core import mail
from django.conf import settings
from django.db import close_old_connections, connection
from django.test import TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.usuarios.models import DesafioCorreo, Usuario, UsuarioEvento
from apps.usuarios.services_usuarios import crear_usuario, editar_usuario
from apps.usuarios.verificacion import confirmar, procesar_reenvio


def preparar_cambio_sintetico(user, email, actor):
    from secrets import token_urlsafe
    from apps.usuarios.verificacion import CAMBIO
    editar_usuario(user, {'email': email}, actor)
    value = token_urlsafe(32)
    now = timezone.now()
    DesafioCorreo.objects.create(usuario=user, email=email, proposito=CAMBIO,
                                 digest=sha256(value.encode()).hexdigest(), emitido_en=now, vence_en=now+timedelta(hours=1),
                                 sesion_version=Usuario.objects.get(pk=user.pk).sesion_version)
    return value


@override_settings(FYAG_EMAIL_PROFILE='mailpit', EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
                   FYAG_PUBLIC_BASE_URL='https://fyag.test', DEFAULT_FROM_EMAIL='avisos@fyag.test')
class VerificacionTests(TransactionTestCase):
    def setUp(self):
        self.ti = Usuario.objects.create_user(username='ti', email='ti@qa.test', rol='ADMINISTRADOR_TI')
        self.client = APIClient(enforce_csrf_checks=True)
        self.csrf = self.client.get('/api/auth/csrf/').data['csrfToken']

    def post(self, action, data):
        return self.client.post(f'/api/auth/correo/{action}/', data, format='json', HTTP_X_CSRFTOKEN=self.csrf)

    def token(self):
        return mail.outbox[-1].body.split('#token=', 1)[1].split()[0]

    def alta(self, role='TECNICO', index=0):
        return crear_usuario({'email': f'alta{index}@qa.test', 'username': f'alta{index}', 'rol': role}, self.ti).usuario

    def test_seis_roles_verifican_sin_activar_ni_cambiar_credencial(self):
        for i, role in enumerate(Usuario.Rol.values):
            user = self.alta(role, i)
            value = self.token()
            self.assertTrue(DesafioCorreo.objects.filter(usuario=user, digest=sha256(value.encode()).hexdigest()).exists())
            self.assertEqual(self.client.get('/api/auth/correo/verificar/').status_code, 405)
            r = self.post('verificar', {'token': value})
            self.assertEqual(r.status_code, 204)
            self.assertFalse(r.cookies)
            user.refresh_from_db()
            self.assertTrue(user.correo_verificado_en)
            self.assertFalse(user.is_active)
            self.assertEqual(user.seguridad_credencial.estado, 'INICIAL')
            self.assertEqual(self.post('verificar', {'token': value}).status_code, 400)

    def test_reenvio_generico_csrf_limite_y_smtp_opaco(self):
        self.assertEqual(self.client.post('/api/auth/correo/reenviar/', {'email': self.ti.email}, format='json').status_code, 403)
        uno = self.post('reenviar', {'email': self.ti.email})
        dos = self.post('reenviar', {'email': 'inexistente@qa.test'})
        self.assertEqual((uno.status_code, uno.data), (dos.status_code, dos.data))
        self.assertEqual(uno.status_code, 202)
        self.assertFalse(mail.outbox)
        with patch('apps.usuarios.correo.EmailMultiAlternatives.send', side_effect=SMTPException('no imprimir')):
            with self.assertLogs('apps.usuarios.correo', 'WARNING') as events:
                self.assertTrue(procesar_reenvio())
        self.assertNotIn('no imprimir', str(events.output))
        self.assertTrue(procesar_reenvio())
        self.assertFalse(procesar_reenvio())
        for _ in range(2):
            self.assertEqual(self.post('reenviar', {'email': ' TI@QA.TEST '}).status_code, 202)
        self.assertEqual(self.post('reenviar', {'email': self.ti.email}).status_code, 429)

    def test_expiracion_y_cambio_invalida_tokens_y_revoca(self):
        user = self.alta()
        expired = self.token()
        now = timezone.now()
        DesafioCorreo.objects.filter(usuario=user).update(emitido_en=now-timedelta(hours=2), vence_en=now-timedelta(hours=1))
        self.assertEqual(self.post('verificar', {'token': expired}).status_code, 400)
        editar_usuario(user, {'email': 'primer@qa.test'}, self.ti)
        obsolete = self.token()
        editar_usuario(user, {'email': 'nuevo@qa.test'}, self.ti)
        nuevo = self.token()
        user.refresh_from_db()
        self.assertEqual(user.email, 'alta0@qa.test')
        self.assertEqual(user.sesion_version, 1)
        self.assertEqual(self.post('verificar', {'token': obsolete}).status_code, 400)
        self.assertEqual(self.post('verificar', {'token': nuevo}).status_code, 204)
        user.refresh_from_db()
        self.assertEqual((user.email, user.correo_pendiente, user.sesion_version), ('nuevo@qa.test', '', 2))
        self.assertEqual(mail.outbox[-1].to, ['alta0@qa.test'])
        self.assertFalse(DesafioCorreo.objects.filter(usuario=user).exists())

    def test_colision_posterior_no_sustituye_correo(self):
        user = self.alta()
        editar_usuario(user, {'email': 'colision@qa.test'}, self.ti)
        value = self.token()
        Usuario.objects.create_user(username='otro', email='colision@qa.test', rol='TECNICO')
        self.assertEqual(self.post('verificar', {'token': value}).status_code, 400)
        user.refresh_from_db()
        self.assertEqual(user.email, 'alta0@qa.test')

    def test_transiciones_invalidan_cambio_pero_no_titularidad(self):
        from apps.usuarios import services_usuarios as services
        from apps.usuarios.credenciales import restablecer_clave

        password = 'Una-clave-sintetica-394!'
        actions = [
            lambda user: services.cambiar_clave_propia({'clave_actual': password, 'nueva_clave': 'Una-contraseña-distinta-52!'}, user),
            lambda user: services.cambiar_rol(user, {'rol': 'BODEGUERO', 'motivo': 'QA'}, self.ti),
            lambda user: services.actividad_usuario(user, {'motivo': 'QA'}, self.ti, activo=False),
            lambda user: restablecer_clave(user, {'motivo': 'QA'}, self.ti),
            lambda user: Usuario.objects.filter(pk=user.pk).update(sesion_version=user.sesion_version + 1),
        ]
        for i, mutate in enumerate(actions):
            with self.subTest(transition=i):
                user = Usuario.objects.create_user(username=f'cambio{i}', email=f'vigente{i}@qa.test', rol='TECNICO', password=password)
                from apps.usuarios.verificacion import emitir, TITULARIDAD
                from django.db import transaction
                with transaction.atomic():
                    emitir(Usuario.objects.select_for_update().get(pk=user.pk), TITULARIDAD)
                vigente = self.token()
                nuevo = f'nuevo{i}@qa.test'
                editar_usuario(user, {'email': nuevo}, self.ti)
                cambio = self.token()
                mutate(user)
                self.assertEqual(self.post('verificar', {'token': cambio}).status_code, 400)
                self.assertEqual(self.post('verificar', {'token': vigente}).status_code, 204)
                user.refresh_from_db()
                self.assertEqual(user.email, f'vigente{i}@qa.test')
                editar_usuario(user, {'email': nuevo}, self.ti)
                self.assertNotEqual(self.token(), cambio)
                self.assertEqual(self.post('verificar', {'token': self.token()}).status_code, 204)

    def test_confirmaciones_concurrentes_solo_una_confirma(self):
        user = self.alta()
        value = self.token()
        gate = Barrier(2)

        def attempt():
            close_old_connections()
            try:
                gate.wait(timeout=5)
                confirmar(value)
                return True
            except ValidationError:
                return False
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = [pool.submit(attempt), pool.submit(attempt)]
            self.assertEqual(sum(future.result(timeout=10) for future in results), 1)
        self.assertEqual(UsuarioEvento.objects.filter(usuario_objetivo=user, tipo='CORREO_VERIFICADO').count(), 1)


class MigracionVerificacionTests(TransactionTestCase):
    def test_0014_descarta_desafios_de_cambio_sin_version(self):
        from django.db.migrations.executor import MigrationExecutor
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        before = [(app, '0013_verificacion_correo' if app == 'usuarios' else name) for app, name in latest]
        executor.migrate(before)
        try:
            apps = executor.loader.project_state(before).apps
            user = apps.get_model('usuarios', 'Usuario').objects.create(
                username='historica', email='historica@qa.test', rol='BODEGUERO', correo_pendiente='nuevo@qa.test')
            now = timezone.now()
            for i, purpose in enumerate(('TITULARIDAD', 'CAMBIO')):
                apps.get_model('usuarios', 'DesafioCorreo').objects.create(
                    usuario_id=user.pk, digest=str(i) * 64, proposito=purpose, email=user.email,
                    emitido_en=now, vence_en=now + timedelta(hours=1))
            MigrationExecutor(connection).migrate(latest)
            self.assertEqual(list(DesafioCorreo.objects.values_list('proposito', 'sesion_version')), [('TITULARIDAD', None)])
            self.assertEqual(Usuario.objects.get(pk=user.pk).correo_pendiente, 'nuevo@qa.test')
        finally:
            MigrationExecutor(connection).migrate(latest)

    def test_0012_a_0013_conserva_estado_sin_verificar_historicos(self):
        from django.db.migrations.executor import MigrationExecutor
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        before = [(app, '0012_instalacionfyag' if app == 'usuarios' else name) for app, name in latest]
        executor.migrate(before)
        try:
            prev = executor.loader.project_state(before).apps.get_model('usuarios', 'Usuario')
            user = prev.objects.create(username='historica', email='historica@qa.test', rol='BODEGUERO', sesion_version=7)
            row = prev.objects.filter(pk=user.pk).values().get()
            MigrationExecutor(connection).migrate(latest)
            self.assertTrue(Usuario.objects.filter(pk=user.pk).values().get() == dict(row, correo_verificado_en=None, correo_pendiente=''))
            self.assertFalse(DesafioCorreo.objects.exists())
        finally:
            MigrationExecutor(connection).migrate(latest)


@skipUnless(os.environ.get('FYAG_QA_VERIFICACION_MAILPIT') == '1', 'requiere Mailpit QA privado y explícito')
class VerificacionMailpitQA(TransactionTestCase):
    @override_settings(EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend')
    def test_flujo_completo(self):
        self.assertEqual(settings.FYAG_EMAIL_PROFILE, 'mailpit')
        self.assertEqual(settings.EMAIL_HOST, 'mailpit')
        self.assertTrue(connection.settings_dict['NAME'].startswith('test_fyag_verif'))
        ti = Usuario.objects.create_user(username='ti_mailpit', email='ti-mailpit@qa.test', rol='ADMINISTRADOR_TI')
        client = APIClient(enforce_csrf_checks=True)
        csrf = client.get('/api/auth/csrf/').data['csrfToken']

        def post(action, payload):
            return client.post(f'/api/auth/correo/{action}/', payload, format='json', HTTP_X_CSRFTOKEN=csrf)

        def buzon(address):
            with urlopen('http://mailpit:8025/api/v1/messages', timeout=4) as response:
                items = json.load(response)['messages']
            return [item for item in items if any(to['Address'] == address for to in item['To'])]

        def enlace(address):
            items = buzon(address)
            self.assertEqual(len(items), 1)
            with urlopen(f"http://mailpit:8025/api/v1/message/{items[0]['ID']}", timeout=4) as response:
                message = json.load(response)
            return message['Text'].split('#token=', 1)[1].split()[0]

        self.assertEqual(post('reenviar', {'email': ti.email}).status_code, 202)
        self.assertFalse(buzon(ti.email))
        from django.core.management import call_command
        call_command('procesar_verificacion_correo')
        value = enlace(ti.email)
        self.assertEqual(post('verificar', {'token': value}).status_code, 204)
        self.assertEqual(post('verificar', {'token': value}).status_code, 400)
        self.assertEqual(post('reenviar', {'email': ti.email}).status_code, 202)
        call_command('procesar_verificacion_correo')
        ti.refresh_from_db()
        self.assertIsNotNone(ti.correo_verificado_en)
        self.assertEqual(len(buzon(ti.email)), 1)
        anterior = ti.email
        nueva = 'ti-nueva-mailpit@qa.test'
        editar_usuario(ti, {'email': nueva}, ti)
        self.assertEqual(post('verificar', {'token': enlace(nueva)}).status_code, 204)
        ti.refresh_from_db()
        self.assertEqual((ti.email, ti.sesion_version), (nueva, 2))
        self.assertEqual(len(buzon(anterior)), 2)
        from apps.usuarios.tokens import AccessToken
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {AccessToken.for_user(ti)}')
        alta = 'alta-mailpit@qa.test'
        response = client.post('/api/usuarios/', {'email': alta, 'username': 'alta_mailpit', 'rol': 'BODEGUERO'}, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(post('verificar', {'token': enlace(alta)}).status_code, 204)
        user = Usuario.objects.get(email=alta)
        self.assertFalse(user.is_active)
        self.assertEqual(user.seguridad_credencial.estado, 'INICIAL')
