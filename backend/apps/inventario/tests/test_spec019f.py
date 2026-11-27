from decimal import Decimal
from uuid import uuid4

from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase
from rest_framework.exceptions import APIException

from apps.comercial.models import PresupuestoItem
from apps.finanzas.tests.test_concurrencia import CarrerasPostgreSQL
from apps.inventario.models import MovimientoInventario, OperacionMaterial as Op
from apps.obras import services, services_finalizacion as cierre
from apps.obras.exceptions import EstadoIncompatible
from apps.obras.models import CierreCostosObra, GastoObra, Obra
from apps.usuarios.models import Usuario

from .test_materiales import MaterialesBase


class PrevisionBase(MaterialesBase):
    def linea(self, cantidad='5.000', *, vinculada=True, unidad='kg', model=PresupuestoItem):
        return model.objects.create(presupuesto_id=self.obra.presupuesto_id,
            articulo_id=self.article.pk if vinculada else None,
            codigo_articulo=self.article.codigo if vinculada else '', descripcion=self.article.nombre,
            unidad=unidad, precio_unitario=Decimal('930.00'), cantidad=Decimal(cantidad),
            orden=model.objects.filter(presupuesto_id=self.obra.presupuesto_id).count() + 1)

    def planificar(self):
        Obra.objects.filter(pk=self.obra.pk).update(estado='PLANIFICADA', iniciado_en=None)
        self.obra.refresh_from_db()

    def inicio(self):
        return services.iniciar_obra(self.obra.pk, self.supervisor, 'Inicio de obra 019F')

    def ruta_obra(self, suffix):
        return f'/api/obras/{self.obra.pk}/{suffix}/'

    def preflight(self):
        response = self.client.get(self.ruta_obra('requisitos-cierre'))
        self.assertEqual(response.status_code, 200, response.data)
        return response.data


class Integracion019FTests(PrevisionBase, TestCase):
    def setUp(self):
        self.preparar_materiales()

    def test_prevision_no_reserva_inicia_sin_stock_y_reconcilia_parciales(self):
        self.planificar()
        primera, segunda = self.linea(), self.linea('1.000')
        self.linea(vinculada=False)
        url = self.ruta_obra('conciliacion-materiales')
        antes = self.client.get(url).data['results']
        self.assertEqual([r['estado'] for r in antes], ['SIN_AUTORIZACION'] * 2)
        self.assertTrue(all('precio_unitario' not in r for r in antes))
        self.inicio()
        self.assertEqual(self.saldo(), 0)
        self.assertFalse(MovimientoInventario.objects.exists())
        self.assertFalse(GastoObra.objects.exists())
        with self.assertRaises(EstadoIncompatible):
            self.inicio()
        ops = Op.objects.filter(tipo='AUTORIZACION_ENTREGA')
        self.assertCountEqual(ops.values_list('item_presupuesto_id', 'actor_id'),
                              [(i.pk, self.supervisor.pk) for i in (primera, segunda)])
        a = ops.get(item_presupuesto=primera)
        self.recibir('2.000')
        e = self.entregar('2.000', a)
        self.recibir('3.000', '200.00')
        self.entregar('3.000', a)
        self.devolver(e, '1.000')
        fila = self.client.get(url).data['results'][0]
        self.assertEqual((fila['despachado'], fila['devuelto'], fila['neto_imputado'], fila['estado']),
                         ('5.000', '1.000', '4.000', 'COMPLETADO'))
        self.assertEqual(GastoObra.objects.count(), 2)

    def test_inicio_inactivo_o_unidad_incompatible_revierte_todo(self):
        self.planificar()
        self.linea()
        item = self.linea(unidad='metro')
        for activo, mensaje in [(False, 'inactivo'), (True, 'unidad incompatible')]:
            type(self.article).objects.filter(pk=self.article.pk).update(activo=activo)
            respuesta = self.client.post(self.ruta_obra('iniciar'), {'motivo': 'Inicio'}, format='json')
            self.assertEqual(respuesta.status_code, 400, respuesta.data)
            self.assertIn(mensaje, str(respuesta.data))
            self.assertIn(item.codigo_articulo, str(respuesta.data))
            self.obra.refresh_from_db()
            self.assertEqual(self.obra.estado, 'PLANIFICADA')
            self.assertFalse(Op.objects.exists())

    def test_sql_rechaza_asignar_origen_con_cantidad_distinta_y_duplicados(self):
        self.planificar()
        item = self.linea()
        self.inicio()
        original = Op.objects.get(item_presupuesto=item)
        for q in (Decimal('2.000'), original.cantidad):
            values = {f.attname: getattr(original, f.attname) for f in Op._meta.concrete_fields
                      if not f.primary_key}
            values.update(cantidad=q, clave_idempotencia=uuid4())
            with self.assertRaises(IntegrityError), transaction.atomic():
                Op.objects.create(**values)

    def test_devolucion_cierre_confirmacion_obsoleta_y_validacion_automatica(self):
        self.recibir()
        a = self.autorizar()
        entrega = self.entregar('2.000', a)
        d = self.op('AUTORIZACION_DEVOLUCION', entrega=entrega.pk, cantidad='1.000')
        self.acreditar()
        revisada = self.validar()
        self.assertEqual(revisada['materiales_estado'], 'CON_REGISTROS')
        self.assertEqual(revisada['otros_estado'], 'NO_APLICA')
        self.assertIn('Justificación automática', revisada['otros_justificacion'])
        self.assertEqual(self.preflight()['devoluciones'][0]['cantidad'], '1.000')
        post = lambda **data: self.client.post(self.finalizar_url, {**self.revision('Cierre'), **data}, format='json')
        self.assertEqual(post().data['code'], 'devolucion_pendiente')
        self.op('DEVOLUCION', autorizacion=d.pk, cantidad='1.000')
        self.assertFalse(self.control().costos_validados)
        self.validar()
        previa = self.preflight()['confirmacion_remanente']
        self.assertEqual(post().data['code'], 'confirmacion_remanente_requerida')
        self.entregar('1.000', a)
        self.validar()
        self.assertEqual(post(confirmacion_remanente=previa).data['code'], 'confirmacion_remanente_requerida')
        nueva = self.preflight()['confirmacion_remanente']
        self.assertNotEqual(previa, nueva)
        self.assertEqual(post(confirmacion_remanente=nueva).status_code, 200)
        self.assertEqual(CierreCostosObra.objects.count(), 1)
        with self.assertRaises(APIException):
            self.entregar('1.000', a)

    def test_obra_historica_y_permisos_seis_roles(self):
        item = self.linea()
        a = self.autorizar()
        self.obra.refresh_from_db()
        for rol in Usuario.Rol.values:
            actor = Usuario.objects.create_user(username='u-'+rol, email=f'{rol}@example.test', rol=rol)
            self.client.force_authenticate(actor)
            preflight = self.client.get(self.ruta_obra('requisitos-cierre'))
            self.assertEqual(preflight.status_code, 200 if rol == 'SUPERVISOR_OBRAS' else 403)
            previa = self.client.get(self.ruta_obra('conciliacion-materiales'))
            self.assertEqual(previa.status_code, 200 if rol in {'GERENCIA','SUPERVISOR_OBRAS'} else 403)
            if previa.status_code == 200:
                self.assertEqual(previa.data['results'][0]['id'], item.pk)
                self.assertEqual(previa.data['results'][0]['estado'], 'SIN_AUTORIZACION')
        self.assertEqual(list(Op.objects.values_list('pk', 'item_presupuesto_id')), [(a.pk, None)])

    def test_bodega_muestra_origen_y_retiro_terminal_sin_costos(self):
        self.planificar()
        self.linea()
        self.inicio()
        self.acreditar()
        self.validar()
        confirmacion = self.preflight()['confirmacion_remanente']
        self.autenticar(self.bodega)
        ruta = '/api/inventario/bodega/'
        filtros = {'seccion': 'entregas', 'vista': 'pendientes'}
        r = self.client.get(ruta, filtros)
        self.assertEqual(r.status_code, 200, r.data)
        fila = r.data['results'][0]
        self.assertEqual(fila['origen'], 'PRESUPUESTO')
        self.assertEqual(fila['bloqueo'], 'Sin existencias')
        self.assertFalse({'item_presupuesto', 'costo_unitario_neto', 'promedio'} & set(fila))
        self.finalizar(confirmacion)
        self.assertEqual(self.client.get(ruta, filtros).data['count'], 0)
        fila = self.client.get(ruta, {**filtros, 'vista': 'autorizaciones'}).data['results'][0]
        self.assertTrue(fila['inhabilitada'])
        self.assertEqual(fila['pendiente'], '5.000')
        self.assertEqual(fila['maximo'], '0.000')


class Carreras019FTests(PrevisionBase, CarrerasPostgreSQL, TransactionTestCase):
    def setUp(self):
        self.setUpTestData()
        self.preparar_materiales()

    def _revocacion_en_espera(self, ruta, datos, cambios, esperado=401):
        def revocar():
            services._obra_bloqueada(self.obra.pk)
            Usuario.objects.filter(pk=self.supervisor.pk).update(**cambios)

        _, respuesta = self.race(revocar, lambda: self.client.post(self.ruta_obra(ruta), datos, format='json'))
        self.assertEqual(respuesta.status_code, esperado, respuesta.data)

    def test_inicio_rechaza_sesion_revocada_durante_lock(self):
        self.planificar()
        self.linea()
        self._revocacion_en_espera('iniciar', {'motivo':'Inicio'}, {'sesion_version': self.supervisor.sesion_version + 1})
        self.obra.refresh_from_db()
        self.assertEqual(self.obra.estado, 'PLANIFICADA')
        self.assertFalse(Op.objects.exists())

    def test_inicio_revocado_durante_lock_del_articulo_revierte_transicion(self):
        self.planificar()
        self.linea()

        def revocar():
            type(self.article).objects.select_for_update().get(pk=self.article.pk)
            Usuario.objects.filter(pk=self.supervisor.pk).update(sesion_version=self.supervisor.sesion_version + 1)

        _, respuesta = self.race(revocar, lambda: self.client.post(self.ruta_obra('iniciar'), {'motivo':'Inicio'}, format='json'))
        self.assertEqual(respuesta.status_code, 401, respuesta.data)
        self.obra.refresh_from_db()
        self.assertEqual(self.obra.estado, 'PLANIFICADA')
        self.assertFalse(Op.objects.exists())

    def test_validacion_rechaza_credencial_cambiada_durante_lock(self):
        self.acreditar()
        from django.contrib.auth.hashers import make_password
        self._revocacion_en_espera('costos/validar', self.revision('Validar'), {'password': make_password(None)})
        self.assertFalse(self.control().costos_validados)

    def test_finalizacion_rechaza_rol_revocado_durante_lock(self):
        self.acreditar()
        self.validar()
        self._revocacion_en_espera('finalizar', self.revision('Cierre'), {'rol':'GERENCIA'}, esperado=403)
        self.assertFalse(CierreCostosObra.objects.exists())

    def test_validacion_concurrente_no_acredita_costos_distintos(self):
        self.acreditar()
        revisada = self.preflight()['version_actual']
        datos = {'motivo':'Validar', 'version_costos_esperada': revisada}
        _, respuesta = self.race(self.crear_ok, lambda: self.client.post(self.validar_url, datos, format='json'))
        self.assertEqual(respuesta.status_code, 409)
        self.assertEqual(respuesta.data['code'], 'version_costos_obsoleta')
        self.assertFalse(self.control().costos_validados)
        self.assertEqual(self.client.post(self.validar_url, self.revision('Confirmación nueva'), format='json').status_code, 200)

    def test_cierre_concurrente_no_acepta_una_version_nueva_ya_validada(self):
        self.acreditar()
        self.validar()
        datos = self.revision('Cierre revisado')

        def modificar_y_validar():
            self.crear_ok()
            return self.validar()

        nueva, respuesta = self.race(modificar_y_validar,
            lambda: self.client.post(self.finalizar_url, datos, format='json'))
        self.assertTrue(nueva['costos_validados'])
        self.assertEqual(respuesta.status_code, 409)
        self.assertEqual(respuesta.data['code'], 'version_costos_obsoleta')
        self.assertFalse(CierreCostosObra.objects.exists())
        self.assertEqual(self.client.post(self.finalizar_url, self.revision('Confirmación nueva'), format='json').status_code, 200)

    def test_doble_inicio_serializa_en_postgresql(self):
        self.planificar()
        item = self.linea()

        def iniciar():
            try:
                return self.inicio()
            except EstadoIncompatible:
                from apps.inventario.services_materiales import conflicto
                conflicto()

        uno, dos = self.race(iniciar, iniciar)
        self.assertEqual(uno.estado, 'EN_PROCESO')
        self.assertEqual(dos.status_code, 409)
        self.assertEqual(Op.objects.filter(item_presupuesto=item).count(), 1)

    def test_recepcion_gana_a_cierre_e_invalida_costos(self):
        self.recibir()
        e = self.entregar()
        d = self.op('AUTORIZACION_DEVOLUCION', entrega=e.pk, cantidad='1.000')
        self.acreditar()
        self.validar()
        preflight = self.preflight()
        previo = preflight['confirmacion_remanente']

        def finalizar():
            try:
                return cierre.finalizar_obra(self.obra.pk, {'motivo': 'Cierre', 'confirmacion_remanente': previo,
                    'version_costos_esperada': preflight['version_actual']}, self.supervisor)
            except EstadoIncompatible as exc:
                from apps.inventario.services_materiales import conflicto
                conflicto(exc.codigo)

        uno, dos = self.race(lambda: self.op('DEVOLUCION', autorizacion=d.pk, cantidad='1.000'), finalizar)
        self.assertEqual(uno.tipo, 'DEVOLUCION')
        self.assertEqual(dos.detail['code'], 'version_costos_obsoleta')
        self.assertFalse(CierreCostosObra.objects.exists())


class Migracion019FTests(PrevisionBase, TransactionTestCase):
    def test_upgrade_preserva_autorizacion_y_linea_historicas(self):
        self.setUpTestData()
        self.preparar_materiales()
        item = self.linea()
        a = self.autorizar()
        destino = [('inventario', '0009_origen_material_presupuestado')]
        previo = [('inventario', '0008_integridad_mermas'), ('comercial', '0007_presupuestoitem_articulo')]
        self.addCleanup(lambda: MigrationExecutor(connection).migrate(destino))
        executor = MigrationExecutor(connection)
        executor.migrate(previo)
        Modelo = executor.loader.project_state(previo).apps.get_model('inventario', 'OperacionMaterial')
        antes = Modelo.objects.values().get(pk=a.pk)
        MigrationExecutor(connection).migrate(destino)
        despues = Op.objects.values().get(pk=a.pk)
        self.assertIsNone(despues.pop('item_presupuesto_id'))
        self.assertEqual(despues, antes)
        self.assertEqual(PresupuestoItem.objects.get(pk=item.pk).articulo_id, self.article.pk)
