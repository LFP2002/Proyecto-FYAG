from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db.models.deletion import ProtectedError
from django.test import TestCase

from apps.comercial.models import (
    Cliente,
    Presupuesto,
    PresupuestoEvento,
    PresupuestoItem,
)


class DatosPresupuestoMixin:
    @classmethod
    def setUpTestData(cls):
        usuario = get_user_model()
        cls.usuario = usuario.objects.create_user(
            username="finanzas", email="finanzas@example.com",
            rol=usuario.Rol.ADMINISTRATIVO_FINANZAS,
        )
        cls.cliente = Cliente.objects.create(
            tipo_cliente=Cliente.TipoCliente.EMPRESA,
            tipo_identificacion=Cliente.TipoIdentificacion.SIN_IDENTIFICACION,
            nombre_legal="Cliente presupuesto", correo="cliente@example.com",
        )
        cls.presupuesto = Presupuesto.objects.create(
            cliente=cls.cliente, creado_por=cls.usuario,
            descripcion="Servicio de frío", requiere_aprobacion_gerencia=True,
        )

    def nuevo_presupuesto(self, **cambios):
        datos = {
            "cliente": self.cliente, "creado_por": self.usuario,
            "descripcion": "Servicio",
        }
        datos.update(cambios)
        return Presupuesto(**datos)

    def nuevo_item(self, **cambios):
        datos = {
            "presupuesto": self.presupuesto, "descripcion": "Montaje",
            "cantidad": Decimal("2.500"), "unidad": "hora",
            "precio_unitario": Decimal("100.25"), "orden": 1,
        }
        datos.update(cambios)
        return PresupuestoItem(**datos)

    def nuevo_evento(self, **cambios):
        datos = {
            "presupuesto": self.presupuesto, "registrado_por": self.usuario,
            "estado_anterior": None,
            "estado_nuevo": Presupuesto.Estado.BORRADOR,
        }
        datos.update(cambios)
        return PresupuestoEvento(**datos)


class PresupuestoModelTests(DatosPresupuestoMixin, TestCase):
    def test_creacion_inicial_y_relaciones(self):
        presupuesto = self.presupuesto
        presupuesto.refresh_from_db()
        self.assertEqual(presupuesto.estado, Presupuesto.Estado.BORRADOR)
        self.assertEqual(presupuesto.cliente, self.cliente)
        self.assertEqual(presupuesto.creado_por, self.usuario)
        self.assertIsNone(presupuesto.presupuesto_origen)
        self.assertIsNotNone(presupuesto.creado_en)
        self.assertIsNotNone(presupuesto.actualizado_en)
        self.assertFalse(presupuesto.eventos.exists())

    def test_codigo_y_moneda_no_persistidos(self):
        self.assertEqual(
            self.presupuesto.codigo, f"PRE-{self.presupuesto.pk:06d}"
        )
        self.assertEqual(self.presupuesto.moneda, "CLP")
        campos = {campo.name for campo in Presupuesto._meta.fields}
        self.assertTrue({"codigo", "moneda", "monto_neto"}.isdisjoint(campos))

    def test_codigo_superior_a_seis_digitos(self):
        presupuesto = self.nuevo_presupuesto(id=1000001)
        presupuesto.save()
        self.assertEqual(presupuesto.codigo, "PRE-1000001")

    def test_sin_pk_no_inventa_codigo(self):
        self.assertIsNone(self.nuevo_presupuesto().codigo)

    def test_descripcion_trim(self):
        presupuesto = self.nuevo_presupuesto(descripcion="  Servicio Mixto \n")
        presupuesto.save()
        presupuesto.refresh_from_db()
        self.assertEqual(presupuesto.descripcion, "Servicio Mixto")

    def test_descripcion_invalida(self):
        for descripcion in ("", "   ", None, 123):
            with self.subTest(descripcion=descripcion):
                with self.assertRaises(ValidationError):
                    self.nuevo_presupuesto(descripcion=descripcion).save()

    def test_default_true_no_editable(self):
        self.assertIs(self.nuevo_presupuesto().requiere_aprobacion_gerencia, True)
        campo = Presupuesto._meta.get_field("requiere_aprobacion_gerencia")
        self.assertIs(campo.default, True)
        self.assertFalse(campo.editable)

    def test_solo_true_admitido(self):
        for valor in (False, None, 1, "true"):
            with self.subTest(valor=valor):
                with self.assertRaises(ValidationError):
                    self.nuevo_presupuesto(
                        requiere_aprobacion_gerencia=valor
                    ).save()

    def test_coherencia_estados_gerencia(self):
        for estado in (
            Presupuesto.Estado.PENDIENTE_GERENCIA,
            Presupuesto.Estado.APROBADO_GERENCIA,
            Presupuesto.Estado.RECHAZADO_GERENCIA,
        ):
            with self.subTest(estado=estado):
                with self.assertRaises(ValidationError):
                    self.nuevo_presupuesto(
                        estado=estado, requiere_aprobacion_gerencia=False
                    ).save()
                self.nuevo_presupuesto(
                    estado=estado, requiere_aprobacion_gerencia=True
                ).save()

    def test_autoreferencia_rechazada(self):
        self.presupuesto.presupuesto_origen = self.presupuesto
        with self.assertRaises(ValidationError):
            self.presupuesto.save()

    def test_cliente_y_autor_protegidos(self):
        for relacionado in (self.cliente, self.usuario):
            with self.subTest(modelo=type(relacionado).__name__):
                with self.assertRaises(ProtectedError):
                    relacionado.delete()

    def test_origen_protegido(self):
        self.nuevo_presupuesto(presupuesto_origen=self.presupuesto).save()
        with self.assertRaises(ProtectedError):
            self.presupuesto.delete()

    def test_monto_neto_derivado_de_lineas_persistidas(self):
        self.assertEqual(self.presupuesto.monto_neto, Decimal("0.00"))
        for orden in (1, 2):
            self.nuevo_item(
                cantidad=Decimal("0.500"), precio_unitario=Decimal("0.01"),
                orden=orden,
            ).save()
        self.assertEqual(self.presupuesto.monto_neto, Decimal("0.02"))
        item = self.presupuesto.items.get(orden=2)
        item.precio_unitario = Decimal("1")
        item.save()
        self.assertEqual(self.presupuesto.monto_neto, Decimal("0.51"))


class PresupuestoItemModelTests(DatosPresupuestoMixin, TestCase):
    def test_persistencia_trim_y_subtotal(self):
        item = self.nuevo_item(descripcion=" Montaje ", unidad=" hora ")
        item.save()
        item.refresh_from_db()
        self.assertEqual(item.descripcion, "Montaje")
        self.assertEqual(item.unidad, "hora")
        self.assertEqual(item.subtotal, Decimal("250.63"))

    def test_textos_vacios(self):
        for campo in ("descripcion", "unidad"):
            for valor in ("", "  ", None, 123):
                with self.subTest(campo=campo, valor=valor):
                    with self.assertRaises(ValidationError):
                        self.nuevo_item(**{campo: valor}).save()

    def test_decimales_invalidos_no_son_convertidos_por_django(self):
        for campo in ("cantidad", "precio_unitario"):
            for valor in (
                1.5, True, "1.50", Decimal("NaN"), Decimal("Infinity"),
            ):
                with self.subTest(campo=campo, valor=valor):
                    with self.assertRaises(ValidationError):
                        self.nuevo_item(**{campo: valor}).full_clean()

    def test_limites_y_escala_se_validan_antes_de_persistir(self):
        for campo, valor in (
            ("cantidad", "0"), ("cantidad", "-1"),
            ("cantidad", "1.0001"), ("cantidad", "1000000000"),
            ("precio_unitario", "-1"), ("precio_unitario", "0.001"),
            ("precio_unitario", "10000000000000"),
        ):
            with self.subTest(campo=campo, valor=valor):
                with self.assertRaises(ValidationError):
                    self.nuevo_item(**{campo: Decimal(valor)}).save()

    def test_precio_cero(self):
        item = self.nuevo_item(precio_unitario=Decimal("0"))
        item.save()
        self.assertEqual(item.subtotal, Decimal("0.00"))

    def test_orden_invalido(self):
        for orden in (0, -1, 2147483648, True, 1.5, "1"):
            with self.subTest(orden=orden):
                with self.assertRaises(ValidationError):
                    self.nuevo_item(orden=orden).save()

    def test_orden_duplicado(self):
        self.nuevo_item().save()
        with self.assertRaises(ValidationError):
            self.nuevo_item().save()

    def test_orden_determinista_y_huecos_permitidos(self):
        self.nuevo_item(orden=10).save()
        self.nuevo_item(orden=2).save()
        self.assertEqual(
            list(self.presupuesto.items.values_list("orden", flat=True)),
            [2, 10],
        )

    def test_presupuesto_protegido_por_item(self):
        self.nuevo_item().save()
        with self.assertRaises(ProtectedError):
            self.presupuesto.delete()


class PresupuestoEventoModelTests(DatosPresupuestoMixin, TestCase):
    def test_evento_inicial_explicito(self):
        evento = self.nuevo_evento()
        evento.save()
        evento.refresh_from_db()
        self.assertIsNone(evento.estado_anterior)
        self.assertEqual(evento.estado_nuevo, Presupuesto.Estado.BORRADOR)
        self.assertEqual(evento.registrado_por, self.usuario)
        self.assertEqual(evento.motivo, "")
        self.assertIsNotNone(evento.creado_en)

    def test_segundo_evento_inicial_rechazado(self):
        self.nuevo_evento().save()
        with self.assertRaises(ValidationError):
            self.nuevo_evento().save()

    def test_estados_iguales_rechazados(self):
        with self.assertRaises(ValidationError):
            self.nuevo_evento(
                estado_anterior="ENVIADO_CLIENTE",
                estado_nuevo="ENVIADO_CLIENTE",
            ).save()

    def test_motivos_obligatorios(self):
        for destino in ("RECHAZADO_GERENCIA", "RECHAZADO_CLIENTE", "ANULADO"):
            with self.subTest(destino=destino):
                with self.assertRaises(ValidationError):
                    self.nuevo_evento(
                        estado_anterior="ENVIADO_CLIENTE",
                        estado_nuevo=destino,
                        motivo="  ",
                    ).save()

    def test_evento_normal_y_trim(self):
        evento = self.nuevo_evento(
            estado_anterior="BORRADOR", estado_nuevo="PENDIENTE_GERENCIA",
            motivo="  Envío informado  ",
        )
        evento.save()
        evento.refresh_from_db()
        self.assertEqual(evento.motivo, "Envío informado")
        self.presupuesto.refresh_from_db()
        self.assertEqual(self.presupuesto.estado, "BORRADOR")

    def test_presupuesto_y_actor_protegidos_por_evento(self):
        actor = get_user_model().objects.create_user(
            username="actor", email="actor@example.com",
            rol=get_user_model().Rol.GERENCIA,
        )
        self.nuevo_evento(registrado_por=actor).save()
        for relacionado in (self.presupuesto, actor):
            with self.subTest(modelo=type(relacionado).__name__):
                with self.assertRaises(ProtectedError):
                    relacionado.delete()
