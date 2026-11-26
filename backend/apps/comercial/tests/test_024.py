"""SPEC-024: permisos por dominio, scope SQL, flujo y compatibilidad."""
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied

from apps.comercial import services_presupuestos as servicios
from apps.comercial.exceptions import EstadoIncompatible, RecursoNoEncontrado
from apps.comercial.models import Cliente, Presupuesto, PresupuestoEvento, PresupuestoItem
from apps.comercial.services import guardar_cliente, activar_cliente, desactivar_cliente
from apps.usuarios.models import Usuario, SeguridadCredencial, EstadoAcceso
from apps.usuarios.tokens import AccessToken
from .test_presupuesto_api import PresupuestoAPIBase, AF, G, datos_item

S = Usuario.Rol.SUPERVISOR_OBRAS


class Presupuestos024API(PresupuestoAPIBase):
    def propio(self, estado='BORRADOR', actor=None):
        actor = actor or self.usuarios[S]
        p = servicios.crear_presupuesto(cliente=self.cliente, descripcion='Cotización propia', usuario=actor)
        servicios.crear_item(p, {**datos_item(), 'cantidad': Decimal('2.500'),
                                'precio_unitario': Decimal('100.25')}, actor)
        if estado != 'BORRADOR':
            p.estado = estado
            if estado in {'RECHAZADO_GERENCIA', 'APROBADO_GERENCIA', 'PENDIENTE_GERENCIA'}:
                p.politica_aprobacion = 'GERENCIA_LEGADA'; p.requiere_aprobacion_gerencia = True
            p.save()
        return p

    def test_supervisor_crud_borrador_y_flujo_finanzas_cliente(self):
        self.autenticar(S)
        r = self.client.post(self.url, self.cabecera(), format='json')
        self.assertEqual(r.status_code, 201)
        p = Presupuesto.objects.get(pk=r.data['id'])
        self.assertEqual((p.creado_por_id, p.estado, p.politica_aprobacion), (self.usuarios[S].pk, 'BORRADOR', 'FINANZAS'))
        self.assertEqual(self.client.patch(self.detalle(p), {'descripcion': 'Revisado'}, format='json').status_code, 200)
        item = self.client.post(self.detalle(p)+'items/', datos_item(), format='json')
        self.assertEqual(item.status_code, 201)
        ruta = self.detalle(p)+f"items/{item.data['id']}/"
        self.assertEqual(self.client.patch(ruta, {'cantidad': '3.000'}, format='json').status_code, 200)
        self.assertEqual(self.client.delete(ruta).status_code, 204)
        self.assertEqual(self.client.post(self.detalle(p)+'items/', datos_item(), format='json').status_code, 201)
        self.assertEqual(self.accion('enviar-finanzas', p).status_code, 200)
        for rol in (S, AF):
            self.autenticar(rol)
            self.assertEqual(self.client.patch(self.detalle(p), {'descripcion': 'No'}, format='json').status_code, 409)
            self.assertEqual(self.client.post(self.detalle(p)+'items/', datos_item(orden=2), format='json').status_code, 409)
        self.autenticar(AF)
        for accion in ('aprobar-finanzas', 'enviar-cliente', 'registrar-aprobacion-cliente'):
            self.assertEqual(self.accion(accion, p).status_code, 200)
        self.autenticar(S)
        self.assertEqual(self.client.get(self.detalle(p)).data['estado'], 'APROBADO_CLIENTE')
        eventos = self.client.get(self.detalle(p)+'historial/').data['results']
        self.assertEqual([e['estado_nuevo'] for e in eventos], ['BORRADOR', 'PENDIENTE_FINANZAS', 'APROBADO_FINANZAS', 'ENVIADO_CLIENTE', 'APROBADO_CLIENTE'])
        self.assertEqual([e['registrado_por'] for e in eventos], [self.usuarios[S].pk]*2+[self.usuarios[AF].pk]*3)

    def test_scope_sql_y_404_antes_de_body_item_o_estado(self):
        propio = self.propio()
        otro = Usuario.objects.create_user(username='otro_supervisor', email='otro@s.test', rol=S)
        ajenos = (self.presupuesto, self.propio(actor=otro))
        self.autenticar(S)
        with CaptureQueriesContext(connection) as capturadas:
            r = self.client.get(self.url)
        self.assertEqual(r.data['count'], 1)
        self.assertEqual([p['id'] for p in r.data['results']], [propio.pk])
        self.assertTrue(any('"creado_por_id" =' in q['sql'] and 'WHERE' in q['sql'] for q in capturadas))
        for p in ajenos:
            for suffix, metodo in [('', 'get'), ('historial/', 'get'), ('', 'patch'),
                    ('items/', 'post'), (f'items/{propio.items.get().pk}/', 'patch'),
                    (f'items/{propio.items.get().pk}/', 'delete'), ('enviar-finanzas/', 'post'), ('crear-revision/', 'post')]:
                ruta = self.detalle(p)+suffix
                with self.subTest(ruta=ruta, metodo=metodo):
                    args = {} if metodo == 'get' else {'data': '{', 'content_type': 'application/json'}
                    self.assertEqual(getattr(self.client, metodo)(ruta, **args).status_code, 404)
            with self.assertRaises(RecursoNoEncontrado):
                servicios.modificar_presupuesto(p, {}, self.usuarios[S])
        for rol in (AF, G):
            self.autenticar(rol)
            self.assertEqual(self.client.get(self.url).data['count'], 3)

    def test_busqueda_global_y_estado_respetan_scope(self):
        propio = self.propio()
        historico = self.propio('PENDIENTE_GERENCIA')
        otro = Usuario.objects.create_user(username='otro_filtro', email='otro@filtro.test', rol=S)
        ajeno = self.propio(actor=otro)
        self.autenticar(S)
        r = self.client.get(self.url, {'buscar': propio.codigo})
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual([x['id'] for x in r.data['results']], [propio.pk])
        self.assertEqual(r.data['results'][0]['cliente_nombre'], self.cliente.nombre_legal)
        self.assertEqual(self.client.get(self.url, {'buscar': ajeno.codigo}).data['count'], 0)
        self.assertEqual(self.client.get(self.url, {'estado': 'PENDIENTE_FINANZAS'}).data['results'][0]['id'], historico.pk)
        self.assertEqual(self.client.get(self.url, {'buscar': self.cliente.nombre_legal, 'estado': 'BORRADOR'}).data['count'], 1)
        self.autenticar(AF)
        self.assertEqual(self.client.get(self.url, {'buscar': ajeno.codigo}).data['count'], 1)
        for query in ['?estado=NO', '?buscar=' + 'x'*201, '?estado=BORRADOR&estado=ANULADO', '?page=0', '?otro=x']:
            self.assertEqual(self.client.get(self.url+query).status_code, 400)

    def test_matriz_seis_roles_y_decisiones_exclusivas(self):
        p = self.propio()
        for rol in Usuario.Rol:
            self.autenticar(rol)
            self.assertEqual(self.client.get(self.detalle(p)).status_code, 200 if rol in {AF, G, S} else 403)
            self.assertEqual(self.client.options(self.url).status_code, 200 if rol in {AF, G, S} else 403)
            for accion in ('aprobar-finanzas', 'rechazar-finanzas', 'enviar-cliente',
                           'registrar-aprobacion-cliente', 'registrar-rechazo-cliente', 'anular'):
                if rol != AF:
                    self.assertEqual(self.accion(accion, p, {'motivo': 'No autorizado'}).status_code, 403)
            for accion in ('enviar-gerencia', 'aprobar-gerencia', 'rechazar-gerencia'):
                self.assertEqual(self.accion(accion, p).status_code, 403)
            for metodo in ('put', 'delete'):
                self.assertEqual(getattr(self.client, metodo)(self.detalle(p), {}, format='json').status_code,
                                 405 if rol in {AF, G, S} else 403)

    def test_finanzas_edita_borrador_supervisor_sin_cambiar_autor(self):
        p = self.propio()
        self.autenticar(AF)
        self.assertEqual(self.client.patch(self.detalle(p), {'descripcion': 'Corregido por AF'}, format='json').status_code, 200)
        self.assertEqual(self.client.patch(self.detalle(p)+f'items/{p.items.get().pk}/', {'precio_unitario': '9.99'}, format='json').status_code, 200)
        p.refresh_from_db()
        self.assertEqual(p.creado_por_id, self.usuarios[S].pk)
        self.assertEqual(p.eventos.count(), 1)  # No se inventa auditoría de ediciones.

    def test_rechazo_revision_profunda_y_original_intacto(self):
        p = self.propio()
        servicios.enviar_finanzas(p, self.usuarios[S])
        self.assertEqual(self.accion('rechazar-finanzas', p).status_code, 400)
        self.assertEqual(self.accion('rechazar-finanzas', p, {'motivo': 'Ajustar alcance'}).status_code, 200)
        p.refresh_from_db()
        antes = (Presupuesto.objects.filter(pk=p.pk).values().get(), list(p.items.values()), list(p.eventos.values()))
        self.autenticar(S)
        r = self.accion('crear-revision', p)
        self.assertEqual(r.status_code, 201)
        revision = Presupuesto.objects.get(pk=r.data['id'])
        self.assertEqual((revision.creado_por_id, revision.presupuesto_origen_id, revision.estado, revision.politica_aprobacion),
                         (self.usuarios[S].pk, p.pk, 'BORRADOR', 'FINANZAS'))
        self.assertNotEqual(revision.items.get().pk, p.items.get().pk)
        self.assertEqual(revision.items.get().subtotal, p.items.get().subtotal)
        self.assertEqual((revision.eventos.get().estado_anterior, revision.eventos.get().registrado_por_id), (None, self.usuarios[S].pk))
        self.assertEqual(antes, (Presupuesto.objects.filter(pk=p.pk).values().get(), list(p.items.values()), list(p.eventos.values())))
        for estado in Presupuesto.Estado.values:
            if estado == 'RECHAZADO_FINANZAS':
                continue
            origen = self.propio(estado)
            self.assertEqual(self.accion('crear-revision', origen).status_code, 409, estado)

    def test_selector_proyeccion_activos_paginacion_busqueda_y_metodos(self):
        for n in range(28):
            Cliente.objects.create(tipo_cliente='EMPRESA', tipo_identificacion='SIN_IDENTIFICACION',
                nombre_legal=f'Elegible {n:02}', correo='privado@qa.test', telefono='privado', nombre_contacto='privado')
        Cliente.objects.create(tipo_cliente='PERSONA', tipo_identificacion='SIN_IDENTIFICACION',
            nombre_legal='Elegible inactivo', correo='oculto@qa.test', activo=False)
        ruta = self.url+'clientes-elegibles/'
        for rol in Usuario.Rol:
            self.autenticar(rol)
            for metodo in ('get', 'options'):
                self.assertEqual(getattr(self.client, metodo)(ruta).status_code, 200 if rol in {S, AF} else 403)
        self.autenticar(S)
        with CaptureQueriesContext(connection) as capturadas:
            r = self.client.get(ruta+'?buscar=Elegible')
        self.assertEqual(r.data['count'], 28)
        self.assertEqual(len(r.data['results']), 25)
        self.assertTrue(all(set(x) == {'id', 'nombre_legal', 'tipo_cliente'} for x in r.data['results']))
        sql = [q['sql'] for q in capturadas if 'FROM "comercial_cliente"' in q['sql'] and 'COUNT' not in q['sql']][0]
        self.assertNotIn('correo', sql); self.assertNotIn('telefono', sql)
        self.assertEqual(len(self.client.get(ruta+'?buscar=Elegible&page=2').data['results']), 3)
        for query in ('buscar=', 'buscar=a&buscar=b', 'page=0', 'page=x', 'page=1&page=2', 'activo=false', 'page='+'1'*100):
            self.assertEqual(self.client.get(ruta+'?'+query).status_code, 400, query)
        for metodo in ('post', 'patch', 'delete', 'put'):
            self.assertEqual(getattr(self.client, metodo)(ruta, {}, format='json').status_code, 405)
        self.assertEqual(self.client.options(ruta, HTTP_ORIGIN='http://localhost:5173', HTTP_ACCESS_CONTROL_REQUEST_METHOD='GET').status_code, 200)

    def test_clientes_crud_api_y_servicios_siguen_af_only(self):
        self.autenticar(S)
        for metodo, ruta in [('get', '/api/clientes/'), ('get', f'/api/clientes/{self.cliente.pk}/'),
                             ('post', '/api/clientes/'), ('patch', f'/api/clientes/{self.cliente.pk}/'),
                             ('post', f'/api/clientes/{self.cliente.pk}/activar/'), ('post', f'/api/clientes/{self.cliente.pk}/desactivar/')]:
            self.assertEqual(getattr(self.client, metodo)(ruta, {}, format='json').status_code, 403)
        for operacion in [lambda: guardar_cliente({}, usuario=self.usuarios[S]),
                          lambda: guardar_cliente({'nombre_legal': 'No'}, self.cliente, usuario=self.usuarios[S]),
                          lambda: activar_cliente(self.cliente, self.usuarios[S]),
                          lambda: desactivar_cliente(self.cliente, self.usuarios[S])]:
            with self.assertRaises(PermissionDenied):
                operacion()

    def test_flags_claim_y_campos_servidor_no_elevan(self):
        actor = self.usuarios[S]
        actor.is_staff = actor.is_superuser = True; actor.save()
        p = self.propio()
        token = AccessToken.for_user(actor); token['rol'] = AF
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
        self.assertEqual(self.accion('aprobar-finanzas', p).status_code, 403)
        self.assertEqual(self.client.post('/api/clientes/', {}, format='json').status_code, 403)
        for campo, valor in {'creado_por': self.usuarios[AF].pk, 'estado': 'APROBADO_FINANZAS',
                             'politica_aprobacion': 'FINANZAS', 'monto_neto': '10.00', 'items': [],
                             'articulo_inventario': 1}.items():
            self.assertEqual(self.client.post(self.url, self.cabecera(**{campo: valor}), format='json').status_code, 400)

    def test_salida_invalida_cliente_items_total_y_sesion(self):
        actor = self.usuarios[S]
        p = servicios.crear_presupuesto(cliente=self.cliente, descripcion='Sin líneas', usuario=actor)
        self.autenticar(S)
        self.assertEqual(self.accion('enviar-finanzas', p).status_code, 400)
        servicios.crear_item(p, {**datos_item(), 'cantidad': Decimal('1'), 'precio_unitario': Decimal('0')}, actor)
        self.assertEqual(self.accion('enviar-finanzas', p).status_code, 400)
        servicios.modificar_item(p, p.items.get(), {'precio_unitario': Decimal('1')}, actor)
        desactivar_cliente(self.cliente, self.usuarios[AF])
        self.assertEqual(self.accion('enviar-finanzas', p).status_code, 400)
        for campo, valor in [('sesion_version', actor.sesion_version+1), ('is_active', False), ('password', '!cambio')]:
            with self.subTest(campo=campo):
                Usuario.objects.filter(pk=actor.pk).update(**{campo: valor})
                self.assertEqual(self.client.get(self.url).status_code, 401)
                Usuario.objects.filter(pk=actor.pk).update(**{campo: getattr(actor, campo)})
        ahora = timezone.now()
        SeguridadCredencial.objects.filter(usuario=actor).update(estado='INICIAL', emitida_en=ahora, vence_en=ahora+timedelta(hours=1))
        self.assertEqual(self.client.get(self.url).status_code, 401)
        self.client.credentials()
        self.assertEqual(self.client.get(self.url+'clientes-elegibles/').status_code, 401)

    def test_revocacion_final_revierte_incluso_item_ya_guardado(self):
        p = self.propio()
        actor = self.usuarios[S]
        original = servicios._guardar_item
        def revocar(item):
            original(item)
            Usuario.objects.filter(pk=actor.pk).update(sesion_version=actor.sesion_version+1)
        with patch.object(servicios, '_guardar_item', side_effect=revocar), self.assertRaises(AuthenticationFailed):
            servicios.crear_item(p, {**datos_item(orden=2), 'cantidad': Decimal('1'), 'precio_unitario': Decimal('10')}, actor)
        self.assertEqual(p.items.count(), 1)

    def test_bloqueo_c2_impide_creacion_y_selector(self):
        actor = self.usuarios[S]
        from apps.usuarios.politica_bloqueos import DURACIONES
        ahora = timezone.now()
        EstadoAcceso.objects.filter(usuario=actor).update(estado='BLOQUEO_TEMPORAL', bloqueo_inicio=ahora,
            bloqueado_hasta=ahora+DURACIONES[0], ciclos_en=[ahora], actualizado_en=ahora)
        with override_settings(BLOQUEOS_C2_HABILITADO=True, BLOQUEOS_C2_ENTORNO='QA_AISLADO_C2',
                BLOQUEOS_C2_TI_QA_IDS=(900001, 900002), BLOQUEOS_C2_RECUPERACION_QA_CONFIRMADA=True,
                BLOQUEOS_C2_RIESGO_DOS_QA_ACEPTADO=True, BLOQUEOS_C2_RESPUESTAS='401_GENERICO',
                BLOQUEOS_C2_SESIONES_TEMPORALES='REVOCAR_TODAS_QA'):
            self.autenticar(S)
            self.assertEqual(self.client.post(self.url, self.cabecera(), format='json').status_code, 401)
            self.assertEqual(self.client.get(self.url+'clientes-elegibles/').status_code, 401)
            with self.assertRaises(AuthenticationFailed):
                servicios.crear_presupuesto(cliente=self.cliente, descripcion='Bloqueado', usuario=actor)

    def test_alertas_financieras_obras_y_bodega_sin_efectos_automaticos(self):
        from django.apps import apps
        from apps.alertas.models import Alerta
        from apps.obras.models import Obra, GastoObra
        modelos = [*apps.get_app_config('inventario').get_models(), Obra, GastoObra]
        antes = {m._meta.label: m.objects.count() for m in modelos}
        p = self.propio()
        with self.captureOnCommitCallbacks(execute=True):
            servicios.enviar_finanzas(p, self.usuarios[S])
        alerta = Alerta.objects.get(tipo='PRESUPUESTO_PENDIENTE_FINANZAS', recurso_id=p.pk, es_legada=False)
        self.assertEqual(alerta.rol_destinatario, AF)
        self.autenticar(G)
        self.assertEqual(self.client.get(f'/api/alertas/{alerta.pk}/').status_code, 404)
        with self.captureOnCommitCallbacks(execute=True):
            servicios.aprobar_finanzas(p, self.usuarios[AF])
        alerta.refresh_from_db(); self.assertEqual(alerta.estado, 'RESUELTA')
        servicios.enviar_cliente(p, self.usuarios[AF])
        servicios.registrar_aprobacion_cliente(p, self.usuarios[AF])
        self.assertEqual(antes, {m._meta.label: m.objects.count() for m in modelos})
        # SPEC-025B admite un vínculo opcional, sin asignarlo a líneas libres.
        # El flujo comercial no debe crear vínculos ni modificar sus instantáneas.
        item = p.items.get()
        self.assertIsNone(item.articulo_id)
        self.assertEqual(item.codigo_articulo, '')
        self.assertEqual(item.cantidad, Decimal('2.500'))
        self.assertEqual(item.precio_unitario, Decimal('100.25'))
