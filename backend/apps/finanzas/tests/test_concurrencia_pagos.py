from decimal import Decimal
from uuid import uuid4

from django.test import TransactionTestCase

from apps.finanzas import services_documentos as documentos, services_pagos as pagos
from apps.finanzas.consultas_cobranzas import saldo_documento
from apps.finanzas.models import PagoDocumento, FinanzasEvento
from .test_concurrencia import CarrerasPostgreSQL
from .test_pagos import PagosBase


class PagosConcurrenciaTests(PagosBase, CarrerasPostgreSQL, TransactionTestCase):
    def setUp(self):
        self.setUpTestData()
        self.preparar_pagos()

    def crear_pago(self, monto="100.13", clave=None, documento_id=None):
        return pagos.registrar_pago(documento_id or self.doc.pk, self.pago_data(monto=monto), self.finanzas, clave or str(uuid4()))

    def anular_pago(self, pk):
        return pagos.anular_pago(self.doc.pk, pk, {"motivo": "Corrección comprobada", "referencia_reversion_externa": "Respaldo externo"}, self.finanzas)

    def revertir(self):
        return documentos.revertir_documento(self.doc.pk, {"motivo": "Rectificación", "referencia_rectificacion_externa": "Respaldo externo"}, self.finanzas)

    def test_abonos_competidores_no_sobrepagan(self):
        one, two = self.race(lambda: self.crear_pago("1500.00"), lambda: self.crear_pago("1500.00"))
        self.assertTrue(one[1])
        self.assertEqual(two.detail["code"], "monto_excede_saldo")
        self.assertEqual(saldo_documento(self.doc), (Decimal("1500.00"), Decimal("680.35")))
        self.assertEqual(PagoDocumento.objects.count(), 1)

    def test_dos_abonos_completan_exacto_sin_perdidas(self):
        one, two = self.race(lambda: self.crear_pago("1000.00"), lambda: self.crear_pago("1180.35"))
        self.assertTrue(one[1] and two[1])
        self.assertEqual(saldo_documento(self.doc), (Decimal("2180.35"), Decimal("0.00")))

    def test_misma_clave_mismo_contenido_una_creacion(self):
        clave = str(uuid4())
        one, two = self.race(lambda: self.crear_pago(clave=clave), lambda: self.crear_pago(clave=clave))
        self.assertTrue(one[1])
        self.assertFalse(two[1])
        self.assertEqual(one[0].pk, two[0].pk)
        self.assertEqual(PagoDocumento.objects.count(), 1)
        self.assertEqual(FinanzasEvento.objects.filter(tipo="PAGO_REGISTRADO").count(), 1)

    def test_misma_clave_contenido_distinto_no_duplica(self):
        clave = str(uuid4())
        one, two = self.race(lambda: self.crear_pago(clave=clave), lambda: self.crear_pago(monto="10.00", clave=clave))
        self.assertTrue(one[1])
        self.assertEqual(two.detail["code"], "idempotencia_conflictiva")
        self.assertEqual(PagoDocumento.objects.count(), 1)

    def test_misma_clave_entre_documentos_unicidad_postgresql(self):
        otra = self.otra_finalizada()
        doc = documentos.registrar_documento(self.payload(obra=otra.pk, folio_externo="20002"), self.finanzas)
        clave = str(uuid4())
        one, two = self.race(lambda: self.crear_pago(clave=clave), lambda: self.crear_pago(clave=clave, documento_id=doc.pk))
        self.assertTrue(one[1])
        self.assertEqual(two.detail["code"], "idempotencia_conflictiva")
        self.assertEqual(PagoDocumento.objects.count(), 1)
        self.assertEqual(FinanzasEvento.objects.filter(tipo="PAGO_REGISTRADO").count(), 1)

    def test_pago_antes_de_reversion_bloquea_reversion(self):
        one, two = self.race(self.crear_pago, self.revertir)
        self.assertTrue(one[1])
        self.assertEqual(two.detail["code"], "pagos_pendientes_de_resolver")
        self.doc.refresh_from_db()
        self.assertEqual(self.doc.estado, "VIGENTE")

    def test_reversion_antes_de_pago_bloquea_pago(self):
        one, two = self.race(self.revertir, self.crear_pago)
        self.assertEqual(one.estado, "REVERTIDO")
        self.assertEqual(two.detail["code"], "documento_revertido")
        self.assertFalse(PagoDocumento.objects.exists())

    def test_anulacion_antes_de_pago_libera_saldo(self):
        original, _ = self.crear_pago("1500.00")
        one, two = self.race(lambda: self.anular_pago(original.pk), lambda: self.crear_pago("1500.00"))
        self.assertFalse(one.activo)
        self.assertTrue(two[1])
        self.assertEqual(PagoDocumento.objects.filter(activo=True).count(), 1)
        self.assertEqual(saldo_documento(self.doc)[0], Decimal("1500.00"))

    def test_pago_antes_de_anulacion_conserva_balance(self):
        original, _ = self.crear_pago("500.00")
        one, two = self.race(lambda: self.crear_pago("1500.00"), lambda: self.anular_pago(original.pk))
        self.assertTrue(one[1])
        self.assertFalse(two.activo)
        self.assertEqual(saldo_documento(self.doc), (Decimal("1500.00"), Decimal("680.35")))

    def test_anulacion_simultanea_un_evento_y_sin_saldo_negativo(self):
        original, _ = self.crear_pago()
        one, two = self.race(lambda: self.anular_pago(original.pk), lambda: self.anular_pago(original.pk))
        self.assertFalse(one.activo)
        self.assertEqual(two.detail["code"], "pago_ya_anulado")
        self.assertEqual(original.eventos.count(), 2)
        self.assertEqual(saldo_documento(self.doc), (Decimal("0.00"), Decimal("2180.35")))

    def test_anular_y_revertir_serializados_preservan_historia(self):
        original, _ = self.crear_pago()
        one, two = self.race(lambda: self.anular_pago(original.pk), self.revertir)
        self.assertFalse(one.activo)
        self.assertEqual(two.estado, "REVERTIDO")
        self.assertEqual(PagoDocumento.objects.count(), 1)
        self.assertEqual(original.eventos.count(), 2)
