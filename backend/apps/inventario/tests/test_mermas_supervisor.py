from django.test import TestCase

from apps.inventario.models import MovimientoInventario, OperacionMaterial, ExistenciaInventario
from apps.obras.models import GastoObra
from .test_mermas import MermasBase

URL = '/api/inventario/mermas-supervisor/'


class MermasSupervisorTests(MermasBase, TestCase):
    def setUp(self):
        self.preparar_mermas()
        self.preparar_entrega()
        self.autenticar(self.supervisor)

    def test_bandeja_filtros_resumen_y_detalle_no_aditivo(self):
        pending = self.informar('OBRA', cantidad='1.000')
        approved = self.resolver(self.informar('OBRA', cantidad='2.000'))
        self.resolver(self.informar('OBRA', cantidad='1.000'), 'RECHAZAR')
        self.devolver(self.entrega, '1.000')
        r = self.client.get(URL, {'estado': 'PENDIENTE', 'tipo': 'CORTE_NO_REUTILIZABLE', 'buscar': self.obra.codigo})
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data['resumen'], {'pendientes': 1, 'aprobadas': 1, 'rechazadas': 1})
        self.assertEqual(r.data['count'], 1)
        row = r.data['results'][0]
        self.assertEqual(row['id'], pending.pk)
        self.assertEqual(row['material'], self.article.nombre)
        self.assertEqual(row['obra'], self.obra.codigo)
        self.assertFalse({'clave_idempotencia', 'importe_informativo_no_aditivo'} & set(row))
        detail = self.client.get(f'{URL}{approved.pk}/')
        self.assertEqual(detail.status_code, 200, detail.data)
        d = detail.data
        self.assertEqual((d['entregado'], d['devuelto'], d['mermas_aprobadas'], d['remanente']),
                         ('6.000', '1.000', '2.000', '3.000'))
        self.assertEqual(d['importe_informativo_no_aditivo'], '200.00')
        self.assertEqual([e['tipo'] for e in d['historial']], ['CREACION', 'APROBACION'])

    def test_decision_original_sin_movimientos_o_gastos_adicionales(self):
        m = self.informar('OBRA')
        models = [MovimientoInventario, OperacionMaterial, ExistenciaInventario, GastoObra]
        before = self.foto(models)
        r = self.client.post(f'/api/inventario/mermas-obra/{m.pk}/decidir/',
                             self.entrada_decision_merma(), format='json')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(self.foto(models), before)
        self.assertEqual(self.client.get(f'{URL}{m.pk}/').data['estado'], 'APROBADA')

    def test_permiso_exclusivo_y_filtros(self):
        m = self.informar('OBRA')
        for actor in (self.solicitante, self.bodega, self.finanzas, self.gerencia):
            self.autenticar(actor)
            self.assertEqual(self.client.get(URL).status_code, 403)
            self.assertEqual(self.client.get(f'{URL}{m.pk}/').status_code, 403)
        self.autenticar(self.supervisor)
        for q in ('?estado=otro', '?tipo=DANO', '?buscar=%20', '?buscar=a&buscar=b', '?ambito=BODEGA'):
            self.assertEqual(self.client.get(URL+q).status_code, 400, q)
        self.assertEqual(self.client.get(f'{URL}{m.pk}/?page=1').status_code, 400)
        self.assertIn(self.client.post(URL, {}, format='json').status_code, (403, 405))
