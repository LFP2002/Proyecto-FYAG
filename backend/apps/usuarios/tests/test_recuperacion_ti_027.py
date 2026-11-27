from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from getpass import GetPassWarning
from io import StringIO
from threading import Barrier
from unittest import skipUnless
from unittest.mock import patch

from django.conf import settings
from django.core.management import CommandError, call_command
from django.db import DatabaseError, connection
from django.test import TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.exceptions import APIException
from rest_framework.test import APIClient

from apps.chat import tickets
from apps.usuarios import credenciales, recuperacion_correo
from apps.usuarios.bloqueos import registrar_verificacion
from apps.usuarios.models import DesafioCorreo, DesafioRecuperacionCorreo, EstadoAcceso, RecuperacionTIEvento, SeguridadCredencial, Usuario
from apps.usuarios.politica_bloqueos import Senal
from apps.usuarios.recuperacion_ti import recuperar
from apps.usuarios.tokens import AccessToken, RefreshToken
from .test_administracion import NEW_PASSWORD, PASSWORD

MOD = 'apps.usuarios.management.commands.recuperar_acceso_ti'
META = dict(operador='operador.qa', referencia='AUT-027', motivo='Recuperación autorizada')
AUDIT = '/api/auditoria/eventos/'


class Terminal(StringIO):
    def __exit__(self, *args):
        pass


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class RecuperacionTITests(TransactionTestCase):
    def cuenta(self, rol='ADMINISTRADOR_TI', activa=True, nombre='cuenta'):
        return Usuario.objects.create_user(username=nombre, email=f'{nombre}@qa.test', password=PASSWORD,
                                           rol=rol, is_active=activa, correo_verificado_en=timezone.now())

    def desafios(self, user):
        now = timezone.now()
        state = SeguridadCredencial.objects.get(usuario=user)
        key = 'A' * 43
        rec = DesafioRecuperacionCorreo.objects.create(usuario=user, digest=recuperacion_correo._digest(key),
            vinculo=recuperacion_correo._vinculo(user, state), vence_en=now + timedelta(minutes=15))
        change = DesafioCorreo.objects.create(usuario=user, digest='b' * 64, email='nuevo@qa.test', proposito='CAMBIO',
            emitido_en=now, vence_en=rec.vence_en, sesion_version=user.sesion_version)
        return key, change

    def cli(self, user, confirm=None):
        terminal, stdout, stderr = Terminal(), StringIO(), StringIO()
        respuestas = [str(user.pk), *META.values(), f'RECUPERAR {user.pk}' if confirm is None else confirm]
        with patch(f'{MOD}.abrir_terminal', return_value=terminal), patch(f'{MOD}.getpass', side_effect=respuestas):
            call_command('recuperar_acceso_ti', stdout=stdout, stderr=stderr)
        self.assertEqual((stdout.getvalue(), stderr.getvalue()), ('', ''))
        return terminal.getvalue().splitlines()[0].rsplit(' ', 1)[-1]

    def test_unica_ti_sin_smtp_ni_redis_revocaciones_y_primer_cambio(self):
        user = self.cuenta()
        access, refresh = AccessToken.for_user(user), RefreshToken.for_user(user)
        ticket, _ = tickets.emitir(user)
        canal = tickets.admitir('127.0.0.1')
        identity = tickets.consumir(ticket, canal)
        pendiente, _ = tickets.emitir(user)
        key, change = self.desafios(user)
        with override_settings(FYAG_SECURITY_REDIS_URL='redis://127.0.0.1:1/0', EMAIL_HOST='127.0.0.1', EMAIL_PORT=1,
                               EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend'):
            temporal = self.cli(user)
        self.assertEqual(len(temporal), 43)
        self.assertEqual(Usuario.objects.count(), 1)
        user.refresh_from_db()
        self.assertTrue(user.check_password(temporal))
        self.assertEqual((user.rol, user.is_active, user.email), ('ADMINISTRADOR_TI', True, 'cuenta@qa.test'))
        self.assertFalse(DesafioCorreo.objects.filter(pk=change.pk).exists())
        with self.assertRaises(APIException):
            recuperacion_correo.confirmar(key, NEW_PASSWORD)
        with self.assertRaises(tickets.Denegado):
            tickets.verificar(identity, canal)
        with self.assertRaises(tickets.Denegado):
            tickets.consumir(pendiente, tickets.admitir('127.0.0.1'))
        client = APIClient(enforce_csrf_checks=True)
        self.assertEqual(client.get('/api/auth/me/', HTTP_AUTHORIZATION=f'Bearer {access}').status_code, 401)
        csrf = client.get('/api/auth/csrf/').data['csrfToken']
        client.cookies[settings.JWT_REFRESH_COOKIE_NAME] = str(refresh)
        self.assertEqual(client.post('/api/auth/refresh/', HTTP_X_CSRFTOKEN=csrf).status_code, 401)
        csrf = client.get('/api/auth/csrf/').data['csrfToken']
        login = client.post('/api/auth/login/', {'email': user.email, 'password': temporal}, format='json', HTTP_X_CSRFTOKEN=csrf)
        self.assertEqual((login.status_code, login.data.get('estado')), (200, 'CAMBIO_OBLIGATORIO'))
        self.assertEqual(login.cookies[settings.JWT_REFRESH_COOKIE_NAME]['max-age'], 0)
        changed = client.post('/api/auth/primer-cambio-clave/', {'desafio': login.data['desafio'], 'nueva_clave': NEW_PASSWORD},
                              format='json', HTTP_X_CSRFTOKEN=login.data['csrfToken'])
        self.assertEqual(changed.status_code, 200)
        event = RecuperacionTIEvento.objects.values().get()
        for secret in (temporal, key, PASSWORD, user.password, str(access), str(refresh), login.data['desafio']):
            self.assertNotIn(secret, str(event))

    def test_rechazos_terminal_cancelacion_estado_y_cuenta(self):
        user = self.cuenta()
        with self.assertRaisesMessage(CommandError, 'terminal'), patch(f'{MOD}.sys.stdin', StringIO()):
            call_command('recuperar_acceso_ti')
        with self.assertRaisesMessage(CommandError, 'cancelada'):
            self.cli(user, 'NO')
        with patch(f'{MOD}.abrir_terminal', return_value=Terminal()), patch(f'{MOD}.getpass', side_effect=GetPassWarning):
            with self.assertRaises(CommandError):
                call_command('recuperar_acceso_ti')
        for other in (self.cuenta('TECNICO', nombre='tecnico'), self.cuenta(activa=False, nombre='inactiva')):
            with self.assertRaises(APIException):
                recuperar(other.pk, other.sesion_version, **META)
        with self.assertRaises(APIException):
            recuperar(user.pk, user.sesion_version, **{**META, 'referencia': ''})
        SeguridadCredencial.objects.filter(usuario=user).delete()
        with self.assertRaises(APIException):
            recuperar(user.pk, user.sesion_version, **META)
        self.assertFalse(SeguridadCredencial.objects.filter(usuario=user).exists())
        self.assertFalse(RecuperacionTIEvento.objects.exists())
        self.assertTrue(Usuario.objects.get(pk=user.pk).check_password(PASSWORD))

    def test_rollback_y_concurrencia_con_misma_confirmacion(self):
        user = self.cuenta()
        key, change = self.desafios(user)
        with patch('apps.usuarios.recuperacion_ti.RecuperacionTIEvento.objects.create', side_effect=DatabaseError('detalle privado')):
            with self.assertRaisesMessage(CommandError, 'no realizada') as exc:
                self.cli(user)
            self.assertNotIn('detalle privado', str(exc.exception))
        self.assertTrue(Usuario.objects.get(pk=user.pk).check_password(PASSWORD))
        self.assertTrue(DesafioRecuperacionCorreo.objects.filter(usuario=user).exists())
        self.assertTrue(DesafioCorreo.objects.filter(pk=change.pk).exists())
        self.assertEqual(SeguridadCredencial.objects.get(usuario=user).estado, 'PERSONAL')
        gate = Barrier(2)

        def intentar():
            try:
                gate.wait(timeout=5)
                return recuperar(user.pk, user.sesion_version, **META)
            except APIException as error:
                return error.detail['code']
            finally:
                connection.close()

        with ThreadPoolExecutor(2) as pool:
            futures = [pool.submit(intentar) for _ in range(2)]
            results = [future.result(timeout=15) for future in futures]
        self.assertIn('cuenta_cambio', results)
        emitida, = [result for result in results if result != 'cuenta_cambio']
        self.assertTrue(Usuario.objects.get(pk=user.pk).check_password(emitida.credencial_temporal))
        self.assertEqual(RecuperacionTIEvento.objects.count(), 1)

    def test_auditoria_seis_roles_historial_y_filtros(self):
        target = self.cuenta()
        emitida = recuperar(target.pk, target.sesion_version, **META)
        event = RecuperacionTIEvento.objects.get()
        history = f'/api/usuarios/{target.pk}/historial/'
        filters = {'fuente': event.FUENTE, 'tipo': event.TIPO, 'recurso_tipo': 'USUARIO', 'recurso_id': target.pk}
        for rol in Usuario.Rol.values:
            actor = self.cuenta(rol, nombre=rol.lower())
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f'Bearer {AccessToken.for_user(actor)}')
            audit_response = client.get(AUDIT, filters)
            history_response = client.get(history)
            esperado = 200 if rol == 'ADMINISTRADOR_TI' else 403
            self.assertEqual((audit_response.status_code, history_response.status_code), (esperado, esperado))
            if esperado == 200:
                audit, = audit_response.data['results']
                row, = history_response.data['results']
                for item in (audit, row):
                    self.assertEqual(item['id'], f'{event.FUENTE}:{event.pk}')
                    self.assertIsNone(item['actor'])
                    self.assertEqual(item['actor_identidad_origen'], 'INFRAESTRUCTURA')
                    self.assertEqual(item['datos_nuevos'], {k: META[k] for k in ('operador', 'referencia')})
                    self.assertNotIn(emitida.credencial_temporal, str(item))
                self.assertEqual(client.get(AUDIT, {**filters, 'actor': actor.pk}).data['results'], [])

    @skipUnless(settings.DATABASES['default']['NAME'] in {'fyag_spec018c_c2_qa', 'test_fyag_spec018c_c2_qa'}
                and settings.DATABASES['default']['HOST'] == 'postgres', 'requiere laboratorio C2 aislado')
    def test_c2_bloqueos_y_estado_ausente_sin_excepcion_permanente(self):
        self.assertEqual(connection.settings_dict['NAME'], 'test_fyag_spec018c_c2_qa')
        user, otra = self.cuenta(), self.cuenta(nombre='otra')
        now = timezone.now() + timedelta(seconds=1)
        with override_settings(BLOQUEOS_C1_SIMULACION_HABILITADA=True, BLOQUEOS_C2_HABILITADO=True,
                               BLOQUEOS_C2_ENTORNO='QA_AISLADO_C2', BLOQUEOS_C2_TI_QA_IDS=(user.pk, otra.pk),
                               BLOQUEOS_C2_RECUPERACION_QA_CONFIRMADA=True, BLOQUEOS_C2_RIESGO_DOS_QA_ACEPTADO=True,
                               BLOQUEOS_C2_RESPUESTAS='401_GENERICO', BLOQUEOS_C2_SESIONES_TEMPORALES='REVOCAR_TODAS_QA'), \
                patch('apps.usuarios.bloqueos.timezone.now', side_effect=lambda: now):
            for target, estado, saltos in ((user, 'BLOQUEO_TEMPORAL', (0,)), (otra, 'REQUIERE_TI', (0, 15, 60, 240))):
                for salto in saltos:
                    now += timedelta(minutes=salto)
                    for _ in range(5):
                        registrar_verificacion(target.pk, Senal.CLAVE_INCORRECTA)
                before = EstadoAcceso.objects.get(usuario=target)
                self.assertEqual(before.estado, estado)
                recuperar(target.pk, target.sesion_version, **META)
                final = EstadoAcceso.objects.get(usuario=target)
                self.assertEqual((final.estado, final.intentos, final.version), ('NORMAL', 0, before.version + 1))
                self.assertEqual(RecuperacionTIEvento.objects.get(usuario=target).acceso_anterior, estado)
            otra.refresh_from_db()
            EstadoAcceso.objects.filter(usuario=otra).delete()
            with self.assertRaises(APIException):
                recuperar(otra.pk, otra.sesion_version, **META)
            self.assertFalse(EstadoAcceso.objects.filter(usuario=otra).exists())
