from decimal import Decimal
from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

from django.db import connection, transaction, IntegrityError
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.exceptions import APIException

from apps.usuarios.models import Usuario, SeguridadCredencial
from apps.usuarios.tokens import AccessToken
from apps.obras import services as obras
from apps.obras.models import ObraParticipante, GastoObra, CostoObraEvento, ControlCostosObra, CierreCostosObra
from apps.finanzas.models import Egreso, PagoDocumento
from apps.inventario import services_solicitudes as services, services_materiales as bodega
from apps.inventario import consultas_solicitudes as consultas
from apps.inventario.models import SolicitudMaterialObra as Solicitud, SolicitudMaterialEvento as Evento, OperacionMaterial as Op, MovimientoInventario, EstadoValoracion
from apps.inventario.serializers_solicitudes import SolicitudSerializer
from .test_materiales import MaterialesBase

URL = '/api/inventario/solicitudes-materiales/'
CATALOGO = '/api/inventario/articulos-solicitables/'


class SolicitudesBase(MaterialesBase):
    def preparar_solicitudes(self):
        self.preparar_materiales()
        self.solicitante = self.otro_tecnico
        self.participante, _ = obras.asignar_participante(self.obra,
            {'tecnico': self.solicitante.pk, 'motivo': 'Participación adicional'}, self.supervisor)

    def entrada_solicitud(self, **cambios):
        return {'obra': self.obra.pk, 'articulo': self.article.pk, 'cantidad': '4.000',
                'justificacion': ' Material adicional requerido ', 'clave_idempotencia': str(uuid4()), **cambios}

    def solicitar(self, actor=None, **cambios):
        return services.crear_solicitud(self.entrada_solicitud(**cambios), actor or self.solicitante)[0]

    def entrada_decision(self, s, decision='APROBAR', **cambios):
        return {'decision': decision, 'motivo': ' Revisión técnica de materiales ', 'clave_idempotencia': str(uuid4()),
                **({'cantidad_aprobada': format(s.cantidad_solicitada, '.3f')} if decision == 'APROBAR' else {}), **cambios}

    def decidir(self, s, decision='APROBAR', actor=None, **cambios):
        return services.decidir_solicitud(s.pk, self.entrada_decision(s, decision, **cambios), actor or self.supervisor)[0]

    def desasignar(self):
        return obras.desasignar_participante(self.obra, self.participante.pk, self.supervisor, 'Cambio de equipo')


class SolicitudesDominioTests(SolicitudesBase, TestCase):
    def setUp(self):
        self.preparar_solicitudes()

    def test_solicitud_valida_sin_stock_sin_precio_y_sin_efectos(self):
        modelos = [Op, MovimientoInventario, EstadoValoracion, GastoObra, CostoObraEvento, ControlCostosObra, Egreso, PagoDocumento]
        antes = {m: list(m.objects.order_by('pk').values()) for m in modelos}
        s = self.solicitar()
        self.assertEqual((s.estado, s.solicitante_id, s.unidad), ('PENDIENTE', self.solicitante.pk, self.article.unidad))
        self.assertEqual(s.justificacion, 'Material adicional requerido')
        self.assertEqual(s.eventos.get().actor_id, self.solicitante.pk)
        for m, filas in antes.items():
            self.assertEqual(list(m.objects.order_by('pk').values()), filas, m.__name__)

    def test_no_participante_y_desasignado_no_crean(self):
        ajeno = Usuario.objects.create_user(username='ajeno_sol', email='ajeno_sol@example.test', rol='TECNICO')
        for actor in [ajeno, self.solicitante]:
            if actor == self.solicitante:
                self.desasignar()
            with self.assertRaises(APIException) as error:
                self.solicitar(actor=actor)
            self.assertEqual(error.exception.status_code, 404)
        self.assertFalse(Solicitud.objects.filter(obra=self.obra).exists())

    def test_aprobacion_total_y_parcial_sin_stock_una_autorizacion_real(self):
        for cantidad in ['4.000', '1.250']:
            s = self.solicitar()
            decidido = self.decidir(s, cantidad_aprobada=cantidad)
            op = decidido.autorizacion
            self.assertEqual(decidido.estado, 'APROBADA')
            self.assertEqual(decidido.cantidad_aprobada, Decimal(cantidad))
            self.assertEqual(op.solicitud_material_id, s.pk)
            self.assertEqual((op.tipo, op.actor_id, op.obra_id, op.articulo_id, op.unidad),
                ('AUTORIZACION_ENTREGA', self.supervisor.pk, s.obra_id, s.articulo_id, s.unidad))
            self.assertEqual(op.cantidad, Decimal(cantidad))
            evento = decidido.eventos.get(tipo='APROBACION')
            self.assertEqual(len({s.clave_idempotencia, evento.clave_idempotencia, op.clave_idempotencia}), 3)
            self.assertEqual(Op.objects.filter(solicitud_material=s).count(), 1)
        self.assertFalse(MovimientoInventario.objects.filter(articulo=self.article).exists())
        self.assertFalse(GastoObra.objects.filter(obra=self.obra).exists())

    def test_rechazo_no_autorizacion_y_doble_decision_conflictiva(self):
        s = self.solicitar()
        r = self.decidir(s, 'RECHAZAR')
        self.assertEqual(r.estado, 'RECHAZADA')
        self.assertIsNone(r.autorizacion_id)
        self.assertIsNone(r.cantidad_aprobada)
        for decision in ['APROBAR', 'RECHAZAR']:
            with self.assertRaises(APIException) as error:
                self.decidir(s, decision)
            self.assertEqual(error.exception.detail['code'], 'solicitud_ya_decidida')
        self.assertEqual(s.eventos.count(), 2)
        self.assertFalse(Op.objects.filter(solicitud_material=s).exists())

    def test_historia_visible_tras_desasignacion_y_aprobacion_bloqueada(self):
        s = self.solicitar()
        self.desasignar()
        with self.assertRaises(APIException) as error:
            self.decidir(s)
        self.assertEqual(error.exception.status_code, 409)
        self.autenticar(self.solicitante)
        self.assertEqual(self.client.get(f'{URL}{s.pk}/').status_code, 200)
        self.assertEqual(self.client.get(URL, {'obra': self.obra.pk}).data['count'], 1)
        # Rechazar sí puede resolver una petición de un participante desasignado.
        self.assertEqual(self.decidir(s, 'RECHAZAR').estado, 'RECHAZADA')

    def test_obras_operativas_y_conservacion_historica_al_finalizar(self):
        self.cambiar_estado(self.obra, 'SUSPENDIDA')
        s = self.solicitar()
        self.assertEqual(self.decidir(s).estado, 'APROBADA')
        pendiente = self.solicitar()
        for estado in ['PLANIFICADA', 'FINALIZADA', 'CANCELADA']:
            self.cambiar_estado(self.obra, estado)
            with self.assertRaises(APIException) as error:
                self.solicitar()
            self.assertEqual(error.exception.status_code, 409)
            for decision in ['APROBAR', 'RECHAZAR']:
                with self.assertRaises(APIException):
                    self.decidir(pendiente, decision)
            self.autenticar(self.solicitante)
            self.assertEqual(self.client.get(f'{URL}{s.pk}/').status_code, 200)
        self.assertFalse(CierreCostosObra.objects.filter(obra=self.obra).exists())

    def test_articulo_inactivo_o_unidad_cambiada_no_aprueba(self):
        s = self.solicitar()
        from apps.inventario import services as inventario
        inventario.editar_articulo(self.article.pk, {'activo': False}, self.bodega)
        with self.assertRaises(APIException):
            self.solicitar()
        with self.assertRaises(APIException):
            self.decidir(s)
        inventario.editar_articulo(self.article.pk, {'activo': True, 'unidad': 'metro'}, self.bodega)
        with self.assertRaises(APIException):
            self.decidir(s)
        s.refresh_from_db()
        self.assertEqual(s.unidad, 'kg')
        self.assertEqual(self.decidir(s, 'RECHAZAR').estado, 'RECHAZADA')

    def test_idempotencia_creacion_decision_y_replay_original(self):
        data = self.entrada_solicitud(cantidad='1')
        s, creado = services.crear_solicitud(data, self.solicitante)
        replay, nuevo = services.crear_solicitud({**data, 'cantidad': '1.000'}, self.solicitante)
        self.assertTrue(creado)
        self.assertFalse(nuevo)
        self.assertEqual(s.pk, replay.pk)
        d = self.entrada_decision(s)
        decidido, nuevo = services.decidir_solicitud(s.pk, d, self.supervisor)
        r, nuevo2 = services.decidir_solicitud(s.pk, d, self.supervisor)
        self.assertTrue(nuevo)
        self.assertFalse(nuevo2)
        self.assertEqual(r.autorizacion_id, decidido.autorizacion_id)
        self.autenticar(self.solicitante)
        response = self.client.post(URL, data, format='json')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['estado'], 'PENDIENTE')
        self.assertIsNone(response.data['autorizacion'])
        self.assertEqual(self.client.get(f'{URL}{s.pk}/').data['estado'], 'APROBADA')
        for cambios in [{'cantidad': '2'}, {'justificacion': 'Distinta'}]:
            with self.assertRaises(APIException) as error:
                services.crear_solicitud({**data, **cambios}, self.solicitante)
            self.assertEqual(error.exception.detail['code'], 'idempotencia_conflictiva')
        with self.assertRaises(APIException):
            services.decidir_solicitud(s.pk, {**d, 'clave_idempotencia': data['clave_idempotencia']}, self.supervisor)
        otro = Usuario.objects.create_user(username='supervisor_otra_dec', email='supervisor_otra_dec@example.test', rol='SUPERVISOR_OBRAS')
        with self.assertRaises(APIException):
            services.decidir_solicitud(s.pk, d, otro)
        self.assertEqual(s.eventos.count(), 2)

    def test_cantidad_aprobada_no_supera_solicitada(self):
        s = self.solicitar()
        with self.assertRaises(APIException) as error:
            self.decidir(s, cantidad_aprobada='4.001')
        self.assertEqual(error.exception.detail['code'], 'cantidad_aprobada_excesiva')
        s.refresh_from_db()
        self.assertEqual(s.estado, 'PENDIENTE')
        self.assertFalse(Op.objects.filter(solicitud_material=s).exists())

    def test_aprobacion_reutiliza_019b_y_despachos_generan_un_gasto_cada_uno(self):
        s = self.solicitar()
        decidido = self.decidir(s, cantidad_aprobada='3.000')
        with self.assertRaises(APIException):
            self.entregar('1.000', decidido.autorizacion)
        self.recibir('10.000', '100.00')
        modelos = [Egreso, PagoDocumento]
        antes = {m: list(m.objects.order_by('pk').values()) for m in modelos}
        for q in ['1.000', '2.000']:
            d = {'autorizacion': decidido.autorizacion_id, 'cantidad': q, 'clave_idempotencia': str(uuid4())}
            e, _ = bodega.operar('ENTREGA', d, self.bodega)
            replay, nuevo = bodega.operar('ENTREGA', d, self.bodega)
            self.assertFalse(nuevo)
            self.assertEqual(e.pk, replay.pk)
            self.assertEqual(e.gasto.registrado_por_id, self.bodega.pk)
        self.assertEqual(GastoObra.objects.filter(obra=self.obra, origen='BODEGA_019B').count(), 2)
        self.assertEqual(self.saldo(), 7)
        with self.assertRaises(APIException):
            self.entregar('0.001', decidido.autorizacion)
        for m in modelos:
            self.assertEqual(list(m.objects.order_by('pk').values()), antes[m])

    def test_fallos_revierten_solicitud_decision_y_autorizacion(self):
        with patch.object(Evento.objects, 'create', side_effect=RuntimeError('fallo')):
            with self.assertRaises(RuntimeError):
                self.solicitar()
        self.assertFalse(Solicitud.objects.filter(obra=self.obra).exists())
        s = self.solicitar()
        with patch.object(Evento.objects, 'create', side_effect=RuntimeError('fallo')):
            with self.assertRaises(RuntimeError):
                self.decidir(s)
        s.refresh_from_db()
        self.assertEqual(s.estado, 'PENDIENTE')
        self.assertFalse(Op.objects.filter(solicitud_material=s).exists())
        with patch.object(bodega, '_autorizar_entrega_bloqueada', side_effect=IntegrityError('inesperado')):
            with self.assertRaises(IntegrityError):
                self.decidir(s)

    def test_sql_original_y_eventos_no_admiten_mutaciones_o_actores_impropios(self):
        s = self.solicitar()
        normal_b = self.autorizar(format(s.cantidad_solicitada, '.3f'))
        with self.assertRaises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
            cursor.execute("""UPDATE inventario_solicitudmaterialobra SET estado='APROBADA', cantidad_aprobada=cantidad_solicitada,
                motivo_decision='Aprobación SQL falsa', decidido_por_id=%s, decidido_en=%s, autorizacion_id=%s WHERE id=%s""",
                [self.supervisor.pk, timezone.now(), normal_b.pk, s.pk])
        with self.assertRaises(IntegrityError), transaction.atomic():
            Evento.objects.create(solicitud=s, tipo='APROBACION', actor=self.supervisor, motivo=normal_b.motivo,
                cantidad_aprobada=s.cantidad_solicitada, autorizacion=normal_b, clave_idempotencia=uuid4(), huella='a'*64)
        for columna, valor in [('solicitante_id', self.tecnico.pk), ('unidad', 'otra'), ('cantidad_solicitada', '2.000'),
                               ('justificacion', 'Cambio'), ('huella', 'b'*64), ('estado', 'RECHAZADA')]:
            with self.assertRaises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
                cursor.execute(f'UPDATE inventario_solicitudmaterialobra SET {columna}=%s WHERE id=%s', [valor, s.pk])
        with self.assertRaises(IntegrityError), transaction.atomic():
            Evento.objects.create(solicitud=s, tipo='RECHAZO', actor=self.solicitante, motivo='No autorizado', clave_idempotencia=uuid4(), huella='a'*64)
        decidido = self.decidir(s)
        for sql, params in [
            ('UPDATE inventario_solicitudmaterialobra SET autorizacion_id=NULL WHERE id=%s', [s.pk]),
            ('UPDATE inventario_solicitudmaterialevento SET actor_id=%s WHERE solicitud_id=%s', [self.tecnico.pk, s.pk]),
            ('DELETE FROM inventario_solicitudmaterialevento WHERE solicitud_id=%s', [s.pk]),
            ('UPDATE inventario_operacionmaterial SET solicitud_material_id=NULL WHERE id=%s', [decidido.autorizacion_id]),
        ]:
            with self.assertRaises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
                cursor.execute(sql, params)

    def test_sql_impide_solicitud_sin_evento_y_autorizacion_huerfana(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Solicitud.objects.create(obra=self.obra, solicitante=self.solicitante, articulo=self.article, unidad='kg',
                cantidad_solicitada='1.000', justificacion='Registro sin evento', clave_idempotencia=uuid4(), huella='a'*64)
            with connection.cursor() as cursor:
                cursor.execute('SET CONSTRAINTS ALL IMMEDIATE')
        s = self.solicitar()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Op.objects.create(tipo='AUTORIZACION_ENTREGA', obra=self.obra, articulo=self.article, cantidad='1.000', unidad='kg',
                actor=self.supervisor, clave_idempotencia=uuid4(), huella='a'*64, referencia='Sin decisión', motivo='Sin decisión', solicitud_material=s)
            with connection.cursor() as cursor:
                cursor.execute('SET CONSTRAINTS ALL IMMEDIATE')


class SolicitudesAPITests(SolicitudesBase, TestCase):
    def setUp(self):
        self.preparar_solicitudes()

    def test_matriz_seis_roles_claims_y_flags_no_elevan_privilegios(self):
        s = self.solicitar()
        for rol in Usuario.Rol.values:
            actor = Usuario.objects.create_user(username='sol_'+rol, email=rol+'@sol.test', rol=rol, is_staff=True, is_superuser=True)
            token = AccessToken.for_user(actor)
            token['rol'] = 'SUPERVISOR_OBRAS'
            self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
            lector = rol in {'TECNICO', 'SUPERVISOR_OBRAS', 'GERENCIA'}
            for ruta in [CATALOGO, URL]:
                self.assertEqual(self.client.get(ruta).status_code, 200 if lector else 403, (rol, ruta))
            self.assertEqual(self.client.get(f'{URL}{s.pk}/').status_code,
                404 if rol == 'TECNICO' else 200 if lector else 403)
            self.assertEqual(self.client.post(URL, {}, format='json').status_code, 400 if rol == 'TECNICO' else 403)
            self.assertEqual(self.client.post(f'{URL}{s.pk}/decidir/', {}, format='json').status_code, 400 if rol == 'SUPERVISOR_OBRAS' else 403)

    def test_scope_sql_y_404_ajena_historia_propia_detalle(self):
        s = self.solicitar()
        ajena = self.solicitar(actor=self.tecnico)
        self.decidir(s)
        self.autenticar(self.solicitante)
        r = self.client.get(URL, {'obra': self.obra.pk, 'articulo': self.article.pk, 'estado': 'APROBADA'})
        self.assertEqual([x['id'] for x in r.data['results']], [s.pk])
        self.assertIn('solicitante_id', str(consultas.listado(self.solicitante, {}).query))
        self.assertEqual(self.client.get(f'{URL}{ajena.pk}/').status_code, 404)
        r = self.client.get(f'{URL}{s.pk}/')
        self.assertEqual([e['tipo'] for e in r.data['historial']], ['CREACION', 'APROBACION'])
        self.assertEqual(r.data['historial'][0]['actor'], self.solicitante.pk)
        self.assertEqual(r.data['historial'][1]['actor'], self.supervisor.pk)
        for item in [r.data, *r.data['historial']]:
            self.assertFalse(set(item) & {'costo_unitario_neto', 'saldo', 'promedio', 'gasto', 'movimiento', 'huella'})
        self.assertEqual(self.client.get(URL, {'solicitante': self.tecnico.pk}).status_code, 400)

    def test_catalogo_exclusivo_activos_sin_stock_ni_costos(self):
        self.autenticar(self.solicitante)
        r = self.client.get(CATALOGO, {'buscar': self.article.codigo})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(set(r.data['results'][0]), {'id', 'codigo', 'nombre', 'unidad'})
        from apps.inventario import services as inventario
        inventario.editar_articulo(self.article.pk, {'activo': False}, self.bodega)
        self.assertEqual(self.client.get(CATALOGO, {'buscar': self.article.codigo}).data['count'], 0)
        for ruta in ['existencias/', 'movimientos/', 'articulos/', 'entregas/', 'valorizaciones/']:
            self.assertEqual(self.client.get('/api/inventario/'+ruta).status_code, 403)

    def test_catalogo_busqueda_paginada_y_filtros_cerrados(self):
        from apps.inventario import services as inventario
        prefijo = f'catalogo-c1-{self.article.pk}-'
        for indice in range(26):
            inventario.crear_articulo({'codigo': prefijo+str(indice), 'nombre': 'Solicitable sin stock', 'unidad': 'u'}, self.bodega)
        self.autenticar(self.solicitante)
        r = self.client.get(CATALOGO, {'buscar': prefijo})
        self.assertEqual((r.data['count'], len(r.data['results'])), (26, 25))
        self.assertEqual(len(self.client.get(r.data['next']).data['results']), 1)
        for item in r.data['results']:
            self.assertEqual(set(item), {'id', 'codigo', 'nombre', 'unidad'})
        for query in ['?saldo=1', '?activo=false', '?buscar=', '?buscar=a&buscar=b', '?page=0']:
            self.assertEqual(self.client.get(CATALOGO+query).status_code, 400)

    def test_creacion_http_y_replay_y_decision_idempotente(self):
        self.autenticar(self.solicitante)
        data = self.entrada_solicitud()
        r = self.client.post(URL, data, format='json')
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(set(r.data), set(SolicitudSerializer.Meta.fields))
        replay = self.client.post(URL, data, format='json')
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(replay.data, r.data)
        self.assertEqual(replay['Idempotency-Replayed'], 'true')
        s = Solicitud.objects.get(pk=r.data['id'])
        self.autenticar(self.supervisor)
        d = self.entrada_decision(s, cantidad_aprobada='1.000')
        r = self.client.post(f'{URL}{s.pk}/decidir/', d, format='json')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r['Idempotency-Replayed'], 'false')
        replay = self.client.post(f'{URL}{s.pk}/decidir/', d, format='json')
        self.assertEqual(replay.data, r.data)
        self.assertEqual(replay['Idempotency-Replayed'], 'true')

    def test_payloads_ids_decimales_textos_y_uuid_estrictos(self):
        self.autenticar(self.solicitante)
        for campo, valores in [
            ('cantidad', [1, 1.5, True, None, '0', '-1', 'NaN', 'Infinity', '1e2', '1.0001', '1000000000.000', ' 1 ']),
            ('obra', [True, '1', 0, -1, 9223372036854775808]), ('articulo', [True, '1', 0]),
            ('justificacion', [None, True, '', '   ', 'Con\ncontrol', 'Con\x85control', 'Con\x9fcontrol', 'x'*2001]),
            ('clave_idempotencia', ['', None, str(uuid4())+' ', 'x']),
        ]:
            for valor in valores:
                r = self.client.post(URL, self.entrada_solicitud(**{campo: valor}), format='json')
                self.assertEqual(r.status_code, 400, (campo, valor, r.data))
        for extra in [{'actor': self.tecnico.pk}, {'solicitante': self.tecnico.pk}, {'estado': 'APROBADA'}, {'autorizacion': 1},
                      {'cantidad_solicitada': '1'}, {'unidad': 'kg'}, {'costo': '100'}, {'creado_en': '2026-01-01'}]:
            self.assertEqual(self.client.post(URL, self.entrada_solicitud(**extra), format='json').status_code, 400)

    def test_decision_cerrada_y_referencias_inexistentes(self):
        s = self.solicitar()
        self.autenticar(self.supervisor)
        for data in [
            {'decision': 'APROBAR', 'motivo': 'M'}, {'decision': 'RECHAZAR', 'cantidad_aprobada': None, 'motivo': 'M'},
            {'decision': 'OTRA', 'motivo': 'M'}, {'decision': 'RECHAZAR', 'motivo': ''},
            {'decision': 'APROBAR', 'cantidad_aprobada': '1', 'motivo': 'M', 'actor': self.supervisor.pk},
            {'decision': 'APROBAR', 'cantidad_aprobada': '1', 'motivo': 'M', 'autorizacion': 1},
        ]:
            r = self.client.post(f'{URL}{s.pk}/decidir/', {**data, 'clave_idempotencia': str(uuid4())}, format='json')
            self.assertEqual(r.status_code, 400, r.data)
        inexistente = Solicitud.objects.order_by('-pk').first().pk + 1000
        self.assertEqual(self.client.get(f'{URL}{inexistente}/').status_code, 404)
        self.assertEqual(self.client.post(f'{URL}{inexistente}/decidir/', self.entrada_decision(s), format='json').status_code, 404)

    def test_paginacion_filtros_metodos_cache_y_get_sin_escrituras(self):
        for _ in range(26):
            self.solicitar()
        self.autenticar(self.solicitante)
        with CaptureQueriesContext(connection) as queries:
            r = self.client.get(URL)
            self.assertEqual(r.status_code, 200)
            self.assertEqual(len(r.data['results']), 25)
            self.assertEqual(r.data['count'], 26)
            self.assertEqual(len(self.client.get(r.data['next']).data['results']), 1)
            self.assertEqual(self.client.get(f'{URL}{r.data["results"][0]["id"]}/').status_code, 200)
            self.assertEqual(self.client.get(CATALOGO).status_code, 200)
        self.assertFalse(any(q['sql'].lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE')) for q in queries))
        self.assertEqual(r['Cache-Control'], 'private, no-store')
        self.assertIn('Authorization', r['Vary'])
        for suffix in ['?solicitante=1', '?obra=', '?estado=OTRO', '?obra=1&obra=2', '?page=0', '?page=last', '?articulo=true']:
            self.assertEqual(self.client.get(URL+suffix).status_code, 400)
        self.assertEqual(self.client.get(URL+'?page=999').status_code, 404)
        for ruta in [URL, CATALOGO, f'{URL}{r.data["results"][0]["id"]}/']:
            self.assertEqual(self.client.delete(ruta).status_code, 405)

    def test_sesion_revocada_inactiva_y_rol_persistido(self):
        s = self.solicitar()
        for actor, accion, ruta in [(self.solicitante, 'crear', URL), (self.supervisor, 'decidir', URL)]:
            self.autenticar(actor)
            Usuario.objects.filter(pk=actor.pk).update(is_active=False)
            self.assertEqual(self.client.get(ruta).status_code, 401)
            with self.assertRaises(APIException) as error:
                services.crear_solicitud(self.entrada_solicitud(), actor) if accion == 'crear' else services.decidir_solicitud(s.pk, {}, actor)
            self.assertEqual(error.exception.status_code, 401)
            Usuario.objects.filter(pk=actor.pk).update(is_active=True, sesion_version=actor.sesion_version+1)
            self.assertEqual(self.client.get(ruta).status_code, 401)
        self.solicitante.refresh_from_db()
        self.autenticar(self.solicitante)
        Usuario.objects.filter(pk=self.solicitante.pk).update(rol='BODEGUERO')
        self.assertEqual(self.client.get(URL).status_code, 403)

    def test_credencial_temporal_no_accede_a_solicitudes(self):
        for actor in [self.solicitante, self.supervisor]:
            self.autenticar(actor)
            ahora = timezone.now()
            SeguridadCredencial.objects.filter(usuario=actor).update(estado='INICIAL', emitida_en=ahora, vence_en=ahora+timedelta(hours=1))
            self.assertEqual(self.client.get(URL).status_code, 401)
            with self.assertRaises(APIException) as error:
                services.revalidar(actor)
            self.assertEqual(error.exception.status_code, 401)
