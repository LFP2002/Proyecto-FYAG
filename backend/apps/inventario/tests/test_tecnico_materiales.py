from django.test import TestCase
from .test_mermas import MermasBase


class TecnicoMaterialesTests(MermasBase, TestCase):
    url = '/api/inventario/tecnico-materiales/'

    def setUp(self):
        self.preparar_mermas()

    def get(self, section, **params):
        return self.client.get(self.url, {'seccion': section, **params})

    def test_entregas_remanente_y_aislamiento(self):
        e = self.preparar_entrega()
        self.devolver(e, '1.000')
        m = self.informar('OBRA')
        self.resolver(m)
        pending = self.informar('OBRA', cantidad='1.000')
        self.autenticar(self.solicitante)
        response = self.get('entregas', obra=self.obra.pk)
        self.assertEqual(response.status_code, 200, response.data)
        row = response.data['results'][0]
        self.assertEqual((row['id'], row['cantidad'], row['devuelta'], row['mermas_aprobadas'], row['remanente']), (e.pk, '6.000', '1.000', '2.000', '3.000'))
        self.assertNotIn('costo_unitario_neto', row)
        self.assertEqual(self.get('mermas', estado='PENDIENTE', buscar='Manguera').data['results'][0]['id'], pending.pk)
        detail = self.get('merma_detalle', id=m.pk)
        self.assertEqual(detail.status_code, 200, detail.data)
        self.assertEqual(len(detail.data['historial']), 2)
        self.assertNotIn('importe_informativo_no_aditivo', detail.data)
        self.assertEqual(self.get('confirmacion', tipo='MERMA', clave=str(m.clave_idempotencia)).data, {'id': m.pk})
        self.desasignar()
        self.assertEqual(self.get('entregas', obra=self.obra.pk).status_code, 404)
        self.assertEqual(self.get('merma_detalle', id=m.pk).status_code, 200)

    def test_solicitudes_propias_y_permisos(self):
        s = self.solicitar()
        self.autenticar(self.solicitante)
        self.assertEqual(self.get('obras').data['results'][0]['id'], self.obra.pk)
        self.assertEqual(self.get('catalogo', buscar='Manguera').data['results'][0]['id'], self.article.pk)
        self.assertEqual(self.get('solicitudes', buscar=self.obra.codigo).data['results'][0]['id'], s.pk)
        self.assertEqual(self.get('solicitud_detalle', id=s.pk).status_code, 200)
        self.assertEqual(self.get('confirmacion', tipo='SOLICITUD', clave=str(s.clave_idempotencia)).data, {'id': s.pk})
        self.assertEqual(self.get('solicitudes', estado='INCORRECTO').status_code, 400)
        self.assertEqual(self.client.get(self.url+'?seccion=solicitudes&seccion=mermas').status_code, 400)
        self.autenticar(self.tecnico)
        self.assertEqual(self.get('solicitudes').data['count'], 0)
        self.assertEqual(self.get('solicitud_detalle', id=s.pk).status_code, 404)
        self.assertEqual(self.get('confirmacion', tipo='SOLICITUD', clave=str(s.clave_idempotencia)).data, {'id': None})
        self.autenticar(self.supervisor)
        self.assertEqual(self.get('solicitudes').status_code, 403)
