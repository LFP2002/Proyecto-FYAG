from django.contrib.auth.hashers import make_password
from django.test import TestCase, TransactionTestCase
from rest_framework.test import APIClient

from apps.finanzas.tests.test_concurrencia import CarrerasPostgreSQL
from apps.obras import services
from apps.obras.exceptions import PermisoDenegado
from apps.obras.models import CategoriaServicio, CategoriaServicioEvento
from apps.usuarios.models import Usuario
from apps.usuarios.tokens import AccessToken


class Categorias020ATests(TestCase):
    def test_seis_roles_dominio_y_http_flags_claims_no_escalan(self):
        client = APIClient()
        for rol in Usuario.Rol:
            actor = Usuario.objects.create_user(username=f'categoria_{rol}', email=f'categoria_{rol}@example.test', rol=rol,
                                                is_staff=True, is_superuser=True)
            actor.rol = 'SUPERVISOR_OBRAS'
            token = AccessToken.for_user(actor)
            token['rol'] = 'SUPERVISOR_OBRAS'
            client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
            esperado = 200 if rol in ['GERENCIA', 'SUPERVISOR_OBRAS'] else 403
            self.assertEqual(client.get('/api/categorias-servicio/').status_code, esperado)
            respuesta = client.post('/api/categorias-servicio/', {'nombre': f'Alta HTTP {rol}'}, format='json')
            self.assertEqual(respuesta.status_code, 201 if rol == 'SUPERVISOR_OBRAS' else 403)
            categoria = CategoriaServicio.objects.create(nombre=f'Categoría {rol}')
            ruta = f'/api/categorias-servicio/{categoria.pk}/'
            self.assertEqual(client.get(ruta + 'historial/').status_code, esperado)
            operaciones = [lambda: services.crear_categoria(f'Nueva {rol}', actor),
                           lambda: services.renombrar_categoria(categoria, f'Editada {rol}', actor, 'Actualización'),
                           lambda: services.desactivar_categoria(categoria, actor, 'Depuración'),
                           lambda: services.activar_categoria(categoria, actor, 'Reactivación')]
            for operacion in operaciones:
                if rol == 'SUPERVISOR_OBRAS':
                    operacion()
                else:
                    with self.assertRaises(PermisoDenegado):
                        operacion()
            for metodo, sufijo, datos in [('patch', '', {'nombre': f'HTTP {rol}', 'motivo': 'Actualización'}),
                                          ('post', 'desactivar/', {'motivo': 'Depuración'}), ('post', 'activar/', {'motivo': 'Reactivación'})]:
                self.assertEqual(getattr(client, metodo)(ruta + sufijo, datos, format='json').status_code,
                                  200 if rol == 'SUPERVISOR_OBRAS' else 403)


class CategoriasAUD012Tests(TransactionTestCase):
    def test_edicion_denegada_tras_cambio_de_hash_en_espera(self):
        actor = Usuario.objects.create_user(username='supervisor', email='supervisor@example.test', rol='SUPERVISOR_OBRAS')
        categoria = CategoriaServicio.objects.create(nombre='Categoría inicial')

        def renombrar():
            with self.assertRaises(PermisoDenegado):
                services.renombrar_categoria(categoria, 'Otro nombre', actor, 'Corrección')

        nuevo_hash = make_password('Sintetica-nueva-QA-012!')
        CarrerasPostgreSQL.race(self, lambda: CategoriaServicio.objects.select_for_update().get(pk=categoria.pk),
            renombrar, tras_espera=lambda: Usuario.objects.filter(pk=actor.pk).update(password=nuevo_hash))
        categoria.refresh_from_db()
        self.assertEqual(categoria.nombre, 'Categoría inicial')
        self.assertFalse(CategoriaServicioEvento.objects.exists())
