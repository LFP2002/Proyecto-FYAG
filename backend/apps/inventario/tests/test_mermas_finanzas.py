from django.test import TestCase

from .test_mermas import MermasBase, URLS
from apps.inventario.models import MermaEvento, MovimientoInventario, OperacionMaterial


class MermasFinanzasTests(MermasBase, TestCase):
    def setUp(self):
        self.preparar_mermas()
        self.recibir('10.000', '123.45')

    def test_resumen_global_busqueda_paginacion_y_detalle(self):
        aprobada = self.resolver(self.informar())
        rechazada = self.resolver(self.informar(), 'RECHAZAR')
        for _ in range(26):
            self.informar()
        self.autenticar(self.finanzas)
        url = URLS['BODEGA']
        params = {'vista': 'finanzas', 'buscar': 'manguera', 'estado': 'PENDIENTE'}
        before = self.foto([MermaEvento, MovimientoInventario, OperacionMaterial])
        r = self.client.get(url, params)
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual((r.data['count'], len(r.data['results'])), (26, 25))
        expected = {'pendientes': 26, 'aprobadas': 1, 'rechazadas': 1, 'perdida_neta': '246.90'}
        self.assertEqual(r.data['resumen'], expected)
        self.assertEqual(self.client.get(r.data['next']).data['resumen'], expected)
        self.assertEqual(self.client.get(url, {'vista': 'finanzas', 'buscar': 'ausente'}).data['resumen'], expected)
        self.assertEqual(self.client.get(url, {'vista': 'finanzas', 'buscar': self.article.codigo}).data['count'], 28)
        for m, cost in ((aprobada, '246.90'), (rechazada, None)):
            d = self.client.get(f'{url}{m.pk}/', {'vista': 'finanzas'})
            self.assertEqual(d.status_code, 200, d.data)
            self.assertEqual(d.data['articulo_nombre'], 'Manguera QA')
            self.assertEqual(d.data['articulo_codigo'], self.article.codigo)
            self.assertEqual(d.data['importe_perdida'], cost)
            self.assertTrue(d.data['informado_nombre'])
            self.assertTrue(d.data['decidido_nombre'])
            self.assertEqual(len(d.data['historial']), 2)
        self.assertEqual(self.foto([MermaEvento, MovimientoInventario, OperacionMaterial]), before)
        original = self.client.get(url)
        self.assertNotIn('resumen', original.data)
        self.assertNotIn('articulo_nombre', original.data['results'][0])

    def test_vista_exclusiva_y_filtros(self):
        m = self.informar()
        url = URLS['BODEGA']
        for actor in (self.bodega, self.gerencia, self.supervisor, self.solicitante):
            self.autenticar(actor)
            self.assertEqual(self.client.get(url, {'vista': 'finanzas'}).status_code, 403)
            self.assertEqual(self.client.get(f'{url}{m.pk}/', {'vista': 'finanzas'}).status_code, 403)
        self.autenticar(self.finanzas)
        for q in ('?vista=otra', '?vista=finanzas&vista=finanzas', '?buscar=x',
                  '?vista=finanzas&buscar=%20', '?vista=finanzas&buscar='+'x'*151):
            self.assertEqual(self.client.get(url+q).status_code, 400, q)
        self.assertEqual(self.client.get(URLS['OBRA'], {'vista': 'finanzas'}).status_code, 403)
        self.assertEqual(self.client.post(url, {}, format='json').status_code, 403)

    def test_decision_con_uuid_y_relectura_financiera(self):
        m = self.informar()
        self.autenticar(self.finanzas)
        url = URLS['BODEGA']
        payload = self.entrada_decision_merma()
        for _ in range(2):
            r = self.client.post(f'{url}{m.pk}/decidir/', payload, format='json')
            self.assertEqual(r.status_code, 200, r.data)
        d = self.client.get(f'{url}{m.pk}/', {'vista': 'finanzas'})
        self.assertEqual(d.data['estado'], 'APROBADA')
        self.assertEqual(d.data['importe_perdida'], '246.90')
        self.assertEqual(MovimientoInventario.objects.filter(tipo='MERMA').count(), 1)
        self.assertEqual(self.saldo(), 8)
