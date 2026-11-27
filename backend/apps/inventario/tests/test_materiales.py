from decimal import Decimal
from uuid import uuid4
from unittest.mock import patch

from django.db import connection, transaction, IntegrityError
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.exceptions import APIException

from apps.usuarios.models import Usuario
from apps.usuarios.tokens import AccessToken
from apps.obras.tests.test_finalizacion import FinalizacionBase
from apps.obras import services_gastos as gastos
from apps.obras.models import GastoObra, CostoObraEvento, CierreCostosObra
from apps.obras.exceptions import EstadoIncompatible
from apps.finanzas.models import Egreso, PagoDocumento, DocumentoCobro
from apps.inventario import services, services_materiales as materiales
from apps.inventario.permissions_materiales import ESCRITORES
from apps.inventario.models import OperacionMaterial as Op, EstadoValoracion, MovimientoInventario, ExistenciaInventario

RUTAS = {'AUTORIZACION_ENTREGA': 'autorizaciones-entrega', 'ENTREGA': 'entregas',
    'AUTORIZACION_DEVOLUCION': 'autorizaciones-devolucion', 'DEVOLUCION': 'devoluciones',
    'VALORIZACION': 'valorizaciones', 'REGULARIZACION': 'regularizaciones-iniciales'}


class MaterialesBase(FinalizacionBase):
    def confirmacion_cierre(self):
        r = self.client.get(f'/api/obras/{self.obra.pk}/requisitos-cierre/')
        self.assertEqual(r.status_code, 200, r.data)
        self.assertIsNotNone(r.data['confirmacion_remanente'])
        return r.data['confirmacion_remanente']

    def preparar_materiales(self):
        self.preparar()
        self.bodega = Usuario.objects.create_user(username='bodega019b', email='bodega019b@example.test', rol='BODEGUERO')
        self.article = services.crear_articulo({'codigo': 'mat019b', 'nombre': 'Material 019B', 'unidad': 'kg'}, self.bodega)

    def op(self, tipo, **data):
        actor = self.supervisor if tipo.startswith('AUTORIZACION') else self.finanzas if tipo in {'VALORIZACION', 'REGULARIZACION'} else self.bodega
        return materiales.operar(tipo, {'clave_idempotencia': str(uuid4()), **data}, actor)[0]

    def recibir(self, cantidad='10.000', precio='100.00'):
        m, _ = services.registrar_ingreso({'articulo': self.article.pk, 'cantidad': cantidad, 'clave_idempotencia': str(uuid4())}, self.bodega)
        if precio is not None:
            self.op('VALORIZACION', ingreso=m.pk, costo_unitario_neto=precio, referencia='RESPALDO-NETO')
        return m

    def autorizar(self, cantidad='10.000'):
        return self.op('AUTORIZACION_ENTREGA', obra=self.obra.pk, articulo=self.article.pk, cantidad=cantidad)

    def entregar(self, cantidad='2.000', autorizacion=None):
        return self.op('ENTREGA', autorizacion=(autorizacion or self.autorizar()).pk, cantidad=cantidad)

    def devolver(self, entrega, cantidad='1.000'):
        a = self.op('AUTORIZACION_DEVOLUCION', entrega=entrega.pk, cantidad=cantidad)
        return self.op('DEVOLUCION', autorizacion=a.pk, cantidad=cantidad)

    def valor(self):
        return EstadoValoracion.objects.get(articulo=self.article)

    def saldo(self):
        return ExistenciaInventario.objects.get(articulo=self.article).saldo


class MaterialesTests(MaterialesBase, TestCase):
    def setUp(self):
        self.preparar_materiales()

    def test_autorizacion_no_reserva_ni_modifica_costos(self):
        a = self.autorizar()
        self.assertEqual(a.actor_id, self.supervisor.pk)
        self.assertEqual(a.unidad, 'kg')
        self.assertEqual(self.saldo(), 0)
        self.assertFalse(MovimientoInventario.objects.exists())
        self.assertFalse(GastoObra.objects.exists())
        self.assertFalse(CostoObraEvento.objects.exists())

    def test_despachos_parciales_cada_uno_un_gasto_y_costo_congelado(self):
        self.recibir()
        a = self.autorizar('5.000')
        e = self.entregar('2.000', a)
        self.recibir('10.000', '200.00')
        f = self.entregar('3.000', a)
        self.assertEqual(e.costo_unitario_neto, Decimal('100.00'))
        self.assertEqual(f.costo_unitario_neto, Decimal('155.56'))
        self.assertEqual(self.saldo(), Decimal('15.000'))
        self.assertEqual(GastoObra.objects.count(), 2)
        for op in (e, f):
            self.assertEqual(op.gasto.origen, 'BODEGA_019B')
            self.assertEqual(op.gasto.registrado_por_id, self.bodega.pk)
            self.assertEqual(op.movimiento.actor_id, self.bodega.pk)
            ev = op.gasto.eventos.get()
            self.assertEqual(ev.registrado_por_id, self.bodega.pk)
            self.assertEqual(ev.datos_nuevos['origen'], 'BODEGA_019B')
        with self.assertRaises(APIException) as error:
            self.entregar('0.001', a)
        self.assertEqual(error.exception.status_code, 409)

    def test_devolucion_historica_recalcula_promedio_y_mismo_gasto(self):
        self.recibir()
        e = self.entregar('4.000')
        self.recibir('6.000', '200.00')
        self.assertEqual(self.valor().promedio, Decimal('150.00'))
        d = self.devolver(e, '2.000')
        self.assertEqual(d.costo_unitario_neto, Decimal('100.00'))
        self.assertEqual(self.valor().promedio, Decimal('142.86'))
        self.assertEqual(self.saldo(), Decimal('14.000'))
        e.gasto.refresh_from_db()
        self.assertEqual(e.gasto.cantidad_devuelta, Decimal('2.000'))
        self.assertEqual(e.gasto.subtotal, Decimal('200.00'))
        self.assertEqual(e.gasto.eventos.get(tipo='DEVOLUCION').datos_nuevos['devolucion']['cantidad'], '2.000')

    def test_retorno_pendiente_y_parciales_no_reutilizan_cantidades(self):
        self.recibir()
        e = self.entregar('4.000')
        a = self.op('AUTORIZACION_DEVOLUCION', entrega=e.pk, cantidad='3.000')
        self.assertEqual(self.saldo(), 6)
        self.assertEqual(GastoObra.objects.get(pk=e.gasto_id).cantidad_devuelta, 0)
        with self.assertRaises(APIException):
            self.op('AUTORIZACION_DEVOLUCION', entrega=e.pk, cantidad='1.001')
        self.op('DEVOLUCION', autorizacion=a.pk, cantidad='1.000')
        self.op('DEVOLUCION', autorizacion=a.pk, cantidad='2.000')
        with self.assertRaises(APIException):
            self.op('DEVOLUCION', autorizacion=a.pk, cantidad='0.001')
        self.assertEqual(self.saldo(), 9)

    def test_fail_closed_pendientes_y_orden_de_valoracion(self):
        x = self.recibir('2.000', None)
        y = self.recibir('2.000', None)
        a = self.autorizar('1.000')
        with self.assertRaises(APIException) as error:
            self.entregar('1.000', a)
        self.assertEqual(error.exception.detail['code'], 'valoracion_pendiente')
        with self.assertRaises(APIException) as error:
            self.op('VALORIZACION', ingreso=y.pk, costo_unitario_neto='150.00', referencia='R')
        self.assertEqual(error.exception.detail['code'], 'orden_valoracion')
        self.op('VALORIZACION', ingreso=x.pk, costo_unitario_neto='100.00', referencia='R')
        with self.assertRaises(APIException):
            self.entregar('1.000', a)
        self.op('VALORIZACION', ingreso=y.pk, costo_unitario_neto='200.00', referencia='R')
        self.assertEqual(self.valor().promedio, Decimal('150.00'))
        self.entregar('1.000', a)

    def test_sin_stock_no_movimiento_y_salida_agota_promedio(self):
        self.recibir('1.000')
        a = self.autorizar('5.000')
        with self.assertRaises(APIException) as error:
            self.entregar('2.000', a)
        self.assertEqual(error.exception.detail['code'], 'existencia_insuficiente')
        self.assertFalse(GastoObra.objects.exists())
        e = self.entregar('1.000', a)
        self.assertIsNone(self.valor().promedio)
        self.devolver(e, '1.000')
        self.assertEqual(self.valor().promedio, Decimal('100.00'))

    def test_devolucion_con_recepcion_sin_precio_y_articulo_inactivo(self):
        self.recibir('4.000')
        e = self.entregar('2.000')
        a = self.op('AUTORIZACION_DEVOLUCION', entrega=e.pk, cantidad='1.000')
        self.recibir('1.000', None)
        services.editar_articulo(self.article.pk, {'activo': False}, self.bodega)
        self.op('DEVOLUCION', autorizacion=a.pk, cantidad='1.000')
        self.assertEqual(self.saldo(), 4)
        self.assertEqual(self.valor().saldo_valorado, 3)
        with self.assertRaises(APIException):
            self.entregar('1.000')

    def test_half_up_y_limites_sin_perdida_silenciosa(self):
        self.recibir('1.000', '0.01')
        self.recibir('1.000', '0.02')
        self.assertEqual(self.valor().promedio, Decimal('0.02'))
        with self.assertRaises(APIException) as error:
            self.entregar('0.001')
        self.assertEqual(error.exception.detail['code'], 'estado_incompatible')
        self.assertEqual(self.saldo(), 2)
        self.recibir('1.000', '9999999999999.99')
        self.assertLessEqual(self.valor().promedio, materiales.PRECIO_MAXIMO)

    def test_invalidacion_una_vez_y_posterior_revalidacion_y_cierre(self):
        self.completa()
        antes = self.control().version_actual
        self.recibir()
        e = self.entregar()
        c = self.control()
        self.assertEqual(c.version_actual, antes+1)
        self.assertFalse(c.costos_validados)
        self.assertTrue(all(ev.datos_nuevos.get('origen') == 'BODEGA_019B'
            for ev in CostoObraEvento.objects.filter(registrado_por=self.bodega)))
        self.declarar(materiales_estado='CON_REGISTROS')
        self.validar()
        self.assertTrue(self.control().costos_validados)
        antes = self.control().version_actual
        self.devolver(e)
        self.assertEqual(self.control().version_actual, antes+1)
        self.assertFalse(self.control().costos_validados)
        self.validar()
        self.finalizar(self.confirmacion_cierre())
        foto = list(CierreCostosObra.objects.values())
        with self.assertRaises(APIException):
            self.autorizar()
        with self.assertRaises(APIException):
            self.devolver(e)
        self.assertEqual(list(CierreCostosObra.objects.values()), foto)

    def test_guard_servicios_y_rutas_004b_no_conceden_permiso_a_bodega(self):
        self.recibir()
        e = self.entregar()
        for func, data in [(gastos.editar_gasto, {'observacion': 'Manual', 'motivo': 'No'}),
                           (gastos.anular_gasto, {'motivo': 'No'}),
                           (gastos.devolver_gasto, {'cantidad': '1', 'motivo': 'No', 'fecha_devolucion': e.gasto.fecha_gasto})]:
            with self.assertRaises(EstadoIncompatible):
                func(self.obra, e.gasto_id, data, self.supervisor)
        self.autenticar(self.supervisor)
        lectura = self.client.get(self.url)
        self.assertEqual(lectura.status_code, 200)
        fila = next(g for g in lectura.data['results'] if g['id'] == e.gasto_id)
        self.assertEqual(fila['origen'], 'BODEGA_019B')
        self.assertEqual(fila['entrega_bodega'], e.pk)
        self.assertEqual(self.client.patch(f'{self.url}{e.gasto_id}/', {'observacion': 'No', 'motivo': 'No'}, format='json').status_code, 409)
        self.autenticar(self.bodega)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_idempotencia_replay_original_tras_devolucion_y_colisiones(self):
        self.recibir()
        a = self.autorizar()
        data = {'autorizacion': a.pk, 'cantidad': '2', 'clave_idempotencia': str(uuid4())}
        e, creado = materiales.operar('ENTREGA', data, self.bodega)
        self.devolver(e)
        replay, creado2 = materiales.operar('ENTREGA', {**data, 'cantidad': '2.000'}, self.bodega)
        self.assertTrue(creado)
        self.assertFalse(creado2)
        self.assertEqual(e.pk, replay.pk)
        self.assertEqual(replay.cantidad, Decimal('2.000'))
        with self.assertRaises(APIException):
            materiales.operar('ENTREGA', {**data, 'cantidad': '1'}, self.bodega)
        with self.assertRaises(APIException):
            services.registrar_ingreso({'articulo': self.article.pk, 'cantidad': '2', 'clave_idempotencia': data['clave_idempotencia']}, self.bodega)
        self.assertEqual(GastoObra.objects.count(), 1)

    def test_atomicidad_fallo_evento_y_error_inesperado_no_se_oculta(self):
        self.recibir()
        a = self.autorizar()
        antes = self.saldo()
        with patch('apps.obras.services_gastos._evento', side_effect=RuntimeError('fallo')):
            with self.assertRaises(RuntimeError):
                self.entregar('1.000', a)
        self.assertEqual(self.saldo(), antes)
        self.assertEqual(self.valor().saldo_valorado, antes)
        self.assertFalse(GastoObra.objects.exists())
        with patch('apps.inventario.services_materiales._operar', side_effect=IntegrityError('inesperado')):
            with self.assertRaises(IntegrityError):
                self.entregar('1.000', a)

    def test_sql_protege_vinculos_actores_estado_y_libro(self):
        self.recibir()
        e = self.entregar()
        manual = gastos.crear_gasto(self.obra, {**self.entrada(), 'fecha_gasto': timezone.localdate()}, self.supervisor)
        with self.assertRaises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
            cursor.execute('UPDATE obras_costoobraevento SET gasto_id=%s WHERE gasto_id=%s', [e.gasto_id, manual.pk])
        for sql, params in [
            ('UPDATE obras_gastoobra SET costo_unitario_neto=1 WHERE id=%s', [e.gasto_id]),
            ('UPDATE obras_gastoobra SET origen=\'MANUAL\' WHERE id=%s', [e.gasto_id]),
            ('UPDATE obras_gastoobra SET cantidad_devuelta=1 WHERE id=%s', [e.gasto_id]),
            ('UPDATE inventario_operacionmaterial SET cantidad=1 WHERE id=%s', [e.pk]),
            ('DELETE FROM inventario_operacionmaterial WHERE id=%s', [e.pk]),
            ('UPDATE inventario_estadovaloracion SET promedio=1 WHERE articulo_id=%s', [self.article.pk]),
            ('DELETE FROM obras_costoobraevento WHERE gasto_id=%s', [e.gasto_id]),
        ]:
            with self.assertRaises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
                cursor.execute(sql, params)
        with self.assertRaises(IntegrityError), transaction.atomic():
            MovimientoInventario.objects.create(articulo=self.article, tipo='SALIDA', cantidad='1', saldo_anterior='8',
                saldo_posterior='7', clave_idempotencia=uuid4(), actor=self.bodega)

    def test_no_escritura_en_finanzas_021(self):
        modelos = [Egreso, PagoDocumento, DocumentoCobro]
        antes = {m: list(m.objects.order_by('pk').values()) for m in modelos}
        self.recibir()
        e = self.entregar()
        self.devolver(e)
        for m in modelos:
            self.assertEqual(list(m.objects.order_by('pk').values()), antes[m])

    def test_sql_rechaza_actor_unidad_gasto_manual_y_cruces(self):
        base = {'tipo': 'AUTORIZACION_ENTREGA', 'articulo': self.article, 'obra': self.obra, 'cantidad': '1.000',
            'unidad': 'kg', 'referencia': 'R', 'motivo': 'M', 'huella': 'a'*64, 'actor': self.supervisor}
        for cambios in [{'actor': self.bodega}, {'unidad': 'm'}, {'obra': None}]:
            with self.assertRaises(IntegrityError), transaction.atomic():
                Op.objects.create(**{**base, **cambios, 'clave_idempotencia': uuid4()})
        manual = gastos.crear_gasto(self.obra, {**self.entrada(), 'fecha_gasto': timezone.localdate()}, self.supervisor)
        with self.assertRaises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
            cursor.execute("UPDATE obras_gastoobra SET origen='BODEGA_019B' WHERE id=%s", [manual.pk])
        with self.assertRaises(IntegrityError), transaction.atomic():
            GastoObra.objects.create(obra=self.obra, origen='BODEGA_019B', tipo='MATERIAL', descripcion='Huérfano',
                unidad='kg', cantidad='1.000', costo_unitario_neto='100.00', fecha_gasto=manual.fecha_gasto, registrado_por=self.bodega)
            with connection.cursor() as cursor:
                cursor.execute('SET CONSTRAINTS ALL IMMEDIATE')

    def test_operaciones_en_estados_no_operativos_y_suspendida(self):
        self.recibir()
        a = self.autorizar()
        self.cambiar_estado(self.obra, 'SUSPENDIDA')
        e = self.entregar('1.000', a)
        retorno = self.op('AUTORIZACION_DEVOLUCION', entrega=e.pk, cantidad='1.000')
        for estado in ['PLANIFICADA', 'CANCELADA', 'FINALIZADA']:
            self.cambiar_estado(self.obra, estado)
            for tipo, data in [('AUTORIZACION_ENTREGA', {'obra': self.obra.pk, 'articulo': self.article.pk, 'cantidad': '1'}),
                               ('ENTREGA', {'autorizacion': a.pk, 'cantidad': '1'}),
                               ('AUTORIZACION_DEVOLUCION', {'entrega': e.pk, 'cantidad': '1'}),
                               ('DEVOLUCION', {'autorizacion': retorno.pk, 'cantidad': '1'})]:
                with self.assertRaises(APIException) as error:
                    self.op(tipo, **data)
                self.assertEqual(error.exception.status_code, 409)


class MaterialesAPITests(MaterialesBase, TestCase):
    def setUp(self):
        self.preparar_materiales()

    def test_seis_roles_permisos_por_accion_sin_bypass(self):
        for rol in Usuario.Rol.values:
            actor = Usuario.objects.create_user(username='mat_'+rol, email=rol+'@mat.test', rol=rol, is_superuser=True, is_staff=True)
            token = AccessToken.for_user(actor)
            token['rol'] = 'BODEGUERO'
            self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')
            for tipo, ruta in RUTAS.items():
                lee = rol in ({'GERENCIA', 'ADMINISTRATIVO_FINANZAS'} if tipo in {'VALORIZACION', 'REGULARIZACION'} else {'GERENCIA', 'SUPERVISOR_OBRAS', 'BODEGUERO'})
                url = '/api/inventario/'+ruta+'/'
                self.assertEqual(self.client.get(url).status_code, 200 if lee else 403, (rol, ruta))
                r = self.client.post(url, {}, format='json')
                self.assertEqual(r.status_code, 400 if rol == ESCRITORES[tipo] else 403, (rol, ruta, r.data))

    def test_bodega_sin_precios_en_respuestas_queries_y_estado_publico(self):
        self.recibir()
        e = self.entregar()
        self.autenticar(self.bodega)
        for ruta in ['entregas/', 'movimientos/', 'estados-valorizacion/']:
            r = self.client.get('/api/inventario/'+ruta)
            self.assertEqual(r.status_code, 200, r.data)
            for item in r.data['results']:
                self.assertFalse(set(item) & {'gasto', 'costo_unitario_neto', 'promedio_anterior', 'promedio_posterior', 'saldo_valorado_anterior', 'saldo_valorado_posterior'})
        for ruta in ['valorizaciones/', 'regularizaciones-iniciales/']:
            self.assertEqual(self.client.get('/api/inventario/'+ruta).status_code, 403)
        self.assertEqual(self.client.get('/api/inventario/entregas/?costo_unitario_neto=100').status_code, 400)
        self.assertEqual(self.client.get('/api/inventario/estados-valorizacion/').data['results'][0]['estado'], 'DISPONIBLE')
        self.recibir('1.000', None)
        self.assertEqual(self.client.get('/api/inventario/estados-valorizacion/').data['results'][0]['estado'], 'PENDIENTE_VALORIZACION')

    def test_cuerpos_filtros_decimales_y_metodos_estrictos(self):
        self.autenticar(self.supervisor)
        url = '/api/inventario/autorizaciones-entrega/'
        data = {'obra': self.obra.pk, 'articulo': self.article.pk, 'cantidad': '1.000', 'clave_idempotencia': str(uuid4())}
        for cambios in [{'actor': 1}, {'saldo': '1'}, {'precio': '1'}, {'cantidad': 1.5}, {'cantidad': True},
                        {'cantidad': '0'}, {'cantidad': '1.0001'}, {'obra': True}, {'articulo': '1'}, {'clave_idempotencia': 'x'}]:
            self.assertEqual(self.client.post(url, {**data, **cambios}, format='json').status_code, 400)
        for query in ['?x=1', '?obra=', '?obra=1&obra=2', '?page=0', '?page=last', '?articulo=true']:
            self.assertEqual(self.client.get(url+query).status_code, 400)
        self.assertEqual(self.client.delete(url).status_code, 405)
        self.autenticar(self.finanzas)
        m = self.recibir(precio=None)
        for p in [1, 1.5, True, 'NaN', 'Infinity', '-1', '1e2', '1.001', '10000000000000.00']:
            r = self.client.post('/api/inventario/valorizaciones/', {'ingreso': m.pk, 'costo_unitario_neto': p,
                'referencia': 'R', 'clave_idempotencia': str(uuid4())}, format='json')
            self.assertEqual(r.status_code, 400, (p, r.data))

    def test_paginacion_25_get_sin_escrituras_y_revocacion(self):
        for _ in range(26):
            self.autorizar()
        self.autenticar(self.supervisor)
        with CaptureQueriesContext(connection) as queries:
            r = self.client.get('/api/inventario/autorizaciones-entrega/')
        self.assertEqual((r.data['count'], len(r.data['results'])), (26, 25))
        self.assertFalse(any(q['sql'].lstrip().upper().startswith(('UPDATE', 'INSERT', 'DELETE')) for q in queries))
        self.assertEqual(r['Cache-Control'], 'private, no-store')
        self.assertIn('Authorization', r['Vary'])
        Usuario.objects.filter(pk=self.supervisor.pk).update(sesion_version=self.supervisor.sesion_version+1)
        self.assertEqual(self.client.get('/api/inventario/autorizaciones-entrega/').status_code, 401)
        with self.assertRaises(APIException) as error:
            self.autorizar()
        self.assertEqual(error.exception.status_code, 401)

    def test_http_idempotencia_en_todos_los_actos_ejecutables(self):
        m = self.recibir(precio=None)
        etapas = [
            ('VALORIZACION', self.finanzas, {'ingreso': m.pk, 'costo_unitario_neto': '100.00', 'referencia': 'R'}),
            ('AUTORIZACION_ENTREGA', self.supervisor, {'obra': self.obra.pk, 'articulo': self.article.pk, 'cantidad': '2'}),
            ('ENTREGA', self.bodega, None), ('AUTORIZACION_DEVOLUCION', self.supervisor, None), ('DEVOLUCION', self.bodega, None),
        ]
        ids = {}
        for tipo, actor, data in etapas:
            if data is None:
                campo, padre = ('entrega', 'ENTREGA') if tipo == 'AUTORIZACION_DEVOLUCION' else ('autorizacion', 'AUTORIZACION_ENTREGA' if tipo == 'ENTREGA' else 'AUTORIZACION_DEVOLUCION')
                data = {campo: ids[padre], 'cantidad': '1'}
            self.autenticar(actor)
            data = {**data, 'clave_idempotencia': str(uuid4())}
            url = '/api/inventario/'+RUTAS[tipo]+'/'
            r = self.client.post(url, data, format='json')
            self.assertEqual(r.status_code, 201, (tipo, r.data))
            ids[tipo] = r.data['id']
            replay = self.client.post(url, data, format='json')
            self.assertEqual(replay.status_code, 200, replay.data)
            self.assertEqual(replay.data, r.data)
            self.assertEqual(replay['Idempotency-Replayed'], 'true')

    def test_inactividad_y_sin_autenticacion(self):
        self.client.credentials()
        self.assertEqual(self.client.get('/api/inventario/entregas/').status_code, 401)
        for actor, tipo, ruta in [(self.bodega, 'ENTREGA', 'entregas'), (self.supervisor, 'AUTORIZACION_ENTREGA', 'autorizaciones-entrega'),
                                 (self.finanzas, 'VALORIZACION', 'valorizaciones')]:
            self.autenticar(actor)
            Usuario.objects.filter(pk=actor.pk).update(is_active=False)
            self.assertEqual(self.client.get('/api/inventario/'+ruta+'/').status_code, 401)
            with self.assertRaises(APIException) as error:
                materiales.operar(tipo, {}, actor)
            self.assertEqual(error.exception.status_code, 401)
            Usuario.objects.filter(pk=actor.pk).update(is_active=True)


class BodegaOperativaTests(MaterialesBase, TestCase):
    def setUp(self):
        self.preparar_materiales()

    def test_resumen_pendientes_parciales_y_sin_costos(self):
        self.recibir('10.000')
        auth = self.autorizar('5.000')
        delivered = self.entregar('2.000', auth)
        self.op('AUTORIZACION_DEVOLUCION', entrega=delivered.pk, cantidad='1.000')
        self.autenticar(self.bodega)
        url = '/api/inventario/bodega/'
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data['entregas'], 1)
        self.assertEqual(r.data['devoluciones'], 1)
        row = r.data['pendientes'][0]
        self.assertEqual(row['nombre'], self.article.nombre)
        self.assertEqual(row['obra'], self.obra.codigo)
        self.assertEqual((row['pendiente'], row['ejecutada'], row['saldo'], row['maximo']), ('3.000','2.000','8.000','3.000'))
        self.assertNotIn('costo_unitario_neto', row)
        self.assertNotIn('promedio', row)
        self.assertEqual(self.client.get(url, {'seccion':'entregas','vista':'historial'}).data['count'], 1)
        self.assertEqual(self.client.get(url, {'seccion':'inventario','buscar':'Material 019B'}).data['count'], 1)
        self.assertEqual(self.client.get(url, {'seccion':'inventario','stock':'sin_stock'}).data['count'], 0)
        confirmation = self.client.get(url, {'seccion':'confirmacion','tipo':'ENTREGA','clave':str(delivered.clave_idempotencia)})
        self.assertEqual(confirmation.data, {'id':delivered.pk})
        self.entregar('3.000', auth)
        self.assertEqual(self.client.get(url).data['entregas'], 0)
        self.assertEqual(self.client.get(url, {'seccion':'entregas','vista':'autorizaciones'}).data['count'], 1)

    def test_bloqueo_valoracion_y_permisos(self):
        self.recibir('5.000', None)
        self.autorizar('2.000')
        self.autenticar(self.bodega)
        url = '/api/inventario/bodega/'
        row = self.client.get(url).data['pendientes'][0]
        self.assertEqual(row['maximo'], '0.000')
        self.assertIsNotNone(row['bloqueo'])
        for query in ('?seccion=desconocida', '?seccion=inventario&stock=x', '?seccion=movimientos&desde=2026-02-30', '?seccion=inventario&buscar=x&buscar=y', '?seccion=inventario&precio=1'):
            self.assertEqual(self.client.get(url+query).status_code, 400)
        self.assertEqual(self.client.post(url, {}, format='json').status_code, 405)
        for actor in (self.supervisor, self.finanzas):
            self.autenticar(actor)
            self.assertEqual(self.client.get(url).status_code, 403)
