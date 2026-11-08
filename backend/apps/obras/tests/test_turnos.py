from datetime import timedelta
from decimal import Decimal
from io import BytesIO
from pathlib import Path
import struct
import zlib
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, connection, transaction
from django.test import TestCase, override_settings
from django.utils import timezone
from PIL import Image, PngImagePlugin
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from apps.comercial.models import Presupuesto
from apps.obras import services, services_turnos as turnos
from apps.obras.evidencias import MAX_BYTES, ruta_privada
from apps.obras.exceptions import DatosInvalidos, EstadoIncompatible, PermisoDenegado, RecursoNoEncontrado
from apps.obras.models import Obra, TurnoObra, TurnoObraEvento, EvidenciaTurno
from .test_servicios_004a import BaseObras


def foto(formato="PNG", nombre="foto.png"):
    buffer = BytesIO()
    Image.new("RGB", (12, 12), "blue").save(buffer, formato)
    return SimpleUploadedFile(nombre, buffer.getvalue(), content_type="application/octet-stream")


def png_comprimido(ancho, alto):
    # PNG real de color uniforme, construido por filas sin reservar el raster.
    def chunk(tipo, datos):
        return struct.pack(">I", len(datos)) + tipo + datos + struct.pack(">I", zlib.crc32(tipo + datos))

    compresor = zlib.compressobj()
    fila = b"\0" * (ancho + 1)  # Filtro 0 y píxeles de escala de grises.
    comprimido = b"".join(compresor.compress(fila) for _ in range(alto)) + compresor.flush()
    contenido = (b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", ancho, alto, 8, 0, 0, 0, 0))
        + chunk(b"IDAT", comprimido) + chunk(b"IEND", b""))
    return SimpleUploadedFile("comprimida.png", contenido, content_type="image/png")


class TurnosBase(BaseObras):
    def preparar(self):
        self.obra = self.crear(tecnico_responsable=self.tecnico.pk, motivo="Principal")
        services.iniciar_obra(self.obra, self.supervisor, "Inicio")
        self.miembro, _ = services.asignar_participante(self.obra, {"tecnico": self.otro_tecnico.pk, "motivo": "Apoyo"}, self.supervisor)
        self.client = APIClient()
        self.autenticar(self.tecnico)
        self.url = f"/api/obras/{self.obra.pk}/turnos/"

    def autenticar(self, usuario):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(usuario)}")

    def abrir(self, tecnico=None, obra=None):
        return turnos.iniciar_turno(obra or self.obra, {}, tecnico or self.tecnico)

    def cerrar(self, turno, tecnico=None, fotos=()):
        with patch("apps.obras.services_turnos.timezone.now", return_value=turno.iniciado_en + timedelta(seconds=61, microseconds=123456)):
            return turnos.finalizar_turno(turno.obra_id, turno.pk, {"descripcion_trabajo": "Trabajo realizado"}, tecnico or self.tecnico, fotos=fotos)

    def otra_obra(self):
        presupuesto = Presupuesto.objects.create(cliente=self.cliente, creado_por=self.finanzas, descripcion="Otra", estado="APROBADO_CLIENTE")
        obra = services.crear_obra(self.datos(presupuesto=presupuesto.pk, tecnico_responsable=self.tecnico.pk, motivo="Principal"), self.supervisor)
        return services.iniciar_obra(obra, self.supervisor, "Inicio")


class TurnosTests(TurnosBase, TestCase):
    def setUp(self):
        self.preparar()
        self.temporal = TemporaryDirectory()
        self.addCleanup(self.temporal.cleanup)
        configuracion = override_settings(EVIDENCIAS_ROOT=self.temporal.name)
        configuracion.enable()
        self.addCleanup(configuracion.disable)

    def test_foto_en_limite_de_pixeles_es_valida(self):
        turno = self.abrir()
        archivo = png_comprimido(4000, 3000)
        self.assertLess(archivo.size, MAX_BYTES)
        respuesta = self.client.post(self.url + f"{turno.pk}/finalizar/", {
            "descripcion_trabajo": "Trabajo", "fotos[]": [archivo],
        }, format="multipart")
        self.assertEqual(respuesta.status_code, 200, respuesta.data)
        evidencia = turno.fotos.get()
        with Image.open(ruta_privada(evidencia.nombre_interno)) as imagen:
            self.assertEqual(imagen.size, (4000, 3000))
            imagen.load()

    def test_fotos_excesivas_rechazadas_antes_de_procesar_sin_efectos(self):
        turno = self.abrir()
        for accion in ("finalizar", "subsanar"):
            if accion == "subsanar":
                self.cerrar(turno)
                turnos.revisar_turno(self.obra, turno.pk, {
                    "decision": "OBSERVAR", "motivo": "Agregar evidencia",
                }, self.supervisor)
            antes = TurnoObra.objects.values().get(pk=turno.pk)
            eventos = list(turno.eventos.values())
            for dimensiones in ((4000, 3001), (8000, 8000)):
                with self.subTest(accion=accion, dimensiones=dimensiones):
                    archivo = png_comprimido(*dimensiones)
                    self.assertLess(archivo.size, MAX_BYTES)
                    with (
                        patch.object(PngImagePlugin.PngImageFile, "load", side_effect=AssertionError("No decodificar")) as load,
                        patch.object(Image.Image, "convert", side_effect=AssertionError("No convertir")) as convert,
                        patch.object(Image, "new", side_effect=AssertionError("No reservar raster")) as new,
                    ):
                        respuesta = self.client.post(self.url + f"{turno.pk}/{accion}/", {
                            "descripcion_trabajo": "Trabajo", "fotos[]": [archivo],
                        }, format="multipart")
                    self.assertEqual(respuesta.status_code, 400, respuesta.data)
                    self.assertIn("12.000.000", str(respuesta.data))
                    load.assert_not_called()
                    convert.assert_not_called()
                    new.assert_not_called()
                    self.assertEqual(TurnoObra.objects.values().get(pk=turno.pk), antes)
                    self.assertEqual(list(turno.eventos.values()), eventos)
                    self.assertFalse(EvidenciaTurno.objects.exists())
                    self.assertEqual(list(Path(self.temporal.name).iterdir()), [])

    def test_inicio_servidor_body_y_evento(self):
        ahora = timezone.now()
        for datos in ({"tecnico": self.tecnico.pk}, {"iniciado_en": ahora.isoformat()}, {"horas": 1}, [], {"estado_revision": "VALIDADO"}):
            respuesta = self.client.post(self.url + "iniciar/", datos, format="json")
            self.assertEqual(respuesta.status_code, 400, respuesta.data)
        with patch("apps.obras.services_turnos.timezone.now", return_value=ahora):
            respuesta = self.client.post(self.url + "iniciar/", {}, format="json")
        self.assertEqual(respuesta.status_code, 201, respuesta.data)
        turno = TurnoObra.objects.get()
        self.assertEqual(turno.iniciado_en, ahora)
        self.assertEqual(turno.tecnico_id, self.tecnico.pk)
        self.assertEqual(turno.eventos.get().tipo, "INICIO")
        self.assertEqual(turno.eventos.get().registrado_por_id, self.tecnico.pk)
        self.assertNotIn("costo_hora_neto", respuesta.data)
        self.assertEqual(self.client.post(self.url + "iniciar/", {}, format="json").status_code, 409)
        otra = self.otra_obra()
        self.assertEqual(self.client.post(f"/api/obras/{otra.pk}/turnos/iniciar/", {}, format="json").status_code, 409)

    def test_no_asignado_inactivo_roles_y_estados(self):
        services.desasignar_participante(self.obra, self.miembro.pk, self.supervisor, "Baja")
        self.autenticar(self.otro_tecnico)
        self.assertEqual(self.client.post(self.url + "iniciar/", {}, format="json").status_code, 404)
        with self.assertRaises(RecursoNoEncontrado):
            self.abrir(self.otro_tecnico)
        self.autenticar(self.tecnico)
        for estado in ("SUSPENDIDA", "FINALIZADA", "CANCELADA", "PLANIFICADA"):
            cambios = {"estado": estado, "finalizado_en": None, "cancelado_en": None}
            if estado == "FINALIZADA":
                cambios["finalizado_en"] = timezone.now()
            if estado == "CANCELADA":
                cambios["cancelado_en"] = timezone.now()
            if estado == "PLANIFICADA":
                cambios["iniciado_en"] = None
            Obra.objects.filter(pk=self.obra.pk).update(**cambios)
            self.assertEqual(self.client.post(self.url + "iniciar/", {}, format="json").status_code, 409)
        type(self.tecnico).objects.filter(pk=self.tecnico.pk).update(is_active=False)
        with self.assertRaises(PermisoDenegado):
            self.abrir()

    def test_cierre_descripcion_sin_fotos_duracion_exacta(self):
        turno = self.abrir()
        ruta = self.url + f"{turno.pk}/finalizar/"
        for datos in ({}, {"descripcion_trabajo": "  "}, {"descripcion_trabajo": 32}, {"descripcion_trabajo": "x" * 2001}, {"descripcion_trabajo": "Trabajo", "duracion_segundos": 100}, {"descripcion_trabajo": "Trabajo", "terminado_en": timezone.now().isoformat()}):
            respuesta = self.client.post(ruta, datos, format="json")
            self.assertEqual(respuesta.status_code, 400, respuesta.data)
        cerrado = self.cerrar(turno)
        self.assertEqual(cerrado.duracion_segundos, Decimal("61.123456"))
        self.assertEqual(cerrado.estado_revision, "PENDIENTE_REVISION")
        self.assertEqual(cerrado.fotos.count(), 0)
        self.assertEqual(self.client.post(ruta, {"descripcion_trabajo": "Trabajo"}, format="json").status_code, 409)
        self.assertEqual(cerrado.eventos.count(), 2)
        self.obra.refresh_from_db()
        self.assertEqual(self.obra.estado, "EN_PROCESO")

    def test_duracion_no_positiva_rollback(self):
        turno = self.abrir()
        with patch("apps.obras.services_turnos.timezone.now", return_value=turno.iniciado_en):
            with self.assertRaises(EstadoIncompatible):
                turnos.finalizar_turno(self.obra, turno.pk, {"descripcion_trabajo": "Trabajo"}, self.tecnico)
        turno.refresh_from_db()
        self.assertIsNone(turno.terminado_en)
        self.assertEqual(turno.eventos.count(), 1)

    def test_revision_subsanacion_tarifa_y_correccion(self):
        turno = self.cerrar(self.abrir())
        self.autenticar(self.supervisor)
        revisar = self.url + f"{turno.pk}/revisar/"
        self.assertEqual(self.client.post(revisar, {"decision": "VALIDAR", "motivo": "Revisado"}, format="json").status_code, 400)
        observada = self.client.post(revisar, {"decision": "OBSERVAR", "motivo": "Detalle el trabajo"}, format="json")
        self.assertEqual(observada.status_code, 200, observada.data)
        self.autenticar(self.tecnico)
        self.assertEqual(self.client.get(self.url).data["results"][0]["observacion"], "Detalle el trabajo")
        subsanada = self.client.post(self.url + f"{turno.pk}/subsanar/", {"descripcion_trabajo": "Se reemplazó el compresor"}, format="json")
        self.assertEqual(subsanada.status_code, 200, subsanada.data)
        self.assertEqual(subsanada.data["descripcion_trabajo"], "Trabajo realizado\nSe reemplazó el compresor")
        self.autenticar(self.supervisor)
        validada = self.client.post(revisar, {"decision": "VALIDAR", "motivo": "Revisado", "costo_hora_neto": "8000.00"}, format="json")
        self.assertEqual(validada.status_code, 200, validada.data)
        self.assertEqual(validada.data["costo_mano_obra"], "135.83")
        self.assertEqual(self.client.post(revisar, {"decision": "VALIDAR", "motivo": "Otra", "costo_hora_neto": "8000.00"}, format="json").status_code, 409)
        original = (turno.iniciado_en, turno.terminado_en, turno.duracion_segundos)
        corregir = self.url + f"{turno.pk}/corregir/"
        respuesta = self.client.post(corregir, {"duracion_ajustada_segundos": 3600, "costo_hora_neto": "9000.00", "motivo": "Rectificación respaldada"}, format="json")
        self.assertEqual(respuesta.status_code, 200, respuesta.data)
        self.assertEqual(respuesta.data["estado_revision"], "PENDIENTE_REVISION")
        turno.refresh_from_db()
        self.assertEqual((turno.iniciado_en, turno.terminado_en, turno.duracion_segundos), original)
        self.assertIsNone(turno.revisado_por_id)
        evento = turno.eventos.get(tipo="CORRECCION")
        self.assertEqual(evento.tipo, "CORRECCION")
        self.assertEqual(evento.datos_anteriores["costo_hora_neto"], "8000.00")
        self.assertEqual(evento.datos_nuevos["duracion_ajustada_segundos"], 3600)
        self.assertEqual(self.client.post(revisar, {"decision": "VALIDAR", "motivo": "Revalidación", "costo_hora_neto": "9000.00"}, format="json").status_code, 200)
        self.assertEqual(self.client.post(corregir, {"duracion_ajustada_segundos": None, "motivo": "Restituir duración original"}, format="json").status_code, 200)
        turno.refresh_from_db()
        self.assertIsNone(turno.duracion_ajustada_segundos)
        self.autenticar(self.tecnico)
        lectura = self.client.get(self.url).data["results"][0]
        self.assertFalse({"costo_hora_neto", "costo_mano_obra", "eventos", "observacion_revision"} & set(lectura))

    def test_tarifas_estrictas_ajuste_y_redondeo(self):
        turno = self.cerrar(self.abrir())
        self.autenticar(self.supervisor)
        for tarifa in (12, 12.0, True, "NaN", "Infinity", "1e3", "-1.00", "1.001", "10000000000000.00", "1", " 1.00", None):
            respuesta = self.client.post(self.url + f"{turno.pk}/revisar/", {"decision": "VALIDAR", "motivo": "Revisar", "costo_hora_neto": tarifa}, format="json")
            self.assertEqual(respuesta.status_code, 400, respuesta.data)
        for ajuste in (0, -1, True, 1.5, "3600", 9223372036854775808):
            self.assertEqual(self.client.post(self.url + f"{turno.pk}/corregir/", {"duracion_ajustada_segundos": ajuste, "motivo": "Ajuste"}, format="json").status_code, 400)
        turno.duracion_ajustada_segundos = 1
        turno.costo_hora_neto = Decimal("18.00")
        self.assertEqual(turno.costo_mano_obra, Decimal("0.01"))
        turno = turnos.revisar_turno(self.obra, turno.pk, {"decision": "VALIDAR", "motivo": "Tarifa cero registrada", "costo_hora_neto": "0.00"}, self.supervisor)
        self.assertEqual(turno.costo_mano_obra, Decimal("0.00"))

    def test_guards_suspension_desasignacion_principal_y_adicional(self):
        principal = self.abrir()
        apoyo = self.abrir(self.otro_tecnico)
        for accion in (
            lambda: services.suspender_obra(self.obra, self.supervisor, "Pausa"),
            lambda: services.cambiar_tecnico(self.obra, self.otro_tecnico.pk, self.supervisor, "Cambio"),
            lambda: services.desasignar_participante(self.obra, self.miembro.pk, self.supervisor, "Baja"),
        ):
            with self.assertRaises(EstadoIncompatible):
                accion()
        self.cerrar(principal)
        self.cerrar(apoyo, self.otro_tecnico)
        services.cambiar_tecnico(self.obra, self.otro_tecnico.pk, self.supervisor, "Cambio")
        services.suspender_obra(self.obra, self.supervisor, "Pausa")
        self.assertEqual(TurnoObra.objects.count(), 2)
        self.assertEqual(TurnoObra.objects.get(pk=principal.pk).tecnico_id, self.tecnico.pk)

    def test_roles_superusuarios_ajenos_y_precedencia(self):
        turno = self.abrir()
        for usuario in (self.supervisor, self.gerencia, self.finanzas, self.tecnico):
            usuario.is_superuser = True
            usuario.save()
            self.autenticar(usuario)
            self.assertEqual(self.client.get(self.url).status_code, 403 if usuario == self.finanzas else 200)
            if usuario != self.tecnico:
                for accion in ("iniciar", f"{turno.pk}/finalizar", f"{turno.pk}/subsanar"):
                    self.assertEqual(self.client.post(self.url + accion + "/", {}, format="json").status_code, 403)
            if usuario != self.supervisor:
                for accion in ("revisar", "corregir"):
                    self.assertEqual(self.client.post(self.url + f"99999/{accion}/", {}, format="json").status_code, 403)
        self.autenticar(self.otro_tecnico)
        self.assertEqual(self.client.get(self.url).data["count"], 0)
        self.assertEqual(self.client.post(self.url + f"{turno.pk}/finalizar/", {}, format="json").status_code, 404)
        self.assertEqual(self.client.get(self.url + f"{turno.pk}/fotos/99999/").status_code, 404)
        self.assertEqual(self.client.post(self.url + f"99999/finalizar/", {}, format="json").status_code, 404)
        self.assertEqual(self.client.put(self.url, {}, format="json").status_code, 405)
        self.assertEqual(self.client.delete(self.url).status_code, 405)
        self.client.credentials()
        self.assertEqual(self.client.get(self.url).status_code, 401)

    def test_fotos_validas_multipart_descarga_privada(self):
        turno = self.abrir()
        respuesta = self.client.post(self.url + f"{turno.pk}/finalizar/", {
            "descripcion_trabajo": "Trabajo con fotos",
            "fotos[]": [foto("JPEG", "../../intento.jpg"), foto("PNG"), foto("WEBP")],
        }, format="multipart")
        self.assertEqual(respuesta.status_code, 200, respuesta.data)
        self.assertEqual(len(respuesta.data["fotos"]), 3)
        self.assertNotIn("nombre_interno", str(respuesta.data))
        self.assertNotIn("sha256", str(respuesta.data))
        evidencia = EvidenciaTurno.objects.first()
        self.assertTrue(ruta_privada(evidencia.nombre_interno).exists())
        ruta = respuesta.data["fotos"][0]["descarga"]
        for usuario in (self.tecnico, self.supervisor, self.gerencia):
            self.autenticar(usuario)
            descarga = self.client.get(ruta)
            self.assertEqual(descarga.status_code, 200)
            self.assertEqual(descarga["Cache-Control"], "private, no-store")
            self.assertTrue(b"".join(descarga.streaming_content))
        self.autenticar(self.otro_tecnico)
        self.assertEqual(self.client.get(ruta).status_code, 404)
        self.autenticar(self.finanzas)
        self.assertEqual(self.client.get(ruta).status_code, 403)
        self.assertEqual(self.client.get("/media/" + evidencia.nombre_interno).status_code, 404)
        self.client.credentials()
        self.assertEqual(self.client.get(ruta).status_code, 401)

    def test_fotos_malformadas_limites_y_no_huerfanos(self):
        turno = self.abrir()
        for fotos in (
            [SimpleUploadedFile("foto.jpg", b"<script>no imagen</script>", content_type="image/jpeg")],
            [SimpleUploadedFile("foto.png", b"x" * (MAX_BYTES + 1))],
            [foto("GIF")], [foto() for _ in range(6)],
        ):
            respuesta = self.client.post(self.url + f"{turno.pk}/finalizar/", {"descripcion_trabajo": "Trabajo", "fotos[]": fotos}, format="multipart")
            self.assertEqual(respuesta.status_code, 400, respuesta.data)
            turno.refresh_from_db()
            self.assertIsNone(turno.terminado_en)
            self.assertFalse(EvidenciaTurno.objects.exists())
            self.assertEqual(list(Path(self.temporal.name).iterdir()), [])
        self.cerrar(turno, fotos=[foto() for _ in range(5)])
        turnos.revisar_turno(self.obra, turno.pk, {"decision": "OBSERVAR", "motivo": "Aclarar"}, self.supervisor)
        with self.assertRaises(DatosInvalidos):
            turnos.subsanar_turno(self.obra, turno.pk, {}, self.tecnico, fotos=[foto()])
        self.assertEqual(EvidenciaTurno.objects.count(), 5)
        self.assertEqual(len(list(Path(self.temporal.name).iterdir())), 5)

    def test_rollback_evento_y_escritura_archivos(self):
        turno = self.abrir()
        with patch("apps.obras.services_turnos._evento", side_effect=RuntimeError("Fallo evento")):
            with self.assertRaises(RuntimeError):
                self.cerrar(turno, fotos=[foto()])
        turno.refresh_from_db()
        self.assertIsNone(turno.terminado_en)
        self.assertEqual(turno.eventos.count(), 1)
        self.assertFalse(EvidenciaTurno.objects.exists())
        self.assertEqual(list(Path(self.temporal.name).iterdir()), [])
        with patch("apps.obras.services_turnos.EvidenciaTurno.objects.create", side_effect=RuntimeError("Fallo metadata")):
            with self.assertRaises(RuntimeError):
                self.cerrar(turno, fotos=[foto()])
        self.assertEqual(list(Path(self.temporal.name).iterdir()), [])

    def test_constraints_postgres(self):
        turno = self.abrir()
        with self.assertRaises(IntegrityError), transaction.atomic():
            TurnoObra.objects.bulk_create([TurnoObra(obra=self.obra, tecnico=self.tecnico, iniciado_en=timezone.now())])
        for cambios in ({"estado_revision": "OTRO"}, {"duracion_ajustada_segundos": 0}, {"terminado_en": turno.iniciado_en}, {"duracion_segundos": 1}):
            with self.subTest(cambios=cambios), self.assertRaises(IntegrityError), transaction.atomic():
                TurnoObra.objects.filter(pk=turno.pk).update(**cambios)
        with self.assertRaises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
            cursor.execute("UPDATE obras_turnoobra SET costo_hora_neto = 'NaN' WHERE id = %s", [turno.pk])

    def test_paginacion_turnos_solo_propios_sin_n_mas_uno(self):
        for _ in range(26):
            self.cerrar(self.abrir())
        self.cerrar(self.abrir(self.otro_tecnico), self.otro_tecnico)
        with self.assertNumQueries(5):  # JWT, Obra autorizada, count, turnos, fotos.
            respuesta = self.client.get(self.url)
        self.assertEqual(respuesta.data["count"], 26)
        self.assertEqual(len(respuesta.data["results"]), 25)
        self.assertEqual(len(self.client.get(self.url + "?page=2").data["results"]), 1)
        self.assertEqual(self.client.get(self.url + "?page=99").status_code, 404)
        self.assertEqual(self.client.get(self.url + "?tecnico=999").status_code, 400)
        self.autenticar(self.supervisor)
        self.assertEqual(self.client.get(self.url).data["count"], 27)

    def test_subsanar_solo_fotos_y_rollback_preserva_revision(self):
        turno = self.cerrar(self.abrir())
        turnos.revisar_turno(self.obra, turno.pk, {"decision": "OBSERVAR", "motivo": "Agregar evidencia"}, self.supervisor)
        with patch("apps.obras.services_turnos._evento", side_effect=RuntimeError("Fallo")):
            with self.assertRaises(RuntimeError):
                turnos.subsanar_turno(self.obra, turno.pk, {}, self.tecnico, fotos=[foto()])
        turno.refresh_from_db()
        self.assertEqual(turno.estado_revision, "OBSERVADO")
        self.assertEqual(list(Path(self.temporal.name).iterdir()), [])
        respuesta = self.client.post(self.url + f"{turno.pk}/subsanar/", {"fotos[]": [foto()]}, format="multipart")
        self.assertEqual(respuesta.status_code, 200, respuesta.data)
        self.assertEqual(respuesta.data["descripcion_trabajo"], "Trabajo realizado")
        self.assertEqual(respuesta.data["estado_revision"], "PENDIENTE_REVISION")

    def test_rutas_arbitrarias_y_fotos_de_otro_turno(self):
        turno = self.cerrar(self.abrir(), fotos=[foto()])
        evidencia = turno.fotos.get()
        otro = self.cerrar(self.abrir())
        ruta_incorrecta = self.url + f"{otro.pk}/fotos/{evidencia.pk}/"
        self.assertEqual(self.client.get(ruta_incorrecta).status_code, 404)
        for nombre in ("../secreto", "/etc/passwd", "x.png"):
            EvidenciaTurno.objects.filter(pk=evidencia.pk).update(nombre_interno=nombre)
            self.assertEqual(self.client.get(self.url + f"{turno.pk}/fotos/{evidencia.pk}/").status_code, 404)

    def test_estado_cerrado_necesario_y_noop_correccion(self):
        turno = self.abrir()
        with self.assertRaises(EstadoIncompatible):
            turnos.revisar_turno(self.obra, turno.pk, {"decision": "VALIDAR", "motivo": "Revisión", "costo_hora_neto": "100.00"}, self.supervisor)
        with self.assertRaises(EstadoIncompatible):
            turnos.corregir_turno(self.obra, turno.pk, {"duracion_ajustada_segundos": 100, "motivo": "Ajuste"}, self.supervisor)
        self.cerrar(turno)
        self.autenticar(self.supervisor)
        self.assertEqual(self.client.post(self.url + f"{turno.pk}/corregir/", {"motivo": "Sin cambio"}, format="json").status_code, 409)
        for campo in ("iniciado_en", "terminado_en", "duracion_segundos", "revisado_por", "estado_revision"):
            self.assertEqual(self.client.post(self.url + f"{turno.pk}/corregir/", {"motivo": "Ajuste", campo: 1}, format="json").status_code, 400)
        self.assertEqual(turno.eventos.count(), 2)

    def test_rollback_revision_y_arranque(self):
        with patch("apps.obras.services_turnos._evento", side_effect=RuntimeError("Fallo")):
            with self.assertRaises(RuntimeError):
                self.abrir()
        self.assertFalse(TurnoObra.objects.exists())
        turno = self.cerrar(self.abrir())
        with patch("apps.obras.services_turnos._evento", side_effect=RuntimeError("Fallo")):
            with self.assertRaises(RuntimeError):
                turnos.revisar_turno(self.obra, turno.pk, {"decision": "VALIDAR", "motivo": "Revisado", "costo_hora_neto": "100.00"}, self.supervisor)
        turno.refresh_from_db()
        self.assertIsNone(turno.costo_hora_neto)
        self.assertEqual(turno.estado_revision, "PENDIENTE_REVISION")
