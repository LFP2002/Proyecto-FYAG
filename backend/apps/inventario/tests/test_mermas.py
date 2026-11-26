from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

from django.db import connection, transaction, IntegrityError
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from rest_framework.exceptions import APIException

from apps.finanzas.models import Egreso, PagoDocumento
from apps.obras import services as obras
from apps.obras.models import GastoObra, CostoObraEvento, ControlCostosObra, CierreCostosObra
from apps.usuarios.models import Usuario
from apps.usuarios.tokens import AccessToken
from apps.inventario import services as inventario, services_mermas as services, services_materiales as materiales
from apps.inventario.models import Merma, MermaEvento, MovimientoInventario as Movimiento, OperacionMaterial as Op, EstadoValoracion, ExistenciaInventario
from apps.inventario.permissions_mermas import LECTORES
from .test_solicitudes import SolicitudesBase

URLS = {'BODEGA': '/api/inventario/mermas-bodega/', 'OBRA': '/api/inventario/mermas-obra/'}


class MermasBase(SolicitudesBase):
    def preparar_mermas(self):
        self.preparar_solicitudes()
        self.article = inventario.editar_articulo(self.article.pk, {'nombre': 'Manguera QA', 'unidad': 'm'}, self.bodega)

    def entrada_merma(self, ambito='BODEGA', **cambios):
        return {'cantidad': '2.000', 'tipo': 'DANO' if ambito == 'BODEGA' else 'CORTE_NO_REUTILIZABLE',
            'motivo': ' Material roto que no admite reutilización ', 'clave_idempotencia': str(uuid4()),
            **({'articulo': self.article.pk, 'referencia_respaldo': 'Acta interna QA'} if ambito == 'BODEGA'
               else {'entrega': self.entrega.pk, 'actividad': ' Corte en instalación '}), **cambios}

    def informar(self, ambito='BODEGA', **cambios):
        return services.crear(ambito, self.entrada_merma(ambito, **cambios), self.bodega if ambito == 'BODEGA' else self.solicitante)[0]

    def entrada_decision_merma(self, decision='APROBAR', **cambios):
        return {'decision': decision, 'motivo': ' Pérdida verificada ', 'clave_idempotencia': str(uuid4()), **cambios}

    def resolver(self, m, decision='APROBAR', **cambios):
        return services.decidir(m.ambito, m.pk, self.entrada_decision_merma(decision, **cambios),
            self.finanzas if m.ambito == 'BODEGA' else self.supervisor)[0]

    def preparar_entrega(self):
        self.recibir('10.000', '100.00')
        self.entrega = self.entregar('6.000')
        return self.entrega

    def foto(self, modelos):
        return {m: list(m.objects.order_by('pk').values()) for m in modelos}


class MermasDominioTests(MermasBase, TestCase):
    def setUp(self):
        self.preparar_mermas()

    def test_mb_pendiente_sin_efectos_y_baja_unica_con_promedio_historico(self):
        self.recibir('10.000', '123.45')
        modelos = [ExistenciaInventario, EstadoValoracion, Op, Movimiento, GastoObra, Egreso, PagoDocumento]
        antes = self.foto(modelos)
        m = self.informar()
        self.assertEqual(self.foto(modelos), antes)
        self.assertEqual(m.corte_movimiento_id, Movimiento.objects.filter(articulo=self.article).latest('pk').pk)
        m = self.resolver(m)
        self.assertEqual(m.estado, 'APROBADA')
        self.assertEqual(self.saldo(), Decimal('8.000'))
        self.assertEqual((self.valor().saldo_valorado, self.valor().promedio), (Decimal('8.000'), Decimal('123.45')))
        op = m.operacion
        mov = Movimiento.objects.get(operacion=op)
        self.assertEqual((op.tipo, mov.tipo, op.actor_id, mov.actor_id), ('MERMA', 'MERMA', self.finanzas.pk, self.finanzas.pk))
        self.assertIn(str(self.bodega.pk), mov.motivo)
        self.assertEqual(op.merma_bodega_id, m.pk)
        self.assertEqual(op.costo_unitario_neto, Decimal('123.45'))
        for campo in ['obra_id', 'entrega_id', 'autorizacion_id', 'gasto_id', 'ingreso_id', 'solicitud_material_id']:
            self.assertIsNone(getattr(op, campo))
        self.assertEqual(services.importe(m.cantidad, op.costo_unitario_neto), Decimal('246.90'))
        self.recibir('2.000', '200.00')
        op.refresh_from_db()
        self.assertEqual(op.costo_unitario_neto, Decimal('123.45'))
        self.assertEqual(self.foto([GastoObra, Egreso, PagoDocumento]), {k: antes[k] for k in [GastoObra, Egreso, PagoDocumento]})

    def test_mb_agota_saldo_y_promedio_null_y_concilia_sql(self):
        self.recibir('2.000', '10.01')
        self.resolver(self.informar())
        self.assertEqual((self.saldo(), self.valor().saldo_valorado, self.valor().promedio), (0, 0, None))
        with connection.cursor() as cursor:
            cursor.execute("SELECT sum(CASE WHEN tipo IN ('SALIDA','MERMA') THEN -cantidad ELSE cantidad END) FROM inventario_movimientoinventario WHERE articulo_id=%s", [self.article.pk])
            self.assertEqual(cursor.fetchone()[0], self.saldo())
            cursor.execute('SET CONSTRAINTS ALL IMMEDIATE')

    def test_mb_rechazo_no_efectos_incluso_corte_inactivo_o_sin_valorar(self):
        m = self.informar()
        self.recibir(precio=None)
        inventario.editar_articulo(self.article.pk, {'activo': False}, self.bodega)
        antes = self.foto([ExistenciaInventario, EstadoValoracion, Movimiento, Op])
        self.assertEqual(self.resolver(m, 'RECHAZAR').estado, 'RECHAZADA')
        self.assertEqual(self.foto([ExistenciaInventario, EstadoValoracion, Movimiento, Op]), antes)

    def test_mb_corte_cambiado_no_descuenta_ingreso_posterior(self):
        self.recibir()
        m = self.informar()
        self.recibir('1.000', '100.00')
        with self.assertRaises(APIException) as error:
            self.resolver(m)
        self.assertEqual(error.exception.detail['code'], 'corte_desactualizado')
        self.assertEqual(self.saldo(), 11)

    def test_mb_valoracion_sin_movimiento_usa_promedio_oficial_nuevo(self):
        ingreso = self.recibir(precio=None)
        m = self.informar()
        self.op('VALORIZACION', ingreso=ingreso.pk, costo_unitario_neto='77.77', referencia='Valoración oficial')
        self.assertEqual(self.resolver(m).operacion.costo_unitario_neto, Decimal('77.77'))

    def test_mb_stock_valoracion_inactivo_y_subcentavo_conflictos_controlados(self):
        m = self.informar()
        with self.assertRaises(APIException) as error:
            self.resolver(m)
        self.assertEqual(error.exception.detail['code'], 'existencia_insuficiente')
        self.recibir(precio=None)
        m = self.informar()
        with self.assertRaises(APIException) as error:
            self.resolver(m)
        self.assertEqual(error.exception.detail['code'], 'valoracion_pendiente')
        inventario.editar_articulo(self.article.pk, {'activo': False}, self.bodega)
        with self.assertRaises(APIException):
            self.informar()
        with self.assertRaises(APIException):
            self.resolver(m)
        inventario.editar_articulo(self.article.pk, {'activo': True}, self.bodega)
        ingreso = Movimiento.objects.filter(articulo=self.article).latest('pk')
        self.op('VALORIZACION', ingreso=ingreso.pk, costo_unitario_neto='0.01', referencia='Precio pequeño')
        with self.assertRaises(APIException) as error:
            self.resolver(self.informar(cantidad='0.001'))
        self.assertEqual(error.exception.detail['code'], 'importe_fuera_rango')

    def test_ejemplo_seis_metros_reutilizables_reduce_costo_a_cuatro(self):
        e = self.preparar_entrega()
        self.devolver(e, '2.000')
        e.gasto.refresh_from_db()
        self.assertEqual(self.saldo(), 6)
        self.assertEqual((e.gasto.cantidad-e.gasto.cantidad_devuelta)*e.costo_unitario_neto, Decimal('400.00'))

    def test_ejemplo_seis_metros_inutilizables_no_cambia_stock_ni_costos(self):
        e = self.preparar_entrega()
        modelos = [ExistenciaInventario, EstadoValoracion, Movimiento, Op, GastoObra, CostoObraEvento, ControlCostosObra, CierreCostosObra, Egreso, PagoDocumento]
        antes = self.foto(modelos)
        with CaptureQueriesContext(connection) as queries:
            m = self.resolver(self.informar('OBRA'))
        self.assertEqual(self.foto(modelos), antes)
        self.assertEqual(self.saldo(), 4)
        self.assertEqual((e.gasto.cantidad-e.gasto.cantidad_devuelta)*e.costo_unitario_neto, Decimal('600.00'))
        self.assertEqual(m.entrega_id, e.pk)
        self.assertIsNone(m.operacion_id)
        locks = [q['sql'] for q in queries if 'FOR UPDATE' in q['sql']]
        self.assertFalse(any('inventario_articuloinventario' in q or 'obras_gastoobra' in q or 'inventario_estadovaloracion' in q for q in locks))

    def test_mo_sucesivas_parciales_mas_devolucion_nunca_supera_seis(self):
        self.preparar_entrega()
        self.resolver(self.informar('OBRA', cantidad='1.000'))
        self.resolver(self.informar('OBRA', cantidad='2.000'))
        self.devolver(self.entrega, '3.000')
        with self.assertRaises(APIException) as error:
            self.resolver(self.informar('OBRA', cantidad='0.001'))
        self.assertEqual(error.exception.detail['code'], 'remanente_insuficiente')
        with self.assertRaises(APIException):
            self.op('AUTORIZACION_DEVOLUCION', entrega=self.entrega.pk, cantidad='0.001')
        self.assertEqual(services.aprobada(self.entrega.pk), 3)

    def test_autorizacion_antigua_intacta_recepcion_efectiva_disminuye(self):
        e = self.preparar_entrega()
        a = self.op('AUTORIZACION_DEVOLUCION', entrega=e.pk, cantidad='6.000')
        original = Op.objects.filter(pk=a.pk).values().get()
        self.op('DEVOLUCION', autorizacion=a.pk, cantidad='1.000')
        self.resolver(self.informar('OBRA'))
        self.autenticar(self.bodega)
        ruta = '/api/inventario/autorizaciones-devolucion/'
        r = self.client.get(ruta, {'entrega': e.pk})
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data['results'][0]['cantidad_recibible_efectiva'], '3.000')
        self.assertEqual(Op.objects.filter(pk=a.pk).values().get(), original)
        with self.assertRaises(APIException):
            self.op('DEVOLUCION', autorizacion=a.pk, cantidad='3.001')
        self.op('DEVOLUCION', autorizacion=a.pk, cantidad='3.000')
        self.assertEqual(self.client.get(ruta, {'entrega': e.pk}).data['results'][0]['cantidad_recibible_efectiva'], '0.000')
        e.gasto.refresh_from_db()
        self.assertEqual(e.gasto.cantidad_devuelta, 4)

    def test_nuevas_autorizaciones_descuentan_todas_las_previas_y_mo(self):
        self.preparar_entrega()
        a = self.op('AUTORIZACION_DEVOLUCION', entrega=self.entrega.pk, cantidad='3.000')
        self.op('DEVOLUCION', autorizacion=a.pk, cantidad='1.000')
        self.resolver(self.informar('OBRA'))
        self.op('AUTORIZACION_DEVOLUCION', entrega=self.entrega.pk, cantidad='1.000')
        with self.assertRaises(APIException):
            self.op('AUTORIZACION_DEVOLUCION', entrega=self.entrega.pk, cantidad='0.001')

    def test_mo_inexistente_ajena_desasignado_obra_finalizada(self):
        self.preparar_entrega()
        with self.assertRaises(APIException) as error:
            self.informar('OBRA', entrega=self.entrega.pk+10000)
        self.assertEqual(error.exception.status_code, 404)
        m = self.informar('OBRA')
        self.desasignar()
        with self.assertRaises(APIException) as error:
            self.informar('OBRA')
        self.assertEqual(error.exception.status_code, 404)
        with self.assertRaises(APIException):
            self.resolver(m)
        self.assertEqual(self.resolver(m, 'RECHAZAR').estado, 'RECHAZADA')
        self.cambiar_estado(self.obra, 'FINALIZADA')
        with self.assertRaises(APIException):
            self.resolver(m, 'RECHAZAR')
        self.autenticar(self.solicitante)
        self.assertEqual(self.client.get(f'{URLS["OBRA"]}{m.pk}/').status_code, 200)

    def test_replays_historicos_uuid_dominios_y_doble_decision(self):
        self.preparar_entrega()
        for ambito in URLS:
            actor = self.bodega if ambito == 'BODEGA' else self.solicitante
            decide = self.finanzas if ambito == 'BODEGA' else self.supervisor
            data = self.entrada_merma(ambito)
            m, nueva = services.crear(ambito, data, actor)
            self.assertTrue(nueva)
            d = self.entrada_decision_merma()
            res, nueva = services.decidir(ambito, m.pk, d, decide)
            self.assertTrue(nueva)
            replay, nueva = services.decidir(ambito, m.pk, d, decide)
            self.assertFalse(nueva)
            self.assertEqual(res.operacion_id, replay.operacion_id)
            with self.assertRaises(APIException):
                services.decidir(ambito, m.pk, {**d, 'motivo': 'Otra carga'}, decide)
            with self.assertRaises(APIException):
                self.resolver(m, 'RECHAZAR')
            self.autenticar(actor)
            r = self.client.post(URLS[ambito], data, format='json')
            self.assertEqual((r.status_code, r.data['estado'], r['Idempotency-Replayed']), (200, 'PENDIENTE', 'true'))
            self.assertIsNone(r.data['operacion'])
            self.assertEqual(m.eventos.count(), 2)
            with self.assertRaises(APIException):
                services.crear(ambito, {**data, 'cantidad': '1.000'}, actor)
            with self.assertRaises(APIException):
                services.decidir(ambito, m.pk, {**d, 'clave_idempotencia': data['clave_idempotencia']}, decide)

    def test_fallo_evento_revierte_baja_y_proyecciones(self):
        self.recibir()
        m = self.informar()
        modelos = [ExistenciaInventario, EstadoValoracion, Movimiento, Op]
        antes = self.foto(modelos)
        with patch.object(MermaEvento.objects, 'create', side_effect=RuntimeError('Fallo controlado')):
            with self.assertRaises(RuntimeError):
                self.resolver(m)
        self.assertEqual(self.foto(modelos), antes)
        m.refresh_from_db()
        self.assertEqual(m.estado, 'PENDIENTE')

    def test_mo_suspendida_rechazo_y_replay_no_producen_efectos(self):
        self.preparar_entrega()
        self.cambiar_estado(self.obra, 'SUSPENDIDA')
        m = self.informar('OBRA')
        antes = self.foto([Op, Movimiento, EstadoValoracion, GastoObra, CostoObraEvento, ControlCostosObra])
        data = self.entrada_decision_merma('RECHAZAR')
        one, creada = services.decidir('OBRA', m.pk, data, self.supervisor)
        two, nueva = services.decidir('OBRA', m.pk, data, self.supervisor)
        self.assertEqual((creada, nueva, one.estado, two.estado), (True, False, 'RECHAZADA', 'RECHAZADA'))
        self.assertEqual(self.foto(list(antes)), antes)

    def test_uuid_creacion_distinto_actor_y_ambito_conflictivos(self):
        self.preparar_entrega()
        data = self.entrada_merma()
        services.crear('BODEGA', data, self.bodega)
        otro = Usuario.objects.create_user(username='otro_bodega_merma', email='otro_bodega_merma@example.test', rol='BODEGUERO')
        for ambito, payload, actor in [('BODEGA', data, otro), ('OBRA', self.entrada_merma('OBRA', clave_idempotencia=data['clave_idempotencia']), self.solicitante)]:
            with self.assertRaises(APIException) as error:
                services.crear(ambito, payload, actor)
            self.assertEqual(error.exception.detail['code'], 'idempotencia_conflictiva')

    def test_mb_half_up_y_costo_cero_explicito(self):
        self.recibir('1.000', '1.00')
        m = self.resolver(self.informar(cantidad='0.015'))
        self.assertEqual(services.importe(m.cantidad, m.operacion.costo_unitario_neto), Decimal('0.02'))
        # Cero oficial es legítimo, distinto de redondear un positivo a cero.
        self.assertEqual(services.importe(Decimal('0.001'), Decimal('0.00')), Decimal('0.00'))


class MermasAPITests(MermasBase, TestCase):
    def setUp(self):
        self.preparar_mermas()
        self.preparar_entrega()

    def test_matriz_seis_roles_flags_claims_y_costos_restringidos(self):
        mb = self.resolver(self.informar())
        mo = self.resolver(self.informar('OBRA'))
        for rol in Usuario.Rol.values:
            actor = Usuario.objects.create_user(username='merma_'+rol, email=rol+'@merma.test', rol=rol, is_staff=True, is_superuser=True)
            token = AccessToken.for_user(actor)
            token['rol'] = 'GERENCIA'
            self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
            for ambito, m in [('BODEGA', mb), ('OBRA', mo)]:
                lector = rol in LECTORES[ambito]
                r = self.client.get(URLS[ambito])
                self.assertEqual(r.status_code, 200 if lector else 403, (rol, ambito, r.data))
                detalle = self.client.get(f'{URLS[ambito]}{m.pk}/')
                self.assertEqual(detalle.status_code, 404 if rol == 'TECNICO' and ambito == 'OBRA' else 200 if lector else 403)
                if lector and rol != 'TECNICO':
                    campos = set(detalle.data)
                    self.assertEqual('costo_unitario_neto' in campos, rol != 'BODEGUERO')
                    self.assertFalse(any('costo' in k or 'importe' in k for e in detalle.data['historial'] for k in e))
                escritor = 'BODEGUERO' if ambito == 'BODEGA' else 'TECNICO'
                decisor = 'ADMINISTRATIVO_FINANZAS' if ambito == 'BODEGA' else 'SUPERVISOR_OBRAS'
                self.assertEqual(self.client.post(URLS[ambito], {}, format='json').status_code, 400 if rol == escritor else 403)
                self.assertEqual(self.client.post(f'{URLS[ambito]}{m.pk}/decidir/', {}, format='json').status_code, 400 if rol == decisor else 403)

    def test_scope_propio_historia_y_get_no_escribe(self):
        m = self.informar('OBRA')
        ajena = services.crear('OBRA', self.entrada_merma('OBRA'), self.tecnico)[0]
        self.resolver(m)
        self.autenticar(self.solicitante)
        with CaptureQueriesContext(connection) as queries:
            r = self.client.get(URLS['OBRA'], {'obra': self.obra.pk, 'entrega': self.entrega.pk, 'estado': 'APROBADA'})
            d = self.client.get(f'{URLS["OBRA"]}{m.pk}/')
        self.assertEqual([x['id'] for x in r.data['results']], [m.pk])
        self.assertEqual(self.client.get(f'{URLS["OBRA"]}{ajena.pk}/').status_code, 404)
        self.assertEqual([e['tipo'] for e in d.data['historial']], ['CREACION', 'APROBACION'])
        self.assertFalse(set(d.data) & {'costo_unitario_neto', 'importe_informativo_no_aditivo', 'gasto', 'saldo', 'huella'})
        self.assertFalse(any(q['sql'].lstrip().upper().startswith(('INSERT', 'UPDATE', 'DELETE')) for q in queries))
        self.assertEqual(d['Cache-Control'], 'private, no-store')
        self.assertIn('Authorization', d['Vary'])

    def test_payloads_cerrados_decimales_textos_uuid_y_decision_total(self):
        for ambito in URLS:
            self.autenticar(self.bodega if ambito == 'BODEGA' else self.solicitante)
            for campo, valores in [('cantidad', [None, True, 1, 1.1, '0', '-1', '1e2', '1.0001', '1000000000', 'NaN']),
                                   ('motivo', [None, '', '  ', 'a\ncontrol', 'a\x85control', 'x'*2001]),
                                   ('tipo', [[], None, 'TIPO_FALSO']), ('clave_idempotencia', ['x', None])]:
                for valor in valores:
                    r = self.client.post(URLS[ambito], self.entrada_merma(ambito, **{campo: valor}), format='json')
                    self.assertEqual(r.status_code, 400, (ambito, campo, valor, r.data))
            for campo in ['actor', 'estado', 'costo', 'unidad', 'gasto', 'cantidad_aprobada'] + (['obra', 'articulo'] if ambito == 'OBRA' else ['entrega']):
                self.assertEqual(self.client.post(URLS[ambito], self.entrada_merma(ambito, **{campo: 1}), format='json').status_code, 400)
            m = self.informar(ambito)
            self.autenticar(self.finanzas if ambito == 'BODEGA' else self.supervisor)
            self.assertEqual(self.client.post(f'{URLS[ambito]}{m.pk}/decidir/', self.entrada_decision_merma(cantidad='1.000'), format='json').status_code, 400)

    def test_filtros_estrictos_paginacion_y_metodos(self):
        for _ in range(26):
            self.informar()
        self.autenticar(self.bodega)
        r = self.client.get(URLS['BODEGA'], {'articulo': self.article.pk})
        self.assertEqual((r.data['count'], len(r.data['results'])), (26, 25))
        self.assertEqual(len(self.client.get(r.data['next']).data['results']), 1)
        for query in ['?informado_por=1', '?estado=', '?tipo=FALSO', '?articulo=1&articulo=2', '?obra=1', '?page=0', '?page=last']:
            self.assertEqual(self.client.get(URLS['BODEGA']+query).status_code, 400)
        self.assertEqual(self.client.get(URLS['BODEGA']+'?page=999').status_code, 404)
        self.assertEqual(self.client.delete(URLS['BODEGA']).status_code, 405)
        self.assertEqual(self.client.patch(f'{URLS["BODEGA"]}{r.data["results"][0]["id"]}/', {}, format='json').status_code, 405)

    def test_valores_historicos_no_aditivos_en_proyeccion_autorizada(self):
        m = self.resolver(self.informar('OBRA'))
        self.recibir('10.000', '200.00')
        self.autenticar(self.supervisor)
        r = self.client.get(f'{URLS["OBRA"]}{m.pk}/')
        self.assertEqual((r.data['costo_unitario_neto'], r.data['importe_informativo_no_aditivo']), ('100.00', '200.00'))
        self.autenticar(self.bodega)
        r = self.client.get('/api/inventario/movimientos/', {'tipo': 'MERMA'})
        self.assertEqual(r.status_code, 200)

    def test_sesion_version_rol_y_actividad_persistidos(self):
        for actor, ambito in [(self.bodega, 'BODEGA'), (self.solicitante, 'OBRA')]:
            self.autenticar(actor)
            Usuario.objects.filter(pk=actor.pk).update(sesion_version=actor.sesion_version+1)
            self.assertEqual(self.client.get(URLS[ambito]).status_code, 401)
            with self.assertRaises(APIException) as error:
                services.crear(ambito, self.entrada_merma(ambito), actor)
            self.assertEqual(error.exception.status_code, 401)

class BodegaConsultaMermasTests(MermasBase, TestCase):
    def setUp(self):
        self.preparar_mermas()

    def test_proyeccion_mermas_y_confirmacion_propia(self):
        m = self.informar()
        self.autenticar(self.bodega)
        url = '/api/inventario/bodega/'
        response = self.client.get(url, {'seccion': 'mermas', 'buscar': 'Manguera', 'estado': 'PENDIENTE'})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['count'], 1)
        row = response.data['results'][0]
        self.assertEqual((row['id'], row['nombre'], row['cantidad']), (m.pk, 'Manguera QA', '2.000'))
        self.assertNotIn('costo_unitario_neto', row)
        self.assertNotIn('clave_idempotencia', row)
        detail = self.client.get(url, {'seccion': 'merma_detalle', 'merma': m.pk})
        self.assertEqual(detail.status_code, 200, detail.data)
        self.assertEqual(detail.data['historial'][0]['tipo'], 'CREACION')
        self.assertEqual(self.client.get(url, {'seccion': 'confirmacion', 'tipo': 'MERMA', 'clave': str(m.clave_idempotencia)}).data, {'id': m.pk})
        self.assertEqual(self.client.get(url, {'seccion': 'mermas', 'estado': 'APROBADA'}).data['count'], 0)
        self.assertEqual(self.client.get(url, {'seccion': 'merma_detalle', 'merma': 999999}).status_code, 404)
        self.autenticar(self.finanzas)
        self.assertEqual(self.client.get(url, {'seccion': 'mermas'}).status_code, 403)
