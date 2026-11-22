"""Carreras PostgreSQL: conexiones independientes y grafo de locks observado."""
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Event
from unittest.mock import patch

from django.db import connection, close_old_connections
from django.test import TransactionTestCase
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied

from apps.comercial import services_presupuestos as servicios
from apps.comercial.exceptions import EstadoIncompatible, RecursoNoEncontrado
from apps.comercial.models import Presupuesto
from apps.usuarios.models import Usuario
from . import test_presupuesto_concurrencia as carreras
from .test_presupuesto_services import ServiciosPresupuestoMixin, datos_item


class Concurrencia024(ServiciosPresupuestoMixin, TransactionTestCase):
    ejecutar_en_orden = carreras.PresupuestoConcurrenciaTests.ejecutar_en_orden

    def setUp(self):
        self.setUpTestData()
        self.supervisor = Usuario.objects.create_user(username='supervisor_024', email='s024@qa.test', rol='SUPERVISOR_OBRAS')

    def propio(self, estado='BORRADOR'):
        p = servicios.crear_presupuesto(cliente=self.cliente, descripcion='Cotización', usuario=self.supervisor)
        servicios.crear_item(p, datos_item(), self.supervisor)
        if estado != 'BORRADOR':
            p.estado = estado; p.save()
        return p

    def test_supervisor_item_antes_envio(self):
        p = self.propio(); item = p.items.get()
        uno, dos = self.ejecutar_en_orden(
            lambda: servicios.modificar_item(p, item, {'precio_unitario': Decimal('0')}, self.supervisor),
            lambda: servicios.enviar_finanzas(p, self.supervisor), p)
        self.assertEqual(uno.precio_unitario, Decimal('0'))
        self.assertEqual(dos.codigo, 'datos_invalidos')
        p.refresh_from_db(); self.assertEqual(p.estado, 'BORRADOR')

    def test_supervisor_envio_antes_item_finanzas(self):
        p = self.propio(); item = p.items.get()
        uno, dos = self.ejecutar_en_orden(
            lambda: servicios.enviar_finanzas(p, self.supervisor),
            lambda: servicios.modificar_item(p, item, {'precio_unitario': Decimal('1')}, self.usuario), p)
        self.assertEqual(uno.estado, 'PENDIENTE_FINANZAS')
        self.assertIsInstance(dos, EstadoIncompatible)
        item.refresh_from_db(); self.assertEqual(item.precio_unitario, Decimal('100.25'))

    def test_finanzas_aprobar_vs_rechazar_origen_supervisor(self):
        p = self.propio('PENDIENTE_FINANZAS')
        otro = Usuario.objects.create_user(username='af024', email='af024@qa.test', rol='ADMINISTRATIVO_FINANZAS')
        uno, dos = self.ejecutar_en_orden(lambda: servicios.aprobar_finanzas(p, self.usuario),
            lambda: servicios.rechazar_finanzas(p, otro, 'No'), p)
        self.assertEqual(uno.estado, 'APROBADO_FINANZAS'); self.assertIsInstance(dos, EstadoIncompatible)
        self.assertEqual(p.eventos.count(), 2)

    def test_dos_revisiones_supervisor_permitidas_original_intacto(self):
        p = self.propio('RECHAZADO_FINANZAS')
        eventos = list(p.eventos.values()); items = list(p.items.values())
        uno, dos = self.ejecutar_en_orden(lambda: servicios.crear_revision(p, self.supervisor),
            lambda: servicios.crear_revision(p, self.supervisor), p)
        self.assertNotEqual(uno.pk, dos.pk)
        for r in (uno, dos):
            self.assertEqual((r.estado, r.creado_por_id, r.presupuesto_origen_id), ('BORRADOR', self.supervisor.pk, p.pk))
            self.assertEqual(r.eventos.count(), 1)
        self.assertEqual(list(p.items.values()), items); self.assertEqual(list(p.eventos.values()), eventos)

    def test_revocacion_rol_sesion_password_inactivo_esperando_presupuesto(self):
        for campo in ('rol', 'sesion_version', 'password', 'is_active'):
            with self.subTest(campo=campo):
                self.supervisor.refresh_from_db()
                Usuario.objects.filter(pk=self.supervisor.pk).update(rol='SUPERVISOR_OBRAS', is_active=True)
                self.supervisor.refresh_from_db()
                p = self.propio()
                cambios = {'rol': 'GERENCIA', 'sesion_version': self.supervisor.sesion_version+1,
                           'password': '!revocada', 'is_active': False}
                def enviar():
                    try:
                        return servicios.enviar_finanzas(p, self.supervisor)
                    except (AuthenticationFailed, PermissionDenied) as error:
                        return error
                _, resultado = self.ejecutar_en_orden(
                    lambda: Usuario.objects.filter(pk=self.supervisor.pk).update(**{campo: cambios[campo]}), enviar, p)
                self.assertIsInstance(resultado, (AuthenticationFailed, PermissionDenied))
                p.refresh_from_db(); self.assertEqual(p.estado, 'BORRADOR'); self.assertEqual(p.eventos.count(), 1)

    def test_cambio_autor_persistido_durante_espera_no_se_omite(self):
        p = self.propio()
        _, resultado = self.ejecutar_en_orden(
            lambda: Presupuesto.objects.filter(pk=p.pk).update(creado_por=self.usuario),
            lambda: servicios.enviar_finanzas(p, self.supervisor), p)
        self.assertIsInstance(resultado, RecursoNoEncontrado)
        p.refresh_from_db(); self.assertEqual(p.estado, 'BORRADOR')

    def test_revocacion_conexion_real_despues_guardar_item_revierte(self):
        p = self.propio()
        guardado = Event(); continuar = Event()
        original = servicios._guardar_item
        def pausar(item):
            original(item); guardado.set()
            if not continuar.wait(10):
                raise AssertionError('No se liberó escritura')
        def escribir():
            close_old_connections()
            try:
                try:
                    servicios.crear_item(p, datos_item(orden=2), self.supervisor)
                except AuthenticationFailed as error:
                    return error
            finally:
                connection.close()
        with patch.object(servicios, '_guardar_item', side_effect=pausar), ThreadPoolExecutor(max_workers=1) as pool:
            futuro = pool.submit(escribir)
            try:
                self.assertTrue(guardado.wait(10))
                Usuario.objects.filter(pk=self.supervisor.pk).update(sesion_version=self.supervisor.sesion_version+1)
            finally:
                continuar.set()
            self.assertIsInstance(futuro.result(timeout=15), AuthenticationFailed)
        self.assertEqual(p.items.count(), 1); self.assertEqual(p.eventos.count(), 1)
