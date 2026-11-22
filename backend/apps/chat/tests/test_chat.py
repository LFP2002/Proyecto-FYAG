from datetime import timedelta
import json
from uuid import uuid4
from unittest.mock import patch

from django.db import connection, transaction, IntegrityError
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.exceptions import APIException

from apps.chat import services, consultas
from apps.chat.models import ConversacionChat as Conversacion, ParticipanteChat as Participante, MensajeChat as Mensaje, ActoChat
from apps.usuarios.models import Usuario, SeguridadCredencial
from .base import ChatBase, URL


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class ChatTests(ChatBase, TestCase):
    def setUp(self):
        self.preparar()

    def test_directa_unica_par_no_ordenado_y_replays(self):
        data = self.entrada_directa()
        c, nuevo = services.crear_conversacion(data, self.actor)
        replay, nuevo2 = services.crear_conversacion(data, self.actor)
        inversa, nuevo3 = services.crear_conversacion(self.entrada_directa(self.actor), self.otro)
        self.assertEqual((nuevo, nuevo2, nuevo3), (True, False, False))
        self.assertEqual((c.pk, replay.pk), (inversa.pk, inversa.pk))
        self.assertEqual(set(c.participantes.values_list('usuario_id', flat=True)), {self.actor.pk, self.otro.pk})
        with self.assertRaises(APIException) as error:
            services.crear_conversacion({**data, 'destinatario': self.ajeno.pk}, self.actor)
        self.assertEqual(error.exception.status_code, 409)

    def test_grupo_membresia_fija_y_uuid_distinto_otro_grupo(self):
        data = {'tipo': 'GRUPAL', 'titulo': ' Equipo QA ', 'participantes': [self.otro.pk, self.ajeno.pk], 'clave_idempotencia': str(uuid4())}
        c, _ = services.crear_conversacion(data, self.actor)
        replay, nuevo = services.crear_conversacion({**data, 'participantes': list(reversed(data['participantes']))}, self.actor)
        otro, _ = services.crear_conversacion({**data, 'clave_idempotencia': str(uuid4())}, self.actor)
        self.assertEqual(c.pk, replay.pk)
        self.assertFalse(nuevo)
        self.assertNotEqual(c.pk, otro.pk)
        self.assertEqual(c.titulo, 'Equipo QA')
        with self.assertRaises(IntegrityError), transaction.atomic():
            Participante.objects.create(conversacion=c, usuario=self.users[-1])

    def test_grupo_limites_y_participantes_estrictos(self):
        for miembros in [[], [self.otro.pk], [self.otro.pk, self.otro.pk], [self.actor.pk, self.otro.pk], [True, self.otro.pk], list(range(1, 21))]:
            r = self.client.post(URL+'conversaciones/', {'tipo': 'GRUPAL', 'titulo': 'QA', 'participantes': miembros, 'clave_idempotencia': str(uuid4())}, format='json')
            self.assertEqual(r.status_code, 400, r.data)

    def test_directorio_elegible_sin_email_seguridad_ni_ajenos(self):
        Usuario.objects.filter(pk=self.users[-1].pk).update(is_active=False)
        ahora = timezone.now()
        SeguridadCredencial.objects.filter(usuario=self.users[-2]).update(estado='INICIAL', emitida_en=ahora, vence_en=ahora+timedelta(hours=1))
        r = self.client.get(URL+'usuarios/')
        ids = {u['id'] for u in r.data['results']}
        self.assertNotIn(self.actor.pk, ids)
        self.assertNotIn(self.users[-1].pk, ids)
        self.assertNotIn(self.users[-2].pk, ids)
        for u in r.data['results']:
            self.assertEqual(set(u), {'id', 'nombre', 'rol'})
        self.assertEqual(self.client.get(URL+'usuarios/', {'buscar': self.otro.username}).data['results'][0]['id'], self.otro.pk)

    def test_seis_roles_sin_privilegios_para_ajenos(self):
        conv = self.directa()
        mensaje = self.enviar(conv)
        for user in self.users:
            self.autenticar(user)
            self.assertEqual(self.client.get(URL+'usuarios/').status_code, 200)
            propio = user.pk in {self.actor.pk, self.otro.pk}
            self.assertEqual(self.client.get(f'{URL}conversaciones/{conv.pk}/').status_code, 200 if propio else 404)
            self.assertEqual(self.client.get(f'{URL}conversaciones/{conv.pk}/mensajes/').status_code, 200 if propio else 404)
            self.assertEqual(self.client.post(f'{URL}conversaciones/{conv.pk}/leido/', {'ultimo_mensaje_id': mensaje.pk}, format='json').status_code, 200 if propio else 404)
            r = self.client.post(f'{URL}conversaciones/{conv.pk}/mensajes/', {'texto': 'QA', 'clave_idempotencia': str(uuid4())}, format='json')
            self.assertEqual(r.status_code, 201 if propio else 404, r.data)
        self.ajeno.is_staff = self.ajeno.is_superuser = True
        self.ajeno.save(update_fields=['is_staff', 'is_superuser'])
        self.autenticar(self.ajeno)
        self.assertEqual(self.client.get(f'{URL}conversaciones/{conv.pk}/').status_code, 404)

    def test_historial_cursor_estable_y_no_leidos(self):
        c = self.directa()
        mensajes = [self.enviar(c, actor=self.otro, texto=f'QA {i}') for i in range(27)]
        self.enviar(c)  # Mensaje propio no cuenta.
        ruta = f'{URL}conversaciones/{c.pk}/'
        r = self.client.get(ruta+'mensajes/')
        self.assertEqual(len(r.data['results']), 25)
        self.assertEqual(r.data['results'], sorted(r.data['results'], key=lambda m: m['id'], reverse=True))
        next_id = r.data['siguiente_antes_id']
        self.assertEqual(len(self.client.get(ruta+'mensajes/', {'antes_id': next_id}).data['results']), 3)
        detalle = self.client.get(ruta)
        self.assertEqual(detalle.status_code, 200, detalle.data)
        self.assertEqual(detalle.data['no_leidos'], 27)
        self.assertEqual(self.client.get(URL+'conversaciones/').data['results'][0]['no_leidos'], 27)
        services.leer(c.pk, {'ultimo_mensaje_id': mensajes[20].pk}, self.actor)
        services.leer(c.pk, {'ultimo_mensaje_id': mensajes[1].pk}, self.actor)
        self.assertEqual(self.client.get(ruta).data['no_leidos'], 6)
        p = Participante.objects.get(conversacion=c, usuario=self.otro)
        self.assertIsNone(p.ultimo_leido_mensaje_id)

    def test_leido_id_futuro_ajeno_y_mensaje_expirado_denegados(self):
        c = self.directa()
        otro = self.directa(destinatario=self.ajeno.pk)
        m = self.enviar(otro)
        for pk in [m.pk, m.pk+100000]:
            with self.assertRaises(APIException) as error:
                services.leer(c.pk, {'ultimo_mensaje_id': pk}, self.actor)
            self.assertEqual(error.exception.status_code, 404)
        with patch('apps.chat.services.timezone.now', return_value=timezone.now()-timedelta(days=31)):
            viejo = self.enviar(c, actor=self.otro)
        with self.assertRaises(APIException):
            services.leer(c.pk, {'ultimo_mensaje_id': viejo.pk}, self.actor)
        self.assertEqual(self.client.get(f'{URL}conversaciones/{c.pk}/mensajes/').data['results'], [])
        self.assertEqual(self.client.get(f'{URL}conversaciones/{c.pk}/').data['no_leidos'], 0)

    def test_texto_idempotente_normalizado_y_no_editable(self):
        c = self.directa()
        data = {'texto': ' Cafe\u0301 ', 'clave_idempotencia': str(uuid4())}
        m, nuevo = services.publicar_texto(c.pk, data, self.actor)
        r, nuevo2 = services.publicar_texto(c.pk, {**data, 'texto': 'Café'}, self.actor)
        self.assertEqual((m.pk, nuevo, nuevo2, m.texto), (r.pk, True, False, 'Café'))
        with self.assertRaises(APIException):
            services.publicar_texto(c.pk, {**data, 'texto': 'Diferente'}, self.actor)
        with self.assertRaises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
            cursor.execute("UPDATE chat_mensajechat SET texto='Cambio' WHERE id=%s", [m.pk])
        with self.assertRaises(IntegrityError), transaction.atomic():
            m.delete()

    def test_json_ids_texto_queries_y_campos_estrictos(self):
        c = self.directa()
        ruta = f'{URL}conversaciones/{c.pk}/mensajes/'
        for value in ['', ' ', 'x'*2001, 'a\ncontrol', 'a\x85control', True, None, ['texto']]:
            self.assertEqual(self.client.post(ruta, {'texto': value, 'clave_idempotencia': str(uuid4())}, format='json').status_code, 400)
        for extra in ['autor', 'fecha', 'vence_en', 'id', 'archivo']:
            self.assertEqual(self.client.post(ruta, {'texto': 'QA', 'clave_idempotencia': str(uuid4()), extra: 1}, format='json').status_code, 400)
        r = self.client.post(ruta, data='{"texto":"a","texto":"b","clave_idempotencia":"'+str(uuid4())+'"}', content_type='application/json')
        self.assertEqual(r.status_code, 400)
        for value in ['01', '0', '-1', 'true', '9223372036854775808']:
            self.assertEqual(self.client.get(f'{URL}conversaciones/{value}/').status_code, 400)
        for path in ['usuarios/?email=a', 'usuarios/?buscar=', 'conversaciones/?page=0', f'conversaciones/{c.pk}/mensajes/?page=1', f'conversaciones/{c.pk}/mensajes/?antes_id=1&antes_id=2']:
            self.assertEqual(self.client.get(URL+path).status_code, 400)

    def test_credenciales_temporales_sesion_revocada_y_cuenta_inactiva(self):
        token = self.client._credentials['HTTP_AUTHORIZATION']
        Usuario.objects.filter(pk=self.actor.pk).update(sesion_version=self.actor.sesion_version+1)
        self.assertEqual(self.client.get(URL+'usuarios/').status_code, 401)
        self.actor.refresh_from_db(); self.autenticar(self.actor)
        Usuario.objects.filter(pk=self.actor.pk).update(is_active=False)
        self.assertEqual(self.client.get(URL+'usuarios/').status_code, 401)
        Usuario.objects.filter(pk=self.actor.pk).update(is_active=True)
        ahora = timezone.now()
        SeguridadCredencial.objects.filter(usuario=self.actor).update(estado='INICIAL', emitida_en=ahora, vence_en=ahora+timedelta(hours=1))
        self.assertEqual(self.client.get(URL+'usuarios/').status_code, 401)

    def test_get_sin_escrituras_headers_y_ticket_ws(self):
        c = self.directa(); self.enviar(c)
        with CaptureQueriesContext(connection) as queries:
            for path in ['usuarios/', 'conversaciones/', f'conversaciones/{c.pk}/', f'conversaciones/{c.pk}/mensajes/']:
                r = self.client.get(URL+path)
                self.assertEqual(r.status_code, 200, r.data)
                self.assertEqual(r['Cache-Control'], 'private, no-store')
                self.assertIn('Authorization', r['Vary'])
                self.assertEqual(r['X-Content-Type-Options'], 'nosniff')
        self.assertFalse(any(q['sql'].lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE')) for q in queries))
        self.assertEqual(self.client.post(URL+'conexion/', {}, format='json').status_code, 201)
        self.assertEqual(self.client.patch(f'{URL}conversaciones/{c.pk}/', {}, format='json').status_code, 405)

    @override_settings(CHAT_LIMITES={'conversacion': (1, 100), 'mensaje': (1, 100), 'archivo': (1, 100)})
    def test_rate_limit_usuario_y_retry_after(self):
        self.assertEqual(self.client.post(URL+'conversaciones/', self.entrada_directa(), format='json').status_code, 201)
        r = self.client.post(URL+'conversaciones/', self.entrada_directa(), format='json')
        self.assertEqual(r.status_code, 429)
        self.assertIn('Retry-After', r)

    @override_settings(CHAT_LIMITES={'conversacion': (100, 1), 'mensaje': (100, 1), 'archivo': (100, 1)})
    def test_rate_limit_ip_no_se_evade_cambiando_usuario(self):
        self.assertEqual(self.client.post(URL+'conversaciones/', self.entrada_directa(), format='json').status_code, 201)
        self.autenticar(self.ajeno)
        r = self.client.post(URL+'conversaciones/', self.entrada_directa(), format='json')
        self.assertEqual(r.status_code, 429)

    def test_directorio_paginacion_25_y_scopes_sin_n_mas_uno(self):
        prefijo = f'dirchat_{self.actor.pk}_'
        for i in range(26):
            Usuario.objects.create_user(username=prefijo+str(i), email=f'{prefijo}{i}@chat.test', rol='TECNICO')
        with CaptureQueriesContext(connection) as queries:
            r = self.client.get(URL+'usuarios/', {'buscar': prefijo})
        self.assertEqual((r.data['count'], len(r.data['results'])), (26, 25))
        self.assertEqual(len(self.client.get(r.data['next']).data['results']), 1)
        self.assertLess(len(queries), 10)

    def test_sql_tercero_no_publica_ni_altera_cursor_o_membresia(self):
        c = self.directa(); m = self.enviar(c)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Mensaje.objects.create(conversacion=c, autor=self.ajeno, texto='Intruso', vence_en=timezone.now()+timedelta(days=30), clave_idempotencia=uuid4(), huella='a'*64)
        p = Participante.objects.get(conversacion=c, usuario=self.actor)
        services.leer(c.pk, {'ultimo_mensaje_id': m.pk}, self.actor)
        with self.assertRaises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
            cursor.execute('UPDATE chat_participantechat SET ultimo_leido_mensaje_id=NULL WHERE id=%s', [p.pk])
        with self.assertRaises(IntegrityError), transaction.atomic():
            Participante.objects.filter(pk=p.pk).delete()
