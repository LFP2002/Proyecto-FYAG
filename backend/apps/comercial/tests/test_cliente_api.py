from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.urls import resolve
from django.utils import timezone
from rest_framework.test import APITestCase
from apps.usuarios.tokens import AccessToken

from apps.comercial.models import Cliente


Usuario = get_user_model()


def datos_cliente(**cambios):
    datos = {
        "tipo_cliente": "PERSONA",
        "tipo_identificacion": "SIN_IDENTIFICACION",
        "nombre_legal": "Cliente API",
        "correo": "contacto@example.com",
    }
    datos.update(cambios)
    return datos


def datos_rut(**cambios):
    datos = datos_cliente(
        tipo_cliente="EMPRESA", tipo_identificacion="RUT",
        numero_identificacion="12.345.678-5",
    )
    datos.update(cambios)
    return datos


def datos_extranjero(**cambios):
    datos = datos_cliente(
        tipo_identificacion="DOCUMENTO_EXTRANJERO",
        pais_identificacion="AR", tipo_documento_extranjero="DNI",
        numero_identificacion="ab-123",
    )
    datos.update(cambios)
    return datos


class ClienteAPIBase(APITestCase):
    url = "/api/clientes/"

    @classmethod
    def setUpTestData(cls):
        cls.usuarios = {}
        for rol in Usuario.Rol:
            cls.usuarios[rol] = Usuario.objects.create_user(
                username=rol.value.lower(),
                email=f"{rol.value.lower()}@example.com",
                password="Prueba123!", rol=rol,
            )
        cls.cliente = Cliente.objects.create(**datos_cliente())

    def setUp(self):
        self.autenticar(Usuario.Rol.GERENCIA)

    def autenticar(self, rol):
        token = AccessToken.for_user(self.usuarios[rol])
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def detalle(self, pk=None):
        return f"{self.url}{pk or self.cliente.pk}/"

    def crear(self, datos):
        return self.client.post(self.url, datos, format="json")


class ClienteAutenticacionAPITests(ClienteAPIBase):
    def test_sin_token(self):
        self.client.credentials()
        self.assertEqual(self.client.get(self.url).status_code, 401)

    def test_jwt_real(self):
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_token_invalido(self):
        self.client.credentials(HTTP_AUTHORIZATION="Bearer token-invalido")
        self.assertEqual(self.client.get(self.url).status_code, 401)

    def test_token_expirado(self):
        token = AccessToken.for_user(self.usuarios[Usuario.Rol.GERENCIA])
        token.set_exp(
            from_time=timezone.now() - timedelta(minutes=10),
            lifetime=timedelta(minutes=1),
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual(self.client.get(self.url).status_code, 401)


class ClientePermisosAPITests(ClienteAPIBase):
    def comprobar_operaciones(self, rol, autorizado):
        self.autenticar(rol)
        operaciones = (
            ("get", self.url, None, 200),
            ("get", self.detalle(), None, 200),
            ("post", self.url, datos_cliente(), 201),
            ("patch", self.detalle(), {"nombre_legal": "Modificado"}, 200),
            ("post", self.detalle() + "desactivar/", {}, 200),
            ("post", self.detalle() + "activar/", {}, 200),
        )
        for metodo, url, datos, esperado in operaciones:
            with self.subTest(rol=rol, metodo=metodo, url=url):
                respuesta = getattr(self.client, metodo)(
                    url, datos, format="json"
                )
                self.assertEqual(
                    respuesta.status_code, esperado if autorizado else 403
                )

    def test_roles_administrativos(self):
        for rol in (
            Usuario.Rol.GERENCIA, Usuario.Rol.ADMINISTRATIVO_FINANZAS,
        ):
            self.comprobar_operaciones(rol, True)

    def test_roles_sin_acceso(self):
        for rol in (Usuario.Rol.SUPERVISOR_OBRAS, Usuario.Rol.TECNICO):
            self.comprobar_operaciones(rol, False)
        self.assertEqual(Cliente.objects.count(), 1)
        self.cliente.refresh_from_db()
        self.assertEqual(self.cliente.nombre_legal, "Cliente API")
        self.assertTrue(self.cliente.activo)

    def test_rol_del_frontend_no_autoriza(self):
        self.autenticar(Usuario.Rol.TECNICO)
        respuesta = self.client.post(
            self.url + "?rol=GERENCIA",
            datos_cliente(rol="GERENCIA", role="GERENCIA"),
            format="json", HTTP_X_ROLE="GERENCIA",
        )
        self.assertEqual(respuesta.status_code, 403)


class ClienteCreacionAPITests(ClienteAPIBase):
    def test_rut_y_contacto_canonicos(self):
        respuesta = self.crear(datos_rut(
            nombre_legal="  Empresa Demo SpA  ",
            correo="  CONTACTO@EXAMPLE.COM  ",
        ))
        self.assertEqual(respuesta.status_code, 201, respuesta.data)
        cliente = Cliente.objects.get(pk=respuesta.data["id"])
        self.assertEqual(cliente.numero_identificacion, "12345678-5")
        self.assertEqual(cliente.nombre_legal, "Empresa Demo SpA")
        self.assertEqual(cliente.correo, "contacto@example.com")
        self.assertTrue(cliente.activo)

    def test_persona_sin_identificacion(self):
        respuesta = self.crear(datos_cliente())
        self.assertEqual(respuesta.status_code, 201)
        self.assertIsNone(respuesta.data["numero_identificacion"])

    def test_extranjero_canonico(self):
        respuesta = self.crear(datos_extranjero(
            pais_identificacion=" ar ", tipo_documento_extranjero=" dni ",
            numero_identificacion=" ab-123/45 ",
        ))
        self.assertEqual(respuesta.status_code, 201, respuesta.data)
        cliente = Cliente.objects.get(pk=respuesta.data["id"])
        self.assertEqual(cliente.pais_identificacion, "AR")
        self.assertEqual(cliente.tipo_documento_extranjero, "DNI")
        self.assertEqual(cliente.numero_identificacion, "AB-123/45")

    def test_id_y_fechas_solo_lectura(self):
        respuesta = self.crear(datos_cliente(
            id=999999, creado_en="2000-01-01T00:00:00Z",
            actualizado_en="2000-01-01T00:00:00Z",
        ))
        self.assertEqual(respuesta.status_code, 201)
        self.assertNotEqual(respuesta.data["id"], 999999)
        cliente = Cliente.objects.get(pk=respuesta.data["id"])
        self.assertNotEqual(cliente.creado_en.year, 2000)
        self.assertNotEqual(cliente.actualizado_en.year, 2000)

    def test_salida_solo_campos_publicos(self):
        respuesta = self.client.get(self.detalle())
        self.assertEqual(set(respuesta.data), {
            "id", "tipo_cliente", "tipo_identificacion",
            "numero_identificacion", "pais_identificacion",
            "tipo_documento_extranjero", "nombre_legal", "nombre_contacto",
            "correo", "telefono", "activo", "creado_en", "actualizado_en",
        })


class ClienteValidacionAPITests(ClienteAPIBase):
    def test_campo_desconocido_en_post_no_crea_cliente(self):
        cantidad = Cliente.objects.count()
        for formato in ("json", "multipart"):
            with self.subTest(formato=formato):
                respuesta = self.client.post(
                    self.url, datos_cliente(correoo="error@example.com"),
                    format=formato,
                )
                self.assertEqual(respuesta.status_code, 400)
                self.assertEqual(
                    str(respuesta.data["correoo"]),
                    "No es un campo permitido.",
                )
                self.assertEqual(Cliente.objects.count(), cantidad)

    def test_campo_desconocido_en_patch_no_modifica_cliente(self):
        anterior = Cliente.objects.values().get(pk=self.cliente.pk)
        for formato in ("json", "multipart"):
            with self.subTest(formato=formato):
                respuesta = self.client.patch(self.detalle(), {
                    "telefno": "+56912345678",
                    "nombre_legal": "Cambio que no debe persistir",
                }, format=formato)
                self.assertEqual(respuesta.status_code, 400)
                self.assertEqual(
                    str(respuesta.data["telefno"]),
                    "No es un campo permitido.",
                )
                self.assertEqual(
                    Cliente.objects.values().get(pk=self.cliente.pk), anterior
                )

    def test_datos_invalidos(self):
        casos = (
            datos_rut(numero_identificacion="12345678-9"),
            datos_cliente(nombre_legal="  "),
            datos_cliente(correo="", telefono=""),
            datos_cliente(correo="correo-invalido"),
            datos_extranjero(pais_identificacion=None),
            datos_extranjero(numero_identificacion=None),
            datos_extranjero(tipo_documento_extranjero=None),
            datos_extranjero(pais_identificacion="123"),
            datos_rut(pais_identificacion="CL"),
            datos_cliente(numero_identificacion="123"),
            datos_cliente(tipo_cliente="OTRO"),
        )
        for datos in casos:
            with self.subTest(datos=datos):
                respuesta = self.crear(datos)
                self.assertEqual(respuesta.status_code, 400, respuesta.data)
                self.assertNotIn("Traceback", str(respuesta.data))
                self.assertNotIn("constraint", str(respuesta.data))
        self.assertEqual(Cliente.objects.count(), 1)

    def test_activo_rechazado_en_creacion(self):
        for activo in (False, True, None):
            with self.subTest(activo=activo):
                respuesta = self.crear(datos_cliente(activo=activo))
                self.assertEqual(respuesta.status_code, 400)
                self.assertIn("activo", respuesta.data)
                self.assertEqual(
                    str(respuesta.data["activo"]),
                    "Utilice la operación de activación/desactivación.",
                )

    def test_activo_rechazado_en_patch(self):
        respuesta = self.client.patch(
            self.detalle(), {"activo": False}, format="json"
        )
        self.assertEqual(respuesta.status_code, 400)
        self.assertEqual(
            str(respuesta.data["activo"]),
            "Utilice la operación de activación/desactivación.",
        )
        self.cliente.refresh_from_db()
        self.assertTrue(self.cliente.activo)

    def test_patch_transicion_incompleta(self):
        cliente = Cliente.objects.create(**datos_rut())
        respuesta = self.client.patch(self.detalle(cliente.pk), {
            "tipo_identificacion": "SIN_IDENTIFICACION",
        }, format="json")
        self.assertEqual(respuesta.status_code, 400)
        cliente.refresh_from_db()
        self.assertEqual(cliente.tipo_identificacion, "RUT")
        self.assertEqual(cliente.numero_identificacion, "12345678-5")

    def test_patch_valida_contacto_final(self):
        respuesta = self.client.patch(
            self.detalle(), {"correo": ""}, format="json"
        )
        self.assertEqual(respuesta.status_code, 400)


class ClienteDuplicadosAPITests(ClienteAPIBase):
    def test_rut_equivalente_duplicado(self):
        self.assertEqual(self.crear(datos_rut()).status_code, 201)
        respuesta = self.crear(datos_rut(
            numero_identificacion="00012345678-5",
        ))
        self.assertEqual(respuesta.status_code, 400)
        self.assertEqual(str(respuesta.data["numero_identificacion"][0]),
                         "Ya existe un cliente con este RUT.")
        self.assertEqual(Cliente.objects.filter(
            tipo_identificacion="RUT"
        ).count(), 1)

    def test_extranjero_equivalente_duplicado(self):
        self.assertEqual(self.crear(datos_extranjero()).status_code, 201)
        respuesta = self.crear(datos_extranjero(
            pais_identificacion="ar", tipo_documento_extranjero="dni",
            numero_identificacion="AB-123",
        ))
        self.assertEqual(respuesta.status_code, 400)
        self.assertEqual(Cliente.objects.filter(
            tipo_identificacion="DOCUMENTO_EXTRANJERO"
        ).count(), 1)

    def test_integrity_error_conocido_se_convierte_en_400(self):
        # Omite la detección previa para probar el conflicto real en PostgreSQL.
        for datos in (datos_rut(), datos_extranjero()):
            with self.subTest(datos=datos):
                Cliente.objects.create(**datos)
                with (
                    patch("apps.comercial.serializers.validar_cliente"),
                    patch("apps.comercial.services.validar_cliente"),
                ):
                    respuesta = self.crear(datos)
                self.assertEqual(respuesta.status_code, 400)
                self.assertNotIn("cliente_", str(respuesta.data))
                self.assertNotIn("DETAIL", str(respuesta.data))
        self.assertEqual(Cliente.objects.count(), 3)

    def test_integrity_error_desconocido_no_se_oculta(self):
        with patch.object(Cliente, "save", side_effect=IntegrityError("otro")):
            with self.assertRaises(IntegrityError):
                self.crear(datos_cliente())


class ClienteModificacionAPITests(ClienteAPIBase):
    def test_patch_contacto_normalizado(self):
        respuesta = self.client.patch(self.detalle(), {
            "nombre_legal": "  Nuevo Nombre  ",
            "nombre_contacto": "  Ana Pérez  ",
            "correo": "  NUEVO@EXAMPLE.COM  ", "telefono": "  +54 123  ",
        }, format="json")
        self.assertEqual(respuesta.status_code, 200, respuesta.data)
        self.cliente.refresh_from_db()
        self.assertEqual(self.cliente.nombre_legal, "Nuevo Nombre")
        self.assertEqual(self.cliente.nombre_contacto, "Ana Pérez")
        self.assertEqual(self.cliente.correo, "nuevo@example.com")
        self.assertEqual(self.cliente.telefono, "+54 123")

    def test_transicion_sin_identificacion_a_rut(self):
        respuesta = self.client.patch(self.detalle(), {
            "tipo_identificacion": "RUT",
            "numero_identificacion": "12.345.678-5",
        }, format="json")
        self.assertEqual(respuesta.status_code, 200)
        self.cliente.refresh_from_db()
        self.assertEqual(self.cliente.numero_identificacion, "12345678-5")

    def test_transicion_a_sin_identificacion_explicita(self):
        cliente = Cliente.objects.create(**datos_extranjero())
        respuesta = self.client.patch(self.detalle(cliente.pk), {
            "tipo_identificacion": "SIN_IDENTIFICACION",
            "numero_identificacion": None, "pais_identificacion": None,
            "tipo_documento_extranjero": None,
        }, format="json")
        self.assertEqual(respuesta.status_code, 200)
        cliente.refresh_from_db()
        self.assertIsNone(cliente.numero_identificacion)
        self.assertIsNone(cliente.pais_identificacion)
        self.assertIsNone(cliente.tipo_documento_extranjero)

    def test_patch_no_cambia_pk_ni_fecha_creacion(self):
        fecha = self.cliente.creado_en
        pk = self.cliente.pk
        respuesta = self.client.patch(self.detalle(), {
            "id": 999999, "creado_en": "2000-01-01T00:00:00Z",
            "actualizado_en": "2000-01-01T00:00:00Z",
        }, format="json")
        self.assertEqual(respuesta.status_code, 200)
        self.cliente.refresh_from_db()
        self.assertEqual(self.cliente.pk, pk)
        self.assertEqual(self.cliente.creado_en, fecha)
        self.assertNotEqual(self.cliente.actualizado_en.year, 2000)

    def test_patch_mismo_rut_no_es_duplicado(self):
        cliente = Cliente.objects.create(**datos_rut())
        respuesta = self.client.patch(self.detalle(cliente.pk), {
            "numero_identificacion": "00012345678-5",
        }, format="json")
        self.assertEqual(respuesta.status_code, 200)


class ClienteEstadoAPITests(ClienteAPIBase):
    def test_estado_idempotente_y_persistente(self):
        for accion, esperado in (
            ("desactivar", False), ("desactivar", False),
            ("activar", True), ("activar", True),
        ):
            with self.subTest(accion=accion, esperado=esperado):
                respuesta = self.client.post(
                    self.detalle() + accion + "/", {}, format="json"
                )
                self.assertEqual(respuesta.status_code, 200)
                self.assertEqual(respuesta.data["activo"], esperado)
                self.cliente.refresh_from_db()
                self.assertEqual(self.cliente.activo, esperado)

    def test_inactivo_visible_editable_y_reactivable(self):
        self.client.post(self.detalle() + "desactivar/")
        listado = self.client.get(self.url)
        self.assertIn(self.cliente.pk, [fila["id"] for fila in listado.data])
        self.assertEqual(self.client.get(self.detalle()).status_code, 200)
        respuesta = self.client.patch(self.detalle(), {
            "nombre_legal": "Histórico",
        }, format="json")
        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(respuesta.data["activo"])
        self.assertEqual(self.client.post(
            self.detalle() + "activar/"
        ).status_code, 200)


class ClienteRutasAPITests(ClienteAPIBase):
    def test_delete_prohibido_conserva_cliente(self):
        self.assertEqual(self.client.delete(self.detalle()).status_code, 405)
        self.assertTrue(Cliente.objects.filter(pk=self.cliente.pk).exists())

    def test_put_prohibido(self):
        respuesta = self.client.put(
            self.detalle(), datos_cliente(), format="json"
        )
        self.assertEqual(respuesta.status_code, 405)

    def test_inexistentes(self):
        for metodo, sufijo in (
            ("get", ""), ("patch", ""),
            ("post", "activar/"), ("post", "desactivar/"),
        ):
            with self.subTest(metodo=metodo, sufijo=sufijo):
                respuesta = getattr(self.client, metodo)(
                    self.detalle(999999) + sufijo, {}, format="json"
                )
                self.assertEqual(respuesta.status_code, 404)

    def test_orden_determinista(self):
        primero = Cliente.objects.create(**datos_cliente(nombre_legal="AAA"))
        segundo = Cliente.objects.create(**datos_cliente(nombre_legal="AAA"))
        respuesta = self.client.get(self.url)
        self.assertEqual(
            [fila["id"] for fila in respuesta.data],
            [primero.pk, segundo.pk, self.cliente.pk],
        )

    def test_rutas_clientes_y_auth(self):
        for ruta, nombre in (
            (self.url, "cliente-list"),
            (self.detalle(), "cliente-detail"),
            (self.detalle() + "activar/", "cliente-activar"),
            (self.detalle() + "desactivar/", "cliente-desactivar"),
            ("/api/auth/login/", "login"),
            ("/api/auth/csrf/", "csrf"),
            ("/api/auth/refresh/", "token_refresh"),
            ("/api/auth/logout/", "logout"),
            ("/api/auth/me/", "perfil_actual"),
        ):
            with self.subTest(ruta=ruta):
                self.assertEqual(resolve(ruta).url_name, nombre)
