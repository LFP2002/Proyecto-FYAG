from decimal import Decimal

from django.db import DataError, IntegrityError, connection, transaction
from django.test import TestCase

from apps.comercial.models import (
    Presupuesto,
    PresupuestoEvento,
    PresupuestoItem,
)
from apps.comercial.tests.test_presupuesto_model import DatosPresupuestoMixin


class PresupuestoConstraintsTests(DatosPresupuestoMixin, TestCase):
    def assert_rechazo_bd(self, instancia, constraint=None):
        with self.assertRaises(IntegrityError) as error:
            with transaction.atomic():
                type(instancia).objects.bulk_create([instancia])
        if constraint:
            self.assertEqual(
                error.exception.__cause__.diag.constraint_name, constraint
            )

    def test_estado_fuera_de_choices(self):
        self.assert_rechazo_bd(
            self.nuevo_presupuesto(estado="OTRO"), "presupuesto_estado_valido"
        )

    def test_descripcion_vacia_o_sin_normalizar(self):
        for descripcion in ("", "  ", " Servicio "):
            with self.subTest(descripcion=descripcion):
                self.assert_rechazo_bd(
                    self.nuevo_presupuesto(descripcion=descripcion),
                    "presupuesto_descripcion_valida",
                )

    def test_booleano_y_estados_gerencia(self):
        for estado in (
            "PENDIENTE_GERENCIA", "APROBADO_GERENCIA", "RECHAZADO_GERENCIA",
        ):
            with self.subTest(estado=estado):
                self.assert_rechazo_bd(
                    self.nuevo_presupuesto(estado=estado),
                    "presupuesto_gerencia_coherente",
                )

    def test_autoreferencia_por_update(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Presupuesto.objects.filter(pk=self.presupuesto.pk).update(
                    presupuesto_origen_id=self.presupuesto.pk
                )

    def test_campos_obligatorios_no_null(self):
        for campo in (
            "cliente_id", "creado_por_id", "requiere_aprobacion_gerencia",
        ):
            with self.subTest(campo=campo):
                self.assert_rechazo_bd(self.nuevo_presupuesto(**{campo: None}))

    def test_cantidad_no_positiva(self):
        for valor in ("0", "-1"):
            with self.subTest(valor=valor):
                self.assert_rechazo_bd(
                    self.nuevo_item(cantidad=Decimal(valor)),
                    "presupuesto_item_cantidad_rango",
                )

    def test_precio_negativo(self):
        self.assert_rechazo_bd(
            self.nuevo_item(precio_unitario=Decimal("-1")),
            "presupuesto_item_precio_rango",
        )

    def test_nan_rechazado_por_constraints_postgresql(self):
        item = self.nuevo_item()
        item.save()
        for columna, constraint in (
            ("cantidad", "presupuesto_item_cantidad_rango"),
            ("precio_unitario", "presupuesto_item_precio_rango"),
        ):
            with self.subTest(columna=columna):
                # SQL intencional: DecimalField rechaza NaN incluso en bulk.
                with self.assertRaises(IntegrityError) as error:
                    with transaction.atomic(), connection.cursor() as cursor:
                        cursor.execute(
                            f'UPDATE comercial_presupuestoitem SET "{columna}"'
                            " = %s::numeric WHERE id = %s", ["NaN", item.pk],
                        )
                self.assertEqual(
                    error.exception.__cause__.diag.constraint_name, constraint
                )

    def test_numeric_rechaza_infinito_y_exceso_precision(self):
        item = self.nuevo_item()
        item.save()
        for columna, valor in (
            ("cantidad", "Infinity"), ("cantidad", "-Infinity"),
            ("precio_unitario", "Infinity"),
            ("cantidad", "1000000000"),
            ("precio_unitario", "10000000000000"),
        ):
            with self.subTest(columna=columna, valor=valor):
                with self.assertRaises(DataError):
                    with transaction.atomic(), connection.cursor() as cursor:
                        cursor.execute(
                            f'UPDATE comercial_presupuestoitem SET "{columna}"'
                            " = %s::numeric WHERE id = %s", [valor, item.pk],
                        )

    def test_textos_item_normalizados_no_vacios(self):
        for campo, constraint in (
            ("descripcion", "presupuesto_item_desc_valida"),
            ("unidad", "presupuesto_item_unidad_valida"),
        ):
            for valor in ("", "  ", " texto "):
                with self.subTest(campo=campo, valor=valor):
                    self.assert_rechazo_bd(
                        self.nuevo_item(**{campo: valor}), constraint
                    )

    def test_orden_positivo(self):
        for orden in (0, -1):
            with self.subTest(orden=orden):
                self.assert_rechazo_bd(
                    self.nuevo_item(orden=orden),
                    "presupuesto_item_orden_rango",
                )

    def test_orden_maximo_y_limite_columna(self):
        PresupuestoItem.objects.bulk_create([
            self.nuevo_item(orden=2147483647)
        ])
        with self.assertRaises(DataError):
            with transaction.atomic():
                PresupuestoItem.objects.bulk_create([
                    self.nuevo_item(orden=2147483648)
                ])

    def test_orden_unico_por_presupuesto(self):
        self.nuevo_item().save()
        self.assert_rechazo_bd(
            self.nuevo_item(), "presupuesto_item_orden_unico"
        )
        otro = self.nuevo_presupuesto()
        otro.save()
        PresupuestoItem.objects.bulk_create([
            self.nuevo_item(presupuesto=otro)
        ])

    def test_evento_estados_validos(self):
        for cambios in (
            {"estado_anterior": "OTRO", "estado_nuevo": "ENVIADO_CLIENTE"},
            {"estado_anterior": "BORRADOR", "estado_nuevo": "OTRO"},
        ):
            with self.subTest(cambios=cambios):
                self.assert_rechazo_bd(self.nuevo_evento(**cambios))

    def test_evento_null_iff_borrador(self):
        for anterior, nuevo in (
            (None, "ENVIADO_CLIENTE"), ("ENVIADO_CLIENTE", "BORRADOR"),
        ):
            with self.subTest(anterior=anterior, nuevo=nuevo):
                self.assert_rechazo_bd(self.nuevo_evento(
                    estado_anterior=anterior, estado_nuevo=nuevo,
                ), "pres_evento_inicial_coherente")

    def test_evento_inicial_unico(self):
        self.nuevo_evento().save()
        self.assert_rechazo_bd(
            self.nuevo_evento(), "pres_evento_inicial_unico"
        )

    def test_evento_estados_distintos(self):
        self.assert_rechazo_bd(self.nuevo_evento(
            estado_anterior="ENVIADO_CLIENTE", estado_nuevo="ENVIADO_CLIENTE",
        ), "pres_evento_estados_distintos")

    def test_evento_motivo_normalizado(self):
        self.assert_rechazo_bd(
            self.nuevo_evento(motivo=" texto "),
            "pres_evento_motivo_normalizado",
        )

    def test_evento_motivo_requerido(self):
        for destino in ("RECHAZADO_GERENCIA", "RECHAZADO_CLIENTE", "ANULADO"):
            with self.subTest(destino=destino):
                self.assert_rechazo_bd(self.nuevo_evento(
                    estado_anterior="ENVIADO_CLIENTE", estado_nuevo=destino,
                ), "pres_evento_motivo_obligatorio")

    def test_evento_orden_determinista(self):
        primero = self.nuevo_evento()
        primero.save()
        segundo = self.nuevo_evento(
            estado_anterior="BORRADOR", estado_nuevo="ENVIADO_CLIENTE"
        )
        segundo.save()
        PresupuestoEvento.objects.filter(pk=segundo.pk).update(
            creado_en=primero.creado_en
        )
        self.assertEqual(
            list(self.presupuesto.eventos.values_list("pk", flat=True)),
            [primero.pk, segundo.pk],
        )
