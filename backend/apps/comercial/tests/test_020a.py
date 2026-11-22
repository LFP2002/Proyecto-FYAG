"""Contrato 020A: autoridad persistida, legado y ausencia de bypass Django/JWT."""
from unittest.mock import patch

from django.test import TestCase
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied

from apps.comercial import services_presupuestos as presupuestos
from apps.comercial.services import guardar_cliente, activar_cliente, desactivar_cliente
from apps.comercial.tests.test_presupuesto_api import PresupuestoAPIBase, AF, G
from apps.comercial.tests.test_presupuesto_services import ServiciosPresupuestoMixin, datos_item
from apps.usuarios.models import Usuario
from apps.usuarios.tokens import AccessToken


class AutoridadDominioTests(ServiciosPresupuestoMixin, TestCase):
    def test_seis_roles_flags_y_rol_en_memoria_no_autorizan_escrituras(self):
        for rol in Usuario.Rol:
            actor = Usuario.objects.create_user(username=f'actor_{rol}', email=f'{rol}@example.test', rol=rol,
                                                is_staff=True, is_superuser=True)
            actor.rol = AF  # La autoridad no es este objeto mutable.
            operaciones = [
                lambda: guardar_cliente({'nombre_legal': 'Actualizado'}, self.cliente, usuario=actor),
                lambda: activar_cliente(self.cliente, actor),
                lambda: desactivar_cliente(self.cliente, actor),
                lambda: presupuestos.modificar_presupuesto(self.presupuesto, {'descripcion': 'Actualizado'}, actor),
                lambda: presupuestos.crear_item(self.presupuesto, datos_item(), actor),
                lambda: presupuestos.modificar_item(self.presupuesto, 999999, {}, actor),
                lambda: presupuestos.eliminar_item(self.presupuesto, 999999, actor),
                lambda: presupuestos.enviar_finanzas(self.presupuesto, actor),
                lambda: presupuestos.aprobar_finanzas(self.presupuesto, actor),
                lambda: presupuestos.rechazar_finanzas(self.presupuesto, actor, 'Decisión'),
                lambda: presupuestos.crear_revision(self.presupuesto, actor),
                lambda: presupuestos.anular_presupuesto(self.presupuesto, actor, 'Decisión'),
                lambda: presupuestos.crear_presupuesto(cliente=self.cliente, descripcion='Servicio', usuario=actor),
            ]
            for numero, operacion in enumerate(operaciones):
                with self.subTest(rol=rol, operacion=operacion):
                    if rol == Usuario.Rol.SUPERVISOR_OBRAS:
                        # 024: Clientes/decisiones siguen 403; recursos AF son 404;
                        # únicamente la creación nueva ahora está permitida.
                        from apps.comercial.exceptions import RecursoNoEncontrado
                        if numero == 12:
                            self.assertEqual(operacion().creado_por_id, actor.pk)
                        else:
                            with self.assertRaises(RecursoNoEncontrado if numero in {3, 4, 5, 6, 7, 10} else PermissionDenied):
                                operacion()
                    elif rol != AF:
                        with self.assertRaises(PermissionDenied):
                            operacion()
            if rol == AF:
                item = presupuestos.crear_item(self.presupuesto, datos_item(), actor)
                presupuestos.modificar_item(self.presupuesto, item, {'descripcion': 'Nueva'}, actor)
                presupuestos.eliminar_item(self.presupuesto, item, actor)
        self.assertEqual(self.presupuesto.eventos.count(), 0)
        self.assertFalse(self.presupuesto.items.exists())

    def test_actor_ausente_y_rutas_de_dominio_retiradas_sin_mutacion(self):
        falso = Usuario(pk=self.usuario.pk, rol=AF, sesion_version=self.usuario.sesion_version)
        for operacion in [
            lambda: presupuestos.crear_item(self.presupuesto, datos_item(), falso),
            lambda: guardar_cliente({}, self.cliente),
            lambda: presupuestos.crear_item(self.presupuesto, datos_item()),
            lambda: presupuestos.modificar_presupuesto(self.presupuesto, {}),
            lambda: presupuestos.eliminar_item(self.presupuesto, 999),
            lambda: presupuestos.modificar_item(self.presupuesto, 999, {}),
            lambda: presupuestos.enviar_gerencia(self.presupuesto, self.usuario),
            lambda: presupuestos.aprobar_gerencia(self.presupuesto, self.usuario),
            lambda: presupuestos.rechazar_gerencia(self.presupuesto, self.usuario, 'Decisión'),
        ]:
            with self.assertRaises(PermissionDenied):
                operacion()

    def test_revocacion_tras_lock_deniega_sin_evento(self):
        presupuesto = self.preparar('PENDIENTE_FINANZAS')
        original = presupuestos._presupuesto_bloqueado

        def revocar(referencia, usuario=None):
            actual = original(referencia, usuario)
            Usuario.objects.filter(pk=self.usuario.pk).update(sesion_version=self.usuario.sesion_version + 1)
            return actual

        with patch.object(presupuestos, '_presupuesto_bloqueado', side_effect=revocar):
            with self.assertRaises(AuthenticationFailed):
                presupuestos.aprobar_finanzas(presupuesto, self.usuario)
        presupuesto.refresh_from_db()
        self.assertEqual(presupuesto.estado, 'PENDIENTE_FINANZAS')
        self.assertEqual(presupuesto.eventos.count(), 1)

    def test_legado_resuelto_por_af_no_reescribe_eventos(self):
        for decision, destino in [(presupuestos.aprobar_finanzas, 'APROBADO_FINANZAS'),
                                  (presupuestos.rechazar_finanzas, 'RECHAZADO_FINANZAS')]:
            presupuesto = self.preparar('PENDIENTE_GERENCIA')
            antes = list(presupuesto.eventos.values())
            decision(presupuesto, self.usuario, 'Decisión de Finanzas')
            self.assertEqual(list(presupuesto.eventos.filter(pk__in=[e['id'] for e in antes]).values()), antes)
            evento = presupuesto.eventos.last()
            self.assertEqual((evento.estado_anterior, evento.estado_nuevo), ('PENDIENTE_GERENCIA', destino))
            self.assertEqual(evento.registrado_por, self.usuario)
            presupuesto.refresh_from_db()
            self.assertEqual(presupuesto.politica_aprobacion, 'GERENCIA_LEGADA')
            self.assertTrue(presupuesto.requiere_aprobacion_gerencia)


class ContratoHTTP020ATests(PresupuestoAPIBase):
    def test_acciones_gerenciales_retiradas_para_seis_roles_antes_de_body_o_recurso(self):
        for rol in Usuario.Rol:
            self.autenticar(rol)
            for nombre in ['enviar-gerencia', 'aprobar-gerencia', 'rechazar-gerencia']:
                for pk in [self.presupuesto.pk, 999999]:
                    respuesta = self.client.post(f'{self.url}{pk}/{nombre}/', '{', content_type='application/json')
                    self.assertEqual(respuesta.status_code, 403, (rol, nombre))

    def test_claim_af_y_flags_no_conceden_decisiones_a_gerencia(self):
        actor = self.usuarios[G]
        actor.is_staff = actor.is_superuser = True
        actor.save()
        token = AccessToken.for_user(actor)
        token['rol'] = AF
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        self.assertEqual(self.client.get(self.detalle()).status_code, 200)
        for accion in ['enviar-finanzas', 'aprobar-finanzas', 'rechazar-finanzas']:
            self.assertEqual(self.accion(accion, datos={'motivo': 'Decisión'}).status_code, 403)
        self.assertEqual(self.presupuesto.eventos.count(), 1)

    def test_politica_es_servidor_y_finanzas_revisa_sin_segunda_persona(self):
        for metodo in ['post', 'patch']:
            ruta = self.url if metodo == 'post' else self.detalle()
            datos = self.cabecera(politica_aprobacion='GERENCIA_LEGADA')
            self.assertEqual(getattr(self.client, metodo)(ruta, datos, format='json').status_code, 400)
        self.assertEqual(self.accion('enviar-finanzas').status_code, 200)
        respuesta = self.accion('aprobar-finanzas')
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.data['politica_aprobacion'], 'FINANZAS')
        self.assertFalse(respuesta.data['requiere_aprobacion_gerencia'])
