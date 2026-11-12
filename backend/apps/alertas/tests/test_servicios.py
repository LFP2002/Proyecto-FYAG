from datetime import date, datetime, timedelta, timezone as utc
from io import StringIO
from unittest.mock import patch
from uuid import uuid4

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.management import call_command, CommandError
from django.db import connection, IntegrityError, models, transaction
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.alertas import services
from apps.alertas.consultas import condicion
from apps.alertas.models import Alerta, AlertaEvento, EstadoReconciliacion
from apps.alertas.serializers import inicio_civil
from apps.comercial import services_presupuestos as comercial
from apps.comercial.models import Presupuesto
from apps.obras import services as obras, services_turnos as turnos
from apps.finanzas import services_documentos as documentos, services_pagos as pagos
from apps.finanzas.tests.base import FinanzasBase
from apps.finanzas.models import DocumentoCobro
from apps.finanzas.validaciones import hoy_santiago
from .base import AlertasBase


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class CicloAlertasTests(AlertasBase, TestCase):
    def setUp(self):
        self.preparar_alertas()

    def test_presupuesto_transiciones_reales_crean_resuelven_rechazo_y_aprobacion(self):
        for decision in ("aprobar_gerencia", "rechazar_gerencia"):
            p = self.pendiente()
            self.assertFalse(condicion("PRESUPUESTO_PENDIENTE_GERENCIA", p.pk))
            with self.captureOnCommitCallbacks(execute=True):
                comercial.enviar_gerencia(p, self.finanzas)
            alerta = Alerta.objects.get(tipo="PRESUPUESTO_PENDIENTE_GERENCIA", recurso_id=p.pk)
            self.assertEqual(alerta.estado, "PENDIENTE")
            with self.captureOnCommitCallbacks(execute=True):
                getattr(comercial, decision)(p, self.gerencia, "Decisión revisada")
            alerta.refresh_from_db()
            self.assertEqual(alerta.estado, "RESUELTA")
            self.assertEqual(set(alerta.eventos.values_list("tipo", flat=True)), {"CREACION", "RESOLUCION"})
            self.assertTrue(all(e.actor_id is None and e.motivo == "" for e in alerta.eventos.all()))

    def test_obra_dos_roles_atencion_independiente_y_generaciones(self):
        a = self.suspender()
        s = Alerta.objects.get(tipo="OBRA_SUSPENDIDA", rol_destinatario="SUPERVISOR_OBRAS")
        services.atender(self.gerencia, a.pk, "  Coordinado  ")
        s.refresh_from_db()
        self.assertEqual(s.estado, "PENDIENTE")
        services.atender(self.supervisor, s.pk, "Equipo informado")
        with self.captureOnCommitCallbacks(execute=True):
            obras.reanudar_obra(self.obra, self.supervisor, "Continuar")
        self.assertEqual(Alerta.objects.filter(estado="RESUELTA").count(), 2)
        a.refresh_from_db()
        self.assertEqual(a.motivo_atencion, "Coordinado")
        self.assertEqual(a.atendida_por_id, self.gerencia.pk)
        with self.captureOnCommitCallbacks(execute=True):
            obras.suspender_obra(self.obra, self.supervisor, "Segunda pausa")
        self.assertEqual(Alerta.objects.filter(generacion=2, estado="PENDIENTE").count(), 2)
        self.assertEqual(AlertaEvento.objects.count(), 8)

    def test_turno_cierre_observacion_subsanacion_validacion_correccion(self):
        t = self.abrir()
        self.assertFalse(condicion("TURNO_PENDIENTE_REVISION", t.pk))
        with self.captureOnCommitCallbacks(execute=True):
            self.cerrar(t)
        a = Alerta.objects.get(tipo="TURNO_PENDIENTE_REVISION")
        with self.captureOnCommitCallbacks(execute=True):
            turnos.revisar_turno(self.obra, t.pk, {"decision": "OBSERVAR", "motivo": "Aclarar"}, self.supervisor)
        a.refresh_from_db()
        self.assertEqual(a.estado, "RESUELTA")
        with self.captureOnCommitCallbacks(execute=True):
            turnos.subsanar_turno(self.obra, t.pk, {"descripcion_trabajo": "Aclaración"}, self.tecnico)
        self.assertTrue(Alerta.objects.filter(tipo=a.tipo, generacion=2, estado="PENDIENTE").exists())
        with self.captureOnCommitCallbacks(execute=True):
            turnos.revisar_turno(self.obra, t.pk, {"decision": "VALIDAR", "motivo": "Revisado", "costo_hora_neto": "10.00"}, self.supervisor)
        self.assertFalse(Alerta.objects.filter(tipo=a.tipo, estado="PENDIENTE").exists())
        with self.captureOnCommitCallbacks(execute=True):
            turnos.corregir_turno(self.obra, t.pk, {"motivo": "Corrección", "costo_hora_neto": "20.00"}, self.supervisor)
        self.assertTrue(Alerta.objects.filter(tipo=a.tipo, generacion=3, estado="PENDIENTE").exists())

    def test_reconciliar_idempotente_no_duplica_eventos_y_actualiza_comprobacion_controlada(self):
        a = self.suspender()
        antes = list(AlertaEvento.objects.values())
        for _ in range(3):
            services.reconciliar()
        self.assertEqual(list(AlertaEvento.objects.values()), antes)
        with patch("apps.alertas.services.hora_servidor", return_value=timezone.now() + timedelta(seconds=61)):
            services.reconciliar()
        a.refresh_from_db()
        self.assertGreater(a.ultima_comprobacion_en, a.creado_en)
        self.assertEqual(a.generacion, 1)

    def test_atencion_no_modifica_dominio_y_conflictos(self):
        a = self.suspender()
        self.obra.refresh_from_db()
        antes = self.obra.__dict__.copy()
        services.atender(self.gerencia, a.pk, "Revisar")
        with self.assertRaises(services.ConflictoAlerta) as cm:
            services.atender(self.gerencia, a.pk, "Otra vez")
        self.assertEqual(cm.exception.detail["code"], "alerta_ya_atendida")
        self.obra.refresh_from_db()
        self.assertEqual(self.obra.__dict__, antes)
        obras.reanudar_obra(self.obra, self.supervisor, "Continuar")
        services.reconciliar()
        with self.assertRaises(services.ConflictoAlerta) as cm:
            services.atender(self.gerencia, a.pk, "Otra vez")
        self.assertEqual(cm.exception.detail["code"], "alerta_resuelta")

    def test_causa_desactualizada_no_se_resuelve_al_atender(self):
        a = self.suspender()
        obras.reanudar_obra(self.obra, self.supervisor, "Continuar")
        with self.assertRaises(services.ConflictoAlerta) as cm:
            services.atender(self.gerencia, a.pk, "Revisar")
        self.assertEqual(cm.exception.detail["code"], "alerta_desactualizada")
        a.refresh_from_db()
        self.assertEqual(a.estado, "PENDIENTE")

    def test_callback_fallido_no_reversion_y_recuperacion(self):
        with patch("apps.alertas.services.reconciliar_recurso", side_effect=RuntimeError("SECRETO")), self.assertLogs("apps.alertas.services", level="ERROR") as logs:
            with self.captureOnCommitCallbacks(execute=True):
                obras.suspender_obra(self.obra, self.supervisor, "Pausa")
        self.assertNotIn("SECRETO", str(logs.output))
        self.obra.refresh_from_db()
        self.assertEqual(self.obra.estado, "SUSPENDIDA")
        self.assertFalse(Alerta.objects.exists())
        services.reconciliar()
        self.assertEqual(Alerta.objects.count(), 2)

    def test_on_commit_no_consulta_antes_del_commit_y_rollback_descarta(self):
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            obras.suspender_obra(self.obra, self.supervisor, "Pausa")
        self.assertTrue(callbacks)
        self.assertFalse(Alerta.objects.exists())
        with self.captureOnCommitCallbacks(execute=True) as descartadas:
            with self.assertRaises(RuntimeError):
                with transaction.atomic():
                    services.notificar_despues_commit("OBRA_SUSPENDIDA", self.obra.pk)
                    raise RuntimeError()
        self.assertFalse(descartadas)

    def test_historial_append_only_modelos_y_querysets(self):
        a = self.suspender()
        e = a.eventos.get()
        for obj in (a, e):
            for accion in (obj.save, obj.delete, lambda obj=obj: type(obj).objects.filter(pk=obj.pk).update(estado_nuevo="X"), lambda obj=obj: type(obj).objects.filter(pk=obj.pk).delete(), lambda obj=obj: type(obj).objects.bulk_update([obj], ["id"])):
                with self.assertRaises(DjangoValidationError):
                    accion()

    def test_constraints_sql_catalogo_estado_unicidad_y_fechas(self):
        a = self.suspender()
        for cambios in [{"tipo": "INVENTADA"}, {"recurso_tipo": "PRESUPUESTO"}, {"rol_destinatario": "ADMINISTRADOR_TI"}, {"generacion": 0}, {"recurso_id": 0}, {"estado": "ATENDIDA"}, {"estado": "RESUELTA"}, {"atendida_en": timezone.now()}, {"ultima_comprobacion_en": a.creado_en - timedelta(seconds=1)}]:
            with self.assertRaises(IntegrityError), transaction.atomic():
                models.QuerySet(model=Alerta).filter(pk=a.pk).update(**cambios)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Alerta.objects.create(tipo=a.tipo, recurso_tipo=a.recurso_tipo, recurso_id=a.recurso_id, rol_destinatario=a.rol_destinatario, generacion=2)
        e = a.eventos.get()
        with self.assertRaises(IntegrityError), transaction.atomic():
            models.QuerySet(model=AlertaEvento).filter(pk=e.pk).update(tipo="ATENCION")
        with self.assertRaises(IntegrityError), transaction.atomic():
            models.QuerySet(model=AlertaEvento).filter(pk=e.pk).update(tipo="RESOLUCION", estado_nuevo="RESUELTA", estado_anterior=None)

    def test_comando_once_y_fallo_no_actualiza_salud(self):
        self.suspender()
        output = StringIO()
        call_command("reconciliar_alertas", once=True, stdout=output)
        self.assertIn('"reconciliacion": "correcta"', output.getvalue())
        antes = EstadoReconciliacion.objects.get().ultima_correcta_en
        with patch("apps.alertas.management.commands.reconciliar_alertas.reconciliar", side_effect=RuntimeError("SECRETO")), self.assertLogs("apps.alertas.management.commands.reconciliar_alertas", level="ERROR") as logs:
            with self.assertRaises(CommandError) as cm:
                call_command("reconciliar_alertas", once=True)
        self.assertNotIn("SECRETO", str(cm.exception) + str(logs.output))
        self.assertEqual(EstadoReconciliacion.objects.get().ultima_correcta_en, antes)
        call_command("reconciliar_alertas", once=True, stdout=StringIO())

    def test_comando_rechaza_cadencia_invalida(self):
        for intervalo in (0, -1, 3601):
            with self.assertRaises(CommandError):
                call_command("reconciliar_alertas", once=True, interval=intervalo)

    def test_loop_recupera_error_y_detiene_limpiamente(self):
        class Parada:
            esperas = 0
            def is_set(self):
                return self.esperas == 2
            def set(self):
                self.esperas = 2
            def wait(self, segundos):
                self.esperas += 1
        parada = Parada()
        real = services.reconciliar
        contador = []
        def ciclo():
            contador.append(1)
            if len(contador) == 1:
                raise RuntimeError("SECRETO")
            return real()
        with patch("apps.alertas.management.commands.reconciliar_alertas.Event", return_value=parada), patch("apps.alertas.management.commands.reconciliar_alertas.signal.signal"), patch("apps.alertas.management.commands.reconciliar_alertas.reconciliar", side_effect=ciclo), self.assertLogs("apps.alertas.management.commands.reconciliar_alertas", level="ERROR"):
            call_command("reconciliar_alertas", stdout=StringIO())
        self.assertEqual(len(contador), 2)
        self.assertIsNotNone(EstadoReconciliacion.objects.get().ultima_correcta_en)

    def test_fallo_parcial_no_marca_ciclo_completo_y_reintento_recupera(self):
        obras.suspender_obra(self.obra, self.supervisor, "Pausa")
        original = services.reconciliar_recurso
        def fallar(tipo, pk):
            resultado = original(tipo, pk)
            if tipo == "OBRA_SUSPENDIDA":
                raise RuntimeError()
            return resultado
        with patch.object(services, "reconciliar_recurso", side_effect=fallar):
            with self.assertRaises(RuntimeError):
                services.reconciliar()
        self.assertFalse(EstadoReconciliacion.objects.exists())
        services.reconciliar()
        self.assertEqual(AlertaEvento.objects.count(), 2)

    def test_evento_fallido_revierte_alerta_y_reintento_crea_una_generacion(self):
        obras.suspender_obra(self.obra, self.supervisor, "Pausa")
        with patch("apps.alertas.services._evento", side_effect=RuntimeError()):
            with self.assertRaises(RuntimeError):
                services.reconciliar_recurso("OBRA_SUSPENDIDA", self.obra.pk)
        self.assertFalse(Alerta.objects.exists())
        services.reconciliar_recurso("OBRA_SUSPENDIDA", self.obra.pk)
        self.assertEqual(Alerta.objects.count(), 2)
        self.assertEqual(AlertaEvento.objects.count(), 2)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class CobranzaAlertasTests(FinanzasBase, TestCase):
    def setUp(self):
        self.preparar_finanzas()
        ayer = hoy_santiago() - timedelta(days=1)
        self.doc = documentos.registrar_documento(self.payload(fecha_emision=ayer.isoformat(), fecha_vencimiento=ayer.isoformat()), self.finanzas)

    def pagar(self, monto):
        return pagos.registrar_pago(self.doc.pk, {"monto": monto, "fecha_pago": hoy_santiago().isoformat(), "medio": "EFECTIVO", "referencia_respaldo": "Respaldo"}, self.finanzas, str(uuid4()))[0]

    def test_cobranza_parcial_total_anulacion_y_reversion(self):
        services.reconciliar()
        a = Alerta.objects.get(tipo="COBRANZA_VENCIDA")
        self.assertEqual(a.rol_destinatario, "GERENCIA")
        with self.captureOnCommitCallbacks(execute=True):
            self.pagar("100.13")
        a.refresh_from_db()
        self.assertEqual(a.estado, "PENDIENTE")
        with self.captureOnCommitCallbacks(execute=True):
            p = self.pagar("2080.22")
        a.refresh_from_db()
        self.assertEqual(a.estado, "RESUELTA")
        with self.captureOnCommitCallbacks(execute=True):
            pagos.anular_pago(self.doc.pk, p.pk, {"motivo": "Error", "referencia_reversion_externa": "Respaldo"}, self.finanzas)
        self.assertTrue(Alerta.objects.filter(tipo=a.tipo, generacion=2, estado="PENDIENTE").exists())
        for p in self.doc.pagos.filter(activo=True):
            pagos.anular_pago(self.doc.pk, p.pk, {"motivo": "Error", "referencia_reversion_externa": "Respaldo"}, self.finanzas)
        with self.captureOnCommitCallbacks(execute=True):
            documentos.revertir_documento(self.doc.pk, {"motivo": "Rectificar", "referencia_rectificacion_externa": "Respaldo"}, self.finanzas)
        self.assertFalse(Alerta.objects.filter(tipo=a.tipo, estado="PENDIENTE").exists())

    def test_vencimiento_se_detecta_sin_usuarios_con_fecha_oficial(self):
        vencimiento = self.doc.fecha_vencimiento
        for hoy, existe in [(vencimiento - timedelta(days=1), False), (vencimiento, False), (vencimiento + timedelta(days=1), True)]:
            with patch("apps.finanzas.consultas_cobranzas.hoy_santiago", return_value=hoy):
                call_command("reconciliar_alertas", once=True, stdout=StringIO())
            self.assertEqual(Alerta.objects.filter(tipo="COBRANZA_VENCIDA").exists(), existe)

    def test_dst_dias_23_25_y_medianoche_local_no_utc(self):
        for inicio, fin, horas in [(date(2026, 9, 6), date(2026, 9, 7), 23), (date(2026, 4, 4), date(2026, 4, 5), 25)]:
            self.assertEqual((inicio_civil(fin).astimezone(utc.utc) - inicio_civil(inicio).astimezone(utc.utc)).total_seconds(), horas * 3600)
        models.QuerySet(model=DocumentoCobro).filter(pk=self.doc.pk).update(fecha_emision=date(2026, 9, 5), fecha_vencimiento=date(2026, 9, 6))
        with patch("django.utils.timezone.now", return_value=datetime(2026, 9, 7, 2, 59, tzinfo=utc.utc)):
            self.assertFalse(condicion("COBRANZA_VENCIDA", self.doc.pk))
        with patch("django.utils.timezone.now", return_value=datetime(2026, 9, 7, 3, 0, tzinfo=utc.utc)):
            self.assertTrue(condicion("COBRANZA_VENCIDA", self.doc.pk))

    def test_callback_documento_registrado_usa_condicion_real(self):
        with self.captureOnCommitCallbacks(execute=True):
            # Ejecutar las callbacks pendientes de este bloque explícitamente.
            services.notificar_despues_commit("COBRANZA_VENCIDA", self.doc.pk)
        self.assertEqual(Alerta.objects.filter(tipo="COBRANZA_VENCIDA").count(), 1)

    def test_api_documento_solo_folio_y_obra_sin_montos(self):
        services.reconciliar()
        self.autenticar(self.gerencia)
        response = self.client.get("/api/alertas/", {"tipo": "COBRANZA_VENCIDA"})
        self.assertEqual(response.status_code, 200, response.data)
        row = response.data["results"][0]
        self.assertEqual(row["recurso_codigo"], self.doc.folio_externo)
        self.assertEqual(row["obra"], self.obra.pk)
        for secreto in ("monto_total", "2080.22", "2180.35", "referencia_respaldo", self.cliente.correo):
            self.assertNotIn(secreto, str(row))
