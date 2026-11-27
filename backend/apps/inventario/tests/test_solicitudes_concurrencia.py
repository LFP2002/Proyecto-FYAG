from concurrent.futures import ThreadPoolExecutor
from threading import Event

from django.db import connection, transaction, close_old_connections
from django.test import TransactionTestCase
from django.test.utils import CaptureQueriesContext

from apps.finanzas.tests.test_concurrencia import CarrerasPostgreSQL
from apps.inventario import services_solicitudes as services
from apps.inventario.models import OperacionMaterial as Op, SolicitudMaterialObra as Solicitud, ArticuloInventario
from apps.obras.models import GastoObra, CierreCostosObra
from apps.usuarios.models import Usuario
from .test_solicitudes import SolicitudesBase


class CarrerasSolicitudesTests(SolicitudesBase, CarrerasPostgreSQL, TransactionTestCase):
    def setUp(self):
        self.setUpTestData()
        self.preparar_solicitudes()

    def test_dos_aprobaciones_distintas_una_autorizacion(self):
        s = self.solicitar()
        one, two = self.race(lambda: self.decidir(s), lambda: self.decidir(s))
        self.assertEqual(one.estado, 'APROBADA')
        self.assertEqual(two.detail['code'], 'solicitud_ya_decidida')
        self.assertEqual(Op.objects.filter(solicitud_material=s).count(), 1)

    def test_aprobacion_y_rechazo_una_decision(self):
        s = self.solicitar()
        one, two = self.race(lambda: self.decidir(s), lambda: self.decidir(s, 'RECHAZAR'))
        self.assertEqual(one.estado, 'APROBADA')
        self.assertEqual(two.status_code, 409)
        self.assertEqual(s.eventos.exclude(tipo='CREACION').count(), 1)

    def test_rechazo_y_aprobacion_sin_autorizacion(self):
        s = self.solicitar()
        one, two = self.race(lambda: self.decidir(s, 'RECHAZAR'), lambda: self.decidir(s))
        self.assertEqual(one.estado, 'RECHAZADA')
        self.assertEqual(two.status_code, 409)
        self.assertFalse(Op.objects.filter(solicitud_material=s).exists())

    def test_creacion_uuid_igual_carga_igual(self):
        data = self.entrada_solicitud()
        action = lambda: services.crear_solicitud(data, self.solicitante)
        one, two = self.race(action, action)
        self.assertTrue(one[1])
        self.assertFalse(two[1])
        self.assertEqual(one[0].pk, two[0].pk)
        self.assertEqual(Solicitud.objects.filter(clave_idempotencia=data['clave_idempotencia']).count(), 1)

    def test_creacion_uuid_igual_carga_distinta(self):
        data = self.entrada_solicitud()
        one, two = self.race(lambda: services.crear_solicitud(data, self.solicitante),
            lambda: services.crear_solicitud({**data, 'cantidad': '2.000'}, self.solicitante))
        self.assertTrue(one[1])
        self.assertEqual(two.detail['code'], 'idempotencia_conflictiva')

    def test_decision_uuid_igual_carga_igual(self):
        s = self.solicitar()
        data = self.entrada_decision(s)
        action = lambda: services.decidir_solicitud(s.pk, data, self.supervisor)
        one, two = self.race(action, action)
        self.assertTrue(one[1])
        self.assertFalse(two[1])
        self.assertEqual(one[0].autorizacion_id, two[0].autorizacion_id)
        self.assertEqual(Op.objects.filter(solicitud_material=s).count(), 1)

    def test_decision_uuid_igual_carga_distinta(self):
        s = self.solicitar()
        data = self.entrada_decision(s)
        one, two = self.race(lambda: services.decidir_solicitud(s.pk, data, self.supervisor),
            lambda: services.decidir_solicitud(s.pk, {**data, 'cantidad_aprobada': '2.000'}, self.supervisor))
        self.assertTrue(one[1])
        self.assertEqual(two.detail['code'], 'idempotencia_conflictiva')

    def test_desasignacion_antes_aprobacion(self):
        s = self.solicitar()
        _, two = self.race(self.desasignar, lambda: self.decidir(s))
        self.assertEqual(two.status_code, 409)
        self.assertFalse(Op.objects.filter(solicitud_material=s).exists())

    def test_aprobacion_antes_desasignacion_conserva_autor_real(self):
        s = self.solicitar()
        one, two = self.race(lambda: self.decidir(s), self.desasignar)
        self.assertEqual(one.estado, 'APROBADA')
        self.assertFalse(two.activo)
        s.refresh_from_db()
        self.assertEqual(s.solicitante_id, self.solicitante.pk)
        self.assertEqual(s.autorizacion.actor_id, self.supervisor.pk)

    def test_finalizacion_antes_decision_preserva_pendiente(self):
        self.completa()
        s = self.solicitar()
        _, two = self.race(self.finalizar, lambda: self.decidir(s))
        self.assertEqual(two.status_code, 409)
        s.refresh_from_db()
        self.assertEqual(s.estado, 'PENDIENTE')
        self.assertTrue(CierreCostosObra.objects.filter(obra=self.obra).exists())
        self.assertFalse(Op.objects.filter(solicitud_material=s).exists())

    def test_aprobacion_no_invalida_costos_pero_exige_confirmar_nuevo_remanente(self):
        self.completa()
        s = self.solicitar()
        version = self.control().version_actual
        def finalizar():
            from apps.obras.exceptions import CierreMaterialesPendientes
            from apps.inventario.services_materiales import conflicto
            try:
                return self.finalizar()
            except CierreMaterialesPendientes as exc:
                conflicto(exc.codigo)

        one, two = self.race(lambda: self.decidir(s), finalizar)
        self.assertEqual(one.estado, 'APROBADA')
        self.assertEqual(two.detail['code'], 'confirmacion_remanente_requerida')
        self.assertEqual(self.control().version_actual, version)
        self.assertEqual(self.finalizar(self.confirmacion_cierre()).estado, 'FINALIZADA')
        foto = list(CierreCostosObra.objects.filter(obra=self.obra).values())
        from rest_framework.exceptions import APIException
        with self.assertRaises(APIException):
            self.entregar('1.000', one.autorizacion)
        self.assertEqual(list(CierreCostosObra.objects.filter(obra=self.obra).values()), foto)

    def test_revocacion_supervisor_durante_espera_raiz(self):
        s = self.solicitar()

        def revocar():
            from apps.obras.services import _obra_bloqueada
            _obra_bloqueada(self.obra.pk)
            Usuario.objects.filter(pk=self.supervisor.pk).update(sesion_version=self.supervisor.sesion_version+1)

        _, two = self.race(revocar, lambda: self.decidir(s))
        self.assertEqual(two.status_code, 401)
        self.assertFalse(Op.objects.filter(solicitud_material=s).exists())

    def test_revocacion_tecnico_durante_espera_articulo(self):
        def revocar():
            ArticuloInventario.objects.select_for_update().get(pk=self.article.pk)
            Usuario.objects.filter(pk=self.solicitante.pk).update(sesion_version=self.solicitante.sesion_version+1)

        _, two = self.race(revocar, self.solicitar)
        self.assertEqual(two.status_code, 401)
        self.assertFalse(Solicitud.objects.filter(obra=self.obra).exists())

    def test_claves_asesoras_se_adquieren_antes_de_raices(self):
        s = self.solicitar()
        with CaptureQueriesContext(connection) as queries:
            self.decidir(s)
        sql = [q['sql'] for q in queries]
        asesores = [i for i, q in enumerate(sql) if 'pg_advisory_xact_lock' in q]
        raiz = next(i for i, q in enumerate(sql) if 'comercial_presupuesto' in q and 'FOR UPDATE' in q)
        self.assertEqual(len(asesores), 2)
        self.assertLess(max(asesores), raiz)

    def test_autorizacion_invisible_hasta_commit_y_despacho_posterior(self):
        self.recibir()
        s = self.solicitar()
        ready, release = Event(), Event()

        def aprobar():
            close_old_connections()
            try:
                with transaction.atomic():
                    r = self.decidir(s)
                    ready.set()
                    if not release.wait(10):
                        raise AssertionError('No se liberó la aprobación')
                return r.autorizacion_id
            finally:
                connection.close()

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(aprobar)
            try:
                self.assertTrue(ready.wait(10))
                self.assertFalse(Op.objects.filter(solicitud_material=s).exists())
            finally:
                release.set()
            autorizacion_id = future.result(timeout=15)
        autorizado = Op.objects.get(pk=autorizacion_id)
        self.entregar('1.000', autorizado)
        self.assertEqual(GastoObra.objects.filter(obra=self.obra, origen='BODEGA_019B').count(), 1)
