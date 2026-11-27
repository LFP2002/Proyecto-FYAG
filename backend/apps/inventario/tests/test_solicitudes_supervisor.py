from django.test import TestCase

from apps.inventario.models import MovimientoInventario, OperacionMaterial
from .test_solicitudes import SolicitudesBase

URL = '/api/inventario/solicitudes-supervisor/'


class SolicitudesSupervisorTests(SolicitudesBase, TestCase):
    def setUp(self):
        self.preparar_solicitudes()
        self.autenticar(self.supervisor)

    def test_bandeja_nombres_stock_filtros_e_indicadores_globales(self):
        self.recibir('3.000')
        pending = self.solicitar()
        approved = self.decidir(self.solicitar(), cantidad_aprobada='2.000')
        self.decidir(self.solicitar(), 'RECHAZAR')
        r = self.client.get(URL, {'estado': 'PENDIENTE', 'buscar': self.obra.codigo})
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data['resumen'], {'pendientes': 1, 'aprobadas': 1, 'rechazadas': 1})
        self.assertEqual(r.data['count'], 1)
        row = r.data['results'][0]
        self.assertEqual(row['id'], pending.pk)
        self.assertEqual(row['material'], self.article.nombre)
        self.assertEqual(row['solicitante'], self.solicitante.get_full_name().strip() or self.solicitante.username)
        self.assertEqual(row['saldo'], '3.000')
        self.assertFalse({'clave_idempotencia', 'costo_unitario_neto'} & set(row))
        detail = self.client.get(f'{URL}{approved.pk}/')
        self.assertEqual(detail.status_code, 200, detail.data)
        self.assertEqual(detail.data['cantidad_aprobada'], '2.000')
        self.assertEqual([e['tipo'] for e in detail.data['historial']], ['CREACION', 'APROBACION'])
        self.assertEqual(OperacionMaterial.objects.filter(tipo='ENTREGA').count(), 0)
        self.assertEqual(MovimientoInventario.objects.count(), 1)

    def test_lectura_exclusiva_y_filtros_invalidos(self):
        s = self.solicitar()
        for actor in (self.solicitante, self.bodega, self.finanzas, self.gerencia):
            self.autenticar(actor)
            self.assertEqual(self.client.get(URL).status_code, 403)
            self.assertEqual(self.client.get(f'{URL}{s.pk}/').status_code, 403)
        self.autenticar(self.supervisor)
        for q in ('?estado=otro', '?buscar=%20', '?buscar=a&buscar=b', '?obra=1'):
            self.assertEqual(self.client.get(URL+q).status_code, 400, q)
        self.assertEqual(self.client.get(f'{URL}{s.pk}/?page=1').status_code, 400)
        self.assertIn(self.client.post(URL, {}, format='json').status_code, (403, 405))
        self.assertFalse(OperacionMaterial.objects.exists())
