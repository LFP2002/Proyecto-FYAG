from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.db import IntegrityError, connection, transaction
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from apps.comercial.models import Presupuesto
from apps.obras import services, services_gastos
from apps.obras.models import CostoObraEvento, GastoObra, Obra
from .test_servicios_004a import BaseObras


class GastosBase(BaseObras):
    def preparar(self):
        self.obra = self.crear(tecnico_responsable=self.tecnico.pk, motivo="Principal")
        services.iniciar_obra(self.obra, self.supervisor, "Inicio")
        self.client = APIClient()
        self.autenticar(self.supervisor)
        self.url = f"/api/obras/{self.obra.pk}/gastos/"
        self.url_historial = f"/api/obras/{self.obra.pk}/costos/historial/"

    def autenticar(self, usuario):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(usuario)}")

    def entrada(self, **cambios):
        datos = {
            "tipo": "MATERIAL",
            "descripcion": "Tubería de cobre",
            "unidad": "metro",
            "cantidad": "2.500",
            "costo_unitario_neto": "12500.00",
            "fecha_gasto": timezone.localdate().isoformat(),
        }
        datos.update(cambios)
        return datos

    def crear_api(self, **cambios):
        return self.client.post(self.url, self.entrada(**cambios), format="json")

    def crear_ok(self, **cambios):
        respuesta = self.crear_api(**cambios)
        self.assertEqual(respuesta.status_code, 201, respuesta.data)
        return GastoObra.objects.get(pk=respuesta.data["id"])

    def otra_obra(self):
        presupuesto = Presupuesto.objects.create(
            cliente=self.cliente, creado_por=self.finanzas,
            descripcion="Otra obra", estado=Presupuesto.Estado.APROBADO_CLIENTE,
        )
        obra = services.crear_obra(self.datos(
            presupuesto=presupuesto.pk, tecnico_responsable=self.tecnico.pk,
            motivo="Principal",
        ), self.supervisor)
        return services.iniciar_obra(obra, self.supervisor, "Inicio")

    def cambiar_estado(self, obra, estado):
        cambios = {"estado": estado, "finalizado_en": None, "cancelado_en": None}
        if estado == "PLANIFICADA":
            cambios["iniciado_en"] = None
        else:
            cambios["iniciado_en"] = timezone.now()
        if estado == "FINALIZADA":
            cambios["finalizado_en"] = timezone.now()
        if estado == "CANCELADA":
            cambios["cancelado_en"] = timezone.now()
        Obra.objects.filter(pk=obra.pk).update(**cambios)

    def iniciar_hace_dias(self, dias):
        Obra.objects.filter(pk=self.obra.pk).update(
            creado_en=timezone.now() - timedelta(days=dias + 1),
            iniciado_en=timezone.now() - timedelta(days=dias),
        )

    def material_con_devolucion(self):
        """Gasto fechado hace 2 días y devolución de hace 1 día."""
        hoy = timezone.localdate()
        self.iniciar_hace_dias(2)
        gasto = self.crear_ok(fecha_gasto=(hoy - timedelta(days=2)).isoformat())
        respuesta = self.client.post(self.url + f"{gasto.pk}/devolver/", {
            "cantidad": "1.000",
            "fecha_devolucion": (hoy - timedelta(days=1)).isoformat(),
            "motivo": "Devolución parcial",
        }, format="json")
        self.assertEqual(respuesta.status_code, 200, respuesta.data)
        return gasto


class GastosTests(GastosBase, TestCase):
    def setUp(self):
        self.preparar()

    def test_creacion_de_cada_tipo_y_auditoria(self):
        for tipo in GastoObra.Tipo.values:
            with self.subTest(tipo=tipo):
                respuesta = self.crear_api(tipo=tipo)
                self.assertEqual(respuesta.status_code, 201, respuesta.data)
                self.assertEqual(respuesta.data["obra"], self.obra.pk)
                self.assertEqual(respuesta.data["tipo"], tipo)
                self.assertEqual(respuesta.data["vigente"], True)
                self.assertEqual(respuesta.data["cantidad_devuelta"], "0.000")
                self.assertEqual(respuesta.data["registrado_por"], self.supervisor.pk)
                self.assertEqual(respuesta.data["subtotal"], "31250.00")
                gasto = GastoObra.objects.get(pk=respuesta.data["id"])
                self.assertEqual(gasto.obra_id, self.obra.pk)
                evento = gasto.eventos.get()
                self.assertEqual(evento.tipo, "ALTA")
                self.assertEqual(evento.registrado_por_id, self.supervisor.pk)
                self.assertEqual(evento.datos_anteriores, {})
                self.assertEqual(evento.datos_nuevos["tipo"], tipo)
        self.assertEqual(CostoObraEvento.objects.count(), 5)
        # La Obra sale siempre de la URL: no se admite en el cuerpo.
        self.assertEqual(
            self.crear_api(obra=self.otra_obra().pk).status_code, 400,
        )

    def test_contrato_estricto_y_fechas(self):
        futuro = (timezone.localdate() + timedelta(days=1)).isoformat()
        pasado = (timezone.localdate() - timedelta(days=1)).isoformat()
        casos = [
            {"tipo": "MATERIALES"}, {"tipo": ""}, {"tipo": 1},
            {"descripcion": " "}, {"descripcion": "x" * 501}, {"descripcion": 3},
            {"unidad": ""}, {"unidad": "x" * 31},
            {"cantidad": 2.5}, {"cantidad": 2}, {"cantidad": True},
            {"cantidad": "2,5"}, {"cantidad": "2.5000"}, {"cantidad": "1e2"},
            {"cantidad": "NaN"}, {"cantidad": "Infinity"}, {"cantidad": "-1"},
            {"cantidad": "0"}, {"cantidad": None},
            {"costo_unitario_neto": 12500.0}, {"costo_unitario_neto": "1.001"},
            {"costo_unitario_neto": "-0.01"}, {"costo_unitario_neto": "NaN"},
            {"costo_unitario_neto": "1e3"}, {"costo_unitario_neto": None},
            {"fecha_gasto": futuro}, {"fecha_gasto": pasado},
            {"fecha_gasto": "2026-13-01"}, {"fecha_gasto": None},
            {"referencia_respaldo": "x" * 501}, {"observacion": "x" * 2001},
            {"vigente": False}, {"cantidad_devuelta": "1.000"},
            {"subtotal": "1.00"}, {"registrado_por": 1}, {"id": 1},
            {"creado_en": timezone.now().isoformat()}, {"anulado_por": 1},
        ]
        for cambios in casos:
            with self.subTest(cambios=cambios):
                self.assertEqual(self.crear_api(**cambios).status_code, 400)
        for campo in ("tipo", "descripcion", "unidad", "cantidad",
                      "costo_unitario_neto", "fecha_gasto"):
            datos = self.entrada()
            datos.pop(campo)
            self.assertEqual(self.client.post(self.url, datos, format="json").status_code, 400)
        self.assertFalse(GastoObra.objects.exists())
        self.assertFalse(CostoObraEvento.objects.exists())

    def test_referencia_y_observacion_opcionales(self):
        gasto = self.crear_ok(
            referencia_respaldo="  Guía 123  ", observacion="  Sin novedad  ",
        )
        self.assertEqual(gasto.referencia_respaldo, "Guía 123")
        self.assertEqual(gasto.observacion, "Sin novedad")
        otra = self.crear_ok(referencia_respaldo="", observacion="")
        self.assertEqual(otra.referencia_respaldo, "")
        self.assertEqual(otra.observacion, "")

    def test_decimales_y_redondeo_por_registro(self):
        medio = self.crear_ok(cantidad="0.110", costo_unitario_neto="0.05")
        self.assertEqual(medio.subtotal, Decimal("0.01"))
        otro = self.crear_ok(tipo="OTRO", cantidad="0.333", costo_unitario_neto="3.00")
        self.assertEqual(otro.subtotal, Decimal("1.00"))
        transporte = self.crear_ok(
            tipo="TRANSPORTE", cantidad="1.000", costo_unitario_neto="6500.00",
        )
        self.assertEqual(transporte.subtotal, Decimal("6500.00"))
        maximo = self.crear_ok(cantidad="999999999.999", costo_unitario_neto="9999999999999.99")
        self.assertIsInstance(maximo.subtotal, Decimal)
        self.assertEqual(
            self.crear_api(cantidad="1000000000.000").status_code, 400,
        )

    def test_devoluciones_parciales_totales_y_rechazos(self):
        gasto = self.crear_ok()
        ruta = self.url + f"{gasto.pk}/devolver/"
        parcial = self.client.post(ruta, {
            "cantidad": "1.000", "fecha_devolucion": timezone.localdate().isoformat(),
            "motivo": "Material no utilizado",
        }, format="json")
        self.assertEqual(parcial.status_code, 200, parcial.data)
        self.assertEqual(parcial.data["cantidad_devuelta"], "1.000")
        self.assertEqual(parcial.data["subtotal"], "18750.00")
        evento = gasto.eventos.get(tipo="DEVOLUCION")
        self.assertEqual(evento.registrado_por_id, self.supervisor.pk)
        self.assertEqual(evento.datos_anteriores["cantidad_devuelta"], "0.000")
        self.assertEqual(evento.datos_nuevos["devolucion"]["cantidad"], "1.000")
        for datos in (
            {"cantidad": "2.000", "fecha_devolucion": timezone.localdate().isoformat(), "motivo": "Exceso"},
            {"cantidad": "1.000", "fecha_devolucion": (timezone.localdate() - timedelta(days=1)).isoformat(), "motivo": "Antes del gasto"},
            {"cantidad": "1.000", "fecha_devolucion": (timezone.localdate() + timedelta(days=1)).isoformat(), "motivo": "Futura"},
            {"cantidad": "0", "fecha_devolucion": timezone.localdate().isoformat(), "motivo": "Cero"},
            {"cantidad": 1.0, "fecha_devolucion": timezone.localdate().isoformat(), "motivo": "Float"},
            {"cantidad": "1.000", "fecha_devolucion": timezone.localdate().isoformat()},
        ):
            with self.subTest(datos=datos):
                self.assertEqual(self.client.post(ruta, datos, format="json").status_code, 400)
        gasto.refresh_from_db()
        self.assertEqual(gasto.cantidad_devuelta, Decimal("1.000"))
        self.assertEqual(gasto.eventos.filter(tipo="DEVOLUCION").count(), 1)
        total = self.client.post(ruta, {
            "cantidad": "1.500", "fecha_devolucion": timezone.localdate().isoformat(),
            "motivo": "Devolución total",
        }, format="json")
        self.assertEqual(total.status_code, 200, total.data)
        self.assertEqual(total.data["subtotal"], "0.00")
        self.assertEqual(total.data["cantidad_devuelta"], "2.500")
        self.assertEqual(GastoObra.objects.count(), 1)
        otro = self.crear_ok(tipo="TRANSPORTE")
        respuesta = self.client.post(self.url + f"{otro.pk}/devolver/", {
            "cantidad": "1.000", "fecha_devolucion": timezone.localdate().isoformat(),
            "motivo": "No aplica",
        }, format="json")
        self.assertEqual(respuesta.status_code, 400)

    def test_correcciones_motivo_auditoria_y_noop(self):
        gasto = self.crear_ok()
        ruta = self.url + f"{gasto.pk}/"
        anterior = gasto.actualizado_en
        sin_cambio = self.client.patch(ruta, {"descripcion": gasto.descripcion}, format="json")
        self.assertEqual(sin_cambio.status_code, 200, sin_cambio.data)
        gasto.refresh_from_db()
        self.assertEqual(gasto.actualizado_en, anterior)
        self.assertEqual(gasto.eventos.count(), 1)
        self.assertEqual(self.client.patch(ruta, {
            "cantidad": "3.000",
        }, format="json").status_code, 400)
        respuesta = self.client.patch(ruta, {
            "descripcion": "  Tubería de cobre 1/2  ", "cantidad": "3.000",
            "costo_unitario_neto": "13000.00", "motivo": "  Corrección de factura  ",
        }, format="json")
        self.assertEqual(respuesta.status_code, 200, respuesta.data)
        self.assertEqual(respuesta.data["descripcion"], "Tubería de cobre 1/2")
        self.assertEqual(respuesta.data["subtotal"], "39000.00")
        evento = gasto.eventos.get(tipo="CORRECCION")
        self.assertEqual(evento.motivo, "Corrección de factura")
        self.assertEqual(evento.datos_anteriores["cantidad"], "2.500")
        self.assertEqual(evento.datos_anteriores["subtotal"], "31250.00")
        self.assertEqual(evento.datos_nuevos["cantidad"], "3.000")
        self.assertEqual(evento.datos_nuevos["subtotal"], "39000.00")
        # Fecha anterior al inicio: solo una corrección motivada la admite.
        inferior = (timezone.localdate() - timedelta(days=2)).isoformat()
        self.assertEqual(self.client.patch(ruta, {
            "fecha_gasto": inferior, "motivo": "Respaldo documental",
        }, format="json").status_code, 200)
        gasto.refresh_from_db()
        self.assertEqual(gasto.fecha_gasto.isoformat(), inferior)
        for datos in (
            {"cantidad": "0.500", "motivo": "Bajo la devolución"},
            {"tipo": "OTRO", "motivo": "Cambio incompatible"},
            {"vigente": False, "motivo": "No permitido"},
        ):
            if datos.get("cantidad") == "0.500":
                self.client.post(ruta + "devolver/", {
                    "cantidad": "1.000",
                    "fecha_devolucion": timezone.localdate().isoformat(),
                    "motivo": "Devolución",
                }, format="json")
            with self.subTest(datos=datos):
                self.assertEqual(self.client.patch(ruta, datos, format="json").status_code, 400)
        # Un PATCH sin cambios efectivos no exige motivo ni audita.
        self.assertEqual(self.client.patch(
            ruta, {"motivo": "Solo motivo"}, format="json",
        ).status_code, 200)
        self.assertEqual(gasto.eventos.filter(tipo="CORRECCION").count(), 2)

    def test_correccion_de_fecha_valida_frente_a_devoluciones(self):
        gasto = self.material_con_devolucion()
        hoy = timezone.localdate()
        nueva = (hoy - timedelta(days=5)).isoformat()
        respuesta = self.client.patch(self.url + f"{gasto.pk}/", {
            "fecha_gasto": nueva, "motivo": "Respaldo documental",
        }, format="json")
        self.assertEqual(respuesta.status_code, 200, respuesta.data)
        gasto.refresh_from_db()
        self.assertEqual(gasto.fecha_gasto.isoformat(), nueva)
        evento = gasto.eventos.get(tipo="CORRECCION")
        self.assertEqual(
            evento.datos_anteriores["fecha_gasto"],
            (hoy - timedelta(days=2)).isoformat(),
        )
        self.assertEqual(evento.datos_nuevos["fecha_gasto"], nueva)
        # La nueva fecha es anterior al inicio, pero no posterior a la devolución.
        self.assertLess(gasto.fecha_gasto, timezone.localdate(gasto.obra.iniciado_en))

    def test_correccion_de_fecha_invalida_frente_a_devoluciones(self):
        gasto = self.material_con_devolucion()
        gasto.refresh_from_db()
        anterior = (gasto.fecha_gasto, gasto.actualizado_en, gasto.subtotal)
        eventos = gasto.eventos.count()
        respuesta = self.client.patch(self.url + f"{gasto.pk}/", {
            "fecha_gasto": timezone.localdate().isoformat(),
            "motivo": "Cambio posterior a la devolución",
        }, format="json")
        self.assertEqual(respuesta.status_code, 400)
        self.assertIn("fecha_gasto", respuesta.data)
        gasto.refresh_from_db()
        self.assertEqual(
            (gasto.fecha_gasto, gasto.actualizado_en, gasto.subtotal), anterior,
        )
        self.assertEqual(gasto.eventos.count(), eventos)
        self.assertFalse(gasto.eventos.filter(tipo="CORRECCION").exists())

    def test_historial_de_devoluciones_se_conserva_tras_correcciones(self):
        gasto = self.material_con_devolucion()
        hoy = timezone.localdate()
        devolucion = gasto.eventos.get(tipo="DEVOLUCION")
        antes = (
            devolucion.motivo, devolucion.datos_anteriores,
            devolucion.datos_nuevos, devolucion.creado_en,
        )
        self.assertEqual(self.client.patch(self.url + f"{gasto.pk}/", {
            "fecha_gasto": hoy.isoformat(), "motivo": "Intento inválido",
        }, format="json").status_code, 400)
        self.assertEqual(self.client.patch(self.url + f"{gasto.pk}/", {
            "fecha_gasto": (hoy - timedelta(days=4)).isoformat(),
            "motivo": "Corrección válida",
        }, format="json").status_code, 200)
        devolucion.refresh_from_db()
        self.assertEqual(
            (devolucion.motivo, devolucion.datos_anteriores,
             devolucion.datos_nuevos, devolucion.creado_en),
            antes,
        )
        self.assertEqual(
            [evento.tipo for evento in gasto.eventos.order_by("creado_en", "id")],
            ["ALTA", "DEVOLUCION", "CORRECCION"],
        )

    def test_anulacion_baja_logica_repetida_e_historial(self):
        gasto = self.crear_ok()
        ruta = self.url + f"{gasto.pk}/"
        self.client.post(ruta + "devolver/", {
            "cantidad": "1.000", "fecha_devolucion": timezone.localdate().isoformat(),
            "motivo": "Devolución",
        }, format="json")
        respuesta = self.client.post(ruta + "anular/", {
            "motivo": "Registro duplicado",
        }, format="json")
        self.assertEqual(respuesta.status_code, 200, respuesta.data)
        self.assertFalse(respuesta.data["vigente"])
        self.assertEqual(respuesta.data["anulado_por"], self.supervisor.pk)
        self.assertEqual(respuesta.data["motivo_anulacion"], "Registro duplicado")
        self.assertIsNotNone(respuesta.data["anulado_en"])
        evento = gasto.eventos.get(tipo="ANULACION")
        self.assertEqual(evento.datos_nuevos["anulacion"]["motivo"], "Registro duplicado")
        eventos = gasto.eventos.count()
        self.assertEqual(self.client.post(ruta + "anular/", {"motivo": "Otra"}, format="json").status_code, 409)
        self.assertEqual(self.client.post(ruta + "devolver/", {
            "cantidad": "1.000", "fecha_devolucion": timezone.localdate().isoformat(),
            "motivo": "Otra",
        }, format="json").status_code, 409)
        self.assertEqual(self.client.patch(ruta, {"descripcion": "Cambio", "motivo": "Cambio"}, format="json").status_code, 409)
        self.assertEqual(gasto.eventos.count(), eventos)
        self.assertEqual(GastoObra.objects.count(), 1)
        self.assertEqual(self.client.delete(ruta).status_code, 405)
        self.assertEqual(self.client.put(ruta, {}, format="json").status_code, 405)

    def test_historial_economico_y_paginacion(self):
        gasto = self.crear_ok()
        ruta = self.url + f"{gasto.pk}/"
        self.client.patch(ruta, {"observacion": "Verificado", "motivo": "Nota"}, format="json")
        self.client.post(ruta + "devolver/", {
            "cantidad": "1.000", "fecha_devolucion": timezone.localdate().isoformat(),
            "motivo": "Devolución",
        }, format="json")
        self.client.post(ruta + "anular/", {"motivo": "Baja"}, format="json")
        historial = self.client.get(self.url_historial)
        self.assertEqual(historial.status_code, 200, historial.data)
        self.assertEqual([e["tipo"] for e in historial.data["results"]],
                         ["ALTA", "CORRECCION", "DEVOLUCION", "ANULACION"])
        self.assertEqual(historial.data["results"][0]["gasto"], gasto.pk)
        self.assertEqual(historial.data["results"][0]["obra"], self.obra.pk)
        self.assertEqual(self.client.post(self.url_historial, {}, format="json").status_code, 405)
        self.assertEqual(self.client.get(self.url_historial + "?gasto=1").status_code, 400)
        for _ in range(26):
            self.crear_ok()
        listado = self.client.get(self.url)
        self.assertEqual(listado.data["count"], 27)
        self.assertEqual(len(listado.data["results"]), 25)
        self.assertEqual(len(self.client.get(self.url + "?page=2").data["results"]), 2)
        self.assertEqual(self.client.get(self.url + "?page=99").status_code, 404)
        self.assertEqual(self.client.get(self.url + "?tipo=MATERIAL").status_code, 400)

    def test_permisos_cuatro_roles_y_superusuarios(self):
        gasto = self.crear_ok()
        rutas_post = [
            (self.url, self.entrada()),
            (self.url + f"{gasto.pk}/devolver/", {
                "cantidad": "1.000", "fecha_devolucion": timezone.localdate().isoformat(),
                "motivo": "Devolución",
            }),
            (self.url + f"{gasto.pk}/anular/", {"motivo": "Baja"}),
        ]
        for usuario in (self.tecnico, self.finanzas):
            usuario.is_superuser = True
            usuario.save()
            self.autenticar(usuario)
            self.assertEqual(self.client.get(self.url).status_code, 403)
            self.assertEqual(self.client.get(self.url_historial).status_code, 403)
            for ruta, datos in rutas_post:
                self.assertEqual(self.client.post(ruta, datos, format="json").status_code, 403)
            self.assertEqual(self.client.patch(
                self.url + f"{gasto.pk}/", {"observacion": "X", "motivo": "X"},
                format="json",
            ).status_code, 403)
        self.gerencia.is_superuser = True
        self.gerencia.save()
        self.autenticar(self.gerencia)
        self.assertEqual(self.client.get(self.url).status_code, 200)
        self.assertEqual(self.client.get(self.url_historial).status_code, 200)
        for ruta, datos in rutas_post:
            self.assertEqual(self.client.post(ruta, datos, format="json").status_code, 403)
        self.assertEqual(self.client.patch(
            self.url + f"{gasto.pk}/", {"observacion": "X", "motivo": "X"},
            format="json",
        ).status_code, 403)
        self.autenticar(self.tecnico)
        detalle = self.client.get(f"/api/obras/{self.obra.pk}/")
        self.assertNotIn("gastos", detalle.data)
        self.assertNotIn("subtotal", detalle.data)
        self.client.credentials()
        self.assertEqual(self.client.get(self.url).status_code, 401)
        self.assertEqual(self.client.post(self.url, self.entrada(), format="json").status_code, 401)

    def test_gastos_de_otra_obra_responden_404(self):
        gasto = self.crear_ok()
        otra = self.otra_obra()
        base = f"/api/obras/{otra.pk}/gastos/"
        self.assertEqual(self.client.patch(base + f"{gasto.pk}/", {"observacion": "X", "motivo": "X"}, format="json").status_code, 404)
        self.assertEqual(self.client.post(base + f"{gasto.pk}/devolver/", {
            "cantidad": "1.000", "fecha_devolucion": timezone.localdate().isoformat(),
            "motivo": "X",
        }, format="json").status_code, 404)
        self.assertEqual(self.client.post(base + f"{gasto.pk}/anular/", {"motivo": "X"}, format="json").status_code, 404)
        self.assertEqual(self.client.get(base).data["count"], 0)
        self.assertEqual(self.client.get(base + "99999/").status_code, 405)
        self.assertEqual(self.client.post(base + "99999/devolver/", {
            "cantidad": "1.000", "fecha_devolucion": timezone.localdate().isoformat(),
            "motivo": "X",
        }, format="json").status_code, 404)

    def test_estados_de_obra_habilitados_y_rechazados(self):
        gasto = self.crear_ok()
        ruta = self.url + f"{gasto.pk}/"
        for estado in ("PLANIFICADA", "FINALIZADA", "CANCELADA"):
            with self.subTest(estado=estado):
                self.cambiar_estado(self.obra, estado)
                self.assertEqual(self.crear_api().status_code, 409)
                self.assertEqual(self.client.patch(ruta, {"observacion": "X", "motivo": "X"}, format="json").status_code, 409)
                self.assertEqual(self.client.post(ruta + "devolver/", {
                    "cantidad": "1.000", "fecha_devolucion": timezone.localdate().isoformat(),
                    "motivo": "X",
                }, format="json").status_code, 409)
                self.assertEqual(self.client.post(ruta + "anular/", {"motivo": "X"}, format="json").status_code, 409)
        self.cambiar_estado(self.obra, "SUSPENDIDA")
        self.assertEqual(self.crear_api().status_code, 201)
        self.assertEqual(self.client.patch(ruta, {"observacion": "Suspendida", "motivo": "X"}, format="json").status_code, 200)
        self.assertEqual(self.client.post(ruta + "devolver/", {
            "cantidad": "1.000", "fecha_devolucion": timezone.localdate().isoformat(),
            "motivo": "X",
        }, format="json").status_code, 200)
        self.assertEqual(self.client.post(ruta + "anular/", {"motivo": "X"}, format="json").status_code, 200)

    def test_rollback_de_creacion_y_devolucion(self):
        datos = self.entrada()
        datos["fecha_gasto"] = timezone.localdate()
        with patch("apps.obras.services_gastos._evento", side_effect=RuntimeError("Fallo")):
            with self.assertRaises(RuntimeError):
                services_gastos.crear_gasto(self.obra, datos, self.supervisor)
        self.assertFalse(GastoObra.objects.exists())
        self.assertFalse(CostoObraEvento.objects.exists())
        gasto = self.crear_ok()
        with patch("apps.obras.services_gastos._evento", side_effect=RuntimeError("Fallo")):
            with self.assertRaises(RuntimeError):
                services_gastos.devolver_gasto(self.obra, gasto.pk, {
                    "cantidad": "1.000",
                    "fecha_devolucion": timezone.localdate(),
                    "motivo": "X",
                }, self.supervisor)
        gasto.refresh_from_db()
        self.assertEqual(gasto.cantidad_devuelta, Decimal("0.000"))
        self.assertEqual(gasto.eventos.count(), 1)

    def test_constraints_postgres(self):
        gasto = self.crear_ok()
        for cambios in (
            {"tipo": "INVALIDO"}, {"cantidad": Decimal("0")},
            {"costo_unitario_neto": Decimal("-1")},
            {"cantidad_devuelta": Decimal("3.000")},
            {"vigente": False},
        ):
            with self.subTest(cambios=cambios), self.assertRaises(IntegrityError), transaction.atomic():
                GastoObra.objects.filter(pk=gasto.pk).update(**cambios)
        GastoObra.objects.filter(pk=gasto.pk).update(cantidad_devuelta=Decimal("1.000"))
        with self.assertRaises(IntegrityError), transaction.atomic():
            GastoObra.objects.filter(pk=gasto.pk).update(tipo="TRANSPORTE")
        with self.assertRaises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
            cursor.execute("UPDATE obras_gastoobra SET costo_unitario_neto = 'NaN' WHERE id = %s", [gasto.pk])
        with self.assertRaises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
            cursor.execute("UPDATE obras_gastoobra SET cantidad = 'NaN' WHERE id = %s", [gasto.pk])
