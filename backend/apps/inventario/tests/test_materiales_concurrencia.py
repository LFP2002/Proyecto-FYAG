"""Cada carrera comprueba una espera real con pg_blocking_pids, sin sleeps."""
from uuid import uuid4
from decimal import Decimal

from django.test import TransactionTestCase

from apps.finanzas.tests.test_concurrencia import CarrerasPostgreSQL
from apps.inventario import services, services_materiales as materiales
from apps.inventario.models import ArticuloInventario, MovimientoInventario, OperacionMaterial as Op
from apps.usuarios.models import Usuario
from apps.obras.exceptions import ErrorObras
from apps.obras.models import GastoObra, CierreCostosObra
from .test_materiales import MaterialesBase


class CarrerasMaterialesTests(MaterialesBase, CarrerasPostgreSQL, TransactionTestCase):
    def setUp(self):
        self.setUpTestData()
        self.preparar_materiales()
        self.recibir()

    def test_dos_despachos_remanente_unico(self):
        a = self.autorizar()
        one, two = self.race(lambda: self.entregar('6.000', a), lambda: self.entregar('6.000', a))
        self.assertIsInstance(one, Op)
        self.assertEqual(two.status_code, 409)
        self.assertEqual(self.saldo(), 4)
        self.assertEqual(GastoObra.objects.count(), 1)

    def test_dos_recepciones_devuelven_como_maximo_autorizado(self):
        e = self.entregar('4.000')
        a = self.op('AUTORIZACION_DEVOLUCION', entrega=e.pk, cantidad='3.000')
        action = lambda: self.op('DEVOLUCION', autorizacion=a.pk, cantidad='2.000')
        one, two = self.race(action, action)
        self.assertIsInstance(one, Op)
        self.assertEqual(two.status_code, 409)
        self.assertEqual(GastoObra.objects.get(pk=e.gasto_id).cantidad_devuelta, 2)
        self.assertEqual(self.saldo(), 8)

    def test_dos_autorizaciones_retorno_no_reutilizan_pendiente(self):
        e = self.entregar('4.000')
        action = lambda: self.op('AUTORIZACION_DEVOLUCION', entrega=e.pk, cantidad='3.000')
        one, two = self.race(action, action)
        self.assertIsInstance(one, Op)
        self.assertEqual(two.status_code, 409)
        self.assertEqual(self.saldo(), 6)

    def test_misma_uuid_igual_y_diferente(self):
        a = self.autorizar()
        data = {'autorizacion': a.pk, 'cantidad': '1.000', 'clave_idempotencia': str(uuid4())}
        action = lambda: materiales.operar('ENTREGA', data, self.bodega)
        one, two = self.race(action, action)
        self.assertTrue(one[1])
        self.assertFalse(two[1])
        self.assertEqual(one[0].pk, two[0].pk)
        data = {**data, 'clave_idempotencia': str(uuid4())}
        one, two = self.race(lambda: materiales.operar('ENTREGA', data, self.bodega),
            lambda: materiales.operar('ENTREGA', {**data, 'cantidad': '2.000'}, self.bodega))
        self.assertTrue(one[1])
        self.assertEqual(two.status_code, 409)
        self.assertEqual(GastoObra.objects.count(), 2)

    def test_ingreso_frente_despacho_bloquea_por_pendiente(self):
        a = self.autorizar()
        one, two = self.race(lambda: self.recibir('1.000', None), lambda: self.entregar('1.000', a))
        self.assertIsInstance(one, MovimientoInventario)
        self.assertEqual(two.detail['code'], 'valoracion_pendiente')
        self.assertEqual(self.saldo(), 11)
        self.assertFalse(GastoObra.objects.exists())

    def test_despacho_frente_ingreso_no_adquiere_raiz_inversa(self):
        a = self.autorizar()
        one, two = self.race(lambda: self.entregar('1.000', a), lambda: self.recibir('1.000', None))
        self.assertIsInstance(one, Op)
        self.assertIsInstance(two, MovimientoInventario)
        self.assertEqual(self.saldo(), 10)
        self.assertEqual(self.valor().saldo_valorado, 9)

    def test_valoracion_frente_ingreso_conserva_secuencia(self):
        m = self.recibir('2.000', None)
        one, two = self.race(lambda: self.op('VALORIZACION', ingreso=m.pk, costo_unitario_neto='200.00', referencia='R'),
            lambda: self.recibir('1.000', None))
        self.assertIsInstance(one, Op)
        self.assertIsInstance(two, MovimientoInventario)
        self.assertEqual(self.valor().promedio,  Decimal('116.67'))
        self.assertEqual(self.saldo(), 13)
        self.assertEqual(self.valor().saldo_valorado, 12)

    def test_despacho_frente_finalizacion_invalida_validacion(self):
        self.completa()
        a = self.autorizar()

        def finalizar():
            try:
                return self.finalizar()
            except ErrorObras:
                materiales.conflicto()

        one, two = self.race(lambda: self.entregar('1.000', a), finalizar)
        self.assertIsInstance(one, Op)
        self.assertEqual(two.status_code, 409)
        self.assertFalse(CierreCostosObra.objects.exists())

    def test_finalizacion_antes_despacho_preserva_cierre(self):
        self.completa()
        a = self.autorizar()
        one, two = self.race(self.finalizar, lambda: self.entregar('1.000', a))
        self.assertEqual(one.estado, 'FINALIZADA')
        self.assertEqual(two.status_code, 409)
        self.assertEqual(self.saldo(), 10)
        self.assertEqual(CierreCostosObra.objects.count(), 1)

    def test_revocacion_durante_espera_articulo(self):
        a = self.autorizar()

        def revocar():
            ArticuloInventario.objects.select_for_update().get(pk=self.article.pk)
            Usuario.objects.filter(pk=self.bodega.pk).update(sesion_version=self.bodega.sesion_version+1)

        _, two = self.race(revocar, lambda: self.entregar('1.000', a))
        self.assertEqual(two.status_code, 401)
        self.assertEqual(self.saldo(), 10)
        self.assertFalse(GastoObra.objects.exists())
