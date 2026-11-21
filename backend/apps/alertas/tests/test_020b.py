from datetime import timedelta

from django.db import IntegrityError, models, transaction
from django.test import TestCase
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, NotFound

from apps.alertas import services
from apps.alertas.models import Alerta, AlertaEvento
from apps.comercial.models import Presupuesto
from apps.finanzas.tests.base import FinanzasBase
from apps.finanzas import services_documentos
from apps.finanzas.validaciones import hoy_santiago
from apps.usuarios.models import Usuario
from apps.usuarios.tokens import AccessToken
from .base import AlertasBase, URL


class EstadoUnico020BTests(AlertasBase, TestCase):
    def setUp(self):
        self.preparar_alertas()

    def test_gerencia_observa_mismo_id_estado_historial_y_responsable(self):
        a = self.suspender()
        s = self.client.get(f'{URL}{a.pk}/').data
        self.assertEqual(s['rol_responsable'], 'SUPERVISOR_OBRAS')
        self.assertEqual(s['destinatarios'], ['SUPERVISOR_OBRAS', 'GERENCIA'])
        self.assertEqual(s['acciones_permitidas'], ['ATENDER'])
        self.assertFalse(s['es_legada'])
        r = self.client.post(f'{URL}{a.pk}/atender/', {'motivo': 'Coordinado'}, format='json')
        self.assertEqual(r.status_code, 200)
        self.autenticar(self.gerencia)
        g = self.client.get(f'{URL}{a.pk}/').data
        self.assertEqual((g['id'], g['estado'], g['atendida_por']), (a.pk, 'ATENDIDA', self.supervisor.pk))
        self.assertEqual(g['rol_destinatario'], 'GERENCIA')
        self.assertEqual(g['rol_responsable'], s['rol_responsable'])
        self.assertEqual(g['acciones_permitidas'], [])
        self.assertEqual(self.client.get(URL).data['count'], 1)
        self.assertEqual(self.client.get(f'{URL}{a.pk}/historial/').data['count'], 2)
        self.assertEqual(self.client.get(URL + 'resumen/').data['por_estado']['ATENDIDA'], 1)
        self.assertEqual(Alerta.objects.count(), 1)

    def test_matriz_seis_roles_flags_claims_lectura_y_atencion(self):
        a = self.suspender()
        for rol in Usuario.Rol:
            actor = Usuario.objects.create_user(username=f'b020_{rol}', email=f'{rol}@b020.test', rol=rol, is_staff=True, is_superuser=True)
            token = AccessToken.for_user(actor)
            token['rol'] = 'SUPERVISOR_OBRAS'
            self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
            lectura = 200 if rol in ['GERENCIA', 'SUPERVISOR_OBRAS'] else 404 if rol == 'ADMINISTRATIVO_FINANZAS' else 403
            self.assertEqual(self.client.get(f'{URL}{a.pk}/').status_code, lectura, rol)
            esperado = 200 if rol == 'SUPERVISOR_OBRAS' else 404 if rol == 'ADMINISTRATIVO_FINANZAS' else 403
            self.assertEqual(self.client.post(f'{URL}{a.pk}/atender/', {'motivo': 'Revisión'}, format='json').status_code, esperado, rol)
        self.assertEqual(a.eventos.filter(tipo='ATENCION').count(), 1)
        with self.assertRaises(PermissionDenied):
            services.atender(self.gerencia, a.pk, 'No permitido')
        with self.assertRaises(NotFound):
            services.atender(self.finanzas, a.pk, 'No permitido')

    def test_presupuestos_y_turnos_sin_gerencia_archivo_solo_destinatario(self):
        p = self.pendiente()
        Presupuesto.objects.filter(pk=p.pk).update(estado='PENDIENTE_FINANZAS')
        self.cerrar(self.abrir())
        services.reconciliar()
        self.autenticar(self.gerencia)
        self.assertEqual(self.client.get(URL).data['count'], 0)
        self.assertEqual(set(self.client.get(URL + 'resumen/').data['por_tipo']), {'OBRA_SUSPENDIDA', 'COBRANZA_VENCIDA'})
        self.autenticar(self.finanzas)
        self.assertEqual(self.client.get(URL).data['count'], 1)
        self.assertEqual(set(self.client.get(URL + 'resumen/').data['por_tipo']), {'PRESUPUESTO_PENDIENTE_FINANZAS', 'COBRANZA_VENCIDA'})
        self.autenticar(self.supervisor)
        self.assertEqual(self.client.get(URL).data['count'], 1)
        for valor in ['TRUE', '1', '', 'false&legado=true']:
            self.assertEqual(self.client.get(URL + '?legado=' + valor).status_code, 400)

    def test_constraints_no_permiten_copia_gerencial_ni_segundo_episodio_abierto(self):
        a = self.suspender()
        for cambios in [dict(rol_destinatario='GERENCIA'), dict(generacion=2)]:
            datos = dict(tipo=a.tipo, recurso_tipo=a.recurso_tipo, recurso_id=a.recurso_id,
                         generacion=1, rol_destinatario='SUPERVISOR_OBRAS')
            with self.assertRaises(IntegrityError), transaction.atomic():
                Alerta.objects.create(**{**datos, **cambios})
        with self.assertRaises(IntegrityError), transaction.atomic():
            models.QuerySet(model=Alerta).filter(pk=a.pk).update(rol_destinatario='GERENCIA')
        self.assertEqual(AlertaEvento.objects.count(), 1)


class CobranzaCompartida020BTests(FinanzasBase, TestCase):
    def setUp(self):
        self.preparar_finanzas()
        ayer = hoy_santiago() - timedelta(days=1)
        self.doc = services_documentos.registrar_documento(self.payload(fecha_emision=ayer.isoformat(), fecha_vencimiento=ayer.isoformat()), self.finanzas)

    def test_solo_finanzas_atiende_y_gerencia_observa_cobranza(self):
        # La atención antigua de G se conserva, pero no acredita atención de AF.
        hora = timezone.now()
        vieja = Alerta.objects.create(es_legada=True, tipo='COBRANZA_VENCIDA', recurso_tipo='DOCUMENTO',
            recurso_id=self.doc.pk, generacion=1, rol_destinatario='GERENCIA', estado='ATENDIDA',
            creado_en=hora, atendida_en=hora, atendida_por=self.gerencia, motivo_atencion='Historia de G')
        AlertaEvento.objects.create(alerta=vieja, tipo='CREACION', estado_nuevo='PENDIENTE', registrado_en=hora)
        AlertaEvento.objects.create(alerta=vieja, tipo='ATENCION', estado_anterior='PENDIENTE', estado_nuevo='ATENDIDA',
            actor=self.gerencia, motivo='Historia de G', registrado_en=hora)
        historia = list(vieja.eventos.values())
        services.reconciliar()
        a = Alerta.objects.get(es_legada=False, tipo='COBRANZA_VENCIDA')
        self.assertEqual(a.estado, 'PENDIENTE')
        self.assertEqual(a.generacion, 2)
        self.assertIsNone(a.atendida_por_id)
        self.assertEqual(list(vieja.eventos.values()), historia)
        self.autenticar(self.finanzas)
        self.assertEqual(self.client.get(f'{URL}{vieja.pk}/').status_code, 404)
        r = self.client.post(f'{URL}{a.pk}/atender/', {'motivo': 'Gestión de cobro'}, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        self.autenticar(self.gerencia)
        self.assertEqual(self.client.get(f'{URL}{a.pk}/').data['estado'], 'ATENDIDA')
        self.assertEqual(self.client.get(URL).data['count'], 1)
        self.assertEqual(self.client.get(URL, {'legado': 'true', 'estado': 'TODAS'}).data['count'], 1)
        self.autenticar(self.supervisor)
        self.assertEqual(self.client.get(f'{URL}{a.pk}/historial/').status_code, 404)
