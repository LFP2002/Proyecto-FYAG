from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from apps.comercial import services_presupuestos as servicios
from apps.comercial.exceptions import (
    ClienteInactivo,
    DatosInvalidos,
    EstadoIncompatible,
    MotivoObligatorio,
)
from apps.comercial.models import Presupuesto
from apps.comercial.services import desactivar_cliente
from apps.comercial.tests.test_presupuesto_services import (
    ServiciosPresupuestoMixin,
    datos_item,
)


class PresupuestoEstadosTests(ServiciosPresupuestoMixin, TestCase):
    def test_matriz_completa_estados_acciones(self):
        acciones = (
            (servicios.enviar_finanzas, "PENDIENTE_FINANZAS", {"BORRADOR"}),
            (servicios.aprobar_finanzas, "APROBADO_FINANZAS",
             {"PENDIENTE_GERENCIA", "PENDIENTE_FINANZAS"}),
            (servicios.rechazar_finanzas, "RECHAZADO_FINANZAS",
             {"PENDIENTE_GERENCIA", "PENDIENTE_FINANZAS"}),
            (servicios.enviar_cliente, "ENVIADO_CLIENTE",
             {"APROBADO_GERENCIA", "APROBADO_FINANZAS"}),
            (servicios.registrar_aprobacion_cliente, "APROBADO_CLIENTE",
             {"ENVIADO_CLIENTE"}),
            (servicios.registrar_rechazo_cliente, "RECHAZADO_CLIENTE",
             {"ENVIADO_CLIENTE"}),
            (servicios.anular_presupuesto, "ANULADO", {
                "BORRADOR", "PENDIENTE_GERENCIA", "APROBADO_GERENCIA",
                "PENDIENTE_FINANZAS", "APROBADO_FINANZAS",
                "ENVIADO_CLIENTE", "APROBADO_CLIENTE",
            }),
        )
        for origen in Presupuesto.Estado:
            for accion, destino, origenes in acciones:
                with self.subTest(origen=origen, accion=accion.__name__):
                    presupuesto = self.preparar(origen)
                    if origen in origenes:
                        resultado = accion(
                            presupuesto, self.usuario, "  Decisión  "
                        )
                        self.assertEqual(resultado.estado, destino)
                        evento = resultado.eventos.last()
                        self.assertEqual(evento.estado_anterior, origen)
                        self.assertEqual(evento.estado_nuevo, destino)
                        self.assertEqual(evento.registrado_por, self.usuario)
                        self.assertEqual(evento.motivo, "Decisión")
                        self.assertEqual(resultado.eventos.count(), 2)
                    else:
                        with self.assertRaises(EstadoIncompatible):
                            accion(presupuesto, self.usuario, "Decisión")
                        presupuesto.refresh_from_db()
                        self.assertEqual(presupuesto.estado, origen)
                        self.assertEqual(presupuesto.eventos.count(), 1)

    def test_flujo_completo_con_finanzas(self):
        presupuesto = self.crear()
        servicios.crear_item(presupuesto, datos_item(), usuario=self.usuario)
        for accion in (
            servicios.enviar_finanzas, servicios.aprobar_finanzas,
            servicios.enviar_cliente, servicios.registrar_aprobacion_cliente,
        ):
            accion(presupuesto, self.usuario)
        presupuesto.refresh_from_db()
        self.assertEqual(presupuesto.estado, "APROBADO_CLIENTE")
        self.assertEqual(list(presupuesto.eventos.values_list(
            "estado_nuevo", flat=True
        )), ["BORRADOR", "PENDIENTE_FINANZAS", "APROBADO_FINANZAS",
             "ENVIADO_CLIENTE", "APROBADO_CLIENTE"])

    def test_finanzas_obligatoria_sin_dependencia_del_monto(self):
        for precio in ("1", "9000000"):
            with self.subTest(precio=precio):
                presupuesto = self.crear()
                servicios.crear_item(presupuesto, datos_item(
                    precio_unitario=Decimal(precio),
                ), usuario=self.usuario)
                with self.assertRaises(EstadoIncompatible):
                    servicios.enviar_cliente(presupuesto, self.usuario)
                self.assertEqual(presupuesto.eventos.count(), 1)
                for accion in (servicios.enviar_finanzas,
                               servicios.aprobar_finanzas,
                               servicios.enviar_cliente):
                    accion(presupuesto, self.usuario)
                presupuesto.refresh_from_db()
                self.assertEqual(presupuesto.estado, "ENVIADO_CLIENTE")
                self.assertIs(presupuesto.requiere_aprobacion_gerencia, False)

    def test_salida_sin_items(self):
        presupuesto = self.crear()
        with self.assertRaises(DatosInvalidos):
            servicios.enviar_finanzas(presupuesto, self.usuario)
        self.assertEqual(presupuesto.eventos.count(), 1)

    def test_salida_total_cero_o_redondeado_a_cero(self):
        for precio in (Decimal("0"), Decimal("0.01")):
            with self.subTest(precio=precio):
                presupuesto = self.crear()
                servicios.crear_item(presupuesto, datos_item(
                    cantidad=Decimal("0.001"), precio_unitario=precio,
                ), usuario=self.usuario)
                with self.assertRaises(DatosInvalidos):
                    servicios.enviar_finanzas(presupuesto, self.usuario)
                presupuesto.refresh_from_db()
                self.assertEqual(presupuesto.estado, "BORRADOR")

    def test_linea_gratis_y_positiva(self):
        presupuesto = self.crear()
        servicios.crear_item(presupuesto, datos_item(
            precio_unitario=Decimal("0"),
        ), usuario=self.usuario)
        servicios.crear_item(presupuesto, datos_item(orden=4), usuario=self.usuario)
        resultado = servicios.enviar_finanzas(presupuesto, self.usuario)
        self.assertEqual(resultado.estado, "PENDIENTE_FINANZAS")
        self.assertEqual(resultado.monto_neto, Decimal("250.63"))

    def test_cliente_inactivo_impide_salida(self):
        presupuesto = self.crear()
        servicios.crear_item(presupuesto, datos_item(), usuario=self.usuario)
        desactivar_cliente(self.cliente, usuario=self.usuario)
        with self.assertRaises(ClienteInactivo):
            servicios.enviar_finanzas(presupuesto, self.usuario)
        presupuesto.refresh_from_db()
        self.assertEqual(presupuesto.estado, "BORRADOR")

    def test_desactivacion_posterior_no_invalida_historico(self):
        presupuesto = self.preparar("PENDIENTE_GERENCIA")
        desactivar_cliente(self.cliente, usuario=self.usuario)
        servicios.aprobar_finanzas(presupuesto, self.usuario)
        servicios.enviar_cliente(presupuesto, self.usuario)
        servicios.registrar_aprobacion_cliente(presupuesto, self.usuario)
        presupuesto.refresh_from_db()
        self.assertEqual(presupuesto.estado, "APROBADO_CLIENTE")

    def test_motivo_obligatorio_sin_efectos_parciales(self):
        for origen, accion in (
            ("PENDIENTE_GERENCIA", servicios.rechazar_finanzas),
            ("PENDIENTE_FINANZAS", servicios.rechazar_finanzas),
            ("ENVIADO_CLIENTE", servicios.registrar_rechazo_cliente),
            ("BORRADOR", servicios.anular_presupuesto),
        ):
            with self.subTest(accion=accion):
                presupuesto = self.preparar(origen)
                for motivo in ("", " \n "):
                    with self.assertRaises(MotivoObligatorio):
                        accion(presupuesto, self.usuario, motivo)
                presupuesto.refresh_from_db()
                self.assertEqual(presupuesto.estado, origen)
                self.assertEqual(presupuesto.eventos.count(), 1)

    def test_motivo_invalido(self):
        for motivo in (None, 123, "x" * 2001):
            with self.subTest(motivo=motivo):
                with self.assertRaises(DatosInvalidos):
                    servicios.anular_presupuesto(
                        self.presupuesto, self.usuario, motivo
                    )

    def test_anular_no_exige_items_ni_cliente_activo(self):
        desactivar_cliente(self.cliente, usuario=self.usuario)
        resultado = servicios.anular_presupuesto(
            self.presupuesto, self.usuario, "Retirado"
        )
        self.assertEqual(resultado.estado, "ANULADO")

    def test_reintento_no_crea_evento(self):
        presupuesto = self.preparar("PENDIENTE_GERENCIA")
        servicios.aprobar_finanzas(presupuesto, self.usuario)
        with self.assertRaises(EstadoIncompatible):
            servicios.aprobar_finanzas(presupuesto, self.usuario)
        self.assertEqual(presupuesto.eventos.count(), 2)

    def test_rollback_estado_y_fecha_si_falla_evento(self):
        presupuesto = self.preparar("PENDIENTE_GERENCIA")
        fecha = presupuesto.actualizado_en
        with patch.object(servicios, "_evento", side_effect=RuntimeError):
            with self.assertRaises(RuntimeError):
                servicios.aprobar_finanzas(presupuesto, self.usuario)
        presupuesto.refresh_from_db()
        self.assertEqual(presupuesto.estado, "PENDIENTE_GERENCIA")
        self.assertEqual(presupuesto.actualizado_en, fecha)
        self.assertEqual(presupuesto.eventos.count(), 1)
