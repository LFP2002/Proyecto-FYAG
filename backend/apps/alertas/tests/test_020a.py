from django.test import TestCase
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied

from apps.alertas import services
from apps.alertas.models import Alerta, AlertaEvento
from apps.comercial.models import Presupuesto
from apps.comercial import services_presupuestos
from apps.usuarios.models import Usuario
from apps.usuarios.tokens import AccessToken
from .base import AlertasBase, URL


class Alertas020ATests(AlertasBase, TestCase):
    def setUp(self):
        self.preparar_alertas()

    def test_finanzas_consulta_atiende_y_resolucion_automatica_conserva_atencion(self):
        p = self.pendiente()
        with self.captureOnCommitCallbacks(execute=True):
            services_presupuestos.enviar_finanzas(p, self.finanzas)
        a = Alerta.objects.get(tipo='PRESUPUESTO_PENDIENTE_FINANZAS')
        self.assertEqual(a.rol_destinatario, 'ADMINISTRATIVO_FINANZAS')
        self.assertFalse(Alerta.objects.filter(rol_destinatario='GERENCIA').exists())
        self.autenticar(self.finanzas)
        self.assertEqual(self.client.get(URL).data['count'], 1)
        r = self.client.post(f'{URL}{a.pk}/atender/', {'motivo': 'Revisando'}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        with self.captureOnCommitCallbacks(execute=True):
            services_presupuestos.aprobar_finanzas(p, self.finanzas)
        a.refresh_from_db()
        self.assertEqual(a.estado, 'RESUELTA')
        self.assertEqual(a.atendida_por_id, self.finanzas.pk)
        self.assertEqual(a.motivo_atencion, 'Revisando')
        self.assertEqual(set(a.eventos.values_list('tipo', flat=True)), {'CREACION', 'ATENCION', 'RESOLUCION'})

    def test_legado_reconciliado_sin_falsificar_autores_o_reescribir_historia(self):
        p = self.pendiente()
        Presupuesto.objects.filter(pk=p.pk).update(estado='PENDIENTE_GERENCIA', politica_aprobacion='GERENCIA_LEGADA', requiere_aprobacion_gerencia=True)
        a = Alerta.objects.create(tipo='PRESUPUESTO_PENDIENTE_GERENCIA', recurso_tipo='PRESUPUESTO',
                                  recurso_id=p.pk, rol_destinatario='GERENCIA', generacion=1)
        services._evento(a, 'CREACION', None, ahora=a.creado_en)
        e = a.eventos.get()
        antes = list(a.eventos.values())
        services.reconciliar()
        a.refresh_from_db()
        self.assertEqual(a.estado, 'RESUELTA')
        self.assertIsNone(a.atendida_por_id)
        self.assertEqual(list(a.eventos.filter(pk=e.pk).values()), antes)
        resolucion = a.eventos.get(tipo='RESOLUCION')
        self.assertIsNone(resolucion.actor_id)
        self.assertTrue(Alerta.objects.filter(tipo='PRESUPUESTO_PENDIENTE_FINANZAS', recurso_id=p.pk, estado='PENDIENTE').exists())
        services.reconciliar()
        self.assertEqual(Alerta.objects.count(), 2)
        self.assertEqual(a.eventos.count(), 2)

    def test_gerencia_solo_lectura_aun_con_flags_claims_y_body_invalido(self):
        self.suspender()
        a = Alerta.objects.get(rol_destinatario='GERENCIA')
        actor = self.gerencia
        actor.is_staff = actor.is_superuser = True
        actor.save()
        token = AccessToken.for_user(actor)
        token['rol'] = 'SUPERVISOR_OBRAS'
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        r = self.client.get(f'{URL}{a.pk}/')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['acciones_permitidas'], [])
        for pk in [a.pk, 999999]:
            self.assertEqual(self.client.post(f'{URL}{pk}/atender/', '{', content_type='application/json').status_code, 403)
        with self.assertRaises(PermissionDenied):
            services.atender(actor, a.pk, 'No autorizado')
        self.assertEqual(a.eventos.count(), 1)

    def test_atencion_gerencial_historica_permanece_exacta_al_retirar_solicitud(self):
        p = self.pendiente()
        Presupuesto.objects.filter(pk=p.pk).update(estado='PENDIENTE_GERENCIA', politica_aprobacion='GERENCIA_LEGADA', requiere_aprobacion_gerencia=True)
        ahora = timezone.now()
        # Fixture histórica: no se invoca una atención gerencial nueva.
        a = Alerta.objects.create(tipo='PRESUPUESTO_PENDIENTE_GERENCIA', recurso_tipo='PRESUPUESTO',
                                  recurso_id=p.pk, rol_destinatario='GERENCIA', generacion=1,
                                  estado='ATENDIDA', creado_en=ahora, atendida_en=ahora,
                                  atendida_por=self.gerencia, motivo_atencion='Atención histórica')
        AlertaEvento.objects.create(alerta=a, tipo='CREACION', estado_nuevo='PENDIENTE', registrado_en=ahora)
        AlertaEvento.objects.create(alerta=a, tipo='ATENCION', estado_anterior='PENDIENTE', estado_nuevo='ATENDIDA',
                                   actor=self.gerencia, motivo='Atención histórica', registrado_en=ahora)
        antes = list(a.eventos.order_by('pk').values())
        services.reconciliar()
        a.refresh_from_db()
        self.assertEqual(a.estado, 'RESUELTA')
        self.assertEqual((a.atendida_por_id, a.atendida_en, a.motivo_atencion),
                         (self.gerencia.pk, ahora, 'Atención histórica'))
        self.assertEqual(list(a.eventos.exclude(tipo='RESOLUCION').order_by('pk').values()), antes)
        self.assertIsNone(a.eventos.get(tipo='RESOLUCION').actor_id)

    def test_seis_roles_no_obtienen_alertas_ajenas(self):
        self.suspender()
        for rol in Usuario.Rol:
            actor = Usuario.objects.create_user(username=f'alerta_{rol}', email=f'alerta_{rol}@example.test', rol=rol, is_staff=True, is_superuser=True)
            actor.rol = 'GERENCIA'
            token = AccessToken.for_user(actor)
            token['rol'] = 'GERENCIA'
            self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
            r = self.client.get(URL)
            self.assertEqual(r.status_code, 200 if rol in ['GERENCIA', 'SUPERVISOR_OBRAS', 'ADMINISTRATIVO_FINANZAS'] else 403)
            if r.status_code == 200:
                self.assertTrue(all(a['rol_destinatario'] == rol for a in r.data['results']))
