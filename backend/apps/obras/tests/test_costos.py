from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.db import connection
from django.utils import timezone

from apps.obras import services, services_costos as costos, services_gastos as gastos, services_turnos as turnos
from apps.obras.exceptions import CostosIncompletos, DatosInvalidos, SinCambios
from apps.obras.models import ControlCostosObra, CortesiaObra, CostoObraEvento, GastoObra, Obra, TurnoObra
from .test_gastos import GastosBase
from .test_turnos import foto


class CostosBase(GastosBase):
    def preparar(self):
        super().preparar()
        self.control_url = f"/api/obras/{self.obra.pk}/costos/control/"
        self.validar_url = f"/api/obras/{self.obra.pk}/costos/validar/"
        self.resumen_url = f"/api/obras/{self.obra.pk}/costos/resumen/"
        self.cortesia_url = f"/api/obras/{self.obra.pk}/cortesia-sin-cobro/"

    def control(self):
        return ControlCostosObra.objects.get(obra=self.obra)

    def crear_control(self):
        # Fixture explícita: ninguna consulta del servicio crea esta fila.
        return ControlCostosObra.objects.get_or_create(obra=self.obra)[0]

    def declarar(self, **cambios):
        datos = {"materiales_estado": "NO_APLICA", "materiales_justificacion": "No se utilizaron materiales",
                 "otros_estado": "NO_APLICA", "otros_justificacion": "Sin otros gastos", "motivo": "Revisión de rubros"}
        datos.update(cambios)
        return costos.declarar_rubros(self.obra, datos, self.supervisor)

    def abrir(self):
        return turnos.iniciar_turno(self.obra, {}, self.tecnico)

    def cerrar(self, turno, *, fotos=()):
        with patch("apps.obras.services_turnos.timezone.now", return_value=turno.iniciado_en + timedelta(seconds=3600)):
            return turnos.finalizar_turno(self.obra, turno.pk, {"descripcion_trabajo": "Trabajo acreditable"}, self.tecnico, fotos=fotos)

    def revisar(self, turno, decision="VALIDAR", tarifa="8000.00"):
        return turnos.revisar_turno(self.obra, turno.pk, {
            "decision": decision, "costo_hora_neto": tarifa, "motivo": "Contraste con evidencia",
        }, self.supervisor)

    def acreditar(self, tarifa="8000.00"):
        turno = self.abrir()
        self.cerrar(turno)
        return self.revisar(turno, tarifa=tarifa)

    def validar(self):
        return costos.validar_costos(self.obra, {"motivo": "Costos y evidencia revisados"}, self.supervisor)

    def marcar_validado(self):
        # Simula una marca previa para probar limpieza en TODAS las mutaciones,
        # incluso las que parten de un turno pendiente o abierto.
        control = self.crear_control()
        control.version_validada = control.version_actual
        control.validado_por = self.supervisor
        control.validado_en = timezone.now()
        control.save()
        return control

    def verificar_invalidacion(self, operacion):
        antes = self.marcar_validado()
        resultado = operacion()
        despues = self.control()
        self.assertEqual(despues.version_actual, antes.version_actual + 1)
        self.assertIsNone(despues.version_validada)
        self.assertIsNone(despues.validado_por_id)
        self.assertIsNone(despues.validado_en)
        return resultado


class ControlCostosTests(CostosBase, TestCase):
    def setUp(self):
        self.preparar()

    def test_control_inicial_y_lecturas_sin_incrementos(self):
        self.assertFalse(ControlCostosObra.objects.exists())
        primero = self.client.get(self.control_url)
        self.assertEqual(primero.status_code, 200)
        self.assertEqual(primero.data["version_actual"], 0)
        self.assertEqual(primero.data["materiales_estado"], "PENDIENTE")
        self.assertEqual(primero.data["otros_estado"], "PENDIENTE")
        self.assertEqual(primero.data["obra"], self.obra.pk)
        self.assertEqual(primero.data["materiales_justificacion"], "")
        self.assertEqual(primero.data["otros_justificacion"], "")
        self.assertFalse(primero.data["costos_validados"])
        for campo in ("id", "version_validada", "validado_por", "validado_en", "creado_en", "actualizado_en"):
            self.assertIsNone(primero.data[campo])
        for _ in range(2):
            self.assertEqual(self.client.get(self.control_url).data, primero.data)
            self.assertEqual(self.client.get(self.resumen_url).status_code, 200)
        self.assertFalse(ControlCostosObra.objects.exists())
        self.assertFalse(CostoObraEvento.objects.exists())

    def test_patch_noop_sin_control_no_inserta_filas(self):
        for datos in ({}, {"motivo": "Sin cambios"}, {"materiales_justificacion": "  ", "otros_justificacion": ""}):
            respuesta = self.client.patch(self.control_url, datos, format="json")
            self.assertEqual(respuesta.status_code, 200, respuesta.data)
            self.assertIsNone(respuesta.data["id"])
            self.assertEqual(respuesta.data["version_actual"], 0)
        self.assertFalse(ControlCostosObra.objects.exists())
        self.assertFalse(CostoObraEvento.objects.exists())

    def test_get_control_y_resumen_no_modifican_control_existente(self):
        self.declarar()
        antes = list(ControlCostosObra.objects.values())
        eventos = list(CostoObraEvento.objects.values())
        for _ in range(2):
            self.assertEqual(self.client.get(self.control_url).status_code, 200)
            self.assertEqual(self.client.get(self.resumen_url).status_code, 200)
        self.assertEqual(list(ControlCostosObra.objects.values()), antes)
        self.assertEqual(list(CostoObraEvento.objects.values()), eventos)

    def test_primera_escritura_efectiva_crea_control_unico(self):
        self.assertFalse(ControlCostosObra.objects.exists())
        datos = {"materiales_estado": "NO_APLICA", "materiales_justificacion": "Sin materiales", "motivo": "Revisión"}
        respuesta = self.client.patch(self.control_url, datos, format="json")
        self.assertEqual(respuesta.status_code, 200, respuesta.data)
        self.assertIsNotNone(respuesta.data["id"])
        self.assertIsNotNone(respuesta.data["creado_en"])
        self.assertEqual(respuesta.data["version_actual"], 1)
        self.assertEqual(ControlCostosObra.objects.count(), 1)
        self.assertEqual(self.client.patch(self.control_url, datos, format="json").data, respuesta.data)
        self.assertEqual(ControlCostosObra.objects.count(), 1)
        self.assertEqual(CostoObraEvento.objects.count(), 1)

    def test_primer_gasto_crea_control_sin_consulta_previa(self):
        self.crear_ok()
        self.assertEqual(ControlCostosObra.objects.count(), 1)
        self.assertEqual(self.control().version_actual, 1)

    def test_declaracion_no_aplica_y_actor_recuperable(self):
        resultado = self.declarar()
        self.assertEqual(resultado["version_actual"], 1)
        evento = CostoObraEvento.objects.get(tipo="DECLARACION")
        self.assertIsNone(evento.gasto_id)
        self.assertEqual(evento.control_id, self.control().pk)
        self.assertEqual(evento.registrado_por_id, self.supervisor.pk)
        self.assertTrue(evento.creado_en)
        self.assertEqual(evento.datos_anteriores["materiales_estado"], "PENDIENTE")
        self.assertEqual(evento.datos_nuevos["otros_estado"], "NO_APLICA")

    def test_declaracion_con_registros_y_sin_justificacion_obsoleta(self):
        self.crear_ok()
        self.crear_ok(tipo="TRANSPORTE")
        resultado = self.declarar(materiales_estado="CON_REGISTROS", otros_estado="CON_REGISTROS")
        self.assertEqual(resultado["materiales_justificacion"], "")
        self.assertEqual(resultado["otros_justificacion"], "")

    def test_declaraciones_incompatibles_sin_efectos(self):
        antes = self.crear_control()
        for datos in (
            {"materiales_estado": "CON_REGISTROS", "motivo": "Sin registros"},
            {"materiales_estado": "NO_APLICA", "motivo": "Sin justificación"},
            {"otros_estado": "NO_APLICA", "otros_justificacion": " "},
            {"otros_estado": "PENDIENTE"}, {"mano_obra_estado": "NO_APLICA"},
            {"materiales_estado": True}, {"version_actual": 8}, {"validado_por": self.supervisor.pk},
        ):
            with self.subTest(datos=datos):
                self.assertEqual(self.client.patch(self.control_url, datos, format="json").status_code, 400)
        self.crear_ok()
        respuesta = self.client.patch(self.control_url, {
            "materiales_estado": "NO_APLICA", "materiales_justificacion": "Incompatible", "motivo": "X",
        }, format="json")
        self.assertEqual(respuesta.status_code, 400)
        self.assertEqual(self.control().version_actual, antes.version_actual + 1)  # solo el gasto
        self.assertFalse(CostoObraEvento.objects.filter(tipo="DECLARACION").exists())

    def test_motivo_cambio_efectivo_y_noop_normalizado(self):
        self.declarar()
        antes = self.control()
        eventos = CostoObraEvento.objects.count()
        datos = {"materiales_estado": "NO_APLICA", "materiales_justificacion": "  No se utilizaron materiales  "}
        self.assertEqual(self.client.patch(self.control_url, datos, format="json").status_code, 200)
        self.assertEqual(ControlCostosObra.objects.get(pk=antes.pk).actualizado_en, antes.actualizado_en)
        self.assertEqual(self.control().version_actual, antes.version_actual)
        self.assertEqual(CostoObraEvento.objects.count(), eventos)
        datos["materiales_justificacion"] = "Otra justificación"
        self.assertEqual(self.client.patch(self.control_url, datos, format="json").status_code, 400)

    def test_nuevo_gasto_restablece_solo_rubro_incompatible(self):
        self.declarar()
        self.verificar_invalidacion(lambda: self.crear_ok())
        control = self.control()
        self.assertEqual(control.materiales_estado, "PENDIENTE")
        self.assertEqual(control.materiales_justificacion, "")
        self.assertEqual(control.otros_estado, "NO_APLICA")
        automatico = control.eventos.order_by("id").last()
        self.assertEqual(automatico.datos_nuevos["materiales_estado"], "PENDIENTE")

    def test_anular_ultimo_gasto_restablece_con_registros(self):
        gasto = self.crear_ok()
        self.declarar(materiales_estado="CON_REGISTROS")
        self.verificar_invalidacion(lambda: gastos.anular_gasto(self.obra, gasto.pk, {"motivo": "Duplicado"}, self.supervisor))
        self.assertEqual(self.control().materiales_estado, "PENDIENTE")

    def test_cambio_de_tipo_revisa_ambos_rubros(self):
        gasto = self.crear_ok()
        self.declarar(materiales_estado="CON_REGISTROS")
        self.verificar_invalidacion(lambda: gastos.editar_gasto(self.obra, gasto.pk, {"tipo": "OTRO", "motivo": "Clasificación"}, self.supervisor))
        self.assertEqual(self.control().materiales_estado, "PENDIENTE")
        self.assertEqual(self.control().otros_estado, "PENDIENTE")

    def test_gastos_cada_mutacion_incrementa_una_vez(self):
        gasto = self.verificar_invalidacion(lambda: self.crear_ok())
        self.verificar_invalidacion(lambda: gastos.editar_gasto(self.obra, gasto.pk, {"costo_unitario_neto": "900.00", "motivo": "Factura"}, self.supervisor))
        self.verificar_invalidacion(lambda: gastos.devolver_gasto(self.obra, gasto.pk, {"cantidad": "1.000", "fecha_devolucion": timezone.localdate(), "motivo": "Sobrante"}, self.supervisor))
        self.verificar_invalidacion(lambda: gastos.anular_gasto(self.obra, gasto.pk, {"motivo": "Duplicado"}, self.supervisor))

    def test_gasto_noop_y_rechazos_no_invalidan(self):
        gasto = self.crear_ok()
        antes = self.marcar_validado()
        gastos.editar_gasto(self.obra, gasto.pk, {"descripcion": gasto.descripcion}, self.supervisor)
        with self.assertRaises(DatosInvalidos):
            gastos.editar_gasto(self.obra, gasto.pk, {"cantidad": "0"}, self.supervisor)
        despues = self.control()
        self.assertEqual(despues.version_actual, antes.version_actual)
        self.assertTrue(despues.costos_validados)
        self.assertEqual(despues.actualizado_en, antes.actualizado_en)

    def test_fallo_evento_gasto_revierte_tambien_invalidacion(self):
        gasto = self.crear_ok()
        antes = self.marcar_validado()
        original = GastoObra.objects.values().get(pk=gasto.pk)
        eventos = CostoObraEvento.objects.count()
        with patch("apps.obras.services_gastos.CostoObraEvento.objects.create", side_effect=RuntimeError("Evento")):
            with self.assertRaises(RuntimeError):
                gastos.editar_gasto(self.obra, gasto.pk, {"descripcion": "Cambio", "motivo": "Documento"}, self.supervisor)
        self.assertEqual(GastoObra.objects.values().get(pk=gasto.pk), original)
        self.assertEqual(self.control().version_actual, antes.version_actual)
        self.assertTrue(self.control().costos_validados)
        self.assertEqual(CostoObraEvento.objects.count(), eventos)

    def test_version_participantes_y_reasignacion_una_sola_vez(self):
        miembro, _ = self.verificar_invalidacion(lambda: services.asignar_participante(self.obra, {"tecnico": self.otro_tecnico.pk, "motivo": "Apoyo"}, self.supervisor))
        self.verificar_invalidacion(lambda: services.desasignar_participante(self.obra, miembro.pk, self.supervisor, "Baja"))
        self.verificar_invalidacion(lambda: services.asignar_participante(self.obra, {"tecnico": self.otro_tecnico.pk, "motivo": "Vuelve"}, self.supervisor))
        self.verificar_invalidacion(lambda: services.cambiar_tecnico(self.obra, self.otro_tecnico.pk, self.supervisor, "Principal"))
        antes = self.control()
        with self.assertRaises(SinCambios):
            services.cambiar_tecnico(self.obra, self.otro_tecnico.pk, self.supervisor, "No cambia")
        self.assertEqual(self.control().version_actual, antes.version_actual)

    def test_ficha_operativa_sin_efecto_economico_no_incrementa(self):
        antes = self.marcar_validado()
        services.editar_obra(self.obra, {"descripcion": "Nueva ficha", "motivo": "Precisión"}, self.supervisor)
        self.assertEqual(self.control().version_actual, antes.version_actual)


class ValidacionCostosTests(CostosBase, TestCase):
    def setUp(self):
        self.preparar()

    def test_validacion_exitosa_y_repetida_sin_evento(self):
        self.acreditar()
        self.declarar()
        antes = self.control()
        resultado = self.validar()
        self.assertTrue(resultado["costos_validados"])
        self.assertEqual(resultado["version_validada"], antes.version_actual)
        self.assertEqual(resultado["version_actual"], antes.version_actual)
        self.assertEqual(resultado["validado_por"], self.supervisor.pk)
        evento = CostoObraEvento.objects.get(tipo="VALIDACION")
        self.assertEqual(evento.control_id, antes.pk)
        self.assertIsNone(evento.gasto_id)
        con_fecha = self.control().validado_en
        respuesta = self.client.post(self.validar_url, {"motivo": "Repetida"}, format="json")
        self.assertEqual(respuesta.status_code, 409)
        self.assertEqual(respuesta.data["code"], "sin_cambios")
        self.assertEqual(self.control().validado_en, con_fecha)
        self.assertEqual(CostoObraEvento.objects.filter(tipo="VALIDACION").count(), 1)
        self.obra.refresh_from_db()
        self.assertEqual(self.obra.estado, "EN_PROCESO")
        self.assertIsNone(self.obra.finalizado_en)

    def test_validacion_incompleta_estructurada_y_sin_evento(self):
        self.assertFalse(ControlCostosObra.objects.exists())
        respuesta = self.client.post(self.validar_url, {"motivo": "Revisión"}, format="json")
        self.assertEqual(respuesta.status_code, 409)
        self.assertEqual(respuesta.data["code"], "costos_incompletos")
        self.assertIn("sin_turno_acreditado", respuesta.data["pendientes"])
        self.assertIn("costo_total_no_positivo", respuesta.data["pendientes"])
        self.assertFalse(ControlCostosObra.objects.exists())
        self.assertFalse(CostoObraEvento.objects.exists())

    def test_turno_abierto_pendiente_y_observado_bloquean(self):
        self.declarar()
        turno = self.abrir()
        for paso in (lambda: None, lambda: self.cerrar(turno), lambda: self.revisar(turno, "OBSERVAR")):
            paso()
            with self.assertRaises(CostosIncompletos) as error:
                self.validar()
            self.assertIn("turnos_sin_acreditar", error.exception.pendientes)
        self.assertFalse(CostoObraEvento.objects.filter(tipo="VALIDACION").exists())

    def test_tarifa_cero_y_total_cero_rechazado(self):
        self.acreditar(tarifa="0.00")
        self.declarar()
        with self.assertRaises(CostosIncompletos) as error:
            self.validar()
        self.assertIn("costo_total_no_positivo", error.exception.pendientes)

    def test_responsable_inactivo_o_sin_membresia_bloquea(self):
        self.acreditar()
        self.declarar()
        self.tecnico.is_active = False
        self.tecnico.save()
        with self.assertRaises(CostosIncompletos) as error:
            self.validar()
        self.assertIn("responsable_no_elegible", error.exception.pendientes)

    def test_validacion_fallida_retira_marca_previa_obsoleta(self):
        self.acreditar()
        self.declarar()
        self.validar()
        antes = self.control()
        self.tecnico.is_active = False
        self.tecnico.save()
        with self.assertRaises(CostosIncompletos):
            self.validar()
        nuevo = self.control()
        self.assertIsNone(nuevo.version_validada)
        self.assertIsNone(nuevo.validado_por_id)
        self.assertIsNone(nuevo.validado_en)
        self.assertEqual(nuevo.version_actual, antes.version_actual)
        self.assertEqual(CostoObraEvento.objects.filter(tipo="VALIDACION").count(), 1)

    def test_devolucion_acumulada_sin_respaldo_bloquea_validacion(self):
        self.acreditar()
        gasto = self.crear_ok()
        self.declarar(materiales_estado="CON_REGISTROS")
        # SQL preserva CHECK de cantidades pero no el historial cruzado.
        GastoObra.objects.filter(pk=gasto.pk).update(cantidad_devuelta=Decimal("1.000"))
        with self.assertRaises(CostosIncompletos) as error:
            self.validar()
        self.assertIn("gasto_inconsistente", error.exception.pendientes)

    def test_fecha_excepcional_motivada_sigue_acreditable(self):
        self.acreditar()
        gasto = self.crear_ok()
        gastos.editar_gasto(self.obra, gasto.pk, {
            "fecha_gasto": timezone.localdate() - timedelta(days=2), "motivo": "Corrección documental",
        }, self.supervisor)
        self.declarar(materiales_estado="CON_REGISTROS")
        self.assertTrue(self.validar()["costos_validados"])

    def test_validacion_suspendida_es_provisional_sin_finalizar(self):
        self.acreditar()
        self.declarar()
        services.suspender_obra(self.obra, self.supervisor, "Pausa")
        self.assertTrue(self.validar()["costos_validados"])
        self.obra.refresh_from_db()
        self.assertEqual(self.obra.estado, "SUSPENDIDA")
        self.assertIsNone(self.obra.finalizado_en)
        self.assertTrue(self.client.get(self.resumen_url).data["provisional"])

    def test_validacion_y_declaraciones_rechazan_server_managed(self):
        for campo, valor in (("version_actual", 1), ("costos_completos", True), ("costo_total", "99.00"), ("estado", "VALIDADO"), ("obra", self.obra.pk)):
            with self.subTest(campo=campo):
                self.assertEqual(self.client.post(self.validar_url, {"motivo": "X", campo: valor}, format="json").status_code, 400)
        self.assertEqual(self.client.post(self.validar_url, {}, format="json").status_code, 400)

    def test_estados_no_habilitados_y_lecturas(self):
        for estado in ("PLANIFICADA", "FINALIZADA", "CANCELADA"):
            self.cambiar_estado(self.obra, estado)
            self.assertEqual(self.client.get(self.control_url).status_code, 200)
            self.assertEqual(self.client.get(self.resumen_url).status_code, 200)
            self.assertEqual(self.client.patch(self.control_url, {"materiales_estado": "NO_APLICA", "materiales_justificacion": "X", "motivo": "X"}, format="json").status_code, 409)
            self.assertEqual(self.client.post(self.validar_url, {"motivo": "X"}, format="json").status_code, 409)
            self.assertEqual(self.client.post(self.cortesia_url, {"justificacion": "X"}, format="json").status_code, 409)

    def test_rollback_validacion_y_declaracion(self):
        self.acreditar()
        self.declarar()
        antes = costos.snapshot(self.control())
        with patch("apps.obras.services_costos._evento", side_effect=RuntimeError("Evento")):
            with self.assertRaises(RuntimeError):
                self.validar()
            with self.assertRaises(RuntimeError):
                self.declarar(materiales_justificacion="Cambio real")
        self.assertEqual(costos.snapshot(self.control()), antes)


class ResumenCortesiaTests(CostosBase, TestCase):
    def setUp(self):
        self.preparar()

    def test_suma_decimal_por_registro_y_exclusion_anulados(self):
        self.crear_ok(cantidad="0.100", costo_unitario_neto="0.05")
        self.crear_ok(cantidad="0.100", costo_unitario_neto="0.05")
        self.crear_ok(tipo="OTRO", cantidad="0.333", costo_unitario_neto="3.00")
        anulado = self.crear_ok()
        gastos.anular_gasto(self.obra, anulado.pk, {"motivo": "Duplicado"}, self.supervisor)
        self.acreditar()
        datos = self.client.get(self.resumen_url).data
        self.assertEqual(datos["materiales_total"], "0.02")
        self.assertEqual(datos["otros_total"], "1.00")
        self.assertEqual(datos["mano_obra_total"], "8000.00")
        self.assertEqual(datos["costo_total"], "8001.02")
        self.assertTrue(datos["provisional"])

    def test_material_totalmente_devuelto_sigue_con_registros(self):
        gasto = self.crear_ok()
        gastos.devolver_gasto(self.obra, gasto.pk, {"cantidad": "2.500", "fecha_devolucion": timezone.localdate(), "motivo": "Todo sobrante"}, self.supervisor)
        self.declarar(materiales_estado="CON_REGISTROS")
        self.assertEqual(self.client.get(self.resumen_url).data["materiales_total"], "0.00")
        self.acreditar()
        self.assertTrue(self.validar()["costos_validados"])
        with self.assertRaises(DatosInvalidos):
            self.declarar()

    def test_turnos_pendientes_y_observados_excluidos_del_resumen(self):
        self.acreditar()
        turno = self.abrir()
        self.cerrar(turno)
        self.assertEqual(self.client.get(self.resumen_url).data["mano_obra_total"], "8000.00")
        self.revisar(turno, "OBSERVAR")
        self.assertEqual(self.client.get(self.resumen_url).data["mano_obra_total"], "8000.00")

    def test_resumen_sin_consultas_por_fila(self):
        self.crear_control()
        with CaptureQueriesContext(connection) as primera:
            costos.resumen_costos(self.obra, self.supervisor)
        for _ in range(8):
            self.crear_ok()
        self.acreditar()
        with CaptureQueriesContext(connection) as segunda:
            costos.resumen_costos(self.obra, self.supervisor)
        self.assertEqual(len(segunda), len(primera))

    def test_contrato_estricto_cortesia(self):
        for datos in ({}, {"justificacion": " "}, {"justificacion": True},
                      {"justificacion": "X", "tipo": "SIN_COBRO"},
                      {"justificacion": "X", "autorizado_por": self.supervisor.pk},
                      {"justificacion": "X", "obra": self.obra.pk},
                      {"justificacion": "X", "costo_total": "0.00"}):
            self.assertEqual(self.client.post(self.cortesia_url, datos, format="json").status_code, 400)
        self.assertFalse(CortesiaObra.objects.exists())

    def test_cortesia_no_altera_costos_ni_presupuesto(self):
        gasto = self.crear_ok()
        self.acreditar()
        self.declarar(materiales_estado="CON_REGISTROS")
        self.validar()
        previo = self.client.get(self.resumen_url).data
        presupuesto = type(self.presupuesto).objects.values().get(pk=self.presupuesto.pk)
        gasto_antes = GastoObra.objects.values().get(pk=gasto.pk)
        turnos_antes = list(TurnoObra.objects.values())
        self.verificar_invalidacion(lambda: costos.registrar_cortesia(self.obra, {"justificacion": "Atención excepcional"}, self.supervisor))
        nuevo = self.client.get(self.resumen_url).data
        self.assertEqual(nuevo["costo_total"], previo["costo_total"])
        self.assertTrue(nuevo["cortesia_sin_cobro"])
        self.assertFalse(nuevo["costos_validados"])
        self.assertEqual(GastoObra.objects.values().get(pk=gasto.pk), gasto_antes)
        self.assertEqual(list(TurnoObra.objects.values()), turnos_antes)
        self.assertEqual(type(self.presupuesto).objects.values().get(pk=self.presupuesto.pk), presupuesto)

    def test_cortesia_incompleta_no_valida_costos(self):
        self.assertEqual(self.client.post(self.cortesia_url, {"justificacion": "Cortesía excepcional"}, format="json").status_code, 200)
        self.assertEqual(self.client.get(self.resumen_url).data["costo_total"], "0.00")
        self.assertEqual(self.client.post(self.validar_url, {"motivo": "Revisión"}, format="json").status_code, 409)

    def test_rectificacion_cortesia_y_duplicacion(self):
        costos.registrar_cortesia(self.obra, {"justificacion": "Primera"}, self.supervisor)
        antes = self.control()
        self.assertEqual(self.client.post(self.cortesia_url, {"justificacion": "Primera"}, format="json").status_code, 409)
        self.assertEqual(self.control().version_actual, antes.version_actual)
        for datos in ({"justificacion": "Nueva"}, {"justificacion": "Nueva", "motivo": "Nueva"}):
            self.assertEqual(self.client.post(self.cortesia_url, datos, format="json").status_code, 400)
        self.verificar_invalidacion(lambda: costos.registrar_cortesia(self.obra, {"justificacion": "Nueva", "motivo": "Corrección documentada"}, self.supervisor))
        self.assertEqual(CortesiaObra.objects.count(), 1)
        eventos = list(CostoObraEvento.objects.filter(tipo="CORTESIA").order_by("id"))
        self.assertEqual(len(eventos), 2)
        self.assertEqual(eventos[1].datos_anteriores["justificacion"], "Primera")
        self.assertEqual(eventos[1].datos_nuevos["justificacion"], "Nueva")

    def test_cortesia_rollback_no_deja_constancia_ni_version(self):
        antes = self.crear_control()
        with patch("apps.obras.services_costos._evento", side_effect=RuntimeError("Fallo")):
            with self.assertRaises(RuntimeError):
                costos.registrar_cortesia(self.obra, {"justificacion": "Atención"}, self.supervisor)
        self.assertFalse(CortesiaObra.objects.exists())
        self.assertEqual(self.control().version_actual, antes.version_actual)
        self.assertFalse(CostoObraEvento.objects.exists())

    def test_proyeccion_finanzas_exacta_y_permisos_roles_superusuarios(self):
        campos_af = {"obra", "materiales_total", "otros_total", "mano_obra_total", "costo_total", "costos_validados", "cortesia_sin_cobro"}
        for usuario in (self.gerencia, self.finanzas, self.supervisor, self.tecnico):
            usuario.is_superuser = True
            usuario.save()
            self.autenticar(usuario)
            autorizado = usuario in (self.gerencia, self.supervisor)
            self.assertEqual(self.client.get(self.control_url).status_code, 200 if autorizado else 403)
            self.assertEqual(self.client.get(self.url_historial).status_code, 200 if autorizado else 403)
            resumen = self.client.get(self.resumen_url)
            self.assertEqual(resumen.status_code, 403 if usuario == self.tecnico else 200)
            if usuario == self.finanzas:
                self.assertEqual(set(resumen.data), campos_af)
            if usuario != self.supervisor:
                self.assertEqual(self.client.patch(self.control_url, {}, format="json").status_code, 403)
                self.assertEqual(self.client.post(self.validar_url, {"motivo": "X"}, format="json").status_code, 403)
                self.assertEqual(self.client.post(self.cortesia_url, {"justificacion": "X"}, format="json").status_code, 403)

    def test_tecnico_sin_campos_economicos_en_obras_y_turnos(self):
        self.acreditar()
        self.autenticar(self.tecnico)
        for ruta in (f"/api/obras/{self.obra.pk}/", f"/api/obras/{self.obra.pk}/turnos/"):
            texto = str(self.client.get(ruta).data)
            for campo in ("costo_hora_neto", "costo_total", "version_actual", "cortesia_sin_cobro", "control_costos"):
                self.assertNotIn(campo, texto)

    def test_http_autenticacion_recursos_metodos_y_sin_finalizacion(self):
        for ruta in (self.control_url, self.resumen_url):
            self.assertEqual(self.client.delete(ruta).status_code, 405)
            self.assertEqual(self.client.put(ruta, {}, format="json").status_code, 405)
            self.assertEqual(self.client.get(ruta + "?rol=GERENCIA").status_code, 400)
        self.assertEqual(self.client.get("/api/obras/999999/costos/control/").status_code, 404)
        for accion in ("finalizar", "cancelar"):
            self.assertEqual(self.client.post(f"/api/obras/{self.obra.pk}/{accion}/", {}, format="json").status_code, 404)
        self.client.credentials()
        for ruta in (self.control_url, self.resumen_url):
            self.assertEqual(self.client.get(ruta).status_code, 401)


class TurnosInvalidacionTests(CostosBase, TestCase):
    def setUp(self):
        self.preparar()
        temporal = TemporaryDirectory()
        self.addCleanup(temporal.cleanup)
        configuracion = override_settings(EVIDENCIAS_ROOT=temporal.name)
        configuracion.enable()
        self.addCleanup(configuracion.disable)
        self.raiz = Path(temporal.name)

    def test_cada_operacion_de_turno_y_adjuntos_incrementa_una_vez(self):
        turno = self.verificar_invalidacion(self.abrir)
        self.verificar_invalidacion(lambda: self.cerrar(turno, fotos=[foto()]))
        self.verificar_invalidacion(lambda: self.revisar(turno, "OBSERVAR"))
        self.verificar_invalidacion(lambda: turnos.subsanar_turno(self.obra, turno.pk, {}, self.tecnico, fotos=[foto()]))
        self.verificar_invalidacion(lambda: self.revisar(turno))
        self.verificar_invalidacion(lambda: turnos.corregir_turno(self.obra, turno.pk, {"duracion_ajustada_segundos": 1800, "motivo": "Tiempo contrastado"}, self.supervisor))
        antes = self.marcar_validado()
        with self.assertRaises(SinCambios):
            turnos.corregir_turno(self.obra, turno.pk, {"duracion_ajustada_segundos": 1800, "motivo": "Igual"}, self.supervisor)
        self.assertEqual(self.control().version_actual, antes.version_actual)
        self.assertTrue(self.control().costos_validados)

    def test_administrativo_sin_ajuste_bloquea_y_verificado_acredita(self):
        turno = self.abrir()
        with patch("apps.obras.services_turnos.timezone.now", return_value=turno.iniciado_en + timedelta(seconds=3600)):
            self.verificar_invalidacion(lambda: turnos.cerrar_administrativamente(self.obra, turno.pk, {"descripcion_trabajo": "Verificado parcialmente", "motivo": "Sin acceso"}, self.supervisor))
        self.declarar()
        with self.assertRaises(CostosIncompletos):
            self.validar()
        turnos.corregir_turno(self.obra, turno.pk, {"duracion_ajustada_segundos": 1800, "motivo": "Duración verificada"}, self.supervisor)
        self.revisar(turno)
        self.assertTrue(self.validar()["costos_validados"])
        self.assertEqual(self.client.get(self.resumen_url).data["mano_obra_total"], "4000.00")

    def test_rollback_fotografias_y_version_si_falla_evento(self):
        turno = self.abrir()
        antes = self.control()
        with patch("apps.obras.services_turnos.TurnoObraEvento.objects.create", side_effect=RuntimeError("Evento")):
            with self.assertRaises(RuntimeError):
                self.cerrar(turno, fotos=[foto()])
        self.assertEqual(self.control().version_actual, antes.version_actual)
        self.assertEqual(list(self.raiz.iterdir()), [])
        turno.refresh_from_db()
        self.assertEqual(turno.estado_revision, "ABIERTO")

    def test_fotografia_ausente_bloquea_pero_cero_fotos_no(self):
        turno = self.abrir()
        self.cerrar(turno, fotos=[foto()])
        self.revisar(turno)
        self.declarar()
        self.assertTrue(self.validar()["costos_validados"])
        for archivo in self.raiz.iterdir():
            archivo.unlink()
        with self.assertRaises(CostosIncompletos) as error:
            self.validar()
        self.assertIn("evidencia_inconsistente", error.exception.pendientes)
        self.assertFalse(self.control().costos_validados)


class ConstraintsCostosTests(CostosBase, TestCase):
    def setUp(self):
        self.preparar()

    def test_constraints_control_version_y_validacion(self):
        control = self.crear_control()
        for cambios in ({"version_actual": -1}, {"version_validada": 1}, {"validado_por": self.supervisor},
                        {"materiales_estado": "INVALIDO"}, {"otros_estado": "NO_APLICA"},
                        {"materiales_justificacion": "No corresponde"}):
            with self.subTest(cambios=cambios), self.assertRaises(IntegrityError), transaction.atomic():
                ControlCostosObra.objects.filter(pk=control.pk).update(**cambios)
        with self.assertRaises(IntegrityError), transaction.atomic():
            ControlCostosObra.objects.bulk_create([ControlCostosObra(obra=self.obra)])

    def test_eventos_tipo_y_recurso_obligatorio_en_postgresql(self):
        control = self.crear_control()
        gasto = self.crear_ok()
        cortesia = CortesiaObra.objects.create(obra=self.obra, justificacion="Atención", autorizado_por=self.supervisor)
        for tipo in ("ALTA", "CORRECCION", "DEVOLUCION", "ANULACION", "DECLARACION", "VALIDACION", "CORTESIA"):
            recurso = {"gasto": gasto} if tipo in ("ALTA", "CORRECCION", "DEVOLUCION", "ANULACION") else {"cortesia": cortesia} if tipo == "CORTESIA" else {"control": control}
            base = dict(obra=self.obra, tipo=tipo, registrado_por=self.supervisor, motivo="Prueba", datos_nuevos={"id": 1})
            CostoObraEvento.objects.create(**base, **recurso)
            for incorrecto in ({}, {"gasto": gasto, "control": control}, {"gasto": gasto, "cortesia": cortesia}):
                with self.subTest(tipo=tipo, incorrecto=incorrecto), self.assertRaises(IntegrityError), transaction.atomic():
                    CostoObraEvento.objects.bulk_create([CostoObraEvento(**base, **incorrecto)])

    def test_evento_no_admite_entidad_de_otra_obra(self):
        otra = self.otra_obra()
        control = self.crear_control()
        with self.assertRaises(ValidationError):
            CostoObraEvento.objects.create(obra=otra, control=control, tipo="DECLARACION", registrado_por=self.supervisor, motivo="X", datos_nuevos={"id": control.pk})

    def test_cortesia_constraints_y_unicidad(self):
        cortesia = CortesiaObra.objects.create(obra=self.obra, justificacion="Atención", autorizado_por=self.supervisor)
        for cambios in ({"tipo": "OTRO"}, {"justificacion": ""}, {"justificacion": " espacio "}):
            with self.assertRaises(IntegrityError), transaction.atomic():
                CortesiaObra.objects.filter(pk=cortesia.pk).update(**cambios)
        with self.assertRaises(IntegrityError), transaction.atomic():
            CortesiaObra.objects.bulk_create([CortesiaObra(obra=self.obra, justificacion="Otra", autorizado_por=self.supervisor)])
