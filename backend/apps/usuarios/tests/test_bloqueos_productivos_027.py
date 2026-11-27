from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import connection
from django.test import TransactionTestCase, override_settings
from django.utils import timezone
from redis.exceptions import ConnectionError
from rest_framework.test import APIClient

from apps.chat import tickets
from apps.usuarios import recuperacion_correo, throttles
from apps.usuarios.models import DesafioRecuperacionCorreo, EstadoAcceso, EventoAcceso, SeguridadCredencial, Usuario
from apps.usuarios.preflight_bloqueos import preflight_si_productivo
from apps.usuarios.recuperacion_ti import recuperar
from apps.usuarios.tokens import AccessToken, RefreshToken
from .test_administracion import NEW_PASSWORD, PASSWORD


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'],
    FYAG_BLOQUEOS_PERFIL='produccion', SECURE_SSL_REDIRECT=True, SESSION_COOKIE_SECURE=True,
    CSRF_COOKIE_SECURE=True, JWT_REFRESH_COOKIE_SECURE=True, FYAG_BLOQUEOS_DOMINIO='institucion.example.org',
    FYAG_BLOQUEOS_CORREO_TI='admin@institucion.example.org', FYAG_BLOQUEOS_AUTORIZACION='AUT-QA-027',
    FYAG_BLOQUEOS_ENTREGA_SMTP='SMTP-QA-027', FYAG_PUBLIC_BASE_URL='https://fyag.example.org',
    FYAG_EMAIL_PROFILE='smtp', EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend',
    EMAIL_HOST='smtp.example.org', EMAIL_HOST_USER='qa', EMAIL_HOST_PASSWORD='sintetica', EMAIL_USE_TLS=True,
    EMAIL_USE_SSL=False, DEFAULT_FROM_EMAIL='avisos@institucion.example.org')
class BloqueosProductivosTests(TransactionTestCase):
    def setUp(self):
        redis = throttles._client(settings.FYAG_SECURITY_REDIS_URL)
        self.enterContext(override_settings(FYAG_SECURITY_REDIS_URL='rediss://:sintetica@redis-prueba:6380/0',
                                            FYAG_SECURITY_REDIS_PREFIX=f'qa:prod:{uuid4().hex}'))
        # En el laboratorio se usa Redis efímero real, no el transporte productivo.
        self.enterContext(patch.object(throttles, '_client', return_value=redis))
        self.ti = self.cuenta('ADMINISTRADOR_TI', email=settings.FYAG_BLOQUEOS_CORREO_TI)

    def cuenta(self, rol, email=None):
        alias = uuid4().hex
        return Usuario.objects.create_user(username=alias, email=email or f'{alias}@qa.test', rol=rol,
                                           password=PASSWORD, correo_verificado_en=timezone.now())

    def post(self, path, data=None, cookie=None):
        client = APIClient(enforce_csrf_checks=True)
        csrf = client.get('/api/auth/csrf/', secure=True).data['csrfToken']
        if cookie:
            client.cookies[settings.JWT_REFRESH_COOKIE_NAME] = cookie
        return client.post('/api/auth/' + path, data or {}, format='json', secure=True,
                           HTTP_X_CSRFTOKEN=csrf, HTTP_REFERER='https://testserver/')

    def login(self, user, password=PASSWORD):
        return self.post('login/', {'email': user.email, 'password': password})

    def fallar(self, user):
        with override_settings(FYAG_SECURITY_REDIS_PREFIX=f'qa:prod:{uuid4().hex}'):
            for _ in range(5):
                response = self.login(user, 'incorrecta')
                self.assertEqual(response.status_code, 401)
        return EstadoAcceso.objects.get(usuario=user)

    def test_seis_roles_incluida_ultima_ti_y_recuperacion_excepcional(self):
        access, refresh = AccessToken.for_user(self.ti), RefreshToken.for_user(self.ti)
        socket, _ = tickets.emitir(self.ti)
        canal = tickets.admitir('127.0.0.1')
        identity = tickets.consumir(socket, canal)
        for rol in Usuario.Rol.values:
            user = self.ti if rol == 'ADMINISTRADOR_TI' else self.cuenta(rol)
            self.assertEqual(self.fallar(user).estado, 'BLOQUEO_TEMPORAL')
        self.assertEqual(Usuario.objects.filter(rol='ADMINISTRADOR_TI').count(), 1)
        self.assertEqual(APIClient().get('/api/auth/me/', secure=True, HTTP_AUTHORIZATION=f'Bearer {access}').status_code, 401)
        self.assertEqual(self.post('refresh/', cookie=str(refresh)).status_code, 401)
        with self.assertRaises(tickets.Denegado):
            tickets.verificar(identity, canal)
        with self.assertRaisesMessage(ImproperlyConfigured, 'TI institucional'):
            preflight_si_productivo()
        with patch.object(throttles, '_client', side_effect=ConnectionError), patch('django.core.mail.backends.smtp.EmailBackend.open', side_effect=OSError):
            temporal = recuperar(self.ti.pk, self.ti.sesion_version + 1, operador='qa', referencia='AUT-027', motivo='Prueba').credencial_temporal
        with patch('apps.usuarios.preflight_bloqueos.get_connection'):
            self.assertTrue(preflight_si_productivo())
            vence_en = SeguridadCredencial.objects.get(usuario=self.ti).vence_en
            with patch('apps.usuarios.preflight_bloqueos.timezone.now', return_value=vence_en), self.assertRaisesMessage(ImproperlyConfigured, 'TI institucional'):
                preflight_si_productivo()
        login = self.login(self.ti, temporal)
        self.assertEqual(login.data['estado'], 'CAMBIO_OBLIGATORIO')
        self.assertEqual(self.post('primer-cambio-clave/', {'desafio': login.data['desafio'], 'nueva_clave': NEW_PASSWORD}).status_code, 200)
        self.assertEqual(self.login(self.ti, NEW_PASSWORD).status_code, 200)

    def test_cuatro_ciclos_fronteras_recuperacion_correo_y_auditoria(self):
        target = self.cuenta('TECNICO')
        ahora = timezone.now() + timedelta(seconds=1)
        with patch('apps.usuarios.autenticacion_c2.timezone.now', side_effect=lambda: ahora):
            for minutos in (15, 60, 240):
                state = self.fallar(target)
                fin = ahora + timedelta(minutes=minutos)
                self.assertEqual(state.bloqueado_hasta, fin)
                ahora = fin - timedelta(microseconds=1)
                self.assertEqual(self.login(target).status_code, 401)
                state.refresh_from_db()
                self.assertEqual(state.bloqueado_hasta, fin)
                ahora = fin
            self.assertEqual(self.fallar(target).estado, 'REQUIERE_TI')
            token = 'A' * 43
            DesafioRecuperacionCorreo.objects.create(usuario=target, digest=recuperacion_correo._digest(token),
                vinculo=recuperacion_correo._vinculo(Usuario.objects.get(pk=target.pk), target.seguridad_credencial),
                vence_en=ahora + timedelta(minutes=15))
            # La caída SMTP posterior al commit no deshace la recuperación.
            with patch('django.core.mail.backends.smtp.EmailBackend.open', side_effect=OSError), self.assertLogs('apps.usuarios.correo', 'WARNING'):
                recuperacion_correo.confirmar(token, NEW_PASSWORD)
            self.assertEqual(EstadoAcceso.objects.get(usuario=target).estado, 'NORMAL')
            self.assertEqual(self.login(target, NEW_PASSWORD).status_code, 200)
            for rol in Usuario.Rol.values:
                actor = self.ti if rol == 'ADMINISTRADOR_TI' else self.cuenta(rol)
                client = APIClient()
                client.credentials(HTTP_AUTHORIZATION=f'Bearer {AccessToken.for_user(actor)}')
                audit = client.get('/api/auditoria/eventos/', {'fuente':'EVENTO_ACCESO', 'recurso_tipo':'USUARIO', 'recurso_id':target.pk}, secure=True)
                history = client.get(f'/api/usuarios/{target.pk}/historial/', secure=True)
                if rol == 'ADMINISTRADOR_TI':
                    self.assertEqual(len(audit.data['results']), 7)
                    self.assertEqual(history.data['count'], 8)
                    self.assertTrue(all(r['actor_identidad_origen'] == 'SISTEMA' and r['actor'] is None for r in audit.data['results']))
                    self.assertNotIn(token, str(history.data))
                else:
                    self.assertEqual((audit.status_code, history.status_code), (403, 403))

    def test_limite_compartido_y_fallo_redis_no_cuentan(self):
        for _ in range(30):
            self.assertEqual(self.post('refresh/').status_code, 401)
        self.assertEqual(self.post('primer-cambio-clave/').status_code, 429)
        for _ in range(5):
            self.assertEqual(self.login(self.ti).status_code, 200)
        self.assertEqual(self.login(self.ti, 'incorrecta').status_code, 429)
        with patch.object(throttles, '_client', side_effect=ConnectionError):
            for path in ('login/', 'refresh/', 'primer-cambio-clave/'):
                self.assertEqual(self.post(path, {'email':self.ti.email, 'password':'incorrecta'}).status_code, 503)
        self.assertEqual(EstadoAcceso.objects.get(usuario=self.ti).intentos, 0)

    def test_concurrencia_y_reset_administrativo_sin_evento_duplicado(self):
        user = self.cuenta('BODEGUERO')
        gate = Barrier(5)
        def intento():
            try:
                gate.wait(timeout=10)
                return self.login(user, 'incorrecta').status_code
            finally:
                connection.close()
        with ThreadPoolExecutor(max_workers=5) as pool:
            jobs = [pool.submit(intento) for _ in range(5)]
            self.assertEqual([job.result(timeout=15) for job in jobs], [401] * 5)
        self.assertEqual(EventoAcceso.objects.filter(usuario=user, tipo='BLOQUEO_TEMPORAL').count(), 1)
        from apps.usuarios.credenciales import restablecer_clave
        restablecer_clave(user, {'motivo':'QA'}, self.ti)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {AccessToken.for_user(self.ti)}')
        history = client.get(f'/api/usuarios/{user.pk}/historial/', secure=True).data
        self.assertEqual(history['count'], 2)
        row = history['results'][-1]
        self.assertEqual((row['tipo'], row['datos_anteriores'], row['datos_nuevos']),
                         ('REEMISION', {'acceso_estado':'BLOQUEO_TEMPORAL'}, {'acceso_estado':'NORMAL'}))

    def test_preflight_y_configuraciones_invalidas(self):
        with patch('apps.usuarios.preflight_bloqueos.get_connection') as smtp:
            self.assertTrue(preflight_si_productivo())
            smtp.assert_called_once()
        for override in ({'FYAG_BLOQUEOS_AUTORIZACION':''}, {'FYAG_BLOQUEOS_ENTREGA_SMTP':''}, {'JWT_REFRESH_COOKIE_SECURE':False},
                         {'EMAIL_USE_TLS':False}, {'FYAG_SECURITY_REDIS_URL':'redis://redis-prueba:6379/0'},
                         {'FYAG_BLOQUEOS_CORREO_TI':'ausente@institucion.example.org'}):
            with override_settings(**override), self.assertRaises(ImproperlyConfigured):
                preflight_si_productivo()
        with patch('apps.usuarios.preflight_bloqueos.get_connection', side_effect=OSError), self.assertRaisesMessage(ImproperlyConfigured, 'SMTP'):
            preflight_si_productivo()
        with patch.object(throttles, '_client', side_effect=ConnectionError), self.assertRaisesMessage(ImproperlyConfigured, 'Redis'):
            preflight_si_productivo()
