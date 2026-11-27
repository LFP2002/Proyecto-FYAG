"""SPEC-025A: catálogo comercial mínimo, de solo lectura."""
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.inventario.models import ArticuloInventario, MovimientoInventario
from apps.inventario.services import crear_articulo
from apps.usuarios.models import Usuario
from .test_presupuesto_api import AF, PresupuestoAPIBase

S = Usuario.Rol.SUPERVISOR_OBRAS


class MaterialesElegibles025A(PresupuestoAPIBase):
    ruta = '/api/presupuestos/materiales-elegibles/'

    def material(self, n, activo=True):
        return crear_articulo({
            'codigo': f'qa25-{n:02}', 'nombre': f'Tubería QA {n:02}',
            'unidad': 'm', 'activo': activo,
        }, self.usuarios[Usuario.Rol.BODEGUERO])

    def test_roles_y_metodos(self):
        self.client.credentials()
        self.assertEqual(self.client.get(self.ruta).status_code, 401)
        for rol in Usuario.Rol:
            self.autenticar(rol)
            for metodo in ('get', 'head', 'options'):
                with self.subTest(rol=rol, metodo=metodo):
                    self.assertEqual(getattr(self.client, metodo)(self.ruta).status_code,
                                     200 if rol in {AF, S} else 403)
        for rol in (AF, S):
            self.autenticar(rol)
            for metodo in ('post', 'patch', 'put', 'delete'):
                self.assertEqual(getattr(self.client, metodo)(self.ruta, {}, format='json').status_code, 405)

    def test_busqueda_paginacion_proyeccion_y_sin_movimientos(self):
        for n in range(28):
            self.material(n)
        self.material(99, activo=False)
        self.autenticar(S)
        antes = (ArticuloInventario.objects.count(), MovimientoInventario.objects.count())
        with CaptureQueriesContext(connection) as consultas:
            respuesta = self.client.get(self.ruta + '?buscar=TUBER')
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.data['count'], 28)
        self.assertEqual(len(respuesta.data['results']), 25)
        self.assertTrue(all(set(row) == {'id', 'codigo', 'nombre', 'unidad'} for row in respuesta.data['results']))
        self.assertEqual(len(self.client.get(self.ruta + '?buscar=QA25&page=2').data['results']), 3)
        self.assertEqual(self.client.get(self.ruta + '?buscar=qa25-99').data['count'], 0)
        self.assertEqual(antes, (ArticuloInventario.objects.count(), MovimientoInventario.objects.count()))
        sql = ' '.join(q['sql'].lower() for q in consultas)
        self.assertNotIn('inventario_existenciainventario', sql)
        self.assertNotIn('inventario_movimientoinventario', sql)

    def test_filtros_invalidos(self):
        self.autenticar(AF)
        for query in ('buscar=', 'buscar=a&buscar=b', 'page=0', 'page=x',
                      'page=1&page=2', 'activo=false', 'buscar=' + 'x'*151,
                      'page=' + '1'*100):
            with self.subTest(query=query):
                self.assertEqual(self.client.get(self.ruta+'?'+query).status_code, 400)
