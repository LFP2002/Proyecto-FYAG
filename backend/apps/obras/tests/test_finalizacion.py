from datetime import timedelta
from decimal import Decimal, localcontext
from unittest.mock import patch

from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, transaction
from django.test import TestCase
from django.utils import timezone

from apps.comercial import services_presupuestos as comercial
from apps.comercial.exceptions import PresupuestoUtilizado
from apps.obras import services, services_costos as costos, services_finalizacion as cierre, services_gastos as gastos, services_turnos as turnos
from apps.obras.exceptions import PermisoDenegado
from apps.obras.models import CierreCostosObra, ControlCostosObra, CostoObraEvento, GastoObra, Obra, ObraEvento, ObraParticipante, TurnoObra
from .test_costos import CostosBase


class FinalizacionBase(CostosBase):
    def preparar(self):
        super().preparar()
        self.finalizar_url = f"/api/obras/{self.obra.pk}/finalizar/"

    def completa(self, *, material=False, tarifa="8000.00"):
        turno = self.acreditar(tarifa=tarifa)
        gasto = self.crear_ok() if material else None
        self.declarar(**({"materiales_estado": "CON_REGISTROS"} if material else {}))
        self.validar()
        return turno, gasto

    def finalizar(self):
        return cierre.finalizar_obra(self.obra, {"motivo": "Trabajo terminado y costos revisados"}, self.supervisor)

    def estado_persistido(self):
        return {modelo.__name__: list(modelo.objects.order_by("pk").values()) for modelo in (
            Obra, ControlCostosObra, CierreCostosObra, ObraEvento, CostoObraEvento, GastoObra, TurnoObra,
        )}

    def rechazar_sin_cambios(self):
        antes = self.estado_persistido()
        respuesta = self.client.post(self.finalizar_url, {"motivo": "Intento de cierre"}, format="json")
        self.assertEqual(respuesta.status_code, 409, respuesta.data)
        self.assertEqual(self.estado_persistido(), antes)
        return respuesta


class FinalizacionTests(FinalizacionBase, TestCase):
    def setUp(self):
        self.preparar()

    def test_finalizacion_exitosa_operativa_y_snapshot(self):
        self.completa(material=True)
        control_antes = costos.snapshot(self.control())
        ficha = self.client.get(f"/api/obras/{self.obra.pk}/").data
        antes = timezone.now()
        respuesta = self.client.post(self.finalizar_url, {"motivo": "  Trabajo y costos verificados  "}, format="json")
        self.assertEqual(respuesta.status_code, 200, respuesta.data)
        self.assertEqual(set(respuesta.data), set(ficha))
        self.assertEqual(respuesta.data["estado"], "FINALIZADA")
        self.obra.refresh_from_db()
        self.assertGreaterEqual(self.obra.finalizado_en, antes)
        self.assertLessEqual(self.obra.finalizado_en, timezone.now())
        snapshot = CierreCostosObra.objects.get(obra=self.obra)
        self.assertEqual(snapshot.materiales_total, Decimal("31250.00"))
        self.assertEqual(snapshot.otros_total, Decimal("0.00"))
        self.assertEqual(snapshot.mano_obra_total, Decimal("8000.00"))
        self.assertEqual(snapshot.costo_total, Decimal("39250.00"))
        self.assertEqual(snapshot.version_validada, control_antes["version_validada"])
        self.assertEqual(snapshot.validado_por_id, self.supervisor.pk)
        self.assertEqual(snapshot.finalizado_por_id, self.supervisor.pk)
        self.assertEqual(costos.snapshot(self.control()), control_antes)
        evento = self.obra.eventos.get(estado_nuevo="FINALIZADA")
        self.assertEqual(evento.estado_anterior, "EN_PROCESO")
        self.assertEqual(evento.tipo, "CAMBIO_ESTADO")
        self.assertEqual(evento.registrado_por_id, self.supervisor.pk)
        self.assertEqual(evento.motivo, "Trabajo y costos verificados")
        self.assertEqual(set(evento.datos_nuevos), {"estado", "finalizado_en"})

    def test_no_finaliza_automaticamente_sin_control(self):
        respuesta = self.rechazar_sin_cambios()
        self.assertIn("control_inexistente", respuesta.data["pendientes"])
        self.assertFalse(ControlCostosObra.objects.exists())
        self.assertFalse(CierreCostosObra.objects.exists())

    def test_declarar_y_acreditar_no_sustituye_validacion_explicita(self):
        self.acreditar()
        self.declarar()
        with patch("apps.obras.services_costos.validar_costos", side_effect=AssertionError("No validar automáticamente")):
            self.rechazar_sin_cambios()
        self.assertFalse(CostoObraEvento.objects.filter(tipo="VALIDACION").exists())

    def test_control_invalidado_por_gasto_rechaza_cierre(self):
        _, gasto = self.completa(material=True)
        gastos.editar_gasto(self.obra, gasto.pk, {"observacion": "Cambio", "motivo": "Documento"}, self.supervisor)
        respuesta = self.rechazar_sin_cambios()
        self.assertIn("validacion_obsoleta_o_ausente", respuesta.data["pendientes"])

    def test_planificada_y_suspendida_rechazadas_reanudar_permite(self):
        self.acreditar()
        self.declarar()
        services.suspender_obra(self.obra, self.supervisor, "Pausa")
        self.rechazar_sin_cambios()
        self.validar()  # Revisión provisional: no habilita cerrar suspendida.
        self.rechazar_sin_cambios()
        services.reanudar_obra(self.obra, self.supervisor, "Continuar")
        self.finalizar()
        otra = self.otra_obra()
        self.cambiar_estado(otra, "PLANIFICADA")
        self.assertEqual(self.client.post(f"/api/obras/{otra.pk}/finalizar/", {"motivo": "X"}, format="json").status_code, 409)

    def test_responsable_inactivo_rol_incorrecto_y_membresia_no_vigente(self):
        self.completa()
        self.tecnico.is_active = False
        self.tecnico.save()
        self.rechazar_sin_cambios()
        self.tecnico.is_active = True
        self.tecnico.rol = self.gerencia.rol
        self.tecnico.save()
        self.rechazar_sin_cambios()
        self.tecnico.rol = services.TECNICO
        self.tecnico.save()
        # Mantener CHECK de baja auditada para simular inconsistencia externa.
        ObraParticipante.objects.filter(obra=self.obra, tecnico=self.tecnico).update(
            activo=False, desasignado_por=self.supervisor, desasignado_en=timezone.now(), motivo_desasignacion="Baja externa",
        )
        respuesta = self.rechazar_sin_cambios()
        self.assertIn("responsable_sin_membresia", respuesta.data["pendientes"])

    def test_recalculo_detecta_turno_abierto_con_marca_aparente(self):
        self.declarar()
        self.abrir()
        self.marcar_validado()  # La marca por sí sola no acredita la ejecución.
        respuesta = self.rechazar_sin_cambios()
        self.assertIn("turnos_abiertos", respuesta.data["pendientes"])
        self.assertTrue(self.control().costos_validados)

    def test_recalculo_detecta_turnos_pendientes_observados_y_sin_tarifa(self):
        turno = self.abrir()
        self.cerrar(turno)
        self.declarar()
        self.marcar_validado()
        respuesta = self.rechazar_sin_cambios()
        self.assertIn("turnos_sin_tarifa", respuesta.data["pendientes"])
        self.revisar(turno, "OBSERVAR")
        self.marcar_validado()
        respuesta = self.rechazar_sin_cambios()
        self.assertIn("turnos_observados", respuesta.data["pendientes"])

    def test_administrativo_sin_ajuste_rechaza_aunque_figure_validado(self):
        turno = self.abrir()
        with patch("apps.obras.services_turnos.timezone.now", return_value=turno.iniciado_en + timedelta(seconds=3600)):
            turnos.cerrar_administrativamente(self.obra, turno.pk, {"descripcion_trabajo": "Verificado parcialmente", "motivo": "Sin acceso"}, self.supervisor)
        TurnoObra.objects.filter(pk=turno.pk).update(estado_revision="VALIDADO", costo_hora_neto=Decimal("8000.00"), revisado_por=self.supervisor, revisado_en=timezone.now(), observacion_revision="Marca externa")
        self.declarar()
        self.marcar_validado()
        self.rechazar_sin_cambios()
        turnos.corregir_turno(self.obra, turno.pk, {"duracion_ajustada_segundos": 1800, "motivo": "Duración acreditada"}, self.supervisor)
        self.revisar(turno)
        self.validar()
        self.finalizar()
        self.assertEqual(CierreCostosObra.objects.get(obra=self.obra).mano_obra_total, Decimal("4000.00"))

    def test_rubros_pendientes_y_total_cero_no_pasan_por_marca(self):
        self.acreditar(tarifa="0.00")
        self.marcar_validado()
        respuesta = self.rechazar_sin_cambios()
        self.assertIn("materiales_sin_declarar_o_incoherente", respuesta.data["pendientes"])
        self.declarar()
        self.marcar_validado()
        respuesta = self.rechazar_sin_cambios()
        self.assertIn("costo_total_no_positivo", respuesta.data["pendientes"])

    def test_revalida_integridad_de_devoluciones_sin_alterar_control(self):
        _, gasto = self.completa(material=True)
        GastoObra.objects.filter(pk=gasto.pk).update(cantidad_devuelta=Decimal("1.000"))
        respuesta = self.rechazar_sin_cambios()
        self.assertIn("gasto_inconsistente", respuesta.data["pendientes"])

    def test_snapshot_decimal_devoluciones_anulados_y_cortesia(self):
        turno = self.acreditar()
        total = self.crear_ok()
        gastos.devolver_gasto(self.obra, total.pk, {"cantidad": "2.500", "fecha_devolucion": timezone.localdate(), "motivo": "Todo sobrante"}, self.supervisor)
        for _ in range(2):
            self.crear_ok(cantidad="0.100", costo_unitario_neto="0.05")
        self.crear_ok(tipo="TRANSPORTE", cantidad="0.333", costo_unitario_neto="3.00")
        anulado = self.crear_ok()
        gastos.anular_gasto(self.obra, anulado.pk, {"motivo": "Duplicado"}, self.supervisor)
        self.declarar(materiales_estado="CON_REGISTROS", otros_estado="CON_REGISTROS")
        costos.registrar_cortesia(self.obra, {"justificacion": "Atención excepcional sin cobro"}, self.supervisor)
        self.validar()
        self.finalizar()
        fotografia = CierreCostosObra.objects.get(obra=self.obra)
        self.assertEqual(fotografia.materiales_total, Decimal("0.02"))
        self.assertEqual(fotografia.otros_total, Decimal("1.00"))
        self.assertEqual(fotografia.mano_obra_total, Decimal("8000.00"))
        self.assertEqual(fotografia.costo_total, Decimal("8001.02"))
        resumen = self.client.get(self.resumen_url).data
        self.assertEqual(resumen["costo_total"], "8001.02")
        self.assertTrue(resumen["cortesia_sin_cobro"])
        self.assertFalse(resumen["provisional"])

    def test_multiples_tecnicos_conservan_tarifas_historicas(self):
        self.acreditar()
        services.asignar_participante(self.obra, {"tecnico": self.otro_tecnico.pk, "motivo": "Apoyo"}, self.supervisor)
        segundo = turnos.iniciar_turno(self.obra, {}, self.otro_tecnico)
        with patch("apps.obras.services_turnos.timezone.now", return_value=segundo.iniciado_en + timedelta(seconds=1800)):
            turnos.finalizar_turno(self.obra, segundo.pk, {"descripcion_trabajo": "Trabajo adicional"}, self.otro_tecnico)
        self.revisar(segundo, tarifa="9000.00")
        self.declarar()
        self.validar()
        self.finalizar()
        self.assertEqual(CierreCostosObra.objects.get(obra=self.obra).mano_obra_total, Decimal("12500.00"))

    def test_segundo_cierre_rechaza_sin_evento_ni_snapshot_extra(self):
        self.completa()
        self.finalizar()
        self.rechazar_sin_cambios()
        self.assertEqual(CierreCostosObra.objects.count(), 1)
        self.assertEqual(self.obra.eventos.filter(estado_nuevo="FINALIZADA").count(), 1)

    def test_snapshot_distingue_validador_y_supervisor_que_finaliza(self):
        self.completa()
        otro_supervisor = type(self.supervisor).objects.create_user(
            username="supervisor_cierre", email="cierre@fyag.test", rol=services.SUPERVISOR,
        )
        self.autenticar(otro_supervisor)
        respuesta = self.client.post(self.finalizar_url, {"motivo": "Revisión final"}, format="json")
        self.assertEqual(respuesta.status_code, 200, respuesta.data)
        fotografia = CierreCostosObra.objects.get(obra=self.obra)
        self.assertEqual(fotografia.validado_por_id, self.supervisor.pk)
        self.assertEqual(fotografia.finalizado_por_id, otro_supervisor.pk)

    def test_snapshot_preexistente_se_maneja_sin_reemplazar(self):
        self.completa()
        CierreCostosObra.objects.create(obra=self.obra, materiales_total="0.00", otros_total="0.00", mano_obra_total="8000.00", costo_total="8000.00", version_validada=self.control().version_actual, validado_por=self.supervisor, finalizado_por=self.supervisor)
        self.rechazar_sin_cambios()

    def test_presupuesto_intacto_y_anulacion_sigue_bloqueada(self):
        self.completa()
        antes = type(self.presupuesto).objects.values().get(pk=self.presupuesto.pk)
        self.finalizar()
        self.assertEqual(type(self.presupuesto).objects.values().get(pk=self.presupuesto.pk), antes)
        with self.assertRaises(PresupuestoUtilizado):
            comercial.anular_presupuesto(self.presupuesto, self.finanzas, "Intento tras cierre")

    def test_rollback_si_falla_snapshot_evento_o_actualizacion_de_obra(self):
        self.completa()
        for punto in ("apps.obras.services_finalizacion.CierreCostosObra.objects.create",
                      "apps.obras.services_finalizacion.base._evento_obra",
                      "apps.obras.services_finalizacion.Obra.save"):
            with self.subTest(punto=punto):
                antes = self.estado_persistido()
                with patch(punto, side_effect=RuntimeError("Fallo forzado")), self.assertRaises(RuntimeError):
                    self.finalizar()
                self.assertEqual(self.estado_persistido(), antes)

    def test_permisos_y_superusuarios_sin_bypass(self):
        self.completa()
        for usuario in (self.tecnico, self.gerencia, self.finanzas):
            usuario.is_superuser = True
            usuario.save()
            self.autenticar(usuario)
            self.assertEqual(self.client.post(self.finalizar_url, {"motivo": "Intento"}, format="json").status_code, 403)
            self.assertEqual(self.client.post("/api/obras/999999/finalizar/", {}, format="json").status_code, 403)
        self.autenticar(self.supervisor)
        self.assertEqual(self.client.post(self.finalizar_url, {"motivo": "Correcto"}, format="json").status_code, 200)

    def test_rol_persistido_del_actor_no_del_caller(self):
        self.completa()
        type(self.supervisor).objects.filter(pk=self.supervisor.pk).update(rol=self.gerencia.rol)
        with self.assertRaises(PermisoDenegado):
            self.finalizar()

    def test_actor_desactivado_no_puede_finalizar_desde_servicio(self):
        self.completa()
        type(self.supervisor).objects.filter(pk=self.supervisor.pk).update(is_active=False)
        with self.assertRaises(PermisoDenegado):
            self.finalizar()
        self.assertFalse(CierreCostosObra.objects.exists())

    def test_contrato_estricto_http_y_metodos(self):
        for datos in ({}, {"motivo": " "}, {"motivo": 7}, {"motivo": True}, {"motivo": None}, {"motivo": "x" * 2001}):
            self.assertEqual(self.client.post(self.finalizar_url, datos, format="json").status_code, 400)
        for campo in ("estado", "finalizado_en", "costo_total", "version_validada", "validado_por", "finalizado_por", "costos_validados", "turnos_completos", "obra"):
            self.assertEqual(self.client.post(self.finalizar_url, {"motivo": "Cierre", campo: "X"}, format="json").status_code, 400)
        for metodo in ("get", "patch", "put", "delete"):
            self.assertEqual(getattr(self.client, metodo)(self.finalizar_url).status_code, 405)
        self.assertEqual(self.client.post("/api/obras/999999/finalizar/", {"motivo": "X"}, format="json").status_code, 404)
        for accion in ("cancelar", "reabrir"):
            self.assertEqual(self.client.post(f"/api/obras/{self.obra.pk}/{accion}/", {}, format="json").status_code, 404)
        self.client.credentials()
        self.assertEqual(self.client.post(self.finalizar_url, {"motivo": "X"}, format="json").status_code, 401)

    def test_terminal_bloquea_todas_las_escrituras_y_mantiene_lecturas(self):
        turno, gasto = self.completa(material=True)
        miembro, _ = services.asignar_participante(self.obra, {"tecnico": self.otro_tecnico.pk, "motivo": "Apoyo"}, self.supervisor)
        self.validar()
        self.finalizar()
        antes = self.estado_persistido()
        rutas_post = {
            "iniciar/": {"motivo": "X"}, "suspender/": {"motivo": "X"}, "reanudar/": {"motivo": "X"},
            "cambiar-tecnico/": {"tecnico_responsable": self.otro_tecnico.pk, "motivo": "X"},
            "participantes/": {"tecnico": self.otro_tecnico.pk, "motivo": "X"},
            f"participantes/{miembro.pk}/desasignar/": {"motivo": "X"},
            "gastos/": self.entrada(), f"gastos/{gasto.pk}/devolver/": {"cantidad": "1.000", "fecha_devolucion": timezone.localdate().isoformat(), "motivo": "X"},
            f"gastos/{gasto.pk}/anular/": {"motivo": "X"}, "costos/validar/": {"motivo": "X"},
            "cortesia-sin-cobro/": {"justificacion": "X"},
            f"turnos/{turno.pk}/revisar/": {"decision": "VALIDAR", "costo_hora_neto": "8000.00", "motivo": "X"},
            f"turnos/{turno.pk}/corregir/": {"duracion_ajustada_segundos": 1800, "motivo": "X"},
            f"turnos/{turno.pk}/cerrar-administrativamente/": {"motivo": "X", "descripcion_trabajo": "X"},
        }
        for ruta, datos in rutas_post.items():
            with self.subTest(ruta=ruta):
                self.assertEqual(self.client.post(f"/api/obras/{self.obra.pk}/{ruta}", datos, format="json").status_code, 409)
        for ruta, datos in (("", {"descripcion": "X", "motivo": "X"}), (f"gastos/{gasto.pk}/", {"observacion": "X", "motivo": "X"}), ("costos/control/", {"motivo": "X"})):
            self.assertEqual(self.client.patch(f"/api/obras/{self.obra.pk}/{ruta}", datos, format="json").status_code, 409)
        self.autenticar(self.tecnico)
        for ruta, datos in (("turnos/iniciar/", {}), (f"turnos/{turno.pk}/finalizar/", {"descripcion_trabajo": "X"}), (f"turnos/{turno.pk}/subsanar/", {"descripcion_trabajo": "X"})):
            self.assertEqual(self.client.post(f"/api/obras/{self.obra.pk}/{ruta}", datos, format="json").status_code, 409)
        detalle = self.client.get(f"/api/obras/{self.obra.pk}/")
        self.assertEqual(detalle.status_code, 200)
        self.assertNotIn("costo_total", detalle.data)
        self.assertEqual(self.client.get(self.resumen_url).status_code, 403)
        self.assertEqual(self.estado_persistido(), antes)
        for usuario in (self.gerencia, self.finanzas, self.supervisor):
            self.autenticar(usuario)
            self.assertEqual(self.client.get(self.resumen_url).data["costo_total"], "39250.00")


class SnapshotCostosTests(FinalizacionBase, TestCase):
    def setUp(self):
        self.preparar()
        self.completa()
        self.finalizar()
        self.cierre = CierreCostosObra.objects.get(obra=self.obra)

    def test_snapshot_no_editable_por_modelo_queryset_ni_admin(self):
        self.assertFalse(admin.site.is_registered(CierreCostosObra))
        for operacion in (lambda: self.cierre.save(), lambda: self.cierre.delete(),
                          lambda: CierreCostosObra.objects.filter(pk=self.cierre.pk).update(costo_total=0),
                          lambda: CierreCostosObra.objects.filter(pk=self.cierre.pk).delete()):
            with self.assertRaises(ValidationError):
                operacion()

    def test_constraints_importes_finitos_suma_version_y_unicidad(self):
        for campo, valor in (("costo_total", "1.00"), ("materiales_total", "-1.00"),
                             ("costo_total", "NaN"), ("version_validada", "-1")):
            with self.subTest(campo=campo, valor=valor), self.assertRaises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
                cursor.execute(f"UPDATE obras_cierrecostosobra SET {campo} = %s WHERE id = %s", [valor, self.cierre.pk])
        valores = {campo.name: getattr(self.cierre, campo.name) for campo in self.cierre._meta.fields if campo.name not in {"id", "creado_en"}}
        with self.assertRaises(IntegrityError), transaction.atomic():
            CierreCostosObra.objects.bulk_create([CierreCostosObra(**valores)])

    def test_resumen_final_usa_fotografia_sin_reescribirla(self):
        antes = CierreCostosObra.objects.values().get(pk=self.cierre.pk)
        # Corrupción SQL fuera de los servicios: no recalcular la fotografía.
        TurnoObra.objects.filter(obra=self.obra).update(costo_hora_neto=Decimal("9000.00"))
        self.assertEqual(self.client.get(self.resumen_url).data["costo_total"], "8000.00")
        self.assertEqual(CierreCostosObra.objects.values().get(pk=self.cierre.pk), antes)

    def test_precision_de_agregados_superior_al_contexto_decimal_default(self):
        otra = self.otra_obra()
        with localcontext() as ctx:
            ctx.prec = 50
            monto = Decimal("123456789012345678901234567890.12")
            snapshot = CierreCostosObra.objects.create(obra=otra, materiales_total=monto, otros_total=monto, mano_obra_total=monto, costo_total=monto * 3, version_validada=0, validado_por=self.supervisor, finalizado_por=self.supervisor)
            snapshot.refresh_from_db()
            self.assertEqual(snapshot.costo_total, monto * 3)
