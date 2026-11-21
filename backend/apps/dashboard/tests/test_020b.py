from django.test import TransactionTestCase

from apps.alertas import services
from apps.alertas.models import Alerta
from apps.comercial.models import Presupuesto
from apps.obras import services as obras
from .base import DashboardBase, RESUMEN


class Indicadores020BTests(DashboardBase, TransactionTestCase):
    def setUp(self):
        self.preparar_dashboard()

    def test_pendientes_finanzas_compatibilidad_y_conteos_sin_duplicar_vistas(self):
        # La preparación finaliza una Obra y conserva el episodio de revisión de turno.
        resueltas = Alerta.objects.filter(es_legada=False, estado='RESUELTA').count()
        obra = self.otra_obra()
        for rol in ['GERENCIA', 'SUPERVISOR_OBRAS']:
            Alerta.objects.create(es_legada=True, tipo='OBRA_SUSPENDIDA', recurso_tipo='OBRA',
                recurso_id=obra.pk, rol_destinatario=rol, generacion=1)
        obras.suspender_obra(obra, self.supervisor, 'Pausa')
        Presupuesto.objects.create(cliente=self.cliente, creado_por=self.finanzas, descripcion='Nuevo', estado='PENDIENTE_FINANZAS')
        Presupuesto.objects.create(cliente=self.cliente, creado_por=self.finanzas, descripcion='Legado', estado='PENDIENTE_GERENCIA',
            politica_aprobacion='GERENCIA_LEGADA', requiere_aprobacion_gerencia=True)
        services.reconciliar()
        self.autenticar(self.gerencia)
        r = self.client.get(RESUMEN, {'desde': '2020-01-01', 'hasta': '2020-01-31'})
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data['operacion']['presupuestos_pendientes_gerencia_actual'], 1)
        self.assertEqual(r.data['operacion']['presupuestos_pendientes_finanzas_actual'], 2)
        indicadores = r.data['incidencias']
        self.assertEqual(indicadores['criticas_activas'], 1)
        self.assertEqual(indicadores['pendientes_por_area'], {'SUPERVISOR_OBRAS': 1, 'ADMINISTRATIVO_FINANZAS': 2})
        self.assertEqual(indicadores['por_estado'], {'PENDIENTE': 3, 'ATENDIDA': 0, 'RESUELTA': resueltas})
        self.assertFalse(indicadores['sincronizacion']['desactualizada'])
        a = Alerta.objects.get(es_legada=False, tipo='OBRA_SUSPENDIDA')
        services.atender(self.supervisor, a.pk, 'Revisado')
        obras.reanudar_obra(obra, self.supervisor, 'Continuar')
        actual = self.client.get(RESUMEN).data['incidencias']
        self.assertEqual(actual['por_estado'], {'PENDIENTE': 2, 'ATENDIDA': 0, 'RESUELTA': resueltas + 1})
        self.assertEqual(actual['criticas_activas'], 0)
        self.assertEqual(Alerta.objects.filter(es_legada=True, estado='PENDIENTE').count(), 2)
