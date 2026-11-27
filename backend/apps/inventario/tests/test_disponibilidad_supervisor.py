from django.test import TestCase

from apps.inventario import services
from apps.inventario.models import MovimientoInventario, OperacionMaterial
from .test_spec019f import PrevisionBase

URL = '/api/inventario/disponibilidad/'


class DisponibilidadSupervisorTests(PrevisionBase, TestCase):
    def setUp(self):
        self.preparar_materiales()
        self.autenticar(self.supervisor)

    def read(self, **filters):
        r = self.client.get(URL, filters)
        self.assertEqual(r.status_code, 200, r.data)
        return r.data

    def test_indicadores_globales_y_paginacion_no_dependen_de_filtros(self):
        self.recibir()
        for i in range(26):
            services.crear_articulo({'codigo': f'qa-{i}', 'nombre': f'Material QA {i}', 'unidad': 'kg'}, self.bodega)
        inactive = services.crear_articulo({'codigo': 'inactivo-qa', 'nombre': 'Inactivo QA', 'unidad': 'kg'}, self.bodega)
        services.editar_articulo(inactive.pk, {'activo': False}, self.bodega)
        a = self.autorizar('5.000')
        self.entregar('2.000', a)
        data = self.read()
        self.assertEqual(data['count'], 27)
        self.assertEqual(len(data['results']), 25)
        self.assertIsNotNone(data['next'])
        summary = {'disponibles': 1, 'sin_stock': 26, 'despachos_pendientes': 1}
        self.assertEqual(data['resumen'], summary)
        self.assertEqual(self.read(page=2)['resumen'], summary)
        filtered = self.read(stock='sin_stock', buscar='QA')
        self.assertEqual(filtered['count'], 26)
        self.assertEqual(filtered['resumen'], summary)
        self.assertEqual(self.read(buscar='inactivo-qa')['count'], 0)
        self.assertEqual(self.read(stock='con_stock')['results'][0]['saldo'], '8.000')

    def test_parcial_devolucion_e_historial_sin_costos(self):
        self.recibir()
        a = self.autorizar('5.000')
        e = self.entregar('2.000', a)
        d = self.op('AUTORIZACION_DEVOLUCION', entrega=e.pk, cantidad='1.000')
        row = self.read(seccion='pendientes', buscar=self.obra.codigo)['results'][0]
        self.assertEqual((row['ejecutada'], row['pendiente']), ('2.000', '3.000'))
        self.assertEqual(row['obra'], self.obra.codigo)
        self.assertEqual(self.read(seccion='historial', vista='por_recibir')['results'][0]['pendiente'], '1.000')
        self.op('DEVOLUCION', autorizacion=d.pk, cantidad='1.000')
        self.assertEqual(self.read(seccion='historial', vista='por_recibir')['count'], 0)
        self.assertEqual(self.read(seccion='historial')['count'], 2)
        for vista in ('entregas', 'devoluciones'):
            row = self.read(seccion='historial', vista=vista)['results'][0]
            self.assertFalse({'costo_unitario_neto', 'promedio', 'clave_idempotencia', 'maximo'} & set(row))
        self.entregar('3.000', a)
        self.assertEqual(self.read(seccion='pendientes')['count'], 0)
        self.assertEqual(self.read()['resumen']['despachos_pendientes'], 0)

    def test_cierre_retira_pendientes_sin_borrar_historial(self):
        self.recibir()
        a = self.autorizar('5.000')
        self.entregar('2.000', a)
        self.acreditar()
        self.validar()
        self.finalizar(self.confirmacion_cierre())
        self.assertEqual(self.read(seccion='pendientes')['count'], 0)
        self.assertEqual(self.read()['resumen']['despachos_pendientes'], 0)
        self.assertEqual(self.read(seccion='historial')['count'], 1)

    def test_permiso_exclusivo_filtros_y_solo_lectura(self):
        for actor in (self.bodega, self.finanzas, self.gerencia):
            self.autenticar(actor)
            self.assertEqual(self.client.get(URL).status_code, 403)
        self.autenticar(self.supervisor)
        for query in ('?seccion=otro', '?stock=otro', '?vista=entregas', '?seccion=pendientes&stock=sin_stock',
                      '?seccion=historial&vista=otro', '?buscar=%20', '?buscar=a&buscar=b'):
            self.assertEqual(self.client.get(URL + query).status_code, 400, query)
        self.assertIn(self.client.post(URL, {}, format='json').status_code, (403, 405))
        self.assertFalse(MovimientoInventario.objects.exists())
        self.assertFalse(OperacionMaterial.objects.exists())
