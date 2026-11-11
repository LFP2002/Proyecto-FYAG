from datetime import timedelta
from decimal import Decimal, localcontext
from unittest.mock import patch
from uuid import uuid4

from django.contrib import admin
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, connection, models, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from rest_framework.exceptions import PermissionDenied

from apps.finanzas import services_documentos as documentos, services_pagos as pagos
from apps.finanzas.models import DocumentoCobro, PagoDocumento, FinanzasEvento
from apps.finanzas.validaciones import hoy_santiago, LIMITE
from apps.usuarios import services_usuarios
from apps.usuarios.models import Usuario
from .base import FinanzasBase


class PagosBase(FinanzasBase):
    def preparar_pagos(self):
        self.preparar_finanzas()
        self.doc = documentos.registrar_documento(self.payload(fecha_emision=(hoy_santiago() - timedelta(days=5)).isoformat()), self.finanzas)
        self.pagos_url = f"/api/finanzas/documentos/{self.doc.pk}/pagos/"

    def pago_data(self, **changes):
        return {"monto": "100.13", "fecha_pago": hoy_santiago().isoformat(), "medio": "TRANSFERENCIA", "referencia_respaldo": " Referencia de comprobante verificado ", **changes}

    def pagar(self, clave=None, data=None, url=None):
        return self.client.post(url or self.pagos_url, data if data is not None else self.pago_data(), format="json", HTTP_IDEMPOTENCY_KEY=clave or str(uuid4()))

    def anular(self, pago_id, data=None):
        return self.client.post(self.pagos_url + f"{pago_id}/anular/", data if data is not None else {"motivo": " Registro corregido ", "referencia_reversion_externa": " Respaldo de corrección externa "}, format="json")

    def cobranza(self):
        return self.client.get(f"/api/finanzas/documentos/{self.doc.pk}/").data["cobranza"]


class PagosTests(PagosBase, TestCase):
    def setUp(self):
        self.preparar_pagos()

    def test_parciales_total_y_sin_pagos_no_es_costo_ni_ingreso(self):
        before = self.estado_persistido()
        self.assertEqual(self.cobranza(), {"moneda": "CLP", "abonado": "0.00", "saldo": "2180.35", "estado": "PENDIENTE"})
        first = self.pagar()
        self.assertEqual(first.status_code, 201, first.data)
        self.assertEqual(first.data["monto"], "100.13")
        self.assertEqual(first.data["naturaleza"], "REGISTRO_ADMINISTRATIVO_DINERO_RECIBIDO")
        self.assertEqual(self.cobranza(), {"moneda": "CLP", "abonado": "100.13", "saldo": "2080.22", "estado": "PARCIAL"})
        self.assertEqual(self.pagar(data=self.pago_data(monto="2080.22")).status_code, 201)
        self.assertEqual(self.cobranza(), {"moneda": "CLP", "abonado": "2180.35", "saldo": "0.00", "estado": "PAGADA"})
        self.assertEqual(self.pagar().data["code"], "monto_excede_saldo")
        self.assertEqual(self.estado_persistido(), before)
        self.assertEqual(FinanzasEvento.objects.filter(tipo="PAGO_REGISTRADO").count(), 2)

    def test_vencimiento_y_prioridad_pagada_fecha_santiago(self):
        ayer = hoy_santiago() - timedelta(days=1)
        models.QuerySet(model=DocumentoCobro).filter(pk=self.doc.pk).update(fecha_vencimiento=ayer)
        self.assertEqual(self.cobranza()["estado"], "VENCIDA")
        self.pagar()
        self.assertEqual(self.cobranza()["estado"], "VENCIDA")
        self.pagar(data=self.pago_data(monto="2080.22"))
        self.assertEqual(self.cobranza()["estado"], "PAGADA")
        # El estado cambia por la fecha local sin escribir DocumentoCobro.
        with patch("apps.finanzas.consultas_cobranzas.hoy_santiago", return_value=ayer):
            self.assertEqual(self.cobranza()["estado"], "PAGADA")

    def test_uuid_requerido_estricto_sin_admitir_campo_body(self):
        for key in [None, "", "x", "true", "1" * 32, str(uuid4()) + "," + str(uuid4())]:
            headers = {} if key is None else {"HTTP_IDEMPOTENCY_KEY": key}
            response = self.client.post(self.pagos_url, self.pago_data(), format="json", **headers)
            self.assertEqual(response.status_code, 400, response.data)
        response = self.pagar(data=self.pago_data(clave_idempotencia=str(uuid4())))
        self.assertEqual(response.status_code, 400)
        self.assertFalse(PagoDocumento.objects.exists())

    def test_idempotencia_payload_canonico_y_operacion_original(self):
        key = str(uuid4())
        first = self.pagar(key, self.pago_data(monto="100.1"))
        replay = self.pagar(key.upper(), self.pago_data(monto="100.10", referencia_respaldo="Referencia de comprobante verificado", observacion=""))
        self.assertEqual(first.status_code, 201, first.data)
        self.assertEqual(replay.status_code, 200, replay.data)
        self.assertEqual(first.data, replay.data)
        self.assertEqual(replay["Idempotency-Replayed"], "true")
        self.assertEqual(PagoDocumento.objects.count(), 1)
        pago = PagoDocumento.objects.get()
        self.assertEqual(pago.huella_solicitud, pagos.huella(self.doc.pk, documentos.datos(pagos.PagoCrearSerializer, self.pago_data(monto="100.10"))))
        self.assertEqual(pago.eventos.count(), 1)
        for key in ["clave_idempotencia", "huella_solicitud", "password", "sesion_version", "costo_total"]:
            self.assertNotIn(key, str(first.data))

    def test_idempotencia_conflictiva_payload_y_documento(self):
        key = str(uuid4())
        self.pagar(key)
        for changes in [{"monto": "101.13"}, {"fecha_pago": (hoy_santiago() - timedelta(days=1)).isoformat()}, {"medio": "EFECTIVO"}, {"referencia_respaldo": "Otro"}, {"observacion": "Otra"}]:
            result = self.pagar(key, self.pago_data(**changes))
            self.assertEqual(result.status_code, 409, result.data)
            self.assertEqual(result.data["code"], "idempotencia_conflictiva")
        otra = self.otra_finalizada()
        other = documentos.registrar_documento(self.payload(obra=otra.pk, folio_externo="20002"), self.finanzas)
        result = self.pagar(key, url=f"/api/finanzas/documentos/{other.pk}/pagos/")
        self.assertEqual(result.data["code"], "idempotencia_conflictiva")
        self.assertEqual(PagoDocumento.objects.count(), 1)

    def test_reintento_tras_pagada_anulacion_y_reversion(self):
        key = str(uuid4())
        data = self.pago_data(monto="2180.35")
        first = self.pagar(key, data)
        self.assertEqual(first.status_code, 201)
        self.assertEqual(self.pagar(key, data).data, first.data)
        self.assertEqual(self.anular(first.data["id"]).status_code, 200)
        self.assertEqual(self.pagar(key, data).data, first.data)
        current = self.client.get(self.pagos_url + f"{first.data['id']}/")
        self.assertFalse(current.data["activo"])
        documentos.revertir_documento(self.doc.pk, {"motivo": "Corrección", "referencia_rectificacion_externa": "Respaldo externo"}, self.finanzas)
        replay = self.pagar(key, data)
        self.assertEqual(replay.status_code, 200, replay.data)
        self.assertEqual(replay.data, first.data)
        self.assertEqual(PagoDocumento.objects.count(), 1)
        self.assertEqual(PagoDocumento.objects.get().eventos.count(), 2)
        self.assertIsNone(self.cobranza())

    def test_misma_solicitud_claves_distintas_son_pagos_distintos(self):
        self.assertEqual(self.pagar().status_code, 201)
        self.assertEqual(self.pagar().status_code, 201)
        self.assertEqual(PagoDocumento.objects.count(), 2)

    def test_recupera_alta_tras_perdida_de_respuesta_despues_del_commit(self):
        clave = str(uuid4())
        with patch("apps.finanzas.views_pagos.PagoRegistroSerializer.to_representation", side_effect=TimeoutError("respuesta perdida")):
            with self.assertRaises(TimeoutError):
                self.pagar(clave)
        self.assertEqual(PagoDocumento.objects.count(), 1)
        replay = self.pagar(clave)
        self.assertEqual(replay.status_code, 200, replay.data)
        self.assertEqual(PagoDocumento.objects.get().eventos.count(), 1)

    def test_fecha_pago_civil_santiago_aun_con_zona_activa_utc(self):
        from datetime import datetime, timezone as tz
        from django.utils import timezone
        instant = datetime(2026, 7, 1, 2, tzinfo=tz.utc)
        models.QuerySet(model=DocumentoCobro).filter(pk=self.doc.pk).update(fecha_emision="2026-06-01")
        with timezone.override("UTC"), patch("django.utils.timezone.now", return_value=instant):
            response = self.pagar(data=self.pago_data(fecha_pago="2026-07-01"))
            self.assertEqual(response.status_code, 400, response.data)
            response = self.pagar(data=self.pago_data(fecha_pago="2026-06-30"))
            self.assertEqual(response.status_code, 201, response.data)

    def test_montos_invalidos_precision_y_sobrepago(self):
        for value in [0, 1, 1.1, True, None, "0", "-1", "NaN", "Infinity", "1e1", "1,00", "1.000", " 1.00", ".10", "1.", "9" * 37 + ".00"]:
            result = self.pagar(data=self.pago_data(monto=value))
            self.assertEqual(result.status_code, 400, (value, result.data))
        result = self.pagar(data=self.pago_data(monto="2180.36"))
        self.assertEqual(result.status_code, 409)
        self.assertEqual(result.data["code"], "monto_excede_saldo")
        self.assertFalse(PagoDocumento.objects.exists())

    def test_limite_decimal_bajo_contexto_pequeno_no_redondea(self):
        # Fixture de frontera NUMERIC, no altera los servicios de origen.
        models.QuerySet(model=DocumentoCobro).filter(pk=self.doc.pk).update(monto_neto=LIMITE, monto_impuesto=Decimal("0.00"), monto_total=LIMITE, tipo_documento="FACTURA_EXENTA")
        with localcontext() as ctx:
            ctx.prec = 50
            parcial = format(LIMITE - Decimal("0.01"), ".2f")
        with localcontext() as ctx:
            ctx.prec = 6
            result = self.pagar(data=self.pago_data(monto=parcial))
            self.assertEqual(result.status_code, 201, result.data)
            self.assertEqual(self.cobranza()["saldo"], "0.01")
            self.assertEqual(self.pagar(data=self.pago_data(monto="0.01")).status_code, 201)
            self.assertEqual(self.cobranza()["saldo"], "0.00")
        self.assertEqual(self.cobranza()["abonado"], str(LIMITE))

    def test_fechas_medios_textos_y_campos_servidor(self):
        for field, value in [("fecha_pago", (hoy_santiago() + timedelta(days=1)).isoformat()), ("fecha_pago", "2000-01-01"), ("fecha_pago", "2026-02-30"), ("fecha_pago", "2026-1-01"), ("fecha_pago", "2026-01-01T00:00:00Z"), ("medio", "BANCO"), ("referencia_respaldo", " "), ("referencia_respaldo", 123), ("observacion", None), ("activo", False), ("saldo", "0.00"), ("documento", self.doc.pk), ("registrado_por", self.gerencia.pk), ("registrado_en", "2020-01-01"), ("anulado_en", None), ("huella_solicitud", "x"), ("numero_tarjeta", "no-aceptar"), ("cvv", "no-aceptar")]:
            result = self.pagar(data=self.pago_data(**{field: value}))
            self.assertEqual(result.status_code, 400, (field, result.data))
        self.assertFalse(PagoDocumento.objects.exists())

    def test_cuatro_medios_sin_integracion_bancaria(self):
        for medio in PagoDocumento.Medio.values:
            self.assertEqual(self.pagar(data=self.pago_data(medio=medio)).status_code, 201)
        self.assertEqual(PagoDocumento.objects.count(), 4)

    def test_anulacion_respaldada_saldo_e_historial_inmutable(self):
        first = self.pagar()
        pk = first.data["id"]
        for data in [{}, {"motivo": "X"}, {"motivo": " ", "referencia_reversion_externa": "X"}, {"motivo": "X", "referencia_reversion_externa": " "}, {"motivo": "X", "referencia_reversion_externa": "X", "monto": "0"}]:
            self.assertEqual(self.anular(pk, data).status_code, 400)
        result = self.anular(pk)
        self.assertEqual(result.status_code, 200, result.data)
        self.assertFalse(result.data["activo"])
        self.assertEqual(result.data["monto"], first.data["monto"])
        self.assertEqual(result.data["documento"], self.doc.pk)
        self.assertEqual(self.anular(pk).data["code"], "pago_ya_anulado")
        self.assertEqual(self.cobranza()["saldo"], "2180.35")
        history = self.client.get(self.pagos_url + "historial/")
        self.assertEqual(history.data["count"], 2)
        self.assertEqual([e["tipo"] for e in history.data["results"]], ["PAGO_REGISTRADO", "PAGO_ANULADO"])
        event = PagoDocumento.objects.get().eventos.get(tipo="PAGO_ANULADO")
        self.assertEqual(event.datos_nuevos["activo"], False)
        for operation in [lambda: event.save(), lambda: event.delete(), lambda: FinanzasEvento.objects.filter(pk=event.pk).update(motivo="x"), lambda: PagoDocumento.objects.get().save(), lambda: PagoDocumento.objects.all().delete()]:
            with self.assertRaises(DjangoValidationError):
                operation()
        self.assertNotIn(PagoDocumento, admin.site._registry)
        with self.assertRaises(ProtectedError):
            models.QuerySet(model=DocumentoCobro).filter(pk=self.doc.pk).delete()

    def test_reversion_documental_bloqueada_hasta_resolver_pagos(self):
        first = self.pagar()
        url = f"/api/finanzas/documentos/{self.doc.pk}/revertir/"
        data = {"motivo": "Rectificación", "referencia_rectificacion_externa": "Externo"}
        result = self.client.post(url, data, format="json")
        self.assertEqual(result.status_code, 409)
        self.assertEqual(result.data["code"], "pagos_pendientes_de_resolver")
        self.assertEqual(self.doc.eventos.count(), 1)
        self.anular(first.data["id"])
        self.assertEqual(self.client.post(url, data, format="json").status_code, 200)
        self.assertEqual(PagoDocumento.objects.count(), 1)
        self.assertIsNone(self.cobranza())
        self.assertEqual(self.pagar().data["code"], "documento_revertido")

    def test_rollback_pago_anulacion_y_evento(self):
        with patch("apps.finanzas.services_documentos.evento", side_effect=RuntimeError("controlado")):
            with self.assertRaises(RuntimeError):
                pagos.registrar_pago(self.doc.pk, self.pago_data(), self.finanzas, str(uuid4()))
        self.assertFalse(PagoDocumento.objects.exists())
        first = self.pagar()
        with patch("apps.finanzas.services_documentos.evento", side_effect=RuntimeError("controlado")):
            with self.assertRaises(RuntimeError):
                pagos.anular_pago(self.doc.pk, first.data["id"], {"motivo": "X", "referencia_reversion_externa": "Y"}, self.finanzas)
        self.assertTrue(PagoDocumento.objects.get().activo)
        self.assertEqual(self.cobranza()["abonado"], "100.13")
        self.assertEqual(PagoDocumento.objects.get().eventos.count(), 1)

    def test_integrity_error_inesperado_no_se_oculta(self):
        with patch("apps.finanzas.services_documentos.evento", side_effect=IntegrityError("inesperado")):
            with self.assertRaisesMessage(IntegrityError, "inesperado"):
                pagos.registrar_pago(self.doc.pk, self.pago_data(), self.finanzas, str(uuid4()))
        self.assertFalse(PagoDocumento.objects.exists())

    def test_permisos_cuatro_roles_options_y_no_filtraciones(self):
        first = self.pagar()
        paths = [self.pagos_url, self.pagos_url + f"{first.data['id']}/", self.pagos_url + "historial/", "/api/finanzas/cobranzas/", "/api/finanzas/cobranzas/resumen/"]
        for user in [self.gerencia, self.finanzas, self.supervisor, self.tecnico]:
            user.is_superuser = user.is_staff = True
            user.save()
            self.autenticar(user)
            expected = 200 if user.rol in ["GERENCIA", "ADMINISTRATIVO_FINANZAS"] else 403
            for path in paths:
                self.assertEqual(self.client.get(path).status_code, expected)
                self.assertEqual(self.client.options(path).status_code, expected)
            if user != self.finanzas:
                self.assertEqual(self.pagar().status_code, 403)
                self.assertEqual(self.anular(first.data["id"]).status_code, 403)
        self.client.credentials()
        for path in paths:
            self.assertEqual(self.client.get(path).status_code, 401)

    def test_jwt_revocado_y_actor_persistido(self):
        ti = Usuario.objects.create_user(username="ti", email="ti@example.test", rol="ADMINISTRADOR_TI")
        services_usuarios.editar_usuario(self.finanzas, {"email": "revocado@example.test"}, ti)
        self.assertEqual(self.pagar().status_code, 401)
        self.finanzas.refresh_from_db()
        self.autenticar(self.finanzas)
        self.finanzas.is_active = False
        self.finanzas.save()
        self.assertEqual(self.client.get(self.pagos_url).status_code, 401)
        with self.assertRaises(PermissionDenied):
            pagos.registrar_pago(self.doc.pk, self.pago_data(), self.finanzas, str(uuid4()))

    def test_pagos_ajenos_ids_y_metodos_sin_crud(self):
        first = self.pagar()
        otra = self.otra_finalizada()
        other = documentos.registrar_documento(self.payload(obra=otra.pk, folio_externo="20002"), self.finanzas)
        path = f"/api/finanzas/documentos/{other.pk}/pagos/{first.data['id']}/"
        self.assertEqual(self.client.get(path).status_code, 404)
        self.assertEqual(self.client.post(path + "anular/", {"motivo": "X", "referencia_reversion_externa": "Y"}, format="json").status_code, 404)
        for value in ["0", "true", "-1", "9223372036854775808"]:
            self.assertEqual(self.client.get(self.pagos_url + value + "/").status_code, 400)
        self.assertEqual(self.client.get(self.pagos_url + "999999/").status_code, 404)
        self.assertEqual(self.client.get("/api/finanzas/documentos/999999/pagos/").status_code, 404)
        for method in ["put", "patch", "delete"]:
            self.assertEqual(getattr(self.client, method)(self.pagos_url + f"{first.data['id']}/", {}, format="json").status_code, 405)

    def test_filtros_pagos_paginacion_historial_y_orden(self):
        for _ in range(27):
            self.assertEqual(self.pagar(data=self.pago_data(monto="1.00")).status_code, 201)
        response = self.client.get(self.pagos_url)
        self.assertEqual(response.data["count"], 27)
        self.assertEqual(len(response.data["results"]), 25)
        self.assertEqual(len(self.client.get(self.pagos_url + "?page=2").data["results"]), 2)
        self.assertEqual([p["id"] for p in response.data["results"]], sorted([p["id"] for p in response.data["results"]], reverse=True))
        self.assertEqual(len(self.client.get(self.pagos_url + "historial/").data["results"]), 25)
        self.assertEqual(self.client.get(self.pagos_url + "historial/?medio=TRANSFERENCIA").status_code, 400)
        self.assertEqual(self.client.get(self.pagos_url + "?activo=true&medio=TRANSFERENCIA&fecha_pago_desde=2020-01-01").data["count"], 27)
        for query in ["activo=1", "medio=OTROS", "page=0", "page=-1", "page=1&page=2", "otro=x", "activo=true&activo=false", "fecha_pago_desde=2026-02-30", "fecha_pago_desde=2026-02-01&fecha_pago_hasta=2020-01-01"]:
            self.assertEqual(self.client.get(self.pagos_url + "?" + query).status_code, 400, query)
        with CaptureQueriesContext(connection) as queries:
            self.client.get(self.pagos_url)
        self.assertLessEqual(len(queries), 6)

    def test_constraints_sql_importes_metadatos_y_referencias(self):
        first = self.pagar()
        obj = PagoDocumento.objects.get()
        for changes in [{"monto": Decimal("0")}, {"monto": Decimal("-1")}, {"medio": "OTRO_X"}, {"activo": False}, {"huella_solicitud": "x"}, {"referencia_respaldo": " "}]:
            with self.assertRaises(IntegrityError), transaction.atomic():
                models.QuerySet(model=PagoDocumento).filter(pk=obj.pk).update(**changes)
        event = obj.eventos.get()
        with self.assertRaises(IntegrityError), transaction.atomic():
            models.QuerySet(model=FinanzasEvento).filter(pk=event.pk).update(documento=self.doc)
        self.assertEqual(first.status_code, 201)
