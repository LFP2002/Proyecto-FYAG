from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.comercial import services_presupuestos as servicios
from apps.comercial.exceptions import ClienteInactivo, EstadoIncompatible
from apps.comercial.models import (
    Presupuesto,
    PresupuestoEvento,
    PresupuestoItem,
)
from apps.comercial.services import desactivar_cliente
from apps.comercial.tests.test_presupuesto_services import (
    ServiciosPresupuestoMixin,
    datos_item,
)


class PresupuestoRevisionTests(ServiciosPresupuestoMixin, TestCase):
    def test_tres_origenes_y_copia_profunda(self):
        actor = get_user_model().objects.create_user(
            username="nuevo", email="nuevo@example.com",
            rol=get_user_model().Rol.ADMINISTRATIVO_FINANZAS,
        )
        for estado in ("RECHAZADO_GERENCIA", "RECHAZADO_CLIENTE", "ANULADO"):
            with self.subTest(estado=estado):
                origen = self.preparar(estado)
                cabecera = Presupuesto.objects.values().get(pk=origen.pk)
                items = list(origen.items.values())
                historial = list(origen.eventos.values())
                revision = servicios.crear_revision(origen, actor)
                self.assertNotEqual(revision.pk, origen.pk)
                self.assertNotEqual(revision.codigo, origen.codigo)
                self.assertEqual(revision.estado, "BORRADOR")
                self.assertEqual(revision.presupuesto_origen_id, origen.pk)
                self.assertEqual(revision.creado_por, actor)
                self.assertEqual(revision.cliente, origen.cliente)
                self.assertEqual(revision.descripcion, origen.descripcion)
                self.assertIs(revision.requiere_aprobacion_gerencia, True)
                self.assertNotEqual(revision.creado_en, origen.creado_en)
                for anterior, copia in zip(origen.items.all(),
                                           revision.items.all(), strict=True):
                    self.assertNotEqual(anterior.pk, copia.pk)
                    for campo in servicios.CAMPOS_ITEM:
                        self.assertEqual(getattr(anterior, campo),
                                         getattr(copia, campo))
                evento = revision.eventos.get()
                self.assertIsNone(evento.estado_anterior)
                self.assertEqual(evento.estado_nuevo, "BORRADOR")
                self.assertEqual(evento.registrado_por, actor)
                self.assertEqual(evento.motivo, "")
                self.assertEqual(
                    Presupuesto.objects.values().get(pk=origen.pk), cabecera
                )
                self.assertEqual(list(origen.items.values()), items)
                self.assertEqual(list(origen.eventos.values()), historial)

    def test_todos_los_origenes_no_permitidos(self):
        for estado in (
            "BORRADOR", "PENDIENTE_GERENCIA", "APROBADO_GERENCIA",
            "ENVIADO_CLIENTE", "APROBADO_CLIENTE",
        ):
            with self.subTest(estado=estado):
                origen = self.preparar(estado)
                with self.assertRaises(EstadoIncompatible):
                    servicios.crear_revision(origen, self.usuario)
                self.assertFalse(origen.revisiones.exists())

    def test_aceptado_anulado_revision_no_reactiva_origen(self):
        origen = self.preparar("APROBADO_CLIENTE")
        servicios.anular_presupuesto(
            origen, self.usuario, "Cliente pide cambio"
        )
        revision = servicios.crear_revision(origen, self.usuario)
        origen.refresh_from_db()
        self.assertEqual(origen.estado, "ANULADO")
        self.assertEqual(revision.estado, "BORRADOR")
        self.assertIs(revision.requiere_aprobacion_gerencia, True)

    def test_multiples_revisiones(self):
        origen = self.preparar("RECHAZADO_CLIENTE")
        primera = servicios.crear_revision(origen, self.usuario)
        segunda = servicios.crear_revision(origen, self.usuario)
        self.assertNotEqual(primera.pk, segunda.pk)
        self.assertEqual(origen.revisiones.count(), 2)

    def test_cliente_inactivo_rechazado(self):
        origen = self.preparar("ANULADO")
        desactivar_cliente(self.cliente)
        with self.assertRaises(ClienteInactivo):
            servicios.crear_revision(origen, self.usuario)
        self.assertFalse(origen.revisiones.exists())

    def test_modificar_copia_no_modifica_original(self):
        origen = self.preparar("RECHAZADO_GERENCIA")
        revision = servicios.crear_revision(origen, self.usuario)
        servicios.modificar_item(revision, revision.items.get(), {
            "descripcion": "Propuesta nueva",
        })
        self.assertEqual(origen.items.get().descripcion, "Montaje")

    def test_rollback_por_evento(self):
        origen = self.preparar("ANULADO")
        antes = (Presupuesto.objects.count(), PresupuestoItem.objects.count(),
                 PresupuestoEvento.objects.count())
        with patch.object(servicios, "_evento", side_effect=RuntimeError):
            with self.assertRaises(RuntimeError):
                servicios.crear_revision(origen, self.usuario)
        self.assertEqual(antes, (
            Presupuesto.objects.count(), PresupuestoItem.objects.count(),
            PresupuestoEvento.objects.count(),
        ))

    def test_rollback_por_segunda_linea(self):
        origen = self.crear()
        servicios.crear_item(origen, datos_item())
        servicios.crear_item(origen, datos_item(orden=7))
        servicios.anular_presupuesto(origen, self.usuario, "Cambio comercial")
        original = servicios._guardar_item
        llamadas = 0

        def fallar_segunda(item):
            nonlocal llamadas
            llamadas += 1
            if llamadas == 2:
                raise RuntimeError("Fallo de copia")
            original(item)

        cantidad_items = PresupuestoItem.objects.count()
        with patch.object(
            servicios, "_guardar_item", side_effect=fallar_segunda
        ):
            with self.assertRaises(RuntimeError):
                servicios.crear_revision(origen, self.usuario)
        self.assertFalse(origen.revisiones.exists())
        self.assertEqual(PresupuestoItem.objects.count(), cantidad_items)
