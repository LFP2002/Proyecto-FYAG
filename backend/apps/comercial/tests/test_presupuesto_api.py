from datetime import timedelta
from decimal import Decimal
import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection
from django.test.utils import CaptureQueriesContext
from django.urls import resolve
from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken

from apps.comercial import services_presupuestos as servicios
from apps.comercial.exceptions import (
    DatosInvalidos,
    MotivoObligatorio,
    RecursoNoEncontrado,
)
from apps.comercial.models import Cliente, Presupuesto, PresupuestoEvento
from apps.comercial.models import PresupuestoItem


Usuario = get_user_model()
AF = Usuario.Rol.ADMINISTRATIVO_FINANZAS
G = Usuario.Rol.GERENCIA


def datos_item(**cambios):
    datos = {
        "descripcion": " Montaje ", "cantidad": "2.500", "unidad": " hora ",
        "precio_unitario": "100.25", "orden": 1,
    }
    datos.update(cambios)
    return datos


class PresupuestoAPIBase(APITestCase):
    url = "/api/presupuestos/"

    @classmethod
    def setUpTestData(cls):
        cls.usuarios = {}
        for rol in Usuario.Rol:
            cls.usuarios[rol] = Usuario.objects.create_user(
                username=rol.value.lower(), email=f"{rol.value}@example.com",
                password="Prueba123!", rol=rol,
            )
        cls.cliente = Cliente.objects.create(
            tipo_cliente="PERSONA", tipo_identificacion="SIN_IDENTIFICACION",
            nombre_legal="Cliente API", correo="cliente@example.com",
        )

    def setUp(self):
        self.autenticar(AF)
        self.presupuesto = self.preparar()

    def autenticar(self, rol):
        token = AccessToken.for_user(self.usuarios[rol])
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def preparar(self, estado="BORRADOR", requiere=True, con_item=True):
        presupuesto = servicios.crear_presupuesto(
            cliente=self.cliente, descripcion="Servicio de frío",
            requiere_aprobacion_gerencia=requiere, usuario=self.usuarios[AF],
        )
        if con_item:
            datos = datos_item()
            datos["cantidad"] = Decimal(datos["cantidad"])
            datos["precio_unitario"] = Decimal(datos["precio_unitario"])
            servicios.crear_item(presupuesto, datos)
        if estado != "BORRADOR":
            # Fixture de estado; también hay pruebas de flujos HTTP completos.
            presupuesto.estado = estado
            presupuesto.save()
        return presupuesto

    def detalle(self, presupuesto=None):
        pk = presupuesto.pk if presupuesto is not None else self.presupuesto.pk
        return f"{self.url}{pk}/"

    def cabecera(self, **cambios):
        datos = {
            "cliente": self.cliente.pk, "descripcion": " Servicio propuesto ",
            "requiere_aprobacion_gerencia": False,
        }
        datos.update(cambios)
        return datos

    def accion(self, nombre, presupuesto=None, datos=None):
        return self.client.post(
            self.detalle(presupuesto) + nombre + "/",
            {} if datos is None else datos, format="json",
        )


class PresupuestoAuthAPITests(PresupuestoAPIBase):
    def test_sin_jwt(self):
        self.client.credentials()
        self.assertEqual(self.client.get(self.url).status_code, 401)

    def test_jwt_real(self):
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_jwt_invalido(self):
        self.client.credentials(HTTP_AUTHORIZATION="Bearer invalido")
        self.assertEqual(self.client.get(self.url).status_code, 401)

    def test_jwt_expirado(self):
        token = AccessToken.for_user(self.usuarios[AF])
        token.set_exp(
            from_time=timezone.now() - timedelta(minutes=10),
            lifetime=timedelta(minutes=1),
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual(self.client.get(self.url).status_code, 401)


class PresupuestoRolesAPITests(PresupuestoAPIBase):
    def operaciones(self):
        borrador = self.preparar()
        detalle = self.detalle(borrador)
        item_url = detalle + f"items/{borrador.items.get().pk}/"
        operaciones = [
            ("get", self.url, {}, {AF, G}, 200),
            ("get", detalle, {}, {AF, G}, 200),
            ("get", detalle + "historial/", {}, {AF, G}, 200),
            ("post", self.url, self.cabecera(), {AF}, 201),
            ("patch", detalle, {"descripcion": "Actualizada"}, {AF}, 200),
            ("post", detalle + "items/", datos_item(orden=2), {AF}, 201),
            ("patch", item_url, {"cantidad": "3"}, {AF}, 200),
            ("delete", item_url, {}, {AF}, 204),
        ]
        for accion, estado, requiere, rol, esperado in (
            ("enviar-gerencia", "BORRADOR", True, AF, 200),
            ("aprobar-gerencia", "PENDIENTE_GERENCIA", True, G, 200),
            ("rechazar-gerencia", "PENDIENTE_GERENCIA", True, G, 200),
            ("enviar-cliente", "BORRADOR", False, AF, 200),
            ("registrar-aprobacion-cliente", "ENVIADO_CLIENTE", True, AF, 200),
            ("registrar-rechazo-cliente", "ENVIADO_CLIENTE", True, AF, 200),
            ("anular", "BORRADOR", True, AF, 200),
            ("crear-revision", "ANULADO", True, AF, 201),
        ):
            presupuesto = self.preparar(estado, requiere)
            datos = (
                {} if accion == "crear-revision" else {"motivo": "Decisión"}
            )
            operaciones.append((
                "post", self.detalle(presupuesto) + accion + "/", datos,
                {rol}, esperado,
            ))
        return operaciones

    def test_matriz_cuatro_roles_todas_las_operaciones(self):
        for rol in Usuario.Rol:
            self.autenticar(rol)
            for metodo, ruta, datos, permitidos, exito in self.operaciones():
                with self.subTest(rol=rol, metodo=metodo, ruta=ruta):
                    respuesta = getattr(self.client, metodo)(
                        ruta, datos, format="json"
                    )
                    self.assertEqual(
                        respuesta.status_code,
                        exito if rol in permitidos else 403,
                        respuesta.data,
                    )

    def test_rol_inyectado_no_autoriza(self):
        for rol in (Usuario.Rol.TECNICO, Usuario.Rol.SUPERVISOR_OBRAS, G):
            self.autenticar(rol)
            respuesta = self.client.post(
                self.url + "?rol=ADMINISTRATIVO_FINANZAS",
                self.cabecera(rol=AF, role=AF), format="json",
                HTTP_X_ROLE=AF,
            )
            self.assertEqual(respuesta.status_code, 403)
        self.autenticar(AF)
        respuesta = self.client.post(
            self.detalle() + "aprobar-gerencia/?rol=GERENCIA",
            {"rol": G}, format="json", HTTP_X_ROLE=G,
        )
        self.assertEqual(respuesta.status_code, 403)

    def test_superuser_no_elude_rol(self):
        tecnico = self.usuarios[Usuario.Rol.TECNICO]
        tecnico.is_superuser = True
        tecnico.save()
        self.autenticar(Usuario.Rol.TECNICO)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_permiso_antes_de_existencia_y_sin_consultas_sensibles(self):
        for rol, sufijo in (
            (Usuario.Rol.TECNICO, "aprobar-gerencia/"),
            (Usuario.Rol.SUPERVISOR_OBRAS, "enviar-gerencia/"),
            (AF, "aprobar-gerencia/"),
            (G, "anular/"),
        ):
            self.autenticar(rol)
            with (
                self.subTest(rol=rol),
                CaptureQueriesContext(connection) as ctx,
            ):
                respuesta = self.client.post(
                    self.url + "999999/" + sufijo, {}, format="json"
                )
            self.assertEqual(respuesta.status_code, 403)
            self.assertFalse(any(
                "comercial_presupuesto" in consulta["sql"]
                for consulta in ctx.captured_queries
            ))


class PresupuestoCabeceraAPITests(PresupuestoAPIBase):
    def test_creacion_cliente_real_sin_identificacion(self):
        respuesta = self.client.post(self.url, self.cabecera(), format="json")
        self.assertEqual(respuesta.status_code, 201, respuesta.data)
        presupuesto = Presupuesto.objects.get(pk=respuesta.data["id"])
        self.assertEqual(presupuesto.cliente_id, self.cliente.pk)
        self.assertEqual(presupuesto.creado_por_id, self.usuarios[AF].pk)
        self.assertEqual(presupuesto.descripcion, "Servicio propuesto")
        self.assertEqual(respuesta.data["monto_neto"], "0.00")
        self.assertEqual(respuesta.data["items"], [])
        self.assertEqual(presupuesto.eventos.count(), 1)

    def test_cliente_inexistente_e_inactivo(self):
        respuesta = self.client.post(
            self.url, self.cabecera(cliente=999999), format="json"
        )
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("cliente", respuesta.data)
        self.cliente.activo = False
        self.cliente.save()
        respuesta = self.client.post(self.url, self.cabecera(), format="json")
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("cliente", respuesta.data)

    def test_tipos_http_estrictos(self):
        for campo, valores in (
            ("cliente", [True, False, 1.0, "1", 0, -1, None]),
            ("requiere_aprobacion_gerencia", [0, 1, "true", "False", None]),
            ("descripcion", [123, True, None, "  "]),
        ):
            for valor in valores:
                with self.subTest(campo=campo, valor=valor):
                    respuesta = self.client.post(
                        self.url, self.cabecera(**{campo: valor}),
                        format="json",
                    )
                    self.assertEqual(respuesta.status_code, 400)
                    self.assertIn(campo, respuesta.data)

    def test_campos_administrados_y_desconocidos_rechazados(self):
        for campo in (
            "id", "codigo", "estado", "presupuesto_origen", "creado_por",
            "creado_en", "actualizado_en", "moneda", "monto_neto",
            "descripccion", "items",
        ):
            with self.subTest(campo=campo):
                respuesta = self.client.post(
                    self.url, self.cabecera(**{campo: "dato"}), format="json"
                )
                self.assertEqual(respuesta.status_code, 400)
                self.assertIn(campo, respuesta.data)
                respuesta = self.client.patch(
                    self.detalle(), {campo: "dato"}, format="json"
                )
                self.assertEqual(respuesta.status_code, 400)
        self.assertEqual(Presupuesto.objects.count(), 1)

    def test_patch_parcial_normalizado(self):
        respuesta = self.client.patch(self.detalle(), {
            "descripcion": " Nueva propuesta ",
        }, format="json")
        self.assertEqual(respuesta.status_code, 200)
        self.presupuesto.refresh_from_db()
        self.assertEqual(self.presupuesto.descripcion, "Nueva propuesta")
        self.assertTrue(self.presupuesto.requiere_aprobacion_gerencia)

    def test_patch_congelado(self):
        presupuesto = self.preparar("ENVIADO_CLIENTE")
        respuesta = self.client.patch(self.detalle(presupuesto), {
            "descripcion": "No permitido",
        }, format="json")
        self.assertEqual(respuesta.status_code, 409)
        self.assertEqual(respuesta.data["code"], "estado_incompatible")

    def test_salida_solo_campos_publicos(self):
        respuesta = self.client.get(self.detalle())
        self.assertEqual(set(respuesta.data), {
            "id", "codigo", "cliente", "descripcion", "estado",
            "requiere_aprobacion_gerencia", "presupuesto_origen", "creado_por",
            "creado_en", "actualizado_en", "moneda", "monto_neto", "items",
        })
        self.assertIsInstance(respuesta.data["creado_por"], int)
        self.assertIsInstance(respuesta.data["cliente"], int)


class PresupuestoDecimalItemsAPITests(PresupuestoAPIBase):
    def setUp(self):
        super().setUp()
        self.url_items = self.detalle() + "items/"
        self.item = self.presupuesto.items.get()
        self.url_item = self.url_items + f"{self.item.pk}/"

    def test_strings_y_precision_salida(self):
        respuesta = self.client.post(self.url_items, datos_item(
            cantidad=" 2.500 ", precio_unitario=" 100.25 ", orden=2,
        ), format="json")
        self.assertEqual(respuesta.status_code, 201)
        self.assertEqual(respuesta.data["cantidad"], "2.500")
        self.assertEqual(respuesta.data["precio_unitario"], "100.25")
        self.assertEqual(respuesta.data["subtotal"], "250.63")
        self.assertEqual(respuesta.data["descripcion"], "Montaje")
        self.assertEqual(respuesta.data["unidad"], "hora")

    def test_http_crudo_rechaza_numeros_y_formatos_no_decimales(self):
        for campo in ("cantidad", "precio_unitario"):
            for valor in (
                2, 2.5, True, False, None, "NaN", "Infinity", "-Infinity",
                "1e3", "1,5", "1,000.00", "1.000.000", "+1", "-1",
                ".5", "5.", "", "   ", "１２.５",
            ):
                with self.subTest(campo=campo, valor=valor):
                    respuesta = self.client.post(
                        self.url_items,
                        json.dumps(datos_item(orden=2, **{campo: valor})),
                        content_type="application/json",
                    )
                    self.assertEqual(respuesta.status_code, 400)
                    self.assertIn(campo, respuesta.data)
        self.assertEqual(self.presupuesto.items.count(), 1)

    def test_json_nan_e_infinity_crudos_rechazados(self):
        for literal in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(literal=literal):
                respuesta = self.client.post(
                    self.url_items, '{"cantidad": ' + literal + '}',
                    content_type="application/json",
                )
                self.assertEqual(respuesta.status_code, 400)

    def test_exceso_escala_precision_y_cantidad_cero(self):
        for campo, valor in (
            ("cantidad", "1.0000"), ("cantidad", "1000000000"),
            ("cantidad", "0"), ("precio_unitario", "1.000"),
            ("precio_unitario", "10000000000000"),
        ):
            with self.subTest(campo=campo, valor=valor):
                respuesta = self.client.post(
                    self.url_items, datos_item(orden=2, **{campo: valor}),
                    format="json",
                )
                self.assertEqual(respuesta.status_code, 400)

    def test_precio_cero_permitido(self):
        respuesta = self.client.post(self.url_items, datos_item(
            orden=2, precio_unitario="0",
        ), format="json")
        self.assertEqual(respuesta.status_code, 201)
        self.assertEqual(respuesta.data["subtotal"], "0.00")

    def test_patch_y_delete_item(self):
        respuesta = self.client.patch(self.url_item, {
            "cantidad": "3", "descripcion": " Nuevo montaje ",
        }, format="json")
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.data["cantidad"], "3.000")
        self.assertEqual(respuesta.data["precio_unitario"], "100.25")
        respuesta = self.client.delete(self.url_item)
        self.assertEqual(respuesta.status_code, 204)
        self.assertEqual(respuesta.content, b"")
        self.assertFalse(
            PresupuestoItem.objects.filter(pk=self.item.pk).exists()
        )

    def test_fk_id_subtotal_y_campos_desconocidos_rechazados(self):
        for campo in (
            "presupuesto", "presupuesto_id", "id", "subtotal", "otro",
        ):
            with self.subTest(campo=campo):
                respuesta = self.client.post(
                    self.url_items, datos_item(orden=2, **{campo: 999999}),
                    format="json",
                )
                self.assertEqual(respuesta.status_code, 400)
                self.assertIn(campo, respuesta.data)
                respuesta = self.client.patch(
                    self.url_item, {campo: 999999}, format="json"
                )
                self.assertEqual(respuesta.status_code, 400)

    def test_orden_duplicado_mensaje_publico(self):
        respuesta = self.client.post(
            self.url_items, datos_item(), format="json"
        )
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("orden", respuesta.data)
        self.assertNotIn("presupuesto_item_orden_unico", str(respuesta.data))

    def test_item_ajeno_o_inexistente_404_incluso_congelado(self):
        otro = self.preparar()
        ajeno = otro.items.get().pk
        self.presupuesto.estado = "ENVIADO_CLIENTE"
        self.presupuesto.save()
        for pk in (ajeno, 999999):
            for metodo in ("patch", "delete"):
                with self.subTest(pk=pk, metodo=metodo):
                    respuesta = getattr(self.client, metodo)(
                        self.url_items + f"{pk}/", {}, format="json"
                    )
                    self.assertEqual(respuesta.status_code, 404)

    def test_congelacion_crud_items(self):
        self.presupuesto.estado = "ENVIADO_CLIENTE"
        self.presupuesto.save()
        for metodo, ruta, datos in (
            ("post", self.url_items, datos_item(orden=2)),
            ("patch", self.url_item, {"cantidad": "3"}),
            ("delete", self.url_item, {}),
        ):
            with self.subTest(metodo=metodo):
                respuesta = getattr(self.client, metodo)(
                    ruta, datos, format="json"
                )
                self.assertEqual(respuesta.status_code, 409)

    def test_neto_suma_lineas_redondeadas_del_detalle(self):
        presupuesto = self.preparar(con_item=False)
        for orden in (3, 1):
            respuesta = self.client.post(
                self.detalle(presupuesto) + "items/", datos_item(
                    cantidad="0.500", precio_unitario="0.01", orden=orden,
                ), format="json",
            )
            self.assertEqual(respuesta.status_code, 201)
        detalle = self.client.get(self.detalle(presupuesto)).data
        self.assertEqual([i["orden"] for i in detalle["items"]], [1, 3])
        self.assertEqual(
            [i["subtotal"] for i in detalle["items"]], ["0.01", "0.01"]
        )
        self.assertEqual(detalle["monto_neto"], "0.02")

    def test_maximos_sin_float_en_respuesta(self):
        respuesta = self.client.post(self.url_items, datos_item(
            orden=2, cantidad="999999999.999",
            precio_unitario="9999999999999.99",
        ), format="json")
        self.assertEqual(respuesta.status_code, 201, respuesta.data)
        self.assertEqual(
            respuesta.data["subtotal"], "9999999999989990000000.00"
        )
        detalle = self.client.get(self.detalle()).data
        self.assertEqual(detalle["monto_neto"], "9999999999989990000250.63")


class PresupuestoEstadosAPITests(PresupuestoAPIBase):
    def test_flujo_con_gerencia_e_historial(self):
        for rol, accion in (
            (AF, "enviar-gerencia"), (G, "aprobar-gerencia"),
            (AF, "enviar-cliente"), (AF, "registrar-aprobacion-cliente"),
        ):
            self.autenticar(rol)
            respuesta = self.accion(accion)
            self.assertEqual(respuesta.status_code, 200, respuesta.data)
        self.assertEqual(respuesta.data["estado"], "APROBADO_CLIENTE")
        historial = self.client.get(self.detalle() + "historial/").data
        self.assertEqual(historial["count"], 5)
        self.assertEqual([e["estado_nuevo"] for e in historial["results"]], [
            "BORRADOR", "PENDIENTE_GERENCIA", "APROBADO_GERENCIA",
            "ENVIADO_CLIENTE", "APROBADO_CLIENTE",
        ])
        self.assertEqual(historial["results"][2]["registrado_por"],
                         self.usuarios[G].pk)
        self.assertEqual(set(historial["results"][0]), {
            "id", "presupuesto", "estado_anterior", "estado_nuevo",
            "registrado_por", "motivo", "creado_en",
        })

    def test_flujo_sin_gerencia(self):
        presupuesto = self.preparar(requiere=False)
        self.assertEqual(
            self.accion("enviar-cliente", presupuesto).status_code, 200
        )
        respuesta = self.accion("registrar-aprobacion-cliente", presupuesto)
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.data["estado"], "APROBADO_CLIENTE")

    def test_atrajos_prohibidos_por_booleano(self):
        respuesta = self.accion("enviar-cliente")
        self.assertEqual(respuesta.status_code, 409)
        self.assertEqual(respuesta.data["code"], "transicion_no_permitida")
        otro = self.preparar(requiere=False)
        self.assertEqual(self.accion("enviar-gerencia", otro).status_code, 409)
        self.autenticar(G)
        self.assertEqual(self.accion("aprobar-gerencia").status_code, 409)

    def test_reintento_conflicto_sin_evento_extra(self):
        self.accion("enviar-gerencia")
        self.autenticar(G)
        self.assertEqual(self.accion("aprobar-gerencia").status_code, 200)
        respuesta = self.accion("aprobar-gerencia")
        self.assertEqual(respuesta.status_code, 409)
        self.assertEqual(respuesta.data["code"], "estado_incompatible")
        self.assertEqual(self.presupuesto.eventos.count(), 3)

    def test_estado_y_desconocidos_rechazados_en_acciones(self):
        for rol, nombre in (
            (AF, "enviar-gerencia"), (AF, "enviar-cliente"),
            (AF, "registrar-aprobacion-cliente"),
            (AF, "registrar-rechazo-cliente"), (AF, "anular"),
            (G, "aprobar-gerencia"), (G, "rechazar-gerencia"),
        ):
            self.autenticar(rol)
            for campo in ("estado", "otro"):
                with self.subTest(nombre=nombre, campo=campo):
                    respuesta = self.accion(nombre, datos={campo: "ANULADO"})
                    self.assertEqual(respuesta.status_code, 400)
                    self.assertIn(campo, respuesta.data)

    def test_motivo_obligatorio_y_trim(self):
        for rol, accion, estado in (
            (G, "rechazar-gerencia", "PENDIENTE_GERENCIA"),
            (AF, "registrar-rechazo-cliente", "ENVIADO_CLIENTE"),
            (AF, "anular", "BORRADOR"),
        ):
            presupuesto = self.preparar(estado)
            self.autenticar(rol)
            for datos in ({}, {"motivo": "  "}, {"motivo": 123}):
                with self.subTest(accion=accion, datos=datos):
                    respuesta = self.accion(accion, presupuesto, datos)
                    self.assertEqual(respuesta.status_code, 400)
                    self.assertIn("motivo", respuesta.data)
            respuesta = self.accion(
                accion, presupuesto, {"motivo": " Cambio "}
            )
            self.assertEqual(respuesta.status_code, 200)
            self.assertEqual(presupuesto.eventos.last().motivo, "Cambio")

    def test_salida_sin_items_y_total_cero(self):
        presupuesto = self.preparar(requiere=False, con_item=False)
        self.assertEqual(
            self.accion("enviar-cliente", presupuesto).status_code, 400
        )
        respuesta = self.client.post(
            self.detalle(presupuesto) + "items/",
            datos_item(precio_unitario="0"),
            format="json",
        )
        self.assertEqual(respuesta.status_code, 201)
        self.assertEqual(
            self.accion("enviar-cliente", presupuesto).status_code, 400
        )


class PresupuestoRevisionAPITests(PresupuestoAPIBase):
    def test_revision_tres_origenes(self):
        for estado in ("RECHAZADO_GERENCIA", "RECHAZADO_CLIENTE", "ANULADO"):
            with self.subTest(estado=estado):
                origen = self.preparar(estado)
                anterior = Presupuesto.objects.values().get(pk=origen.pk)
                respuesta = self.accion("crear-revision", origen)
                self.assertEqual(respuesta.status_code, 201, respuesta.data)
                self.assertEqual(respuesta.data["estado"], "BORRADOR")
                self.assertEqual(
                    respuesta.data["presupuesto_origen"], origen.pk
                )
                self.assertNotEqual(respuesta.data["id"], origen.pk)
                self.assertNotEqual(respuesta.data["items"][0]["id"],
                                    origen.items.get().pk)
                self.assertEqual(
                    Presupuesto.objects.values().get(pk=origen.pk), anterior
                )

    def test_revision_aprobado_cliente_directo_conflicto(self):
        origen = self.preparar("APROBADO_CLIENTE")
        self.assertEqual(
            self.accion("crear-revision", origen).status_code, 409
        )
        self.assertFalse(origen.revisiones.exists())

    def test_revision_rechaza_overrides(self):
        origen = self.preparar("ANULADO")
        for campo in ("motivo", "descripcion", "estado", "cliente"):
            with self.subTest(campo=campo):
                respuesta = self.accion(
                    "crear-revision", origen, {campo: "dato"}
                )
                self.assertEqual(respuesta.status_code, 400)
        self.assertFalse(origen.revisiones.exists())


class PresupuestoLecturaRutasAPITests(PresupuestoAPIBase):
    def test_paginacion_fija_y_orden_determinista(self):
        for _ in range(27):
            self.preparar(con_item=False)
        # Empatar fechas comprueba también el desempate por ID.
        fecha = self.presupuesto.creado_en
        Presupuesto.objects.update(creado_en=fecha)
        respuesta = self.client.get(self.url + "?page_size=100&ordering=id")
        self.assertEqual(respuesta.status_code, 200)
        self.assertEqual(respuesta.data["count"], 28)
        self.assertEqual(len(respuesta.data["results"]), 25)
        self.assertIsNotNone(respuesta.data["next"])
        self.assertIsNone(respuesta.data["previous"])
        esperados = list(Presupuesto.objects.order_by(
            "-creado_en", "-id"
        ).values_list("id", flat=True))
        self.assertEqual(
            [p["id"] for p in respuesta.data["results"]], esperados[:25]
        )
        self.assertNotIn("items", respuesta.data["results"][0])
        pagina2 = self.client.get(self.url + "?page=2").data
        self.assertEqual([p["id"] for p in pagina2["results"]], esperados[25:])
        self.assertIsNone(pagina2["next"])
        self.assertIsNotNone(pagina2["previous"])
        self.assertEqual(
            self.client.get(self.url + "?page=999").status_code, 404
        )

    def test_historial_paginado_orden_y_solo_lectura(self):
        for _ in range(27):
            # Fixture volumétrica; servicios prueba las secuencias reales.
            PresupuestoEvento.objects.create(
                presupuesto=self.presupuesto, registrado_por=self.usuarios[AF],
                estado_anterior="BORRADOR", estado_nuevo="ENVIADO_CLIENTE",
            )
        ruta = self.detalle() + "historial/"
        respuesta = self.client.get(ruta)
        self.assertEqual(respuesta.data["count"], 28)
        self.assertEqual(len(respuesta.data["results"]), 25)
        self.assertEqual([e["id"] for e in respuesta.data["results"]], list(
            self.presupuesto.eventos.values_list("id", flat=True)[:25]
        ))
        self.assertIsNotNone(respuesta.data["next"])
        self.assertIsNone(respuesta.data["previous"])
        pagina2 = self.client.get(ruta + "?page=2").data
        self.assertEqual(len(pagina2["results"]), 3)
        self.assertIsNotNone(pagina2["previous"])
        self.assertIsNone(pagina2["next"])
        for metodo in ("post", "patch", "delete"):
            self.assertEqual(
                getattr(self.client, metodo)(ruta).status_code, 405
            )

    def test_listado_sin_n_mas_uno(self):
        with CaptureQueriesContext(connection) as inicial:
            respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.status_code, 200)
        for _ in range(10):
            self.preparar()
        with CaptureQueriesContext(connection) as ampliado:
            respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.status_code, 200)
        self.assertLessEqual(len(ampliado), len(inicial))
        self.assertTrue(all(p["monto_neto"] == "250.63"
                            for p in respuesta.data["results"]))

    def test_detalle_sin_consultas_por_item_y_snapshot_compartido(self):
        with CaptureQueriesContext(connection) as inicial:
            self.client.get(self.detalle())
        for orden in range(2, 12):
            servicios.crear_item(self.presupuesto, {
                "descripcion": "Línea", "cantidad": Decimal("0.5"),
                "unidad": "hora", "precio_unitario": Decimal("0.01"),
                "orden": orden,
            })
        with CaptureQueriesContext(connection) as ampliado:
            respuesta = self.client.get(self.detalle())
        self.assertLessEqual(len(ampliado), len(inicial))
        self.assertEqual(respuesta.data["monto_neto"], "250.73")
        self.assertEqual(
            sum(Decimal(i["subtotal"]) for i in respuesta.data["items"]),
            Decimal(respuesta.data["monto_neto"]),
        )

    def test_inexistentes_autorizados(self):
        base = self.url + "999999/"
        for metodo, ruta in (
            ("get", base), ("patch", base), ("get", base + "historial/"),
            ("post", base + "items/"), ("patch", base + "items/999999/"),
            ("delete", base + "items/999999/"),
        ):
            with self.subTest(metodo=metodo, ruta=ruta):
                respuesta = getattr(self.client, metodo)(
                    ruta, {}, format="json"
                )
                self.assertEqual(respuesta.status_code, 404)
        for rol, acciones in (
            (AF, (
                "enviar-gerencia", "enviar-cliente", "anular",
                "crear-revision",
                "registrar-aprobacion-cliente", "registrar-rechazo-cliente",
            )),
            (G, ("aprobar-gerencia", "rechazar-gerencia")),
        ):
            self.autenticar(rol)
            for accion in acciones:
                self.assertEqual(self.client.post(
                    base + accion + "/", {}, format="json"
                ).status_code, 404)

    def test_put_delete_presupuesto_405_y_head_options(self):
        for rol in (AF, G):
            self.autenticar(rol)
            for metodo in ("put", "delete"):
                respuesta = getattr(self.client, metodo)(
                    self.detalle(), {}, format="json"
                )
                self.assertEqual(respuesta.status_code, 405)
            for metodo in ("head", "options"):
                self.assertEqual(getattr(self.client, metodo)(
                    self.detalle()
                ).status_code, 200)
        self.assertTrue(
            Presupuesto.objects.filter(pk=self.presupuesto.pk).exists()
        )

    def test_mapping_dominio_y_errores_inesperados(self):
        for error, esperado, campo in (
            (
                DatosInvalidos({"descripcion": ["Inválida"]}),
                400, "descripcion",
            ),
            (MotivoObligatorio(), 400, "motivo"),
            (RecursoNoEncontrado(), 404, "detail"),
        ):
            with self.subTest(error=error):
                with patch.object(
                    servicios, "anular_presupuesto", side_effect=error
                ):
                    respuesta = self.accion(
                        "anular", datos={"motivo": "Retiro"}
                    )
                self.assertEqual(respuesta.status_code, esperado)
                self.assertIn(campo, respuesta.data)
                for interno in (
                    "constraint_name", "SQL", "Traceback", "psycopg",
                ):
                    self.assertNotIn(interno, str(respuesta.data))
        with patch.object(
            servicios, "anular_presupuesto", side_effect=IntegrityError
        ):
            with self.assertRaises(IntegrityError):
                self.accion("anular", datos={"motivo": "Retiro"})

    def test_resolucion_rutas_presupuestos_clientes_auth(self):
        rutas = {
            "/api/presupuestos/": "presupuesto-list",
            "/api/presupuestos/1/": "presupuesto-detail",
            "/api/presupuestos/1/items/": "presupuesto-items",
            "/api/presupuestos/1/items/2/": "presupuesto-item-detalle",
            "/api/presupuestos/1/historial/": "presupuesto-historial",
            "/api/clientes/": "cliente-list",
            "/api/clientes/1/": "cliente-detail",
            "/api/clientes/1/activar/": "cliente-activar",
            "/api/clientes/1/desactivar/": "cliente-desactivar",
            "/api/auth/csrf/": "csrf", "/api/auth/login/": "login",
            "/api/auth/refresh/": "token_refresh",
            "/api/auth/logout/": "logout", "/api/auth/me/": "perfil_actual",
        }
        for accion in (
            "enviar-gerencia", "aprobar-gerencia", "rechazar-gerencia",
            "enviar-cliente", "registrar-aprobacion-cliente",
            "registrar-rechazo-cliente", "anular", "crear-revision",
        ):
            rutas[f"/api/presupuestos/1/{accion}/"] = f"presupuesto-{accion}"
        for ruta, nombre in rutas.items():
            with self.subTest(ruta=ruta):
                self.assertEqual(resolve(ruta).url_name, nombre)
        self.assertEqual(
            self.client.get(self.url + "ruta-invalida/").status_code, 404
        )
