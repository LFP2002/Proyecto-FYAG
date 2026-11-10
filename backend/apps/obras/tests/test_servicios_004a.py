"""Pruebas de dominio 004A: no dependen de la futura API de Obras."""

from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APITestCase
from apps.usuarios.tokens import AccessToken

from apps.comercial import services_presupuestos as comercial
from apps.comercial.exceptions import (
    PresupuestoUtilizado as PresupuestoUtilizadoComercial,
)
from apps.comercial.models import Cliente, Presupuesto
from apps.obras import services
from apps.obras.exceptions import (
    DatosInvalidos,
    EstadoIncompatible,
    PermisoDenegado,
    PresupuestoUtilizado,
    SinCambios,
)
from apps.obras.models import CategoriaServicio, Obra, ObraEvento

Usuario = get_user_model()


class BaseObras:
    @classmethod
    def setUpTestData(cls):
        cls.supervisor = Usuario.objects.create_user(
            username="supervisor04",
            email="supervisor04@fyag.test",
            rol=Usuario.Rol.SUPERVISOR_OBRAS,
        )
        cls.gerencia = Usuario.objects.create_user(
            username="gerencia04",
            email="gerencia04@fyag.test",
            rol=Usuario.Rol.GERENCIA,
        )
        cls.finanzas = Usuario.objects.create_user(
            username="finanzas04",
            email="finanzas04@fyag.test",
            rol=Usuario.Rol.ADMINISTRATIVO_FINANZAS,
        )
        cls.tecnico = Usuario.objects.create_user(
            username="tecnico04",
            email="tecnico04@fyag.test",
            rol=Usuario.Rol.TECNICO,
        )
        cls.otro_tecnico = Usuario.objects.create_user(
            username="tecnico05",
            email="tecnico05@fyag.test",
            rol=Usuario.Rol.TECNICO,
        )
        cls.cliente = Cliente.objects.create(
            tipo_cliente=Cliente.TipoCliente.EMPRESA,
            tipo_identificacion=Cliente.TipoIdentificacion.SIN_IDENTIFICACION,
            nombre_legal="Cliente de obra",
            correo="obras004a@fyag.test",
        )
        cls.presupuesto = Presupuesto.objects.create(
            cliente=cls.cliente,
            creado_por=cls.finanzas,
            descripcion="Reparación presupuestada",
            estado=Presupuesto.Estado.APROBADO_CLIENTE,
        )
        cls.categoria, _ = CategoriaServicio.objects.get_or_create(
            nombre="Mantención",
            defaults={
                "activo": True,
                "creado_por": None,
            },
        )

    def datos(self, **cambios):
        datos = {
            "presupuesto": self.presupuesto.pk,
            "categoria_servicio": self.categoria.pk,
            "descripcion": "Mantención de sistema de frío",
            "fecha_programada": date.today() + timedelta(days=7),
        }
        datos.update(cambios)
        return datos

    def crear(self, **cambios):
        return services.crear_obra(self.datos(**cambios), self.supervisor)


class ServiciosObrasTests(BaseObras, TestCase):
    def test_creacion_planificada_sin_tecnico_evento_y_sin_cambio_comercial(self):
        obra = self.crear()
        self.assertEqual(obra.estado, Obra.Estado.PLANIFICADA)
        self.assertIsNone(obra.tecnico_responsable_id)
        self.assertIsNone(obra.iniciado_en)
        self.presupuesto.refresh_from_db()
        self.assertEqual(self.presupuesto.estado, Presupuesto.Estado.APROBADO_CLIENTE)
        self.assertEqual(self.presupuesto.eventos.count(), 0)
        evento = obra.eventos.get()
        self.assertEqual(evento.tipo, ObraEvento.Tipo.CREACION)
        self.assertEqual(evento.datos_anteriores, {})
        self.assertEqual(evento.datos_nuevos["tecnico_responsable"], None)
        self.assertEqual(evento.registrado_por_id, self.supervisor.pk)

    def test_creacion_con_tecnico_motivo_obligatorio_en_un_evento(self):
        with self.assertRaises(DatosInvalidos):
            self.crear(tecnico_responsable=self.tecnico.pk)
        self.assertEqual(Obra.objects.count(), 0)
        obra = self.crear(
            tecnico_responsable=self.tecnico.pk,
            motivo="  Técnico asignado para el turno  ",
        )
        evento = obra.eventos.get()
        self.assertEqual(evento.motivo, "Técnico asignado para el turno")
        self.assertEqual(evento.datos_nuevos["tecnico_responsable"], self.tecnico.pk)
        # La validación del modelo también cubre escrituras directas del evento.
        with self.assertRaises(ValidationError):
            ObraEvento.objects.create(
                obra=obra,
                tipo=ObraEvento.Tipo.CREACION,
                estado_anterior=None,
                estado_nuevo="PLANIFICADA",
                registrado_por=self.supervisor,
                motivo="",
                datos_nuevos={"tecnico_responsable": self.tecnico.pk},
            )

    def test_presupuesto_y_categoria_requeridos_y_presupuesto_unico(self):
        obra = self.crear()
        with self.assertRaises(PresupuestoUtilizado):
            self.crear()
        self.assertEqual(obra.eventos.count(), 1)
        self.assertEqual(Obra.objects.count(), 1)
        with self.assertRaises(DatosInvalidos):
            services.crear_obra(self.datos(estado="EN_PROCESO"), self.supervisor)
        with self.assertRaises(EstadoIncompatible):
            self.crear(
                presupuesto=Presupuesto.objects.create(
                    cliente=self.cliente,
                    creado_por=self.finanzas,
                    descripcion="Sin aprobar",
                ).pk
            )

    def test_cliente_inactivo_no_bloquea_creacion(self):
        self.cliente.activo = False
        self.cliente.save()
        obra = self.crear()
        self.assertEqual(obra.presupuesto_id, self.presupuesto.pk)

    def test_no_permite_otro_rol_ni_superuser_incorrecto(self):
        for usuario in (self.finanzas, self.gerencia, self.tecnico):
            with self.subTest(rol=usuario.rol):
                with self.assertRaises(PermisoDenegado):
                    services.crear_obra(self.datos(), usuario)
        self.finanzas.is_superuser = True
        self.finanzas.save()
        with self.assertRaises(PermisoDenegado):
            services.crear_obra(self.datos(), self.finanzas)
        self.assertFalse(Obra.objects.exists())

    def test_asignar_iniciar_suspender_reanudar_sin_cambiar_inicio(self):
        obra = self.crear()
        with self.assertRaises(DatosInvalidos):
            services.iniciar_obra(obra, self.supervisor, "Trabajo en terreno")
        services.cambiar_tecnico(obra, self.tecnico.pk, self.supervisor, "Turno")
        iniciado = services.iniciar_obra(obra, self.supervisor, "Ingreso a terreno")
        self.assertEqual(iniciado.estado, Obra.Estado.EN_PROCESO)
        fecha_original = iniciado.iniciado_en
        with self.assertRaises(EstadoIncompatible):
            services.iniciar_obra(obra, self.supervisor, "Duplicado")
        suspendida = services.suspender_obra(obra, self.supervisor, "Falta repuesto")
        self.assertEqual(suspendida.estado, Obra.Estado.SUSPENDIDA)
        reanudada = services.reanudar_obra(obra, self.supervisor, "Llegó repuesto")
        self.assertEqual(reanudada.estado, Obra.Estado.EN_PROCESO)
        self.assertEqual(reanudada.iniciado_en, fecha_original)
        self.assertEqual(obra.eventos.count(), 5)
        self.assertEqual(
            list(obra.eventos.values_list("tipo", flat=True)),
            [
                "CREACION",
                "CAMBIO_TECNICO",
                "CAMBIO_ESTADO",
                "CAMBIO_ESTADO",
                "CAMBIO_ESTADO",
            ],
        )

    def test_desasignar_solo_planificada_y_mismo_tecnico_409(self):
        obra = self.crear(tecnico_responsable=self.tecnico.pk, motivo="Inicial")
        with self.assertRaises(SinCambios):
            services.cambiar_tecnico(obra, self.tecnico.pk, self.supervisor, "Mismo")
        services.cambiar_tecnico(obra, None, self.supervisor, "Reprogramación")
        self.assertIsNone(Obra.objects.get(pk=obra.pk).tecnico_responsable_id)
        services.cambiar_tecnico(obra, self.tecnico.pk, self.supervisor, "Retomado")
        services.iniciar_obra(obra, self.supervisor, "En ejecución")
        with self.assertRaises(DatosInvalidos):
            services.cambiar_tecnico(obra, None, self.supervisor, "Baja")
        self.assertEqual(
            Obra.objects.get(pk=obra.pk).tecnico_responsable_id, self.tecnico.pk
        )

    def test_reasignacion_suspendida_y_tecnico_inactivo(self):
        obra = self.crear(tecnico_responsable=self.tecnico.pk, motivo="Inicial")
        services.iniciar_obra(obra, self.supervisor, "Inicio")
        services.suspender_obra(obra, self.supervisor, "Pausa")
        self.tecnico.is_active = False
        self.tecnico.save()
        with self.assertRaises(DatosInvalidos):
            services.reanudar_obra(obra, self.supervisor, "Intento")
        services.cambiar_tecnico(
            obra, self.otro_tecnico.pk, self.supervisor, "Reemplazo"
        )
        services.reanudar_obra(obra, self.supervisor, "Reanudación")
        self.assertEqual(obra.eventos.count(), 5)

    def test_edicion_con_historial_y_noop(self):
        obra = self.crear()
        anterior = obra.actualizado_en
        igual = services.editar_obra(
            obra,
            {
                "descripcion": obra.descripcion,
            },
            self.supervisor,
        )
        self.assertEqual(igual.actualizado_en, anterior)
        self.assertEqual(obra.eventos.count(), 1)
        nueva_fecha = timezone.localdate() + timedelta(days=10)
        services.editar_obra(
            obra,
            {
                "descripcion": "  Intervención eléctrica  ",
                "fecha_programada": nueva_fecha,
                "motivo": "Recalendarizar",
            },
            self.supervisor,
        )
        actualizado = Obra.objects.get(pk=obra.pk)
        self.assertEqual(actualizado.descripcion, "Intervención eléctrica")
        self.assertEqual(actualizado.fecha_programada, nueva_fecha)
        ev = obra.eventos.last()
        self.assertEqual(ev.tipo, "EDICION")
        self.assertEqual(ev.datos_anteriores["descripcion"], obra.descripcion)
        with self.assertRaises(DatosInvalidos):
            services.editar_obra(obra, {"estado": "FINALIZADA"}, self.supervisor)

    def test_gerencia_categoria_y_desactivacion_bloquean_alta(self):
        with self.assertRaises(PermisoDenegado):
            services.crear_categoria("Reparación de camiones", self.supervisor)
        cat = services.crear_categoria("Reparación de camiones", self.gerencia)
        self.assertEqual(cat.eventos.count(), 1)
        services.desactivar_categoria(cat, self.gerencia, "Depuración")
        with self.assertRaises(DatosInvalidos):
            self.crear(categoria_servicio=cat.pk)
        services.activar_categoria(cat, self.gerencia, "Vuelve al catálogo")
        nueva = self.crear(categoria_servicio=cat.pk)
        self.assertEqual(nueva.categoria_servicio_id, cat.pk)
        with self.assertRaises(DatosInvalidos):
            services.crear_categoria("REPARACIÓN DE CAMIONES", self.gerencia)

    def test_guard_anulacion_presupuesto_usado_sin_evento_comercial(self):
        obra = self.crear()
        antes = self.presupuesto.eventos.count()
        with self.assertRaises(PresupuestoUtilizadoComercial) as error:
            comercial.anular_presupuesto(self.presupuesto, self.finanzas, "Retirado")
        self.assertEqual(error.exception.codigo, "presupuesto_utilizado")
        self.presupuesto.refresh_from_db()
        self.assertEqual(self.presupuesto.estado, "APROBADO_CLIENTE")
        self.assertEqual(self.presupuesto.eventos.count(), antes)
        self.assertEqual(obra.estado, "PLANIFICADA")

    def test_presupuesto_sin_obra_se_puede_anular(self):
        presupuesto = comercial.anular_presupuesto(
            self.presupuesto, self.finanzas, "No ejecutar"
        )
        self.assertEqual(presupuesto.estado, "ANULADO")
        with self.assertRaises(EstadoIncompatible):
            self.crear()

    def test_no_existen_servicios_terminales_004a(self):
        self.assertFalse(hasattr(services, "finalizar_obra"))
        self.assertFalse(hasattr(services, "cancelar_obra"))


class AnulacionConObraHTTPTests(BaseObras, APITestCase):
    def test_anular_presupuesto_con_obra_devuelve_409_publico(self):
        self.crear()
        token = AccessToken.for_user(self.finanzas)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        r = self.client.post(
            f"/api/presupuestos/{self.presupuesto.pk}/anular/",
            {"motivo": "Cancelación solicitada"},
            format="json",
        )
        self.assertEqual(r.status_code, 409, r.data)
        self.assertEqual(r.data["code"], "presupuesto_utilizado")
        self.assertNotIn("IntegrityError", str(r.data))
