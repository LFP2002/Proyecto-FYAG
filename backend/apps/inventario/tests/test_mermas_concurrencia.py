from decimal import Decimal

from django.db import connection
from django.test import TransactionTestCase
from django.test.utils import CaptureQueriesContext

from apps.finanzas.tests.test_concurrencia import CarrerasPostgreSQL
from apps.inventario import services_mermas as services
from apps.inventario.models import Merma, OperacionMaterial as Op, MovimientoInventario as Movimiento, ArticuloInventario
from apps.obras.models import CierreCostosObra
from apps.usuarios.models import Usuario
from .test_mermas import MermasBase


class CarrerasMermasTests(MermasBase, CarrerasPostgreSQL, TransactionTestCase):
    def setUp(self):
        self.setUpTestData()
        self.preparar_mermas()

    def test_dos_aprobaciones_mb_una_baja(self):
        self.recibir()
        m = self.informar()
        one, two = self.race(lambda: self.resolver(m), lambda: self.resolver(m))
        self.assertEqual(one.estado, 'APROBADA')
        self.assertEqual(two.detail['code'], 'merma_ya_decidida')
        self.assertEqual(Movimiento.objects.filter(operacion__merma_bodega=m).count(), 1)
        self.assertEqual(self.saldo(), 8)

    def test_dos_mb_mismo_corte_solo_primera(self):
        self.recibir()
        a, b = self.informar(), self.informar()
        one, two = self.race(lambda: self.resolver(a), lambda: self.resolver(b))
        self.assertEqual(one.estado, 'APROBADA')
        self.assertEqual(two.detail['code'], 'corte_desactualizado')
        self.assertEqual(self.saldo(), 8)

    def test_ingreso_antes_mb_corte_obsoleto(self):
        self.recibir()
        m = self.informar()
        _, two = self.race(lambda: self.recibir('1.000', None), lambda: self.resolver(m))
        self.assertEqual(two.detail['code'], 'corte_desactualizado')
        self.assertEqual(self.saldo(), 11)

    def test_mb_antes_ingreso_no_deadlock(self):
        self.recibir()
        m = self.informar()
        one, two = self.race(lambda: self.resolver(m), lambda: self.recibir('1.000', None))
        self.assertEqual(one.estado, 'APROBADA')
        self.assertEqual(two.tipo, 'INGRESO')
        self.assertEqual(self.saldo(), 9)

    def test_despacho_antes_mb_corte_obsoleto(self):
        self.recibir()
        m, a = self.informar(), self.autorizar()
        _, two = self.race(lambda: self.entregar('1.000', a), lambda: self.resolver(m))
        self.assertEqual(two.detail['code'], 'corte_desactualizado')
        self.assertEqual(self.saldo(), 9)

    def test_mb_antes_despacho_no_inversion_raices(self):
        self.recibir()
        m, a = self.informar(), self.autorizar()
        one, two = self.race(lambda: self.resolver(m), lambda: self.entregar('1.000', a))
        self.assertEqual(one.estado, 'APROBADA')
        self.assertEqual(two.tipo, 'ENTREGA')
        self.assertEqual(self.saldo(), 7)

    def test_valoracion_antes_mb_precio_oficial(self):
        ingreso = self.recibir(precio=None)
        m = self.informar()
        _, two = self.race(lambda: self.op('VALORIZACION', ingreso=ingreso.pk, costo_unitario_neto='55.55', referencia='QA'), lambda: self.resolver(m))
        self.assertEqual(two.operacion.costo_unitario_neto, Decimal('55.55'))

    def test_mb_rechazo_vs_valoracion_sin_cambio_fisico(self):
        ingreso = self.recibir(precio=None)
        m = self.informar()
        one, two = self.race(lambda: self.resolver(m, 'RECHAZAR'),
            lambda: self.op('VALORIZACION', ingreso=ingreso.pk, costo_unitario_neto='50.00', referencia='QA'))
        self.assertEqual(one.estado, 'RECHAZADA')
        self.assertEqual(two.tipo, 'VALORIZACION')
        self.assertEqual(self.saldo(), 10)

    def test_mo_antes_recepcion_antigua_no_recibe_perdida(self):
        self.preparar_entrega()
        a = self.op('AUTORIZACION_DEVOLUCION', entrega=self.entrega.pk, cantidad='6.000')
        m = self.informar('OBRA')
        _, two = self.race(lambda: self.resolver(m), lambda: self.op('DEVOLUCION', autorizacion=a.pk, cantidad='5.000'))
        self.assertEqual(two.detail['code'], 'remanente_insuficiente')
        self.assertEqual(self.saldo(), 4)

    def test_recepcion_antes_mo_no_clasifica_ya_recibido(self):
        self.preparar_entrega()
        a = self.op('AUTORIZACION_DEVOLUCION', entrega=self.entrega.pk, cantidad='6.000')
        m = self.informar('OBRA')
        _, two = self.race(lambda: self.op('DEVOLUCION', autorizacion=a.pk, cantidad='5.000'), lambda: self.resolver(m))
        self.assertEqual(two.detail['code'], 'remanente_insuficiente')
        self.assertEqual(self.saldo(), 9)

    def test_mo_antes_nueva_autorizacion_descuenta_perdida(self):
        self.preparar_entrega()
        m = self.informar('OBRA')
        _, two = self.race(lambda: self.resolver(m), lambda: self.op('AUTORIZACION_DEVOLUCION', entrega=self.entrega.pk, cantidad='5.000'))
        self.assertEqual(two.detail['code'], 'remanente_insuficiente')

    def test_autorizacion_antes_mo_no_reserva_clasificacion(self):
        self.preparar_entrega()
        m = self.informar('OBRA')
        one, two = self.race(lambda: self.op('AUTORIZACION_DEVOLUCION', entrega=self.entrega.pk, cantidad='6.000'), lambda: self.resolver(m))
        self.assertEqual((one.cantidad, two.estado), (6, 'APROBADA'))
        self.assertEqual(self.saldo(), 4)

    def test_dos_mo_misma_entrega_disponibilidad_serializada(self):
        self.preparar_entrega()
        a, b = self.informar('OBRA', cantidad='4.000'), self.informar('OBRA', cantidad='4.000')
        _, two = self.race(lambda: self.resolver(a), lambda: self.resolver(b))
        self.assertEqual(two.detail['code'], 'remanente_insuficiente')
        self.assertEqual(services.aprobada(self.entrega.pk), 4)

    def test_dos_aprobaciones_mo_misma_merma(self):
        self.preparar_entrega()
        m = self.informar('OBRA')
        _, two = self.race(lambda: self.resolver(m), lambda: self.resolver(m))
        self.assertEqual(two.detail['code'], 'merma_ya_decidida')
        self.assertEqual(m.eventos.count(), 2)

    def test_finalizacion_antes_mo_preserva_pendiente(self):
        self.preparar_entrega()
        self.acreditar()
        self.declarar(materiales_estado='CON_REGISTROS')
        self.validar()
        m = self.informar('OBRA')
        confirmacion = self.confirmacion_cierre()
        _, two = self.race(lambda: self.finalizar(confirmacion), lambda: self.resolver(m))
        self.assertEqual(two.status_code, 409)
        m.refresh_from_db()
        self.assertEqual(m.estado, 'PENDIENTE')
        self.assertTrue(CierreCostosObra.objects.filter(obra=self.obra).exists())

    def test_mo_antes_finalizacion_no_invalida_costos(self):
        self.preparar_entrega()
        m = self.informar('OBRA')
        # La entrega invalida; completar revisión vigente antes de finalizar.
        self.acreditar()
        self.declarar(materiales_estado='CON_REGISTROS')
        self.validar()
        version = self.control().version_actual
        confirmacion = self.confirmacion_cierre()
        one, two = self.race(lambda: self.resolver(m), lambda: self.finalizar(confirmacion))
        self.assertEqual((one.estado, two.estado), ('APROBADA', 'FINALIZADA'))
        self.assertEqual(self.control().version_actual, version)

    def test_desasignacion_durante_espera_mo(self):
        self.preparar_entrega()
        m = self.informar('OBRA')
        _, two = self.race(self.desasignar, lambda: self.resolver(m))
        self.assertEqual(two.status_code, 409)

    def test_revocacion_sesion_af_durante_espera_articulo(self):
        self.recibir()
        m = self.informar()
        def revocar():
            ArticuloInventario.objects.select_for_update().get(pk=self.article.pk)
            Usuario.objects.filter(pk=self.finanzas.pk).update(sesion_version=self.finanzas.sesion_version+1)
        _, two = self.race(revocar, lambda: self.resolver(m))
        self.assertEqual(two.status_code, 401)
        self.assertEqual(self.saldo(), 10)

    def test_revocacion_rol_supervisor_durante_espera_raiz(self):
        self.preparar_entrega()
        m = self.informar('OBRA')
        def revocar():
            from apps.obras.services import _obra_bloqueada
            _obra_bloqueada(self.obra.pk)
            Usuario.objects.filter(pk=self.supervisor.pk).update(rol='BODEGUERO')
        _, two = self.race(revocar, lambda: self.resolver(m))
        self.assertEqual(two.status_code, 403)

    def test_cuenta_af_inactiva_durante_espera(self):
        self.recibir()
        m = self.informar()
        def revocar():
            ArticuloInventario.objects.select_for_update().get(pk=self.article.pk)
            Usuario.objects.filter(pk=self.finanzas.pk).update(is_active=False)
        _, two = self.race(revocar, lambda: self.resolver(m))
        self.assertEqual(two.status_code, 401)
        self.assertEqual(self.saldo(), 10)

    def test_desasignacion_durante_creacion_mo(self):
        self.preparar_entrega()
        _, two = self.race(self.desasignar, lambda: self.informar('OBRA'))
        self.assertEqual(two.status_code, 404)
        self.assertFalse(Merma.objects.filter(entrega=self.entrega).exists())

    def test_creacion_uuid_igual_payload_igual(self):
        data = self.entrada_merma()
        action = lambda: services.crear('BODEGA', data, self.bodega)
        one, two = self.race(action, action)
        self.assertEqual((one[1], two[1]), (True, False))
        self.assertEqual(one[0].pk, two[0].pk)

    def test_creacion_uuid_igual_payload_distinto(self):
        data = self.entrada_merma()
        _, two = self.race(lambda: services.crear('BODEGA', data, self.bodega), lambda: services.crear('BODEGA', {**data, 'cantidad': '1.000'}, self.bodega))
        self.assertEqual(two.detail['code'], 'idempotencia_conflictiva')

    def test_decision_uuid_igual_payload_igual(self):
        self.recibir()
        m = self.informar()
        data = self.entrada_decision_merma()
        action = lambda: services.decidir('BODEGA', m.pk, data, self.finanzas)
        one, two = self.race(action, action)
        self.assertEqual((one[1], two[1]), (True, False))
        self.assertEqual(one[0].operacion_id, two[0].operacion_id)
        self.assertEqual(self.saldo(), 8)

    def test_decision_uuid_igual_payload_distinto(self):
        self.recibir()
        m = self.informar()
        data = self.entrada_decision_merma()
        _, two = self.race(lambda: services.decidir('BODEGA', m.pk, data, self.finanzas),
            lambda: services.decidir('BODEGA', m.pk, {**data, 'decision': 'RECHAZAR'}, self.finanzas))
        self.assertEqual(two.detail['code'], 'idempotencia_conflictiva')

    def test_orden_locks_mb_asesores_antes_recursos(self):
        self.recibir()
        m = self.informar()
        with CaptureQueriesContext(connection) as queries:
            self.resolver(m)
        sql = [q['sql'] for q in queries]
        asesores = [i for i, q in enumerate(sql) if 'pg_advisory_xact_lock' in q]
        articulo = next(i for i, q in enumerate(sql) if 'inventario_articuloinventario' in q and 'FOR UPDATE' in q)
        self.assertEqual(len(asesores), 2)
        self.assertLess(max(asesores), articulo)
        self.assertFalse(any('obras_obra' in q and 'FOR UPDATE' in q for q in sql))
