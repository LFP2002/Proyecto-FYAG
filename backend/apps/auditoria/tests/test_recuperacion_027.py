from django.test import TestCase
from rest_framework.test import APIClient

from apps.usuarios.models import RecuperacionCorreoEvento, Usuario, UsuarioEvento
from apps.usuarios.tokens import AccessToken
from .base import URL


class AuditoriaRecuperacionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.users = {rol: Usuario.objects.create_user(username=rol, email=f'{rol}@qa.test', rol=rol)
                     for rol in Usuario.Rol.values}
        cls.target = cls.users['TECNICO']
        cls.actor = cls.users['ADMINISTRADOR_TI']
        cls.history_url = f'/api/usuarios/{cls.target.pk}/historial/'
        cls.legacy = UsuarioEvento.objects.create(usuario_objetivo=cls.target, actor=cls.actor, tipo='EDICION')
        cls.event = RecuperacionCorreoEvento.objects.create(usuario=cls.target, acceso_anterior='REQUIERE_TI', acceso_version_nueva=7)

    def login(self, user):
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {AccessToken.for_user(user)}')

    def test_fuente_privada_orden_filtros_y_cursor(self):
        self.login(self.actor)
        response = self.client.get(URL, {'modulo': 'USUARIOS', 'limit': 1})
        self.assertEqual(response.status_code, 200)
        row, = response.data['results']
        self.assertEqual(row['id'], f'{self.event.FUENTE}:{self.event.pk}')
        self.assertEqual(row['tipo'], self.event.TIPO)
        self.assertEqual(row['recurso_id'], self.target.pk)
        self.assertEqual(row['actor_identidad_origen'], self.event.AUTORIDAD)
        self.assertIsNone(row['actor'])
        self.assertIsNone(row['actor_username'])
        self.assertEqual(row['datos_anteriores'], {'acceso_estado': 'REQUIERE_TI'})
        self.assertEqual(row['datos_nuevos'], {})
        self.assertNotIn('acceso_version_nueva', row)
        next_ = self.client.get(URL, {'cursor': response.data['next_cursor']}).data
        self.assertEqual([e['id'] for e in next_['results']], [f'USUARIO_EVENTO:{self.legacy.pk}'])
        filters = {'fuente': self.event.FUENTE, 'tipo': self.event.TIPO, 'recurso_tipo': 'USUARIO', 'recurso_id': self.target.pk}
        self.assertEqual(self.client.get(URL, filters).data['results'], [row])
        self.assertEqual(self.client.get(URL, {**filters, 'actor': self.target.pk}).data['results'], [])
        self.assertEqual(self.client.get(URL, {**filters, 'recurso_id': self.actor.pk}).data['results'], [])

    def test_historial_mezclado_paginado_y_sin_duplicados(self):
        self.login(self.actor)
        for _ in range(24):
            RecuperacionCorreoEvento.objects.create(usuario=self.target)
        result = self.client.get(self.history_url)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.data['count'], 26)
        rows = result.data['results'] + self.client.get(self.history_url, {'page': 2}).data['results']
        self.assertEqual(len({x['id'] for x in rows}), 26)
        self.assertEqual(rows[0]['id'], self.legacy.pk)
        self.assertEqual(rows[1]['acceso_anterior'], 'REQUIERE_TI')
        self.assertEqual(rows[1]['usuario_objetivo'], self.target.pk)
        self.assertEqual(rows[1]['actor_identidad_origen'], self.event.AUTORIDAD)
        self.assertIsNone(rows[1]['actor'])
        self.assertIsNone(rows[-1]['acceso_anterior'])
        self.assertEqual(self.client.get(self.history_url, {'tipo': self.event.TIPO}).status_code, 400)

    def test_denegado_a_cinco_roles_y_anonimo(self):
        self.assertEqual(self.client.get(self.history_url).status_code, 401)
        self.assertEqual(self.client.get(URL, {'fuente': self.event.FUENTE}).status_code, 401)
        for rol, user in self.users.items():
            if rol != self.actor.rol:
                self.login(user)
                self.assertEqual(self.client.get(self.history_url).status_code, 403)
                self.assertEqual(self.client.get(URL, {'fuente': self.event.FUENTE}).status_code, 403)
