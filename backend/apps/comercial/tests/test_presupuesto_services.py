from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.db import IntegrityError
from django.test import TestCase

from apps.comercial import services_presupuestos as servicios
from apps.comercial.exceptions import (
    ClienteInactivo,
    DatosInvalidos,
    EstadoIncompatible,
    OrdenDuplicado,
    RecursoNoEncontrado,
)
from apps.comercial.models import Cliente, Presupuesto, PresupuestoEvento
from apps.comercial.models import PresupuestoItem
from apps.comercial.services import desactivar_cliente
from apps.comercial.tests.test_presupuesto_model import DatosPresupuestoMixin


def datos_item(**cambios):
    datos = {
        "descripcion": " Montaje ", "cantidad": Decimal("2.500"),
        "unidad": " hora ", "precio_unitario": Decimal("100.25"), "orden": 1,
    }
    datos.update(cambios)
    return datos


class ServiciosPresupuestoMixin(DatosPresupuestoMixin):
    def crear(self, **cambios):
        datos = {
            "cliente": self.cliente, "descripcion": " Servicio de frío ",
            "requiere_aprobacion_gerencia": False, "usuario": self.usuario,
        }
        datos.update(cambios)
        return servicios.crear_presupuesto(**datos)

    def preparar(self, estado, requiere=True):
        presupuesto = self.crear(requiere_aprobacion_gerencia=requiere)
        servicios.crear_item(presupuesto, datos_item())
        # Estado de partida de la prueba, no una transición del servicio.
        presupuesto.estado = estado
        presupuesto.save()
        return presupuesto


class PresupuestoCreacionServiciosTests(ServiciosPresupuestoMixin, TestCase):
    def test_creacion_cabecera_y_evento_inicial(self):
        presupuesto = self.crear()
        self.assertEqual(presupuesto.descripcion, "Servicio de frío")
        self.assertEqual(presupuesto.estado, "BORRADOR")
        self.assertEqual(presupuesto.creado_por, self.usuario)
        self.assertFalse(presupuesto.items.exists())
        evento = presupuesto.eventos.get()
        self.assertIsNone(evento.estado_anterior)
        self.assertEqual(evento.estado_nuevo, "BORRADOR")
        self.assertEqual(evento.registrado_por, self.usuario)
        self.assertEqual(evento.motivo, "")

    def test_cliente_inactivo_persistido_no_instancia_obsoleta(self):
        desactivar_cliente(self.cliente)
        self.assertTrue(self.cliente.activo)
        with self.assertRaises(ClienteInactivo):
            self.crear()
        self.assertEqual(Presupuesto.objects.count(), 1)
        self.assertFalse(PresupuestoEvento.objects.exists())

    def test_cliente_inexistente(self):
        with self.assertRaises(DatosInvalidos) as error:
            self.crear(cliente=999999)
        self.assertIn("cliente", error.exception.errores)

    def test_usuario_interno_requerido(self):
        for usuario in (AnonymousUser(), "GERENCIA", None):
            with self.subTest(usuario=usuario):
                with self.assertRaises(DatosInvalidos):
                    self.crear(usuario=usuario)

    def test_datos_invalidos_no_dejan_filas(self):
        with self.assertRaises(DatosInvalidos):
            self.crear(descripcion="  ")
        self.assertEqual(Presupuesto.objects.count(), 1)

    def test_rollback_si_falla_evento(self):
        with patch.object(servicios, "_evento", side_effect=RuntimeError):
            with self.assertRaises(RuntimeError):
                self.crear()
        self.assertEqual(Presupuesto.objects.count(), 1)
        self.assertFalse(PresupuestoEvento.objects.exists())


class PresupuestoCabeceraServiciosTests(ServiciosPresupuestoMixin, TestCase):
    def test_patch_solo_campos_recibidos(self):
        presupuesto = self.crear()
        actualizado = servicios.modificar_presupuesto(presupuesto, {
            "descripcion": "  Nueva propuesta  ",
        })
        self.assertEqual(actualizado.descripcion, "Nueva propuesta")
        self.assertEqual(actualizado.cliente_id, presupuesto.cliente_id)
        self.assertFalse(actualizado.requiere_aprobacion_gerencia)
        self.assertEqual(actualizado.eventos.count(), 1)

    def test_no_sobrescribe_instancia_obsoleta(self):
        presupuesto = self.crear()
        servicios.modificar_presupuesto(presupuesto, {"descripcion": "Actual"})
        actualizado = servicios.modificar_presupuesto(presupuesto, {
            "requiere_aprobacion_gerencia": True,
        })
        self.assertEqual(actualizado.descripcion, "Actual")

    def test_campos_administrados_rechazados(self):
        for campo in (
            "estado", "id", "creado_por", "presupuesto_origen",
            "creado_en", "actualizado_en", "monto_neto", "descripccion",
        ):
            with self.subTest(campo=campo):
                with self.assertRaises(DatosInvalidos):
                    servicios.modificar_presupuesto(self.presupuesto, {
                        campo: "dato",
                    })

    def test_cambio_cliente_activo(self):
        otro = Cliente.objects.create(
            tipo_cliente="PERSONA", tipo_identificacion="SIN_IDENTIFICACION",
            nombre_legal="Otro", correo="otro@example.com",
        )
        actualizado = servicios.modificar_presupuesto(self.presupuesto, {
            "cliente": otro.pk,
        })
        self.assertEqual(actualizado.cliente_id, otro.pk)

    def test_cliente_explicito_inactivo_rechazado_incluso_mismo_id(self):
        desactivar_cliente(self.cliente)
        with self.assertRaises(ClienteInactivo):
            servicios.modificar_presupuesto(self.presupuesto, {
                "cliente": self.cliente.pk,
            })

    def test_puede_editar_otra_informacion_con_cliente_inactivo(self):
        desactivar_cliente(self.cliente)
        actualizado = servicios.modificar_presupuesto(self.presupuesto, {
            "descripcion": "Actualizada",
        })
        self.assertEqual(actualizado.descripcion, "Actualizada")

    def test_congelado_en_todos_los_estados_no_borrador(self):
        for estado in Presupuesto.Estado:
            if estado == Presupuesto.Estado.BORRADOR:
                continue
            with self.subTest(estado=estado):
                presupuesto = self.preparar(estado)
                presupuesto.estado = "BORRADOR"  # Caller obsoleto/falsificado.
                with self.assertRaises(EstadoIncompatible):
                    servicios.modificar_presupuesto(presupuesto, {
                        "descripcion": "No permitido",
                    })

    def test_inexistente(self):
        with self.assertRaises(RecursoNoEncontrado):
            servicios.modificar_presupuesto(999999, {})


class PresupuestoItemsServiciosTests(ServiciosPresupuestoMixin, TestCase):
    def test_crud_trim_fechas_y_sin_renumerar(self):
        presupuesto = self.crear()
        fecha = presupuesto.actualizado_en
        item = servicios.crear_item(presupuesto, datos_item())
        presupuesto.refresh_from_db()
        self.assertGreater(presupuesto.actualizado_en, fecha)
        self.assertEqual(item.descripcion, "Montaje")
        self.assertEqual(item.unidad, "hora")
        fecha = presupuesto.actualizado_en
        actualizado = servicios.modificar_item(presupuesto, item, {
            "cantidad": Decimal("3"),
        })
        self.assertEqual(actualizado.cantidad, Decimal("3.000"))
        self.assertEqual(actualizado.precio_unitario, Decimal("100.25"))
        presupuesto.refresh_from_db()
        self.assertGreater(presupuesto.actualizado_en, fecha)
        servicios.crear_item(presupuesto, datos_item(orden=9))
        presupuesto.refresh_from_db()
        fecha = presupuesto.actualizado_en
        servicios.eliminar_item(presupuesto, item)
        presupuesto.refresh_from_db()
        self.assertGreater(presupuesto.actualizado_en, fecha)
        self.assertEqual(list(presupuesto.items.values_list(
            "orden", flat=True
        )), [9])
        self.assertEqual(presupuesto.eventos.count(), 1)

    def test_crud_congelado_fuera_de_borrador(self):
        for estado in Presupuesto.Estado:
            if estado == Presupuesto.Estado.BORRADOR:
                continue
            presupuesto = self.preparar(estado)
            item = presupuesto.items.get()
            for operacion in (
                lambda: servicios.crear_item(presupuesto, datos_item(orden=2)),
                lambda: servicios.modificar_item(presupuesto, item, {}),
                lambda: servicios.eliminar_item(presupuesto, item),
            ):
                with self.subTest(estado=estado, operacion=operacion):
                    with self.assertRaises(EstadoIncompatible):
                        operacion()

    def test_orden_duplicado_creacion_y_modificacion(self):
        primero = servicios.crear_item(self.presupuesto, datos_item())
        segundo = servicios.crear_item(self.presupuesto, datos_item(orden=2))
        with self.assertRaises(OrdenDuplicado):
            servicios.crear_item(self.presupuesto, datos_item())
        with self.assertRaises(OrdenDuplicado):
            servicios.modificar_item(self.presupuesto, segundo, {"orden": 1})
        self.assertEqual(self.presupuesto.items.count(), 2)
        servicios.modificar_item(self.presupuesto, primero, {"orden": 1})

    def test_integrity_orden_real_traducido(self):
        servicios.crear_item(self.presupuesto, datos_item())
        # Elude detección previa para verificar el respaldo real de PostgreSQL.
        def insertar_sin_comprobar_orden(item):
            item.full_clean(validate_constraints=False)
            PresupuestoItem.objects.bulk_create([item])

        with patch.object(
            servicios, "_guardar_item",
            side_effect=insertar_sin_comprobar_orden,
        ):
            with self.assertRaises(OrdenDuplicado) as error:
                servicios.crear_item(self.presupuesto, datos_item())
        self.assertNotIn("presupuesto_item_orden_unico", str(error.exception))
        self.assertEqual(self.presupuesto.items.count(), 1)

    def test_integrity_desconocido_no_se_oculta(self):
        with patch.object(
            servicios, "_guardar_item", side_effect=IntegrityError
        ):
            with self.assertRaises(IntegrityError):
                servicios.crear_item(self.presupuesto, datos_item())

    def test_datos_invalidos_y_fk_inyectada(self):
        for datos in (
            datos_item(presupuesto_id=999999), datos_item(presupuesto=999999),
            datos_item(cantidad=1.5), datos_item(orden=0), {},
        ):
            with self.subTest(datos=datos):
                with self.assertRaises(DatosInvalidos):
                    servicios.crear_item(self.presupuesto, datos)
        self.assertFalse(self.presupuesto.items.exists())

    def test_item_ajeno_e_inexistente(self):
        otro = self.crear()
        item = servicios.crear_item(otro, datos_item())
        for referencia in (item, 999999):
            with self.subTest(item=referencia):
                with self.assertRaises(RecursoNoEncontrado):
                    servicios.modificar_item(self.presupuesto, referencia, {})
                with self.assertRaises(RecursoNoEncontrado):
                    servicios.eliminar_item(self.presupuesto, referencia)

    def test_rollback_si_falla_actualizacion_fecha(self):
        with patch.object(
            servicios, "_actualizar_fecha", side_effect=RuntimeError
        ):
            with self.assertRaises(RuntimeError):
                servicios.crear_item(self.presupuesto, datos_item())
        self.assertFalse(self.presupuesto.items.exists())

    def test_total_relee_items_persistidos_no_cache(self):
        presupuesto = self.crear()
        cache = Presupuesto.objects.prefetch_related("items").get(
            pk=presupuesto.pk
        )
        self.assertEqual(
            servicios.recalcular_monto_neto(cache), Decimal("0.00")
        )
        for orden in (1, 2):
            servicios.crear_item(presupuesto, datos_item(
                cantidad=Decimal("0.500"), precio_unitario=Decimal("0.01"),
                orden=orden,
            ))
        self.assertEqual(
            servicios.recalcular_monto_neto(cache), Decimal("0.02")
        )
