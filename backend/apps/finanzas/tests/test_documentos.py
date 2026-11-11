from datetime import timedelta, datetime, timezone as datetime_timezone
from decimal import Decimal
from unittest.mock import patch

from django.contrib import admin
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, connection, models, transaction
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from rest_framework.exceptions import PermissionDenied

from apps.comercial.models import Presupuesto
from apps.finanzas import services_documentos as services
from apps.finanzas.models import DocumentoCobro, CierreSinCobro, FinanzasEvento
from apps.finanzas.serializers_documentos import FinanzasEventoSerializer
from apps.finanzas.validaciones import hoy_santiago, LIMITE, validar_montos
from apps.obras.models import Obra, CortesiaObra, CierreCostosObra
from apps.usuarios.models import Usuario
from apps.usuarios import services_usuarios
from .base import FinanzasBase


class DocumentosTests(FinanzasBase, TestCase):
    def setUp(self):
        self.preparar_finanzas()

    def test_registro_documental_neto_items_sin_confundir_costos(self):
        before = self.estado_persistido()
        response = self.registrar()
        self.assertEqual(response.status_code, 201, response.data)
        obj = DocumentoCobro.objects.get()
        self.assertEqual(obj.monto_neto, self.presupuesto.monto_neto)
        self.assertEqual(obj.monto_neto, Decimal("2080.22"))
        self.assertNotEqual(obj.monto_neto, CierreCostosObra.objects.get(obra=self.obra).costo_total)
        self.assertEqual(response.data["monto_total"], "2180.35")
        self.assertEqual(response.data["naturaleza"], "REGISTRO_ADMINISTRATIVO_DOCUMENTO_EXTERNO")
        self.assertEqual(response.data["referencia_respaldo"], "Archivo interno del documento externo")
        self.assertEqual(obj.registrado_por_id, self.finanzas.pk)
        self.assertEqual(obj.estado, "VIGENTE")
        self.assertEqual(obj.eventos.get().tipo, "DOCUMENTO_REGISTRADO")
        self.assertEqual(self.estado_persistido(), before)
        self.assertEqual(response.data["origen"]["cliente"]["id"], self.cliente.pk)
        self.assertEqual(self.client.get(f"/api/finanzas/obras/{self.obra.pk}/estado-financiero/").data["estado_financiero"], "DOCUMENTADO")

    def test_matriz_cuatro_roles_anonimo_y_superuser_sin_bypass(self):
        obj = services.registrar_documento(self.payload(), self.finanzas)
        paths = [self.documentos_url, f"{self.documentos_url}{obj.pk}/", f"{self.documentos_url}{obj.pk}/historial/", f"/api/finanzas/obras/{self.obra.pk}/estado-financiero/"]
        for actor in [self.gerencia, self.finanzas, self.supervisor, self.tecnico]:
            actor.is_superuser = actor.is_staff = True
            actor.save()
            self.autenticar(actor)
            expected = 200 if actor.rol in ["GERENCIA", "ADMINISTRATIVO_FINANZAS"] else 403
            for path in paths:
                self.assertEqual(self.client.get(path).status_code, expected, (actor.rol, path))
                self.assertEqual(self.client.options(path).status_code, expected)
            self.assertEqual(self.client.get("/api/finanzas/obras-elegibles/").status_code, 200 if actor == self.finanzas else 403)
            if actor != self.finanzas:
                for path in [self.documentos_url, f"{self.documentos_url}{obj.pk}/revertir/", f"/api/finanzas/obras/{self.obra.pk}/registrar-sin-cobro/"]:
                    response = self.client.post(path, {}, format="json")
                    self.assertEqual(response.status_code, 403)
                    self.assertNotIn("10001", str(response.data))
        self.client.credentials()
        for path in paths:
            self.assertEqual(self.client.get(path).status_code, 401)

    def test_rol_persistido_sesion_revocada_e_inactiva(self):
        ti = Usuario.objects.create_user(username="ti", email="ti@example.test", rol="ADMINISTRADOR_TI")
        services_usuarios.cambiar_rol(self.finanzas, {"rol": "TECNICO", "motivo": "Cambio"}, ti)
        self.assertEqual(self.client.get(self.documentos_url).status_code, 401)
        self.finanzas.refresh_from_db()
        self.autenticar(self.finanzas)
        self.assertEqual(self.client.get(self.documentos_url).status_code, 403)
        self.finanzas.is_active = False
        self.finanzas.save()
        self.assertEqual(self.client.get(self.documentos_url).status_code, 401)

    def test_servicio_revalida_actor_no_confia_objeto_o_flags(self):
        Usuario.objects.filter(pk=self.finanzas.pk).update(rol="TECNICO")
        with self.assertRaises(PermissionDenied) as caught:
            services.registrar_documento(self.payload(), self.finanzas)
        self.assertEqual(caught.exception.status_code, 403)
        self.assertFalse(DocumentoCobro.objects.exists())

    def test_cliente_inactivo_historico_elegible(self):
        self.cliente.activo = False
        self.cliente.save()
        self.assertEqual(self.registrar().status_code, 201)

    def test_campos_desconocidos_servidor_y_tipos_rechazados(self):
        for field, value in [("presupuesto", self.presupuesto.pk), ("cliente", self.cliente.pk), ("estado", "REVERTIDO"), ("actor", self.gerencia.pk), ("registrado_por", self.gerencia.pk), ("registrado_en", "2020-01-01"), ("moneda", "USD"), ("pagos", []), ("saldo", "0.00"), ("obra", True), ("obra", "1"), ("obra", 1.0), ("obra", 0), ("obra", 2**63), ("referencia_respaldo", 4), ("folio_externo", 1), ("tipo_documento", "BOLETA")]:
            with self.subTest(field=field, value=value):
                result = self.registrar(**{field: value})
                self.assertEqual(result.status_code, 400, result.data)
        self.assertFalse(FinanzasEvento.objects.exists())

    def test_importes_strings_precision_formato_y_sumas(self):
        for value in [True, 1, 1.5, "-1", "NaN", "Infinity", "1e3", "1E3", "1,00", "1 000", " 1.00", "1.000", ".10", "1.", "9" * 37 + ".00", "١.00"]:
            for field in ["monto_neto", "monto_impuesto", "monto_total"]:
                result = self.registrar(**{field: value})
                self.assertEqual(result.status_code, 400, (field, value, result.data))
        for changes in [{"monto_total": "2180.34"}, {"monto_impuesto": "0.00", "monto_total": "2080.22"}, {"tipo_documento": "FACTURA_EXENTA"}, {"monto_neto": "0.00", "monto_impuesto": "0.00", "monto_total": "0.00"}]:
            self.assertEqual(self.registrar(**changes).status_code, 400)
        self.assertFalse(DocumentoCobro.objects.exists())

    def test_overflow_y_limite_no_redondean(self):
        with self.assertRaises(DjangoValidationError):
            validar_montos(LIMITE, Decimal("0.01"), LIMITE, "FACTURA_AFECTA")
        validar_montos(LIMITE, Decimal("0.00"), LIMITE, "FACTURA_EXENTA")
        result = self.registrar(monto_neto=str(LIMITE), monto_impuesto="0.00", monto_total=str(LIMITE), tipo_documento="FACTURA_EXENTA")
        self.assertEqual(result.status_code, 409)
        self.assertEqual(result.data["code"], "monto_no_coincide")

    def test_exenta_y_no_asume_tasa_iva(self):
        result = self.registrar(tipo_documento="FACTURA_EXENTA", monto_impuesto="0", monto_total="2080.22")
        self.assertEqual(result.status_code, 201, result.data)
        self.assertEqual(result.data["monto_impuesto"], "0.00")

    def test_mismo_folio_en_tipo_distinto_es_permitido(self):
        self.assertEqual(self.registrar().status_code, 201)
        otra = self.otra_finalizada()
        result = self.registrar(obra=otra.pk, tipo_documento="FACTURA_EXENTA", monto_impuesto="0.00", monto_total="2080.22")
        self.assertEqual(result.status_code, 201, result.data)
        self.assertEqual(DocumentoCobro.objects.count(), 2)

    def test_sin_cortesia_no_se_registra_cierre_sin_cobro(self):
        result = self.client.post(f"/api/finanzas/obras/{self.obra.pk}/registrar-sin-cobro/", {"motivo_registro": "Intento sin autorización"}, format="json")
        self.assertEqual(result.status_code, 409)
        self.assertEqual(result.data["code"], "cortesia_requerida")
        self.assertFalse(CierreSinCobro.objects.exists())

    def test_monto_diferente_es_conflicto_con_origen_persistido(self):
        for value, total in [("8000.00", "8100.13"), ("2080.21", "2180.34")]:
            result = self.registrar(monto_neto=value, monto_total=total)
            self.assertEqual(result.status_code, 409)
            self.assertEqual(result.data["code"], "monto_no_coincide")

    def test_folios_ascii_exactos_y_respaldo(self):
        for value in ["", " ", " 001", "001 ", "１２３", "1-2", "1.0", "1\n", "1" * 101]:
            self.assertEqual(self.registrar(folio_externo=value).status_code, 400, repr(value))
        for value in ["", "  ", "x" * 501, None]:
            self.assertEqual(self.registrar(referencia_respaldo=value).status_code, 400)
        result = self.registrar(folio_externo="000123")
        self.assertEqual(result.status_code, 201, result.data)
        self.assertEqual(result.data["folio_externo"], "000123")

    def test_fechas_civiles_santiago(self):
        for field, value in [("fecha_emision", (hoy_santiago() + timedelta(days=1)).isoformat()), ("fecha_vencimiento", "2020-01-01"), ("fecha_emision", "2026-02-30"), ("fecha_emision", "2026-1-01"), ("fecha_emision", "2026-01-01T00:00:00Z"), ("fecha_emision", True)]:
            self.assertEqual(self.registrar(**{field: value}).status_code, 400)
        result = self.registrar(fecha_emision="2020-01-01", fecha_vencimiento="2020-02-01")
        self.assertEqual(result.status_code, 201, result.data)
        with patch("django.utils.timezone.now", return_value=datetime(2026, 7, 1, 2, tzinfo=datetime_timezone.utc)):
            with timezone_override_utc():
                self.assertEqual(hoy_santiago().isoformat(), "2026-06-30")

    def test_elegibilidad_estados_y_origen_sin_escritura(self):
        for state in ["PLANIFICADA", "EN_PROCESO", "SUSPENDIDA"]:
            changes = {"estado": state, "finalizado_en": None}
            if state == "PLANIFICADA":
                changes["iniciado_en"] = None
            else:
                changes["iniciado_en"] = self.obra.iniciado_en
            Obra.objects.filter(pk=self.obra.pk).update(**changes)
            result = self.registrar()
            self.assertEqual(result.status_code, 409)
            self.assertEqual(result.data["code"], "obra_no_finalizada")
        self.assertFalse(FinanzasEvento.objects.exists())

    def test_origen_no_aprobado_y_cierre_ausente(self):
        Presupuesto.objects.filter(pk=self.presupuesto.pk).update(estado="ENVIADO_CLIENTE")
        self.assertEqual(self.registrar().data["code"], "presupuesto_no_aprobado")
        Presupuesto.objects.filter(pk=self.presupuesto.pk).update(estado="APROBADO_CLIENTE")
        with patch("apps.finanzas.services_documentos.CierreCostosObra.objects.filter") as mock:
            mock.return_value.exists.return_value = False
            self.assertEqual(self.registrar().data["code"], "cierre_costos_requerido")
        self.assertEqual(self.registrar(obra=9223372036854775807).status_code, 404)

    def test_duplicidad_vigente_y_folio_revertido_no_reutilizable(self):
        first = self.registrar()
        self.assertEqual(first.status_code, 201)
        self.assertEqual(self.registrar(folio_externo="2").data["code"], "documento_duplicado")
        services.revertir_documento(first.data["id"], {"motivo": "Error externo", "referencia_rectificacion_externa": "Rectificación externa A"}, self.finanzas)
        self.assertEqual(self.registrar().data["code"], "documento_duplicado")
        self.assertEqual(self.registrar(folio_externo="2").status_code, 201)
        self.assertEqual(DocumentoCobro.objects.count(), 2)

    def test_reversion_respaldada_conserva_importes_e_historial(self):
        obj = services.registrar_documento(self.payload(), self.finanzas)
        url = f"{self.documentos_url}{obj.pk}/revertir/"
        for data in [{}, {"motivo": "Error"}, {"motivo": " ", "referencia_rectificacion_externa": "X"}, {"motivo": "Error", "referencia_rectificacion_externa": " "}, {"motivo": "Error", "referencia_rectificacion_externa": "X", "monto_total": "0"}]:
            self.assertEqual(self.client.post(url, data, format="json").status_code, 400)
        result = self.client.post(url, {"motivo": " Registro corregido externamente ", "referencia_rectificacion_externa": " Respaldo NC externo "}, format="json")
        self.assertEqual(result.status_code, 200, result.data)
        self.assertEqual(result.data["estado"], "REVERTIDO")
        self.assertEqual(result.data["monto_total"], "2180.35")
        self.assertEqual(result.data["folio_externo"], "10001")
        self.assertEqual(self.client.post(url, {"motivo": "Otra", "referencia_rectificacion_externa": "Otro"}, format="json").data["code"], "documento_ya_revertido")
        self.assertEqual(obj.eventos.count(), 2)
        self.assertEqual(self.client.get(f"{self.documentos_url}{obj.pk}/historial/").data["count"], 2)
        self.assertEqual(self.client.get(f"/api/finanzas/obras/{self.obra.pk}/estado-financiero/").data["estado_financiero"], "PENDIENTE_FACTURACION")

    def test_rollback_registro_y_reversion_si_evento_falla(self):
        with patch("apps.finanzas.services_documentos.evento", side_effect=RuntimeError("controlado")):
            with self.assertRaises(RuntimeError):
                services.registrar_documento(self.payload(), self.finanzas)
        self.assertFalse(DocumentoCobro.objects.exists())
        obj = services.registrar_documento(self.payload(), self.finanzas)
        with patch("apps.finanzas.services_documentos.evento", side_effect=RuntimeError("controlado")):
            with self.assertRaises(RuntimeError):
                services.revertir_documento(obj.pk, {"motivo": "Error", "referencia_rectificacion_externa": "Externo"}, self.finanzas)
        obj.refresh_from_db()
        self.assertEqual(obj.estado, "VIGENTE")
        self.assertIsNone(obj.revertido_en)
        self.assertEqual(obj.eventos.count(), 1)

    def test_integrity_error_inesperado_no_se_oculta(self):
        with patch("apps.finanzas.services_documentos.evento", side_effect=IntegrityError("fallo inesperado")):
            with self.assertRaisesMessage(IntegrityError, "fallo inesperado"):
                services.registrar_documento(self.payload(), self.finanzas)
        self.assertFalse(DocumentoCobro.objects.exists())

    def test_immutable_admin_metodos_prohibidos_y_rutas_acumulativas(self):
        obj = services.registrar_documento(self.payload(), self.finanzas)
        for model in [DocumentoCobro, CierreSinCobro, FinanzasEvento]:
            self.assertNotIn(model, admin.site._registry)
        for method in ["put", "patch", "delete"]:
            self.assertEqual(getattr(self.client, method)(f"{self.documentos_url}{obj.pk}/", {}, format="json").status_code, 405)
        for action in [lambda: obj.save(), lambda: obj.delete(), lambda: DocumentoCobro.objects.filter(pk=obj.pk).update(monto_total=0), lambda: obj.eventos.all().delete(), lambda: obj.eventos.get().save()]:
            with self.assertRaises(DjangoValidationError):
                action()
        # 007B habilita estas rutas sin cambiar las prohibiciones CRUD de 007A.
        for path in ["cobranzas/", f"documentos/{obj.pk}/pagos/"]:
            self.assertEqual(self.client.get("/api/finanzas/" + path).status_code, 200)

    def test_constraints_db_suma_estado_folio_y_eventos(self):
        obj = services.registrar_documento(self.payload(), self.finanzas)
        # QuerySet base elude guard ORM exclusivamente para probar constraints SQL.
        for changes in [{"monto_total": Decimal("1.00")}, {"monto_impuesto": Decimal("-1.00")}, {"estado": "REVERTIDO"}, {"folio_externo": "１２３"}, {"tipo_documento": "OTRO"}, {"fecha_vencimiento": hoy_santiago() - timedelta(days=1)}]:
            with self.assertRaises(IntegrityError), transaction.atomic():
                models.QuerySet(model=DocumentoCobro).filter(pk=obj.pk).update(**changes)
        event = obj.eventos.get()
        with self.assertRaises(IntegrityError), transaction.atomic():
            models.QuerySet(model=FinanzasEvento).filter(pk=event.pk).update(documento=None)
        obj.pk = None
        obj._state.adding = True
        obj.folio_externo = "999999"
        with self.assertRaises(IntegrityError) as caught, transaction.atomic():
            obj.save()
        self.assertEqual(caught.exception.__cause__.diag.constraint_name, "fin_documento_vigente_unico")

    def test_evento_snapshot_filtrado_sin_datos_privados(self):
        obj = services.registrar_documento(self.payload(), self.finanzas)
        event = obj.eventos.get()
        event.datos_nuevos = {"estado": "VIGENTE", "password": "oculto", "costo_hora_neto": "8000.00", "obra": True}
        self.assertEqual(FinanzasEventoSerializer(event).data["datos_nuevos"], {"estado": "VIGENTE"})
        with self.assertRaises(DjangoValidationError):
            FinanzasEvento.objects.create(documento=obj, actor=self.finanzas, tipo="DOCUMENTO_REGISTRADO", datos_nuevos={"password": "oculto"})
        result = self.client.get(f"{self.documentos_url}{obj.pk}/")
        for key in ["costo_total", "mano_obra_total", "costo_hora_neto", "justificacion", "descripcion_trabajo", "telefono", "correo", "sesion_version", "password"]:
            self.assertNotIn(key, str(result.data))

    def test_filtros_urls_y_paginacion_estrictos(self):
        self.registrar()
        for query in ["estado=x", "tipo_documento=x", "cliente=true", "obra=0", "page=0", "page=-1", "page=1.0", "page=abc", "page=1&page=2", "estado=VIGENTE&estado=REVERTIDO", "otro=x", "fecha_emision_desde=2026-02-30", "fecha_emision_desde=2026-02-01&fecha_emision_hasta=2020-01-01"]:
            self.assertEqual(self.client.get(self.documentos_url + "?" + query).status_code, 400, query)
        query = f"?estado=VIGENTE&tipo_documento=FACTURA_AFECTA&obra={self.obra.pk}&cliente={self.cliente.pk}&fecha_emision_desde=2020-01-01&fecha_emision_hasta={hoy_santiago()}"
        self.assertEqual(self.client.get(self.documentos_url + query).data["count"], 1)
        for identifier in ["0", "-1", "true", "9223372036854775808"]:
            self.assertEqual(self.client.get(f"{self.documentos_url}{identifier}/").status_code, 400)
        self.assertEqual(self.client.get(f"{self.documentos_url}999999/").status_code, 404)

    def test_listado_25_orden_estable_y_sin_n_mas_uno(self):
        for index in range(27):
            obj = services.registrar_documento(self.payload(folio_externo=str(index + 1)), self.finanzas)
            services.revertir_documento(obj.pk, {"motivo": "Corrección externa", "referencia_rectificacion_externa": f"Referencia {index}"}, self.finanzas)
        models.QuerySet(model=DocumentoCobro).update(registrado_en=DocumentoCobro.objects.order_by("id").first().registrado_en)
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(self.documentos_url)
        self.assertEqual(len(response.data["results"]), 25)
        self.assertEqual(response.data["count"], 27)
        self.assertEqual(len(self.client.get(self.documentos_url + "?page=2").data["results"]), 2)
        self.assertEqual([row["id"] for row in response.data["results"]], sorted([row["id"] for row in response.data["results"]], reverse=True))
        self.assertLessEqual(len(queries), 7)

    def test_elegibles_filtra_servidor_y_reversion_rehabilita(self):
        url = "/api/finanzas/obras-elegibles/"
        self.assertEqual(self.client.get(url).data["count"], 1)
        obj = services.registrar_documento(self.payload(), self.finanzas)
        self.assertEqual(self.client.get(url).data["count"], 0)
        services.revertir_documento(obj.pk, {"motivo": "Corrección", "referencia_rectificacion_externa": "Externo"}, self.finanzas)
        self.assertEqual(self.client.get(url).data["count"], 1)
        self.assertEqual(self.client.get(url + "?estado=FINALIZADA").status_code, 400)

    def test_elegibles_paginacion_y_proyeccion_sin_n_mas_uno(self):
        for _ in range(25):
            self.otra_finalizada()
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get("/api/finanzas/obras-elegibles/")
        self.assertEqual(response.data["count"], 26)
        self.assertEqual(len(response.data["results"]), 25)
        self.assertLessEqual(len(queries), 6)
        self.assertEqual(len(self.client.get("/api/finanzas/obras-elegibles/?page=2").data["results"]), 1)


def timezone_override_utc():
    from django.utils import timezone
    return timezone.override("UTC")


class SinCobroTests(FinanzasBase, TestCase):
    con_cortesia = True

    def setUp(self):
        self.preparar_finanzas()
        self.sin_cobro_url = f"/api/finanzas/obras/{self.obra.pk}/registrar-sin-cobro/"

    def test_cortesia_bloquea_documento_y_sin_cobro_no_es_ingreso(self):
        before = self.estado_persistido()
        self.assertEqual(self.registrar().data["code"], "cortesia_sin_cobro")
        state_url = f"/api/finanzas/obras/{self.obra.pk}/estado-financiero/"
        self.assertEqual(self.client.get(state_url).data["estado_financiero"], "PENDIENTE_REGISTRO_SIN_COBRO")
        result = self.client.post(self.sin_cobro_url, {"motivo_registro": " Archivo administrativo de garantía "}, format="json")
        self.assertEqual(result.status_code, 201, result.data)
        self.assertEqual(self.client.get(state_url).data["estado_financiero"], "SIN_COBRO")
        self.assertEqual(self.estado_persistido(), before)
        self.assertEqual(self.presupuesto.monto_neto, Decimal("2080.22"))
        self.assertFalse(DocumentoCobro.objects.exists())
        self.assertEqual(FinanzasEvento.objects.get().tipo, "SIN_COBRO_REGISTRADO")
        self.autenticar(self.gerencia)
        state = self.client.get(state_url)
        self.assertEqual(state.data["cierre_sin_cobro"]["eventos"][0]["tipo"], "SIN_COBRO_REGISTRADO")
        self.autenticar(self.finanzas)
        self.assertEqual(self.client.post(self.sin_cobro_url, {"motivo_registro": "Repetido"}, format="json").data["code"], "sin_cobro_ya_registrado")
        self.assertEqual(self.registrar().data["code"], "sin_cobro_ya_registrado")
        self.assertEqual(self.client.get("/api/finanzas/obras-elegibles/").data["count"], 0)
        self.assertNotIn("saldo", str(self.client.get(state_url).data))

    def test_contrato_estricto_y_rollback(self):
        for payload in [{}, {"motivo_registro": " "}, {"motivo_registro": "X", "cortesia": 1}, {"motivo_registro": "X", "monto": "0.00"}]:
            self.assertEqual(self.client.post(self.sin_cobro_url, payload, format="json").status_code, 400)
        with patch("apps.finanzas.services_documentos.evento", side_effect=RuntimeError("controlado")):
            with self.assertRaises(RuntimeError):
                services.registrar_sin_cobro(self.obra.pk, {"motivo_registro": "Garantía"}, self.finanzas)
        self.assertFalse(CierreSinCobro.objects.exists())
        self.assertFalse(FinanzasEvento.objects.exists())

    def test_sin_cobro_rechaza_obra_no_finalizada(self):
        Obra.objects.filter(pk=self.obra.pk).update(estado="EN_PROCESO", finalizado_en=None)
        result = self.client.post(self.sin_cobro_url, {"motivo_registro": "Intento prematuro"}, format="json")
        self.assertEqual(result.status_code, 409)
        self.assertEqual(result.data["code"], "obra_no_finalizada")
        self.assertFalse(CierreSinCobro.objects.exists())

    def test_no_oculta_documento_historico_revertido(self):
        # Documento histórico anterior a una cortesía: no encubrirlo con cierre.
        cortesia = CortesiaObra.objects.get(obra=self.obra)
        with patch("apps.finanzas.services_documentos.CortesiaObra.objects.filter") as mock:
            mock.return_value.exists.return_value = False
            obj = services.registrar_documento(self.payload(), self.finanzas)
        services.revertir_documento(obj.pk, {"motivo": "Externo", "referencia_rectificacion_externa": "Rectificación"}, self.finanzas)
        self.assertEqual(self.client.post(self.sin_cobro_url, {"motivo_registro": "Intento"}, format="json").data["code"], "documento_duplicado")
        self.assertEqual(CortesiaObra.objects.get(pk=cortesia.pk).justificacion, cortesia.justificacion)
