from decimal import Decimal
from uuid import uuid4
from unittest.mock import patch
import secrets

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import connection, transaction, IntegrityError
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.exceptions import APIException
from rest_framework.test import APIClient

from apps.usuarios.models import Usuario, SeguridadCredencial
from apps.usuarios.tokens import AccessToken, RefreshToken
from apps.usuarios.serializers import VersionedRefreshSerializer
from apps.usuarios import services_usuarios as usuarios
from apps.usuarios.tests import test_concurrencia_006 as concurrencia
from apps.inventario import services
from apps.inventario.models import ArticuloInventario, ExistenciaInventario, MovimientoInventario


class BaseInventario:
    def setUp(self):
        password = secrets.token_urlsafe(32)  # Solo memoria; no credenciales exportadas.
        self.users = {r: Usuario.objects.create_user(username=f"qa_019_{r}", email=f"qa_019_{r.lower()}@example.test",
            password=password, rol=r) for r in Usuario.Rol.values}
        self.bodega = self.users["BODEGUERO"]
        self.article = services.crear_articulo({"codigo": " MAT-01 ", "nombre": "Material", "unidad": " KG "}, self.bodega)
        self.client = APIClient()
        self.auth(self.bodega)

    def auth(self, user):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(user)}")

    def payload(self, **extra):
        return {"articulo": self.article.pk, "cantidad": "1.250", "clave_idempotencia": str(uuid4()), **extra}

    def ingreso(self, **extra):
        return services.registrar_ingreso(self.payload(**extra), self.bodega)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class InventarioTests(BaseInventario, TestCase):
    def test_alta_normalizada_existencia_cero_y_auditoria(self):
        self.assertEqual((self.article.codigo, self.article.unidad), ("mat-01", "kg"))
        self.assertEqual(self.article.creado_por_id, self.bodega.pk)
        self.assertEqual(ExistenciaInventario.objects.get(articulo=self.article).saldo, Decimal("0.000"))
        self.assertFalse(MovimientoInventario.objects.exists())

    def test_matriz_seis_roles_y_flags_no_conceden_privilegios(self):
        for role, user in self.users.items():
            Usuario.objects.filter(pk=user.pk).update(is_staff=True, is_superuser=True)
            self.auth(user)
            for path in ("articulos/", "existencias/", "movimientos/"):
                self.assertEqual(self.client.get("/api/inventario/" + path).status_code,
                    403 if role in {"TECNICO", "ADMINISTRADOR_TI"} else 200, (role, path))
            result = self.client.post("/api/inventario/ingresos/", self.payload(), format="json")
            self.assertEqual(result.status_code, 201 if role == "BODEGUERO" else 403)
            result = self.client.post("/api/inventario/articulos/", {"codigo": f"rol-{role.lower()}", "nombre": "Prueba", "unidad": "u"}, format="json")
            self.assertEqual(result.status_code, 201 if role == "BODEGUERO" else 403)
            result = self.client.patch(f"/api/inventario/articulos/{self.article.pk}/", {"nombre": "Nombre editado"}, format="json")
            self.assertEqual(result.status_code, 200 if role == "BODEGUERO" else 403)

    def test_bodega_denegada_en_dominios_existentes(self):
        for path in ("/api/usuarios/", "/api/clientes/", "/api/presupuestos/", "/api/obras/", "/api/categorias-servicio/",
                     "/api/finanzas/documentos/", "/api/documentos-metadata/", "/api/adjuntos/obras/1/", "/api/auditoria/eventos/", "/api/alertas/", "/api/dashboard/resumen/", "/api/reportes/catalogo/"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 403, path)

    def test_ingreso_exactitud_y_replay(self):
        data = self.payload(cantidad="0.100")
        first = self.client.post("/api/inventario/ingresos/", data, format="json")
        data["cantidad"] = "0.1"
        replay = self.client.post("/api/inventario/ingresos/", data, format="json")
        self.assertEqual((first.status_code, replay.status_code), (201, 200))
        self.assertEqual(first.data, replay.data)
        self.assertEqual(replay["Idempotency-Replayed"], "true")
        self.ingreso(cantidad="0.200")
        self.assertEqual(ExistenciaInventario.objects.get(articulo=self.article).saldo, Decimal("0.300"))
        self.assertEqual(first.data["saldo_posterior"], "0.100")

    def test_clave_distinta_carga_actor_o_articulo_conflicto(self):
        data = self.payload()
        services.registrar_ingreso(data, self.bodega)
        other = Usuario.objects.create_user(username="qa_otrob", email="qa_otrob@example.test", rol="BODEGUERO")
        for changes, actor in (({"cantidad": "2.000"}, self.bodega), ({"motivo": "otro"}, self.bodega), ({}, other),
                               ({"articulo": self.article.pk + 1}, self.bodega), ({"referencia": "otra"}, self.bodega)):
            with self.assertRaises(APIException) as caught:
                services.registrar_ingreso({**data, **changes}, actor)
            self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(MovimientoInventario.objects.count(), 1)

    def test_decimales_estrictos(self):
        for value in (1, 1.25, True, None, "NaN", "Infinity", "1e2", "-1", "0", "1.0000", "1000000000", "1,2", " 1.0 "):
            result = self.client.post("/api/inventario/ingresos/", self.payload(cantidad=value), format="json")
            self.assertEqual(result.status_code, 400, value)
        self.assertFalse(MovimientoInventario.objects.exists())

    def test_campos_cerrados_y_uuid_id_estrictos(self):
        for extra in ({"saldo": "2"}, {"actor": self.bodega.pk}, {"creado_en": "2026-11-20"}, {"tipo": "SALIDA"},
                      {"articulo": True}, {"articulo": "1"}, {"clave_idempotencia": "no-uuid"}):
            self.assertEqual(self.client.post("/api/inventario/ingresos/", self.payload(**extra), format="json").status_code, 400)
        for extra in ({"saldo": "1"}, {"precio": "1"}, {"creado_por": self.bodega.pk}, {"activo": "false"}, {"unidad": ""}):
            self.assertEqual(self.client.patch(f"/api/inventario/articulos/{self.article.pk}/", extra, format="json").status_code, 400)

    def test_unicidad_y_catalogo_noop_edicion(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            ArticuloInventario.objects.filter(pk=self.article.pk).update(unidad="\t")
        with self.assertRaises(APIException):
            services.crear_articulo({"codigo": "MAT-01", "nombre": "Duplicado", "unidad": "u"}, self.bodega)
        old = self.article.actualizado_en
        result = services.editar_articulo(self.article.pk, {"nombre": " Material "}, self.bodega)
        self.assertEqual(result.actualizado_en, old)
        result = services.editar_articulo(self.article.pk, {"codigo": "otro", "unidad": "m"}, self.bodega)
        self.assertEqual((result.codigo, result.unidad), ("otro", "m"))

    def test_movimiento_protege_codigo_unidad_y_desactivacion_conserva_saldo(self):
        data = self.payload()
        services.registrar_ingreso(data, self.bodega)
        for field in ("codigo", "unidad"):
            with self.assertRaises(APIException) as caught:
                services.editar_articulo(self.article.pk, {field: "otro"}, self.bodega)
            self.assertEqual(caught.exception.status_code, 409)
        services.editar_articulo(self.article.pk, {"activo": False}, self.bodega)
        with self.assertRaises(APIException):
            self.ingreso()
        self.assertFalse(services.registrar_ingreso(data, self.bodega)[1])  # replay no es entrada nueva.
        self.assertEqual(ExistenciaInventario.objects.get(articulo=self.article).saldo, Decimal("1.250"))

    def test_metodos_no_publicados(self):
        for method, path in (("delete", f"articulos/{self.article.pk}/"), ("put", f"articulos/{self.article.pk}/"),
                             ("post", "existencias/"), ("post", "movimientos/"), ("get", "ingresos/")):
            self.assertEqual(getattr(self.client, method)("/api/inventario/" + path).status_code, 405)

    def test_lecturas_filtros_paginacion_y_sin_reconstruccion(self):
        for i in range(26):
            services.crear_articulo({"codigo": f"mat-{i+10}", "nombre": "Artículo", "unidad": "u"}, self.bodega)
        result = self.client.get("/api/inventario/articulos/?activo=true&buscar=mat")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(len(result.data["results"]), 25)
        self.assertEqual(result.data["count"], 27)
        before = (ArticuloInventario.objects.count(), ExistenciaInventario.objects.count(), MovimientoInventario.objects.count())
        self.client.get("/api/inventario/existencias/")
        self.client.get(f"/api/inventario/articulos/{self.article.pk}/")
        self.client.get("/api/inventario/movimientos/")
        self.assertEqual((ArticuloInventario.objects.count(), ExistenciaInventario.objects.count(), MovimientoInventario.objects.count()), before)
        self.ingreso()
        today = timezone.localdate().isoformat()
        self.assertEqual(self.client.get(f"/api/inventario/movimientos/?desde={today}&hasta={today}&tipo=INGRESO").data["count"], 1)
        for suffix in ("?saldo=1", "?activo=true&activo=false", "?page=-1"):
            self.assertEqual(self.client.get("/api/inventario/articulos/" + suffix).status_code, 400)
        for suffix in ("?tipo=SALIDA", "?desde=2026-02-30", "?desde=2026-02-02&hasta=2026-01-01"):
            self.assertEqual(self.client.get("/api/inventario/movimientos/" + suffix).status_code, 400)

    def test_usuario_revocado_temporal_inactivo_sin_acceso(self):
        for field in ("is_active", "sesion_version"):
            before = getattr(self.bodega, field)
            Usuario.objects.filter(pk=self.bodega.pk).update(**{field: False if field == "is_active" else before + 1})
            self.assertEqual(self.client.get("/api/inventario/articulos/").status_code, 401)
            Usuario.objects.filter(pk=self.bodega.pk).update(**{field: before})
        SeguridadCredencial.objects.filter(usuario=self.bodega).delete()
        self.assertEqual(self.client.get("/api/inventario/articulos/").status_code, 401)

    def test_cambio_desde_bodega_revoca_tokens(self):
        refresh = str(RefreshToken.for_user(self.bodega))
        usuarios.cambiar_rol(self.bodega, {"rol": "TECNICO", "motivo": "QA019"}, self.users["ADMINISTRADOR_TI"])
        self.assertEqual(self.client.get("/api/inventario/articulos/").status_code, 401)
        with self.assertRaises(APIException):
            VersionedRefreshSerializer().validate({"refresh": refresh})

    def test_ti_puede_crear_filtrar_y_asignar_bodeguero(self):
        self.auth(self.users["ADMINISTRADOR_TI"])
        response = self.client.post("/api/usuarios/", {"username": "qa_nueva_bodega", "email": "qa_nueva_bodega@example.test", "rol": "BODEGUERO"}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["rol"], "BODEGUERO")
        self.assertFalse(response.data["is_active"])
        self.assertEqual(self.client.get("/api/usuarios/?rol=BODEGUERO").data["count"], 2)
        target = self.users["ADMINISTRATIVO_FINANZAS"]
        old = str(AccessToken.for_user(target))
        response = self.client.post(f"/api/usuarios/{target.pk}/cambiar-rol/", {"rol": "BODEGUERO", "motivo": "QA019A"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {old}")
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 401)

    def test_no_autenticado_y_rol_persistido_no_claim(self):
        anonymous = APIClient()
        self.assertEqual(anonymous.get("/api/inventario/articulos/").status_code, 401)
        token = AccessToken.for_user(self.users["TECNICO"])
        token["rol"] = "BODEGUERO"
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual(self.client.get("/api/inventario/articulos/").status_code, 403)

    def test_saldo_maximo_rechaza_exceso_sin_efectos(self):
        self.ingreso(cantidad="999999999.999")
        with self.assertRaises(APIException) as caught:
            self.ingreso(cantidad="0.001")
        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(MovimientoInventario.objects.count(), 1)

    def test_sql_snapshots_y_actor_incorrectos_rechazados(self):
        for actor, before, after in ((self.users["ADMINISTRADOR_TI"], "0", "1"), (self.bodega, "2", "3")):
            with self.assertRaises(IntegrityError), transaction.atomic():
                MovimientoInventario.objects.create(articulo=self.article, actor=actor, cantidad=Decimal("1"),
                    saldo_anterior=Decimal(before), saldo_posterior=Decimal(after), clave_idempotencia=uuid4())
        self.assertEqual(ExistenciaInventario.objects.get(articulo=self.article).saldo, Decimal("0"))

    def test_bodega_temporal_o_bloqueada_no_opera(self):
        from datetime import timedelta
        now = timezone.now()
        SeguridadCredencial.objects.filter(usuario=self.bodega).update(estado="INICIAL", emitida_en=now, vence_en=now+timedelta(hours=1))
        self.assertEqual(self.client.get("/api/inventario/articulos/").status_code, 401)
        SeguridadCredencial.objects.filter(usuario=self.bodega).update(estado="PERSONAL", emitida_en=None, vence_en=None)
        from apps.usuarios.autenticacion_c2 import verificar_acceso
        ti1, ti2 = self.users["ADMINISTRADOR_TI"], Usuario.objects.create_user(username="qa_ti2", email="qa_ti2@example.test", rol="ADMINISTRADOR_TI", password=secrets.token_urlsafe(32))
        with override_settings(BLOQUEOS_C2_HABILITADO=True, BLOQUEOS_C2_ENTORNO="QA_AISLADO_C2",
            BLOQUEOS_C2_TI_QA_IDS=(ti1.pk, ti2.pk), BLOQUEOS_C2_RECUPERACION_QA_CONFIRMADA=True,
            BLOQUEOS_C2_RIESGO_DOS_QA_ACEPTADO=True, BLOQUEOS_C2_RESPUESTAS="401_GENERICO",
            BLOQUEOS_C2_SESIONES_TEMPORALES="REVOCAR_TODAS_QA"):
            for _ in range(5):
                self.assertIsNone(verificar_acceso(self.bodega.email, "qa019-error", None))
            self.assertEqual(self.client.get("/api/inventario/articulos/").status_code, 401)

    def test_rollback_movimiento_revierte_saldo(self):
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                self.ingreso()
                raise RuntimeError("QA rollback")
        self.assertEqual(ExistenciaInventario.objects.get(articulo=self.article).saldo, Decimal("0"))
        self.assertFalse(MovimientoInventario.objects.exists())

    def test_fallo_alta_no_deja_articulo_o_existencia(self):
        with patch.object(ArticuloInventario.objects, "create", side_effect=IntegrityError("QA")):
            with self.assertRaises(IntegrityError):
                services.crear_articulo({"codigo": "nuevo", "nombre": "Nuevo", "unidad": "u"}, self.bodega)
        self.assertEqual(ArticuloInventario.objects.count(), 1)
        self.assertEqual(ExistenciaInventario.objects.count(), 1)

    def test_libro_inmutable_orm_sql_y_rangos(self):
        movement, _ = self.ingreso()
        with self.assertRaises(DjangoValidationError):
            movement.delete()
        with self.assertRaises(DjangoValidationError):
            MovimientoInventario.objects.update(motivo="cambio")
        for sql in ("UPDATE inventario_movimientoinventario SET motivo=motivo", "DELETE FROM inventario_movimientoinventario",
                    "DELETE FROM inventario_existenciainventario", "DELETE FROM inventario_articuloinventario",
                    "UPDATE inventario_articuloinventario SET unidad='otra'", "UPDATE inventario_existenciainventario SET saldo=-1"):
            with self.assertRaises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
                cursor.execute(sql)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class ConcurrenciaInventarioTests(BaseInventario, TransactionTestCase):
    race = concurrencia.ConcurrenciaTests.race

    def test_ingresos_distintos_suman_exactamente(self):
        one, two = self.race(lambda: self.ingreso(cantidad="0.100"), lambda: self.ingreso(cantidad="0.200"))
        self.assertTrue(one[1] and two[1])
        self.assertEqual(ExistenciaInventario.objects.get(articulo=self.article).saldo, Decimal("0.300"))
        self.assertEqual(MovimientoInventario.objects.count(), 2)

    def test_misma_clave_un_movimiento(self):
        data = self.payload()
        action = lambda: services.registrar_ingreso(data, self.bodega)
        one, two = self.race(action, action)
        self.assertTrue(one[1])
        self.assertFalse(two[1])
        self.assertEqual(one[0].pk, two[0].pk)
        self.assertEqual(MovimientoInventario.objects.count(), 1)

    def test_clave_cargas_distintas_conflicto(self):
        data = self.payload()
        one, two = self.race(lambda: services.registrar_ingreso(data, self.bodega),
                             lambda: services.registrar_ingreso({**data, "cantidad": "2"}, self.bodega))
        self.assertTrue(one[1])
        self.assertEqual(two.status_code, 409)

    def test_clave_global_entre_articulos(self):
        other = services.crear_articulo({"codigo": "otro-articulo", "nombre": "Otro", "unidad": "u"}, self.bodega)
        data = self.payload()
        one, two = self.race(lambda: services.registrar_ingreso(data, self.bodega),
                             lambda: services.registrar_ingreso({**data, "articulo": other.pk}, self.bodega))
        self.assertTrue(one[1])
        self.assertEqual(two.status_code, 409)
        self.assertEqual(ExistenciaInventario.objects.get(articulo=other).saldo, Decimal("0"))

    def test_altas_codigo_iguales_concurrentes(self):
        data = {"codigo": "nuevo-igual", "nombre": "Artículo", "unidad": "u"}
        one, two = self.race(lambda: services.crear_articulo(data, self.bodega), lambda: services.crear_articulo(data, self.bodega))
        self.assertIsInstance(one, ArticuloInventario)
        self.assertEqual(two.status_code, 400)
        self.assertEqual(ArticuloInventario.objects.filter(codigo="nuevo-igual").count(), 1)

    def test_desactivacion_antes_de_ingreso(self):
        one, two = self.race(lambda: services.editar_articulo(self.article.pk, {"activo": False}, self.bodega), self.ingreso)
        self.assertFalse(one.activo)
        self.assertEqual(two.status_code, 409)

    def test_saldo_directo_sin_libro_falla_al_commit(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ExistenciaInventario.objects.filter(articulo=self.article).update(saldo=Decimal("1"))
        self.assertEqual(ExistenciaInventario.objects.get(articulo=self.article).saldo, Decimal("0"))
