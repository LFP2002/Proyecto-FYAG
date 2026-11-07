"""Tests iniciales del modelo 004A; no prueban aún servicios ni permisos API."""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from apps.comercial.models import Cliente, Presupuesto
from apps.obras.models import (
    CategoriaServicio, CategoriaServicioEvento, Obra, ObraEvento,
)


class DatosObraMixin:
    @classmethod
    def setUpTestData(cls):
        Usuario = get_user_model()
        cls.supervisor = Usuario.objects.create_user(
            username="supervisor-obras", email="supervisor@fyag.test",
            rol=Usuario.Rol.SUPERVISOR_OBRAS,
        )
        cls.tecnico = Usuario.objects.create_user(
            username="tecnico-obras", email="tecnico@fyag.test",
            rol=Usuario.Rol.TECNICO,
        )
        cls.cliente = Cliente.objects.create(
            tipo_cliente=Cliente.TipoCliente.EMPRESA,
            tipo_identificacion=Cliente.TipoIdentificacion.SIN_IDENTIFICACION,
            nombre_legal="Cliente obras", correo="cliente-obras@fyag.test",
        )
        cls.presupuesto = Presupuesto.objects.create(
            cliente=cls.cliente, creado_por=cls.supervisor,
            descripcion="Servicio de climatización",
        )
        cls.categoria = CategoriaServicio.objects.create(
            nombre="Reparaciones", creado_por=cls.supervisor,
        )

    def obra(self, **cambios):
        campos = dict(
            presupuesto=self.presupuesto,
            categoria_servicio=self.categoria,
            descripcion="Mantención de cámara de frío",
            creado_por=self.supervisor,
            fecha_programada=timezone.localdate() + timedelta(days=5),
        )
        campos.update(cambios)
        return Obra(**campos)


class ModelosObrasTests(DatosObraMixin, TestCase):
    def test_creacion_planificada_antes_de_asignar_tecnico(self):
        obra = self.obra(descripcion="  Cambio de compresor \n")
        obra.save()
        obra.refresh_from_db()
        self.assertEqual(obra.descripcion, "Cambio de compresor")
        self.assertEqual(obra.estado, Obra.Estado.PLANIFICADA)
        self.assertIsNone(obra.tecnico_responsable)
        self.assertIsNone(obra.iniciado_en)
        self.assertEqual(obra.codigo, f"OB-{obra.pk:06d}")
        self.assertEqual(obra.cliente_id, self.cliente.pk)
        self.assertEqual(obra.fecha_programada, timezone.localdate() + timedelta(days=5))

    def test_mismo_presupuesto_no_crea_segunda_obra(self):
        self.obra().save()
        with self.assertRaises(ValidationError):
            self.obra().save()

    def test_unicidad_presupuesto_tambien_aplica_bulk(self):
        self.obra().save()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Obra.objects.bulk_create([self.obra()])

    def test_no_permite_estado_iniciado_sin_inicio_y_tecnico(self):
        for cambios in (
            {"estado": Obra.Estado.EN_PROCESO},
            {"estado": Obra.Estado.EN_PROCESO, "tecnico_responsable": self.tecnico},
            {"estado": Obra.Estado.SUSPENDIDA, "tecnico_responsable": self.tecnico},
        ):
            with self.subTest(cambios=cambios):
                with self.assertRaises(ValidationError):
                    self.obra(**cambios).save()

    def test_estado_en_proceso_exige_inicio_y_responsable(self):
        obra = self.obra()
        obra.save()
        obra.estado = Obra.Estado.EN_PROCESO
        obra.tecnico_responsable = self.tecnico
        obra.iniciado_en = timezone.now()
        obra.save()
        obra.refresh_from_db()
        self.assertEqual(obra.estado, Obra.Estado.EN_PROCESO)
        self.assertEqual(obra.tecnico_responsable, self.tecnico)

    def test_estado_invalido_no_se_persiste(self):
        with self.assertRaises(ValidationError):
            self.obra(estado="ESTADO_FICTICIO").save()

    def test_no_permite_descripcion_vacia_o_no_textual(self):
        for valor in ("", "  ", 123, None):
            with self.subTest(valor=valor):
                with self.assertRaises(ValidationError):
                    self.obra(descripcion=valor).save()

    def test_nombre_categoria_unico_sin_distinguir_mayusculas(self):
        with self.assertRaises(ValidationError):
            CategoriaServicio.objects.create(
                nombre="REPARACIONES", creado_por=self.supervisor,
            )

    def test_migracion_ha_creado_catalogo_base(self):
        esperadas = {
            "Proyecto", "Mantención", "Climatización", "Proyecto eléctrico",
            "Emergencia", "Garantía", "Venta de repuestos", "Mejoras",
        }
        self.assertTrue(esperadas.issubset(
            set(CategoriaServicio.objects.values_list("nombre", flat=True))
        ))

    def test_evento_creacion_se_registra_explicito(self):
        obra = self.obra()
        obra.save()
        evento = ObraEvento.objects.create(
            obra=obra, tipo=ObraEvento.Tipo.CREACION,
            estado_anterior=None, estado_nuevo=Obra.Estado.PLANIFICADA,
            registrado_por=self.supervisor,
            datos_nuevos={"descripcion": obra.descripcion},
        )
        self.assertEqual(evento.estado_nuevo, Obra.Estado.PLANIFICADA)
        self.assertEqual(obra.eventos.count(), 1)
        with self.assertRaises(ValidationError):
            ObraEvento.objects.create(
                obra=obra, tipo=ObraEvento.Tipo.CREACION,
                estado_anterior=None, estado_nuevo=Obra.Estado.PLANIFICADA,
                registrado_por=self.supervisor,
            )

    def test_transiciones_no_permiten_atacajos_ni_motivo_vacio(self):
        obra = self.obra()
        obra.save()
        for anterior, nuevo in (
            ("PLANIFICADA", "FINALIZADA"),
            ("PLANIFICADA", "SUSPENDIDA"),
            ("EN_PROCESO", "CANCELADA"),
        ):
            with self.subTest(anterior=anterior, nuevo=nuevo):
                with self.assertRaises(ValidationError):
                    ObraEvento.objects.create(
                        obra=obra, tipo=ObraEvento.Tipo.CAMBIO_ESTADO,
                        estado_anterior=anterior, estado_nuevo=nuevo,
                        registrado_por=self.supervisor, motivo="Cambio solicitado",
                    )
        with self.assertRaises(ValidationError):
            ObraEvento.objects.create(
                obra=obra, tipo=ObraEvento.Tipo.CAMBIO_ESTADO,
                estado_anterior="PLANIFICADA", estado_nuevo="EN_PROCESO",
                registrado_por=self.supervisor, motivo="  ",
            )

    def test_evento_categoria_conserva_actor(self):
        evento = CategoriaServicioEvento.objects.create(
            categoria=self.categoria,
            tipo=CategoriaServicioEvento.Tipo.ACTIVACION,
            registrado_por=self.supervisor,
            motivo="Reactivación validada",
            datos_anteriores={"activo": False},
            datos_nuevos={"activo": True},
        )
        self.assertEqual(evento.registrado_por, self.supervisor)
