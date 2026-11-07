from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from apps.comercial import services_presupuestos as servicios
from apps.comercial.exceptions import (
    ClienteInactivo,
    DatosInvalidos,
    EstadoIncompatible,
    MotivoObligatorio,
    TransicionNoPermitida,
)
from apps.comercial.models import Presupuesto
from apps.comercial.services import desactivar_cliente
from apps.comercial.tests.test_presupuesto_services import (
    ServiciosPresupuestoMixin,
    datos_item,
)


class PresupuestoEstadosTests(ServiciosPresupuestoMixin, TestCase):
    def test_matriz_completa_estados_acciones_y_booleanos(self):
        acciones = (
            (servicios.enviar_gerencia, "PENDIENTE_GERENCIA", {"BORRADOR"}),
            (servicios.aprobar_gerencia, "APROBADO_GERENCIA",
             {"PENDIENTE_GERENCIA"}),
            (servicios.rechazar_gerencia, "RECHAZADO_GERENCIA",
             {"PENDIENTE_GERENCIA"}),
            (servicios.enviar_cliente, "ENVIADO_CLIENTE",
             {"BORRADOR", "APROBADO_GERENCIA"}),
            (servicios.registrar_aprobacion_cliente, "APROBADO_CLIENTE",
             {"ENVIADO_CLIENTE"}),
            (servicios.registrar_rechazo_cliente, "RECHAZADO_CLIENTE",
             {"ENVIADO_CLIENTE"}),
            (servicios.anular_presupuesto, "ANULADO", {
                "BORRADOR", "PENDIENTE_GERENCIA", "APROBADO_GERENCIA",
                "ENVIADO_CLIENTE", "APROBADO_CLIENTE",
            }),
        )
        estados_gerencia = {
            "PENDIENTE_GERENCIA", "APROBADO_GERENCIA", "RECHAZADO_GERENCIA",
        }
        for requiere in (False, True):
            for origen in Presupuesto.Estado:
                if not requiere and origen in estados_gerencia:
                    continue  # Combinaciones imposibles por constraint.
                for accion, destino, origenes in acciones:
                    with self.subTest(
                        requiere=requiere, origen=origen,
                        accion=accion.__name__,
                    ):
                        presupuesto = self.preparar(origen, requiere)
                        permitido = origen in origenes
                        if accion in (
                            servicios.enviar_gerencia,
                            servicios.aprobar_gerencia,
                            servicios.rechazar_gerencia,
                        ):
                            permitido = permitido and requiere
                        if accion == servicios.enviar_cliente:
                            permitido = (
                                origen == "BORRADOR" and not requiere
                            ) or (origen == "APROBADO_GERENCIA" and requiere)
                        if permitido:
                            resultado = accion(
                                presupuesto, self.usuario, "  Decisión  "
                            )
                            self.assertEqual(resultado.estado, destino)
                            evento = resultado.eventos.last()
                            self.assertEqual(evento.estado_anterior, origen)
                            self.assertEqual(evento.estado_nuevo, destino)
                            self.assertEqual(
                                evento.registrado_por, self.usuario
                            )
                            self.assertEqual(evento.motivo, "Decisión")
                            self.assertEqual(resultado.eventos.count(), 2)
                        else:
                            with self.assertRaises(EstadoIncompatible):
                                accion(presupuesto, self.usuario, "Decisión")
                            presupuesto.refresh_from_db()
                            self.assertEqual(presupuesto.estado, origen)
                            self.assertEqual(presupuesto.eventos.count(), 1)

    def test_flujo_completo_con_gerencia(self):
        presupuesto = self.crear(requiere_aprobacion_gerencia=True)
        servicios.crear_item(presupuesto, datos_item())
        for accion in (
            servicios.enviar_gerencia, servicios.aprobar_gerencia,
            servicios.enviar_cliente, servicios.registrar_aprobacion_cliente,
        ):
            accion(presupuesto, self.usuario)
        presupuesto.refresh_from_db()
        self.assertEqual(presupuesto.estado, "APROBADO_CLIENTE")
        self.assertEqual(list(presupuesto.eventos.values_list(
            "estado_nuevo", flat=True
        )), ["BORRADOR", "PENDIENTE_GERENCIA", "APROBADO_GERENCIA",
             "ENVIADO_CLIENTE", "APROBADO_CLIENTE"])

    def test_ruta_por_booleano_no_por_monto(self):
        for requiere, accion in (
            (True, servicios.enviar_cliente),
            (False, servicios.enviar_gerencia),
        ):
            with self.subTest(requiere=requiere):
                presupuesto = self.crear(
                    requiere_aprobacion_gerencia=requiere
                )
                servicios.crear_item(presupuesto, datos_item(
                    precio_unitario=Decimal("9000000"),
                ))
                with self.assertRaises(TransicionNoPermitida):
                    accion(presupuesto, self.usuario)

    def test_salida_sin_items(self):
        for requiere, accion in (
            (True, servicios.enviar_gerencia),
            (False, servicios.enviar_cliente),
        ):
            with self.subTest(requiere=requiere):
                presupuesto = self.crear(
                    requiere_aprobacion_gerencia=requiere
                )
                with self.assertRaises(DatosInvalidos):
                    accion(presupuesto, self.usuario)
                self.assertEqual(presupuesto.eventos.count(), 1)

    def test_salida_total_cero_o_redondeado_a_cero(self):
        for precio in (Decimal("0"), Decimal("0.01")):
            with self.subTest(precio=precio):
                presupuesto = self.crear()
                servicios.crear_item(presupuesto, datos_item(
                    cantidad=Decimal("0.001"), precio_unitario=precio,
                ))
                with self.assertRaises(DatosInvalidos):
                    servicios.enviar_cliente(presupuesto, self.usuario)
                presupuesto.refresh_from_db()
                self.assertEqual(presupuesto.estado, "BORRADOR")

    def test_linea_gratis_y_positiva(self):
        presupuesto = self.crear()
        servicios.crear_item(presupuesto, datos_item(
            precio_unitario=Decimal("0"),
        ))
        servicios.crear_item(presupuesto, datos_item(orden=4))
        resultado = servicios.enviar_cliente(presupuesto, self.usuario)
        self.assertEqual(resultado.estado, "ENVIADO_CLIENTE")
        self.assertEqual(resultado.monto_neto, Decimal("250.63"))

    def test_cliente_inactivo_impide_salida(self):
        presupuesto = self.crear()
        servicios.crear_item(presupuesto, datos_item())
        desactivar_cliente(self.cliente)
        with self.assertRaises(ClienteInactivo):
            servicios.enviar_cliente(presupuesto, self.usuario)
        presupuesto.refresh_from_db()
        self.assertEqual(presupuesto.estado, "BORRADOR")

    def test_desactivacion_posterior_no_invalida_historico(self):
        presupuesto = self.preparar("PENDIENTE_GERENCIA")
        desactivar_cliente(self.cliente)
        servicios.aprobar_gerencia(presupuesto, self.usuario)
        servicios.enviar_cliente(presupuesto, self.usuario)
        servicios.registrar_aprobacion_cliente(presupuesto, self.usuario)
        presupuesto.refresh_from_db()
        self.assertEqual(presupuesto.estado, "APROBADO_CLIENTE")

    def test_motivo_obligatorio_sin_efectos_parciales(self):
        for origen, accion in (
            ("PENDIENTE_GERENCIA", servicios.rechazar_gerencia),
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
        desactivar_cliente(self.cliente)
        resultado = servicios.anular_presupuesto(
            self.presupuesto, self.usuario, "Retirado"
        )
        self.assertEqual(resultado.estado, "ANULADO")

    def test_reintento_no_crea_evento(self):
        presupuesto = self.preparar("PENDIENTE_GERENCIA")
        servicios.aprobar_gerencia(presupuesto, self.usuario)
        with self.assertRaises(EstadoIncompatible):
            servicios.aprobar_gerencia(presupuesto, self.usuario)
        self.assertEqual(presupuesto.eventos.count(), 2)

    def test_rollback_estado_y_fecha_si_falla_evento(self):
        presupuesto = self.preparar("PENDIENTE_GERENCIA")
        fecha = presupuesto.actualizado_en
        with patch.object(servicios, "_evento", side_effect=RuntimeError):
            with self.assertRaises(RuntimeError):
                servicios.aprobar_gerencia(presupuesto, self.usuario)
        presupuesto.refresh_from_db()
        self.assertEqual(presupuesto.estado, "PENDIENTE_GERENCIA")
        self.assertEqual(presupuesto.actualizado_en, fecha)
        self.assertEqual(presupuesto.eventos.count(), 1)
