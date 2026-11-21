from itertools import product

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.exceptions import IrreversibleError
from django.test import TransactionTestCase
from django.utils import timezone

from apps.alertas import services
from apps.alertas.models import Alerta, AlertaEvento, EstadoReconciliacion
from apps.obras.models import Obra
from .base import AlertasBase, URL


class Migracion020BTests(AlertasBase, TransactionTestCase):
    def setUp(self):
        self.setUpTestData()
        self.preparar_alertas()

    def test_nueve_combinaciones_legadas_conservan_ids_estados_y_eventos_exactos(self):
        obras = [self.otra_obra() for _ in range(9)]
        Obra.objects.filter(pk__in=[o.pk for o in obras]).update(estado='SUSPENDIDA')
        executor = MigrationExecutor(connection)
        hojas = executor.loader.graph.leaf_nodes()
        anterior = ('alertas', '0003_flujo_finanzas_020a')
        executor.migrate([anterior])
        try:
            apps = executor.loader.project_state([anterior]).apps
            A = apps.get_model('alertas', 'Alerta')
            E = apps.get_model('alertas', 'AlertaEvento')
            hora = timezone.now()
            for obra, estados in zip(obras, product(['PENDIENTE', 'ATENDIDA', 'RESUELTA'], repeat=2)):
                for actor, estado in zip([self.gerencia, self.supervisor], estados):
                    atencion = dict(atendida_por_id=actor.pk, atendida_en=hora, motivo_atencion=f'Historia {actor.rol}') if estado == 'ATENDIDA' else {}
                    a = A.objects.create(tipo='OBRA_SUSPENDIDA', recurso_tipo='OBRA', recurso_id=obra.pk,
                        rol_destinatario=actor.rol, generacion=1, estado=estado, creado_en=hora,
                        resuelta_en=hora if estado == 'RESUELTA' else None, **atencion)
                    E.objects.create(alerta=a, tipo='CREACION', estado_nuevo='PENDIENTE', registrado_en=hora)
                    if estado != 'PENDIENTE':
                        E.objects.create(alerta=a, tipo='ATENCION' if estado == 'ATENDIDA' else 'RESOLUCION',
                            estado_anterior='PENDIENTE', estado_nuevo=estado, registrado_en=hora,
                            actor_id=actor.pk if atencion else None, motivo=atencion.get('motivo_atencion', ''))
            alertas = list(A.objects.order_by('pk').values())
            eventos = list(E.objects.order_by('pk').values())
            apps.get_model('alertas', 'EstadoReconciliacion').objects.create(pk=1, ultima_correcta_en=hora)
        finally:
            MigrationExecutor(connection).migrate(hojas)
        self.assertEqual(list(Alerta.objects.order_by('pk').values()), [dict(a, es_legada=True) for a in alertas])
        self.assertEqual(list(AlertaEvento.objects.order_by('pk').values()), eventos)
        self.assertIsNone(EstadoReconciliacion.objects.get(pk=1).ultima_correcta_en)
        services.reconciliar()
        canonicas = Alerta.objects.filter(es_legada=False)
        self.assertEqual(canonicas.count(), 9)
        self.assertEqual(set(canonicas.values_list('estado', flat=True)), {'PENDIENTE'})
        self.assertEqual(set(canonicas.values_list('generacion', flat=True)), {2})
        self.assertFalse(canonicas.exclude(atendida_por=None).exists())
        self.assertEqual(list(Alerta.objects.filter(es_legada=True).order_by('pk').values()), [dict(a, es_legada=True) for a in alertas])
        self.assertEqual(list(AlertaEvento.objects.filter(alerta__es_legada=True).order_by('pk').values()), eventos)
        self.autenticar(self.gerencia)
        self.assertEqual(self.client.get(URL).data['count'], 9)
        self.assertEqual(self.client.get(URL, {'legado': 'true', 'estado': 'TODAS'}).data['count'], 9)
        g = next(a for a in alertas if a['rol_destinatario'] == 'GERENCIA')
        self.assertEqual(self.client.get(f'{URL}{g["id"]}/').status_code, 200)
        self.autenticar(self.supervisor)
        self.assertEqual(self.client.get(f'{URL}{g["id"]}/historial/').status_code, 404)
        s = next(a for a in alertas if a['rol_destinatario'] == 'SUPERVISOR_OBRAS')
        r = self.client.post(f'{URL}{s["id"]}/atender/', {'motivo': 'No reabrir'}, format='json')
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data['code'], 'alerta_legada')
        services.reconciliar()
        self.assertEqual(canonicas.count(), 9)

    def test_reversion_segura_sin_episodios_y_rechazo_con_datos_020b(self):
        hojas = MigrationExecutor(connection).loader.graph.leaf_nodes()
        anterior = ('alertas', '0003_flujo_finanzas_020a')
        MigrationExecutor(connection).migrate([anterior])
        MigrationExecutor(connection).migrate(hojas)
        a = self.suspender()
        antes = Alerta.objects.values().get(pk=a.pk)
        with self.assertRaises(IrreversibleError):
            MigrationExecutor(connection).migrate([anterior])
        self.assertEqual(Alerta.objects.values().get(pk=a.pk), antes)
