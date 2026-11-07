"""Contrato HTTP Obras 004A: JWT, roles, proyecciones y acciones permitidas."""

from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from apps.comercial.models import Cliente, Presupuesto
from apps.obras.models import CategoriaServicio, Obra


Usuario = get_user_model()
G = Usuario.Rol.GERENCIA
AF = Usuario.Rol.ADMINISTRATIVO_FINANZAS
S = Usuario.Rol.SUPERVISOR_OBRAS
T = Usuario.Rol.TECNICO


class ObrasAPIBase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.usuarios = {}
        for rol in Usuario.Rol:
            cls.usuarios[rol] = Usuario.objects.create_user(
                username="api_" + rol.value.lower(),
                email=rol.value.lower() + "_obras@fyag.test",
                password="Prueba123!", rol=rol,
            )
        cls.tecnico2 = Usuario.objects.create_user(
            username="tecnico_adicional", email="tecnico_adicional@fyag.test",
            password="Prueba123!", rol=T,
        )
        cls.cliente = Cliente.objects.create(
            tipo_cliente=Cliente.TipoCliente.EMPRESA,
            tipo_identificacion=Cliente.TipoIdentificacion.SIN_IDENTIFICACION,
            nombre_legal="Cliente para API Obras", correo="cliente_obras@fyag.test",
        )
        cls.presupuesto = Presupuesto.objects.create(
            cliente=cls.cliente,
            descripcion="Presupuesto reservado con valores sensibles",
            estado=Presupuesto.Estado.APROBADO_CLIENTE,
            creado_por=cls.usuarios[AF],
        )
        cls.categoria, _ = CategoriaServicio.objects.get_or_create(
            nombre="Mantención", defaults={"activo": True, "creado_por": None},
        )

    def setUp(self):
        self.client = APIClient()
        self.autenticar(S)

    def autenticar(self, rol):
        usuario = self.usuarios[rol]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(usuario)}")

    def autenticar_usuario(self, usuario):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(usuario)}")

    def crear_presupuesto(self, estado=Presupuesto.Estado.APROBADO_CLIENTE):
        return Presupuesto.objects.create(
            cliente=self.cliente, descripcion="Otro presupuesto comercial",
            estado=estado, creado_por=self.usuarios[AF],
        )

    def datos_creacion(self, *, presupuesto=None, tecnico=None, **extras):
        datos = {
            "presupuesto": presupuesto.pk if presupuesto else self.presupuesto.pk,
            "categoria_servicio": self.categoria.pk,
            "descripcion": "Mantención de equipo de frío",
            "fecha_programada": (date.today() + timedelta(days=4)).isoformat(),
        }
        if tecnico is not None:
            datos["tecnico_responsable"] = tecnico.pk
            datos["motivo"] = "Asignación inicial"
        datos.update(extras)
        return datos

    def crear_obra(self, *, tecnico=None, presupuesto=None, **extras):
        respuesta = self.client.post(
            "/api/obras/",
            self.datos_creacion(tecnico=tecnico, presupuesto=presupuesto, **extras),
            format="json",
        )
        self.assertEqual(respuesta.status_code, 201, respuesta.data)
        return Obra.objects.get(pk=respuesta.data["id"])


class ObrasAPIContratoTests(ObrasAPIBase):
    def test_jwt_obligatorio(self):
        self.client.credentials()
        self.assertEqual(self.client.get("/api/obras/").status_code, 401)
        self.assertEqual(self.client.post("/api/obras/", {}, format="json").status_code, 401)

    def test_crear_planificada_y_respuesta_exacta(self):
        obra = self.crear_obra()
        respuesta = self.client.get(f"/api/obras/{obra.pk}/")
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.data["estado"], "PLANIFICADA")
        self.assertIsNone(respuesta.data["tecnico_responsable"])
        self.assertIsNone(respuesta.data["iniciado_en"])
        self.assertEqual(respuesta.data["cliente"], self.cliente.pk)
        self.assertEqual(set(respuesta.data), {
            "id", "codigo", "presupuesto", "presupuesto_codigo", "cliente",
            "cliente_nombre", "categoria_servicio", "categoria_nombre",
            "descripcion", "tecnico_responsable", "tecnico_nombre",
            "fecha_programada", "iniciado_en", "estado", "finalizado_en",
            "cancelado_en", "creado_por", "creado_en", "actualizado_en",
        })
        self.assertNotIn("monto_neto", respuesta.data)
        self.assertNotIn("items", respuesta.data)
        self.assertNotIn("correo", respuesta.data)
        self.assertEqual(self.client.get("/api/obras/").data["count"], 1)

    def test_solo_presupuesto_aprobado_y_sin_duplicados(self):
        borrador = self.crear_presupuesto(Presupuesto.Estado.BORRADOR)
        respuesta = self.client.post(
            "/api/obras/", self.datos_creacion(presupuesto=borrador), format="json",
        )
        self.assertEqual(respuesta.status_code, 409, respuesta.data)
        obra = self.crear_obra()
        self.assertEqual(obra.estado, Obra.Estado.PLANIFICADA)
        respuesta = self.client.post("/api/obras/", self.datos_creacion(), format="json")
        self.assertEqual(respuesta.status_code, 409, respuesta.data)
        self.assertEqual(str(respuesta.data["code"]), "presupuesto_utilizado")
        self.assertEqual(self.client.get("/api/obras/presupuestos-disponibles/").data["count"], 0)

    def test_entrada_estricta_y_sin_campos_administrados(self):
        for campo, valor in (
            ("estado", "FINALIZADA"), ("codigo", "OB-000009"),
            ("monto_neto", "999"), ("requiere_aprobacion_gerencia", True),
            ("cliente", self.cliente.pk), ("otro", 1),
        ):
            with self.subTest(campo=campo):
                datos = self.datos_creacion()
                datos[campo] = valor

                respuesta = self.client.post(
                    "/api/obras/", datos,
                    format="json",
                )
                self.assertEqual(respuesta.status_code, 400, respuesta.data)
                self.assertIn(campo, respuesta.data)
        self.assertEqual(Obra.objects.count(), 0)

    def test_tipos_estrictos_y_fecha_futura(self):
        for campo, valor in (
            ("presupuesto", str(self.presupuesto.pk)),
            ("presupuesto", True),
            ("categoria_servicio", 1.0),
            ("fecha_programada", "2026-02-30"),
            ("fecha_programada", "11/07/2026"),
            ("descripcion", 33),
        ):
            with self.subTest(campo=campo, valor=valor):
                datos = self.datos_creacion()
                datos[campo] = valor

                respuesta = self.client.post(
                    "/api/obras/", datos,
                    format="json",
                )
                self.assertEqual(respuesta.status_code, 400, respuesta.data)
        self.assertEqual(Obra.objects.count(), 0)

    def test_creacion_con_tecnico_motivo_y_acciones(self):
        obra = self.crear_obra(tecnico=self.usuarios[T])
        detalle = f"/api/obras/{obra.pk}/"
        res = self.client.post(detalle + "iniciar/", {"motivo": "Comenzamos"}, format="json")
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["estado"], "EN_PROCESO")
        iniciado = res.data["iniciado_en"]
        self.assertIsNotNone(iniciado)
        res = self.client.post(detalle + "suspender/", {"motivo": "Sin insumos"}, format="json")
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["estado"], "SUSPENDIDA")
        res = self.client.post(detalle + "reanudar/", {"motivo": "Insumos listos"}, format="json")
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["iniciado_en"], iniciado)
        historia = self.client.get(detalle + "historial/")
        self.assertEqual(historia.status_code, 200)
        self.assertEqual(historia.data["count"], 4)

    def test_no_hay_finalizar_ni_cancelar_004a(self):
        obra = self.crear_obra(tecnico=self.usuarios[T])
        for nombre in ("finalizar", "cancelar"):
            with self.subTest(accion=nombre):
                respuesta = self.client.post(
                    f"/api/obras/{obra.pk}/{nombre}/",
                    {"motivo": "Intento"}, format="json",
                )
                self.assertEqual(respuesta.status_code, 404)
        for metodo in ("put", "delete"):
            self.assertEqual(getattr(self.client, metodo)(f"/api/obras/{obra.pk}/").status_code, 405)

    def test_edicion_y_cambiar_tecnico(self):
        obra = self.crear_obra()
        detalle = f"/api/obras/{obra.pk}/"
        res = self.client.patch(
            detalle, {"descripcion": "  Nueva mantención  ", "motivo": "Corrección"}, format="json",
        )
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["descripcion"], "Nueva mantención")
        res = self.client.post(
            detalle + "cambiar-tecnico/",
            {"tecnico_responsable": self.usuarios[T].pk, "motivo": "Asignación"},
            format="json",
        )
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["tecnico_responsable"], self.usuarios[T].pk)
        res = self.client.post(
            detalle + "cambiar-tecnico/",
            {"tecnico_responsable": self.usuarios[T].pk, "motivo": "Reintento"},
            format="json",
        )
        self.assertEqual(res.status_code, 409, res.data)
        self.assertEqual(str(res.data["code"]), "sin_cambios")
        res = self.client.patch(detalle, {"estado": "FINALIZADA"}, format="json")
        self.assertEqual(res.status_code, 400)

    def test_creacion_exige_motivo_si_asigna_tecnico(self):
        datos = self.datos_creacion(tecnico=self.usuarios[T])
        del datos["motivo"]
        res = self.client.post("/api/obras/", datos, format="json")
        self.assertEqual(res.status_code, 400, res.data)
        self.assertEqual(Obra.objects.count(), 0)

    def test_roles_matriz_y_superusuario_sin_bypass(self):
        for rol in Usuario.Rol:
            self.autenticar(rol)
            respuesta = self.client.post(
                "/api/obras/", self.datos_creacion(), format="json",
            )
            self.assertEqual(respuesta.status_code, 201 if rol == S else 403, respuesta.data)
            # La creación del supervisor queda en la base aislada de este test.
        tecnico = self.usuarios[T]
        tecnico.is_superuser = True
        tecnico.save()
        self.autenticar(T)
        self.assertEqual(self.client.post("/api/obras/", self.datos_creacion(), format="json").status_code, 403)
        self.assertEqual(self.client.get("/api/obras/presupuestos-disponibles/").status_code, 403)

    def test_tecnico_solo_obra_propia_lista_conteo_detalle(self):
        propia = self.crear_obra(tecnico=self.usuarios[T])
        ajena = self.crear_obra(presupuesto=self.crear_presupuesto(), tecnico=self.tecnico2)
        self.autenticar(T)
        listado = self.client.get("/api/obras/")
        self.assertEqual(listado.status_code, 200, listado.data)
        self.assertEqual(listado.data["count"], 1)
        self.assertEqual(listado.data["results"][0]["id"], propia.pk)
        self.assertEqual(self.client.get(f"/api/obras/{propia.pk}/").status_code, 200)
        self.assertEqual(self.client.get(f"/api/obras/{ajena.pk}/").status_code, 404)
        self.assertEqual(self.client.get("/api/obras/?tecnico_responsable=" + str(self.tecnico2.pk)).data["count"], 0)
        self.assertEqual(self.client.get(f"/api/obras/{propia.pk}/historial/").status_code, 403)
        self.assertEqual(self.client.post(f"/api/obras/{propia.pk}/iniciar/", {"motivo": "Intento"}, format="json").status_code, 403)

    def test_finanzas_solo_proyeccion_minima(self):
        obra = self.crear_obra(tecnico=self.usuarios[T])
        self.autenticar(AF)
        res = self.client.get(f"/api/obras/{obra.pk}/")
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(set(res.data), {
            "id", "codigo", "presupuesto", "presupuesto_codigo", "cliente",
            "cliente_nombre", "categoria_servicio", "categoria_nombre",
            "tecnico_responsable", "tecnico_nombre", "fecha_programada",
            "iniciado_en", "estado", "finalizado_en",
        })
        self.assertEqual(self.client.get("/api/obras/").data["results"][0].keys(), res.data.keys())
        for ruta in (
            f"/api/obras/{obra.pk}/historial/",
            "/api/obras/tecnicos-disponibles/",
            "/api/obras/presupuestos-disponibles/",
            "/api/categorias-servicio/",
        ):
            self.assertEqual(self.client.get(ruta).status_code, 403)

    def test_listas_disponibles_y_cambio_de_acceso(self):
        presupuesto2 = self.crear_presupuesto()
        disponibles = self.client.get("/api/obras/presupuestos-disponibles/")
        self.assertEqual(disponibles.status_code, 200)
        self.assertEqual(disponibles.data["count"], 2)
        self.assertEqual(set(disponibles.data["results"][0]), {"id", "codigo", "cliente", "cliente_nombre"})
        tecnicos = self.client.get("/api/obras/tecnicos-disponibles/")
        self.assertEqual(tecnicos.status_code, 200)
        self.assertTrue(all(set(t) == {"id", "nombre"} for t in tecnicos.data["results"]))
        obra = self.crear_obra(tecnico=self.usuarios[T])
        detalle = f"/api/obras/{obra.pk}/"
        self.client.post(detalle + "cambiar-tecnico/", {
            "tecnico_responsable": self.tecnico2.pk, "motivo": "Turno siguiente",
        }, format="json")
        self.autenticar(T)
        self.assertEqual(self.client.get(detalle).status_code, 404)
        self.autenticar_usuario(self.tecnico2)
        self.assertEqual(self.client.get(detalle).status_code, 200)

    def test_filtros_orden_y_query_malformada(self):
        self.crear_obra(tecnico=self.usuarios[T])
        self.crear_obra(presupuesto=self.crear_presupuesto())
        for query in (
            "estado=OTRO", "tecnico_responsable=texto", "cliente=0",
            "fecha_programada_desde=ayer", "ordering=monto_neto", "rol=GERENCIA",
            "fecha_programada_desde=2026-12-31&fecha_programada_hasta=2026-01-01",
        ):
            with self.subTest(query=query):
                res = self.client.get("/api/obras/?" + query)
                self.assertEqual(res.status_code, 400, res.data)
        res = self.client.get("/api/obras/?ordering=fecha_programada")
        self.assertEqual(res.status_code, 200, res.data)
        res = self.client.get("/api/obras/?estado=PLANIFICADA")
        self.assertEqual(res.data["count"], 2)
        res = self.client.get("/api/obras/?page=1000")
        self.assertEqual(res.status_code, 404)

    def test_catalogo_y_permisos(self):
        self.autenticar(S)
        self.assertEqual(self.client.get("/api/categorias-servicio/").status_code, 200)
        self.assertEqual(self.client.post("/api/categorias-servicio/", {"nombre": "Nueva"}, format="json").status_code, 403)
        self.autenticar(G)
        res = self.client.post("/api/categorias-servicio/", {"nombre": "  Calefacción  "}, format="json")
        self.assertEqual(res.status_code, 201, res.data)
        cat = res.data["id"]
        res = self.client.patch(f"/api/categorias-servicio/{cat}/", {
            "nombre": "Servicio de calefacción", "motivo": "Nombre preciso",
        }, format="json")
        self.assertEqual(res.status_code, 200, res.data)
        res = self.client.post(f"/api/categorias-servicio/{cat}/desactivar/", {
            "motivo": "No ofertar"}, format="json",
        )
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data["activo"], False)
        hist = self.client.get(f"/api/categorias-servicio/{cat}/historial/")
        self.assertEqual(hist.status_code, 200, hist.data)
        self.assertEqual(hist.data["count"], 3)
        res = self.client.post("/api/categorias-servicio/", {"nombre": "servicio de calefacción"}, format="json")
        self.assertEqual(res.status_code, 400, res.data)
        self.assertEqual(self.client.get("/api/categorias-servicio/?activo=false").status_code, 200)
        self.assertEqual(self.client.get("/api/categorias-servicio/?activo=sí").status_code, 400)
