from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth.hashers import make_password
from django.test import TransactionTestCase, override_settings

from apps.finanzas import services_documentos as documentos, services_egresos as egresos, services_pagos as pagos
from apps.finanzas.models import CierreSinCobro, DocumentoCobro, Egreso, EgresoEvento, FinanzasEvento, PagoDocumento
from apps.usuarios.bloqueos import registrar_verificacion
from apps.usuarios.models import EstadoAcceso, Usuario
from apps.usuarios.politica_bloqueos import Senal
from .base import FinanzasBase
from .test_concurrencia import CarrerasPostgreSQL
from .test_egresos import EgresosBase, payload
from .test_pagos import PagosBase


class Espera:
    def cambio(self, **fields):
        # Escribir solo el campo comprobado: un bump en todas las carreras
        # ocultaría un validador que solo cotejara sesion_version.
        Usuario.objects.filter(pk=self.finanzas.pk).update(**fields)

    def denegada(self, recurso, operacion, status=401, *, cambiar):
        _, resultado = self.race(
            lambda: type(recurso).objects.select_for_update().get(pk=recurso.pk),
            operacion, tras_espera=cambiar,
        )
        self.assertEqual(getattr(resultado, 'status_code', None), status)


class DocumentosAUD012(Espera, FinanzasBase, CarrerasPostgreSQL, TransactionTestCase):
    def test_registro_denegado_tras_revocacion_en_presupuesto(self):
        self.denegada(self.presupuesto, lambda: documentos.registrar_documento(self.payload(), self.finanzas),
                      cambiar=lambda: self.cambio(sesion_version=self.finanzas.sesion_version + 1))
        self.assertFalse(DocumentoCobro.objects.exists())
        self.assertFalse(FinanzasEvento.objects.exists())

    def test_reversion_denegada_tras_cambio_de_hash_en_documento(self):
        doc = documentos.registrar_documento(self.payload(), self.finanzas)
        self.denegada(doc, lambda: documentos.revertir_documento(doc.pk, {
            'motivo': 'Rectificación', 'referencia_rectificacion_externa': 'R',
        }, self.finanzas), cambiar=lambda: self.cambio(password=make_password('sintetica-nueva-012!')))
        doc.refresh_from_db()
        self.assertEqual(doc.estado, 'VIGENTE')
        self.assertEqual(list(FinanzasEvento.objects.values_list('tipo', flat=True)), ['DOCUMENTO_REGISTRADO'])


class SinCobroAUD012(Espera, FinanzasBase, CarrerasPostgreSQL, TransactionTestCase):
    con_cortesia = True

    def test_cierre_denegado_tras_desactivacion_en_obra(self):
        self.denegada(self.obra, lambda: documentos.registrar_sin_cobro(
            self.obra.pk, {'motivo_registro': 'Garantía'}, self.finanzas), 403,
            cambiar=lambda: self.cambio(is_active=False))
        self.assertFalse(CierreSinCobro.objects.exists())
        self.assertFalse(FinanzasEvento.objects.exists())


class PagosAUD012(Espera, PagosBase, CarrerasPostgreSQL, TransactionTestCase):
    def setUp(self):
        self.setUpTestData()
        self.preparar_pagos()

    def registrar(self):
        return pagos.registrar_pago(self.doc.pk, self.pago_data(), self.finanzas, str(uuid4()))

    def test_registro_denegado_tras_cambio_de_rol_en_documento(self):
        self.denegada(self.doc, self.registrar, 403, cambiar=lambda: self.cambio(rol=Usuario.Rol.GERENCIA))
        self.assertFalse(PagoDocumento.objects.exists())
        self.assertEqual(FinanzasEvento.objects.count(), 1)

    @override_settings(BLOQUEOS_C1_SIMULACION_HABILITADA=True)
    def test_anulacion_denegada_tras_bloqueo_persistido_en_pago(self):
        pago, _ = self.registrar()

        def bloquear():
            for _ in range(5):
                registrar_verificacion(self.finanzas.pk, Senal.CLAVE_INCORRECTA)

        # Solo el selector operativo se sustituye; transición SQL y lectura de
        # acceso son reales. C1 aísla el bloqueo del incremento de sesión de C2.
        with patch('apps.usuarios.acceso.bloqueos_activos', return_value=True):
            self.denegada(pago, lambda: pagos.anular_pago(self.doc.pk, pago.pk, {
                'motivo': 'Rectificación', 'referencia_reversion_externa': 'R',
            }, self.finanzas), cambiar=bloquear)
        self.assertEqual(EstadoAcceso.objects.get(usuario=self.finanzas).estado, 'BLOQUEO_TEMPORAL')
        pago.refresh_from_db()
        self.assertTrue(pago.activo)
        self.assertEqual(FinanzasEvento.objects.count(), 2)


class EgresosAUD012(Espera, EgresosBase, CarrerasPostgreSQL, TransactionTestCase):
    def test_anulacion_denegada_tras_cambio_de_hash_en_egreso(self):
        e = self.crear_egreso()
        self.denegada(e, lambda: egresos.anular_egreso(e.pk, {
            'motivo': 'Rectificación', 'referencia_correccion': 'R',
        }, self.finanzas), cambiar=lambda: self.cambio(password=make_password('sintetica-nueva-012!')))
        e.refresh_from_db()
        self.assertTrue(e.activo)
        self.assertEqual(EgresoEvento.objects.count(), 1)

    def test_replay_denegado_tras_cambio_de_hash_durante_espera_uuid(self):
        key = str(uuid4())
        accion = lambda: egresos.registrar_egreso(payload(), self.finanzas, key)
        primero, segundo = self.race(accion, accion, tras_espera=lambda: self.cambio(
            password=make_password('sintetica-nueva-012!')))
        self.assertTrue(primero[1])
        self.assertEqual(getattr(segundo, 'status_code', None), 401)
        self.assertEqual(Egreso.objects.count(), 1)
        self.assertEqual(EgresoEvento.objects.count(), 1)
