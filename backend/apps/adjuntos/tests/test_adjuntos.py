"""QA real aislado: PostgreSQL, Mongo autenticado y clamd INSTREAM."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from io import BytesIO, StringIO
import hashlib
import json
import os
from pathlib import Path
import socket
from tempfile import TemporaryDirectory
from threading import Barrier, Thread
from unittest.mock import patch
from uuid import uuid4
import zipfile

from bson import Int64
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import DatabaseError, close_old_connections, connection, transaction
from django.test import TransactionTestCase, override_settings
from django.utils import timezone
from PIL import Image
from pymongo import MongoClient
from pymongo.errors import OperationFailure
from pypdf import PdfWriter
from rest_framework.test import APIClient

from apps.adjuntos import almacen, metadata, scanner, services
from apps.adjuntos.exceptions import ContenidoRechazado, ScannerNoDisponible
from apps.adjuntos.models import AdjuntoDocumento
from apps.documentos import mongo
from apps.finanzas.tests.base import FinanzasBase
from apps.obras.models import Obra, ObraParticipante
from apps.obras.tests.test_turnos import TurnosBase, foto, png_comprimido
from apps.usuarios.models import Usuario
from apps.usuarios.tokens import AccessToken

BASE = "/api/adjuntos/"
EICAR = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"


def pdf(activo=False, cifrado=False, eicar=False):
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    if activo:
        from pypdf.generic import DictionaryObject, NameObject, TextStringObject
        writer._root_object[NameObject("/OpenAction")] = DictionaryObject({
            NameObject("/S"): NameObject("/JavaScript"), NameObject("/JS"): TextStringObject("app.alert('test')")})
    if cifrado:
        writer.encrypt("qa")
    if eicar:
        from pypdf.generic import DecodedStreamObject, NameObject
        stream = DecodedStreamObject()
        stream.set_data(EICAR)
        writer.pages[0][NameObject("/Contents")] = writer._add_object(stream)
    out = BytesIO()
    writer.write(out)
    return SimpleUploadedFile("documento.pdf", out.getvalue(), content_type="application/pdf")


class AdjuntosBase(TurnosBase, TransactionTestCase):
    def setUp(self):
        self.setUpTestData()
        self.preparar()
        self.temporal = TemporaryDirectory(prefix="adjuntos-caso-qa-")
        self.addCleanup(self.temporal.cleanup)
        conf = override_settings(ADJUNTOS_ROOT=Path(self.temporal.name))
        conf.enable()
        self.addCleanup(conf.disable)
        self.ruta = BASE + f"obras/{self.obra.pk}/"
        self.autenticar(self.supervisor)

    def subir(self, archivo=None, key=None, ruta=None, **extra):
        return self.client.post(ruta or self.ruta, {"archivo": archivo or foto(), **extra},
            format="multipart", HTTP_IDEMPOTENCY_KEY=str(key or uuid4()))

    def aceptado(self, **kwargs):
        response = self.subir(**kwargs)
        self.assertEqual(response.status_code, 201, getattr(response, "data", None))
        return AdjuntoDocumento.objects.get(pk=response.data["id"])

    def descargar(self, adjunto):
        r = self.client.get(BASE+f"{adjunto.pk}/descargar/")
        self.assertEqual(r.status_code, 200, getattr(r, "data", None))
        data = b"".join(r.streaming_content)
        r.close()
        return r, data


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class AdjuntosAPITests(AdjuntosBase):
    def test_contrato_openapi_postman_referencias_y_vocabularios(self):
        schema = json.loads((settings.BASE_DIR/"docs/openapi/SPEC-012B-v1.json").read_text(encoding="utf-8"))
        self.assertEqual(sum(method in {"get", "post", "patch"} for item in schema["paths"].values() for method in item), 8)
        for tipo, nombre in (("RESPALDO_FACTURA", "Factura"), ("INFORME_TECNICO", "Informe")):
            self.assertEqual(set(schema["components"]["schemas"]["Atributos"+nombre]["properties"]), metadata.CLAVES[tipo])
        def revisar(value):
            if isinstance(value, dict):
                if "$ref" in value:
                    target = schema
                    for key in value["$ref"].removeprefix("#/").split("/"):
                        target = target[key]
                for child in value.values():
                    revisar(child)
            elif isinstance(value, list):
                for child in value:
                    revisar(child)
        revisar(schema)
        postman = json.loads((settings.BASE_DIR/"docs/postman/SPEC-012B.postman_collection.json").read_text(encoding="utf-8"))
        self.assertEqual(len(postman["item"]), 8)

    def test_png_jpeg_saneados_hash_y_headers(self):
        for formato, ext in (("PNG", "png"), ("JPEG", "jpg")):
            out = BytesIO()
            exif = Image.Exif(); exif[270] = "dato privado QA"
            Image.new("RGB", (15, 15), "blue").save(out, formato, exif=exif)
            adj = self.aceptado(archivo=SimpleUploadedFile("foto."+ext, out.getvalue(), content_type="image/"+("jpeg" if ext == "jpg" else ext)))
            response, data = self.descargar(adj)
            self.assertEqual(hashlib.sha256(data).hexdigest(), adj.sha256)
            with Image.open(BytesIO(data)) as im:
                self.assertFalse(im.getexif())
            self.assertEqual(response["Cache-Control"], "private, no-store")
            self.assertEqual(response["X-Content-Type-Options"], "nosniff")
            self.assertIn("Authorization", response["Vary"])
            self.assertIn("attachment", response["Content-Disposition"])
            detail = self.client.get(BASE+f"{adj.pk}/")
            self.assertNotIn("sha256", detail.data)
            self.assertNotIn("clave_interna", detail.data)
        listing = self.client.get(self.ruta)
        self.assertEqual(listing.data["count"], 2)
        self.assertEqual(set(listing.data), {"count", "next", "previous", "results"})

    def test_pdf_original_y_replay_sin_scanner(self):
        archivo = pdf(); original = archivo.read(); archivo.seek(0)
        key = uuid4(); adj = self.aceptado(archivo=archivo, key=key)
        self.assertEqual(self.descargar(adj)[1], original)
        with patch("apps.adjuntos.scanner.analizar", side_effect=AssertionError("No escanear replay")):
            r = self.subir(archivo=SimpleUploadedFile("documento.pdf", original, content_type="application/pdf"), key=key)
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["id"], adj.pk)
        self.assertEqual(self.subir(key=key).status_code, 409)
        self.assertEqual(AdjuntoDocumento.objects.count(), 1)

    def test_pdf_activo_cifrado_malformado_y_poliglota(self):
        files = [pdf(activo=True), pdf(cifrado=True), SimpleUploadedFile("x.pdf", b"%PDF-1.7\n%%EOF", content_type="application/pdf")]
        original = pdf().read()
        buffer = BytesIO(original)
        with zipfile.ZipFile(buffer, "a") as z:
            z.writestr("qa.txt", "texto")
        files.append(SimpleUploadedFile("x.pdf", buffer.getvalue()+b"\n%%EOF", content_type="application/pdf"))
        for archivo in files:
            self.assertEqual(self.subir(archivo=archivo).status_code, 422)
        self.assertFalse(AdjuntoDocumento.objects.exists())

    def test_formatos_mime_truncados_y_limites(self):
        for name, content, mime in (("x.svg", b"<svg/>", "image/svg+xml"), ("x.png", b"PK\x03\x04", "image/png"),
            ("x.png", foto().read()[:-3], "image/png"), ("x.jpg", foto().read(), "image/jpeg"),
            ("x.png", foto().read()+b"<html/>", "image/png"), ("x.png", b"", "image/png")):
            r = self.subir(archivo=SimpleUploadedFile(name, content, content_type=mime))
            self.assertEqual(r.status_code, 422, (name, r.data))
        self.assertEqual(self.subir(archivo=png_comprimido(4000, 3001)).status_code, 422)
        for size in (5*1024*1024+1, 8*1024*1024+1):
            self.assertEqual(self.subir(archivo=SimpleUploadedFile("x.png", b"\x89PNG\r\n\x1a\n"+b"x"*(size-8), content_type="image/png")).status_code, 413)
        self.assertFalse(AdjuntoDocumento.objects.exists())

    def test_multipart_estricto_y_idempotency_obligatorio(self):
        self.assertEqual(self.client.post(self.ruta, {"archivo": foto()}, format="multipart").status_code, 400)
        self.assertEqual(self.subir(extra="x").status_code, 400)
        self.assertEqual(self.client.post(self.ruta, {"archivo": [foto(), foto()]}, format="multipart", HTTP_IDEMPOTENCY_KEY=str(uuid4())).status_code, 400)
        for name in ("../x.png", "C:\\x.png", "x\x00.png"):
            raw = b'--qa\r\nContent-Disposition: form-data; name="archivo"; filename="'+name.encode()+b'"\r\nContent-Type: image/png\r\n\r\n'+foto().read()+b'\r\n--qa--\r\n'
            self.assertEqual(self.client.post(self.ruta, raw, content_type="multipart/form-data; boundary=qa", HTTP_IDEMPOTENCY_KEY=str(uuid4())).status_code, 400)
        self.assertEqual(self.client.post(self.ruta, {"archivo": "base64"}, format="json", HTTP_IDEMPOTENCY_KEY=str(uuid4())).status_code, 415)

    def test_scanner_real_eicar_en_pdf_y_sin_fila(self):
        with self.assertRaises(ContenidoRechazado):
            scanner.analizar(BytesIO(EICAR))
        r = self.subir(archivo=pdf(eicar=True))
        self.assertEqual(r.status_code, 422, r.data)
        self.assertFalse(AdjuntoDocumento.objects.exists())
        self.assertEqual(list((settings.ADJUNTOS_ROOT/"staging").iterdir()), [])

    def test_scanner_inaccesible_no_bloquea_descargas(self):
        adj = self.aceptado()
        with override_settings(ADJUNTOS_SCANNER={"host": "127.0.0.1", "puerto": 1, "timeout": 0.2}):
            self.assertEqual(self.subir().status_code, 503)
            self.descargar(adj)
        self.assertEqual(AdjuntoDocumento.objects.count(), 1)

    def test_timeout_real_socket_fail_closed(self):
        from threading import Event
        stop = Event()
        with socket.socket() as server:
            server.bind(("127.0.0.1", 0)); server.listen(); server.settimeout(2)
            def atender():
                try:
                    conn, _ = server.accept()
                except TimeoutError:
                    return
                with conn:
                    stop.wait(2)
            hilo = Thread(target=atender); hilo.start()
            try:
                with override_settings(ADJUNTOS_SCANNER={"host": "127.0.0.1", "puerto": server.getsockname()[1], "timeout": 0.1}):
                    self.assertEqual(self.subir().status_code, 503)
            finally:
                stop.set(); hilo.join(3)
        self.assertFalse(AdjuntoDocumento.objects.exists())

    def test_roles_lectura_head_options_y_subida(self):
        adj = self.aceptado()
        ti = Usuario.objects.create_user(username="ti012b", email="ti012b@example.test", rol="ADMINISTRADOR_TI", is_staff=True, is_superuser=True)
        for actor in (self.gerencia, self.supervisor, self.finanzas, self.tecnico, ti):
            self.autenticar(actor)
            expected = 403 if actor in (self.finanzas, ti) else 200
            for method in ("get", "head", "options"):
                self.assertEqual(getattr(self.client, method)(BASE+f"{adj.pk}/").status_code, expected, (actor.rol, method))
            self.assertEqual(self.client.get(self.ruta).status_code, expected)
            self.assertEqual(self.subir().status_code, 201 if actor in (self.supervisor, self.tecnico) else 403)

    def test_tecnico_desasignado_idor_y_estados(self):
        self.autenticar(self.otro_tecnico)
        key = uuid4(); adj = self.aceptado(key=key)
        from apps.obras import services as obras
        obras.desasignar_participante(self.obra, self.miembro.pk, self.supervisor, "Fin apoyo")
        for suffix in ("", "descargar/", "anotaciones/"):
            self.assertEqual(self.client.get(BASE+f"{adj.pk}/"+suffix).status_code, 404)
        self.assertEqual(self.subir(key=key).status_code, 404)
        self.assertEqual(self.client.patch(BASE+f"{adj.pk}/anotaciones/", {"revision": 0, "descripcion": "Vista"}, format="json").status_code, 404)
        obras.asignar_participante(self.obra, {"tecnico": self.otro_tecnico.pk, "motivo": "Apoyo"}, self.supervisor)
        self.obra.refresh_from_db()
        inicio = self.obra.iniciado_en
        for estado in ("SUSPENDIDA", "FINALIZADA", "CANCELADA", "PLANIFICADA"):
            # Fixture histórica QA; no cambia reglas del servicio de Obras.
            Obra.objects.filter(pk=self.obra.pk).update(estado=estado,
                iniciado_en=None if estado == "PLANIFICADA" else inicio,
                finalizado_en=timezone.now() if estado == "FINALIZADA" else None,
                cancelado_en=timezone.now() if estado == "CANCELADA" else None)
            self.assertEqual(self.subir().status_code, 409)
            self.autenticar(self.supervisor)
            self.assertEqual(self.subir().status_code, 201 if estado in ("SUSPENDIDA", "FINALIZADA") else 409)
            self.autenticar(self.otro_tecnico)

    def test_jwt_expirado_revocado_inactivo_cambio_rol(self):
        self.client.credentials()
        self.assertEqual(self.client.get(self.ruta).status_code, 401)
        token = AccessToken.for_user(self.supervisor)
        token.set_exp(from_time=timezone.now()-timedelta(days=1), lifetime=timedelta(seconds=1))
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual(self.client.get(self.ruta).status_code, 401)
        self.autenticar(self.supervisor)
        Usuario.objects.filter(pk=self.supervisor.pk).update(sesion_version=self.supervisor.sesion_version+1)
        self.assertEqual(self.client.get(self.ruta).status_code, 401)
        self.supervisor.refresh_from_db(); self.autenticar(self.supervisor)
        Usuario.objects.filter(pk=self.supervisor.pk).update(is_active=False)
        self.assertEqual(self.client.get(self.ruta).status_code, 401)
        Usuario.objects.filter(pk=self.supervisor.pk).update(is_active=True, rol="ADMINISTRADOR_TI")
        self.assertEqual(self.client.get(self.ruta).status_code, 403)

    def test_sql_rollback_compensa_y_reintento(self):
        key = uuid4()
        with patch.object(AdjuntoDocumento, "save", side_effect=DatabaseError("QA")):
            self.assertEqual(self.subir(key=key).status_code, 503)
        self.assertFalse(AdjuntoDocumento.objects.exists())
        self.assertEqual(list((settings.ADJUNTOS_ROOT/"archivos").iterdir()), [])
        self.assertEqual(list((settings.ADJUNTOS_ROOT/"staging").iterdir()), [])
        self.aceptado(key=key)

    def test_commit_rechazado_y_commit_ambiguo_con_replay_seguro(self):
        key = uuid4()
        with patch.object(connection, "commit", side_effect=DatabaseError("commit rechazado QA")):
            self.assertEqual(self.subir(key=key).status_code, 503)
        self.assertFalse(AdjuntoDocumento.objects.exists())
        self.assertEqual(list((settings.ADJUNTOS_ROOT/"archivos").iterdir()), [])
        real_commit = connection.commit
        def confirmar_sin_respuesta():
            real_commit()
            raise DatabaseError("confirmación perdida QA")
        with patch.object(connection, "commit", side_effect=confirmar_sin_respuesta):
            self.assertEqual(self.subir(key=key).status_code, 503)
        adj = AdjuntoDocumento.objects.get()
        self.descargar(adj)
        response = self.subir(key=key)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["id"], adj.pk)

    def test_fallo_publicacion_y_symlinks_no_siguen_destino(self):
        with patch("apps.adjuntos.almacen.os.link", side_effect=OSError("disco QA")):
            self.assertEqual(self.subir().status_code, 503)
        self.assertFalse(AdjuntoDocumento.objects.exists())
        with TemporaryDirectory() as otro:
            root = settings.ADJUNTOS_ROOT/"link"
            root.symlink_to(otro, target_is_directory=True)
            with override_settings(ADJUNTOS_ROOT=root/"hijo"):
                self.assertEqual(self.subir().status_code, 503)
            self.assertEqual(list(Path(otro).iterdir()), [])

    def test_archivo_corrupto_faltante_symlink_y_diagnostico_sin_borrar(self):
        adj = self.aceptado()
        path = settings.ADJUNTOS_ROOT/"archivos"/adj.clave_interna.hex
        path.write_bytes(b"alterado")
        self.assertEqual(self.client.get(BASE+f"{adj.pk}/descargar/").status_code, 409)
        path.unlink()
        self.assertEqual(self.client.get(BASE+f"{adj.pk}/descargar/").status_code, 409)
        path.symlink_to("/etc/passwd")
        self.assertEqual(self.client.get(BASE+f"{adj.pk}/descargar/").status_code, 409)
        orphan = path.parent/uuid4().hex; orphan.write_bytes(b"qa")
        out = StringIO(); call_command("diagnosticar_adjuntos", stdout=out)
        self.assertIn('"archivos_huerfanos": 1', out.getvalue())
        self.assertTrue(orphan.exists()); self.assertTrue(path.is_symlink())

    def test_limite_diez_y_concurrencia_misma_key(self):
        key = uuid4(); barrier = Barrier(2)
        def subir_hilo():
            close_old_connections()
            client = APIClient(); client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(self.supervisor)}")
            barrier.wait(timeout=5)
            try:
                r = client.post(self.ruta, {"archivo": foto()}, format="multipart", HTTP_IDEMPOTENCY_KEY=str(key))
                return r.status_code, r.data
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: subir_hilo(), range(2)))
        self.assertEqual(sorted(r[0] for r in results), [200, 201], results)
        self.assertEqual(results[0][1]["id"], results[1][1]["id"])
        for _ in range(9):
            self.aceptado()
        self.assertEqual(self.subir().status_code, 409)
        self.assertEqual(AdjuntoDocumento.objects.count(), 10)
        self.assertEqual(len(list((settings.ADJUNTOS_ROOT/"archivos").iterdir())), 10)

    def test_revalidar_estado_rol_y_miembro_despues_del_scanner_fuera_locks(self):
        real = scanner.analizar
        def escanear_y_suspender(file):
            self.assertFalse(connection.in_atomic_block)
            real(file)
            Obra.objects.filter(pk=self.obra.pk).update(estado="SUSPENDIDA")
        self.autenticar(self.tecnico)
        with patch("apps.adjuntos.scanner.analizar", side_effect=escanear_y_suspender):
            self.assertEqual(self.subir().status_code, 409)
        Obra.objects.filter(pk=self.obra.pk).update(estado="EN_PROCESO")
        def escanear_y_desasignar(file):
            real(file)
            from apps.obras import services as obras
            obras.desasignar_participante(self.obra, self.miembro.pk, self.supervisor, "Fin apoyo")
        self.autenticar(self.otro_tecnico)
        with patch("apps.adjuntos.scanner.analizar", side_effect=escanear_y_desasignar):
            self.assertEqual(self.subir().status_code, 404)
        self.assertFalse(AdjuntoDocumento.objects.exists())

    def test_idor_otra_obra_key_otro_actor_y_nombre_distinto(self):
        adj = self.aceptado(); key = adj.clave_idempotencia
        self.autenticar(self.tecnico)
        self.assertEqual(self.subir(key=key).status_code, 409)
        self.autenticar(self.supervisor)
        self.assertEqual(self.subir(key=key, nombre_visible="otro.png").status_code, 409)
        otra = self.otra_obra()
        self.assertEqual(self.subir(key=key, ruta=BASE+f"obras/{otra.pk}/").status_code, 409)
        self.autenticar(self.otro_tecnico)
        for method in ("get", "head", "options"):
            self.assertEqual(getattr(self.client, method)(BASE+f"obras/{otra.pk}/").status_code, 404)

    def test_query_numeros_paginacion_y_sin_mongo_en_sql(self):
        adj = self.aceptado()
        with patch("apps.adjuntos.metadata.coleccion", side_effect=AssertionError("SQL no consulta Mongo")):
            self.descargar(adj)
            self.assertEqual(self.client.get(self.ruta).status_code, 200)
        for query in ("page=0", "page=01", "page=2", "page=1&page=1", "format=json", "extra=1"):
            self.assertEqual(self.client.get(self.ruta+"?"+query).status_code, 400)
        for ident in ("0", "01", "-1", "9223372036854775808", "a"):
            self.assertEqual(self.client.get(BASE+ident+"/").status_code, 400)

    def test_checks_sql_y_modelo_inmutable(self):
        from django.core.exceptions import ValidationError
        from django.db import IntegrityError
        adj = self.aceptado()
        for field, value in (("tamano_bytes", 0), ("estado", "PENDIENTE"), ("sha256", "x"), ("tipo", "OTRO"), ("nombre_visible", "../x.png")):
            with self.assertRaises(IntegrityError), transaction.atomic():
                with connection.cursor() as cur:
                    cur.execute(f'UPDATE adjuntos_adjuntodocumento SET "{field}"=%s WHERE id=%s', [value, adj.pk])
        with self.assertRaises(ValidationError):
            adj.save()
        with self.assertRaises(ValidationError):
            AdjuntoDocumento.objects.filter(pk=adj.pk).delete()

    def test_limite_pixeles_exacto_y_no_clobber(self):
        self.aceptado(archivo=png_comprimido(4000, 3000))
        adj = self.aceptado()
        path = settings.ADJUNTOS_ROOT/"archivos"/adj.clave_interna.hex
        original = path.read_bytes()
        with patch("apps.adjuntos.services.uuid4", return_value=adj.clave_interna):
            self.assertEqual(self.subir().status_code, 503)
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(AdjuntoDocumento.objects.count(), 2)

    def test_concurrencia_ultimo_cupo_destino(self):
        for _ in range(9):
            self.aceptado()
        barrier = Barrier(2)
        def cargar(_):
            close_old_connections()
            try:
                client = APIClient(); client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(self.supervisor)}")
                barrier.wait(timeout=5)
                return client.post(self.ruta, {"archivo": foto()}, format="multipart", HTTP_IDEMPOTENCY_KEY=str(uuid4())).status_code
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(cargar, range(2)))
        self.assertEqual(sorted(results), [201, 409])
        self.assertEqual(AdjuntoDocumento.objects.count(), 10)


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class AdjuntosMongoTests(AdjuntosBase):
    def setUp(self):
        super().setUp()
        conf = settings.DOCUMENTOS_MONGO
        assert conf["db"] == "fyag_documentos_test"
        self.admin = MongoClient(conf["host"], conf["puerto"], username=os.environ["FYAG_MONGO_TEST_ROOT_USER"],
            password=os.environ["FYAG_MONGO_TEST_ROOT_PASSWORD"], authSource="admin", tz_aware=True)
        self.addCleanup(self.admin.close)
        self.col = self.admin[conf["db"]][metadata.COL]
        self.col.delete_many({}); self.addCleanup(lambda: self.col.delete_many({}))
        self.adj = self.aceptado()
        self.notas = BASE+f"{self.adj.pk}/anotaciones/"

    def reconciliar(self):
        call_command("reconciliar_adjuntos_mongodb", stdout=StringIO())

    def test_pendiente_reconciliacion_repetida_cas_y_vocabulario(self):
        self.assertEqual(self.client.get(self.notas).status_code, 409)
        self.reconciliar()
        self.assertEqual(self.client.get(self.notas).status_code, 200)
        r = self.client.patch(self.notas, {"revision": 0, "descripcion": "Vista frontal", "atributos": {"vista": "Frontal"}}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.reconciliar(); self.reconciliar()
        self.assertEqual(self.client.get(self.notas).data["descripcion"], "Vista frontal")
        self.assertEqual(self.client.patch(self.notas, {"revision": 0, "descripcion": "Otro"}, format="json").status_code, 409)
        self.assertEqual(self.client.patch(self.notas, {"revision": 1, "atributos": {"folio": "123"}}, format="json").status_code, 400)
        doc = self.col.find_one()
        for key in ("adjunto_id", "destino_id", "tamano_bytes", "anotado_por_id"):
            self.assertIsInstance(doc[key], Int64)
        self.assertNotIn("nombre_visible", doc)

    def test_bson_estricto_minimo_privilegio_y_012a_intacta(self):
        metadata.coleccion(); self.reconciliar()
        doc = self.col.find_one()
        for changes in ({"extra": 1}, {"adjunto_id": 1}, {"atributos": {"$set": "x"}}, {"atributos": {"caras": "x"}}, {"revision": -1}):
            with self.assertRaises(OperationFailure):
                self.col.replace_one({"_id": doc["_id"]}, {**doc, **changes})
        app = metadata.coleccion()
        with self.assertRaises(OperationFailure):
            app.delete_one({"_id": doc["_id"]})
        self.assertEqual(mongo.coleccion().name, "documentos_metadata")
        self.autenticar(self.gerencia)
        self.assertEqual(self.client.get(self.notas).status_code, 200)
        self.assertEqual(self.client.patch(self.notas, {"revision": 0, "descripcion": "Vista"}, format="json").status_code, 403)

    def test_mongo_inaccesible_subida_listado_descarga_y_recuperacion(self):
        with override_settings(DOCUMENTOS_MONGO={**settings.DOCUMENTOS_MONGO, "host": "127.0.0.1", "puerto": 1}):
            self.assertEqual(self.client.get(self.notas).status_code, 503)
            self.assertEqual(self.client.get(self.ruta).status_code, 200)
            self.descargar(self.adj)
            self.aceptado()
        self.reconciliar()
        self.assertEqual(self.col.count_documents({}), 2)
        self.assertEqual(self.client.get(self.notas).status_code, 200)

    def test_cas_concurrente_un_solo_ganador(self):
        self.reconciliar(); barrier = Barrier(2)
        def editar(text):
            close_old_connections()
            try:
                client = APIClient(); client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(self.supervisor)}")
                barrier.wait(timeout=5)
                return client.patch(self.notas, {"revision": 0, "descripcion": text}, format="json").status_code
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(editar, ["Antes", "Después"]))
        self.assertEqual(sorted(results), [200, 409])

    def test_reconciliacion_commit_fuera_de_orden_y_tecnicos_sin_notas_perdidas(self):
        # El PK menor aparece después de una pasada que ya observó PK mayor.
        payload = {field.attname: getattr(self.adj, field.attname) for field in AdjuntoDocumento._meta.fields if field.name not in {"id", "registrado_en"}}
        payload.update(clave_interna=uuid4(), clave_idempotencia=uuid4())
        mayor = AdjuntoDocumento.objects.create(id=self.adj.pk+100, **payload)
        with almacen.Staging() as stage:
            with almacen.copia_verificada(self.adj) as source:
                stage.file.write(source.read())
            stage.publicar(mayor.clave_interna)
        self.reconciliar()
        self.client.patch(self.notas, {"revision": 0, "descripcion": "Vista lateral"}, format="json")
        payload.update(clave_interna=uuid4(), clave_idempotencia=uuid4())
        menor = AdjuntoDocumento.objects.create(id=self.adj.pk+50, **payload)
        with almacen.Staging() as stage:
            with almacen.copia_verificada(self.adj) as source:
                stage.file.write(source.read())
            stage.publicar(menor.clave_interna)
        self.reconciliar(); self.reconciliar()
        self.assertIsNotNone(self.col.find_one({"adjunto_id": menor.pk}))
        self.assertIsNotNone(self.col.find_one({"adjunto_id": mayor.pk}))
        self.assertEqual(self.col.find_one({"adjunto_id": self.adj.pk})["descripcion"], "Vista lateral")

    def test_patch_roles_012b_y_datos_tecnicos_sensibles_rechazados(self):
        self.reconciliar()
        for data in ({"revision": 0, "sha256": "x", "descripcion": "Vista"}, {"revision": True, "descripcion": "Vista"},
            {"revision": 0, "descripcion": "<b>Vista</b>"}, {"revision": 0, "descripcion": "https://example.test"},
            {"revision": 0, "descripcion": "2026-11-13"}, {"revision": 0, "descripcion": "USD 120"},
            {"revision": 0, "etiquetas": ["uno", "UNO"]}, {"revision": 0, "atributos": {"vista": {"$set": "x"}}}):
            self.assertEqual(self.client.patch(self.notas, data, format="json").status_code, 400)
        self.autenticar(self.tecnico)
        self.assertEqual(self.client.patch(self.notas, {"revision": 0, "descripcion": "Vista"}, format="json").status_code, 200)
        self.autenticar(self.finanzas)
        self.assertEqual(self.client.patch(self.notas, {"revision": 1, "descripcion": "Vista"}, format="json").status_code, 403)

    def test_mongo_fuera_atomic_y_validador_b_no_afecta_012a(self):
        from apps.documentos.exceptions import MongoNoDisponible
        with transaction.atomic(), self.assertRaises(MongoNoDisponible):
            metadata.sincronizar(self.adj)
        db = self.col.database
        db.command({"collMod": metadata.COL, "validationLevel": "moderate"})
        try:
            with self.assertRaises(MongoNoDisponible):
                metadata.coleccion()
            self.assertEqual(mongo.coleccion().name, "documentos_metadata")
            self.assertEqual(self.client.get(self.ruta).status_code, 200)
            self.descargar(self.adj)
        finally:
            db.command({"collMod": metadata.COL, "validationLevel": "strict"})


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class AdjuntosFinanzasTests(FinanzasBase, AdjuntosBase):
    def setUp(self):
        super().setUp()
        # Preparar la factura usando exclusivamente los servicios financieros vigentes.
        self.items(self.presupuesto); self.completa(); self.finalizar()
        self.autenticar(self.finanzas); self.documentos_url = "/api/finanzas/documentos/"
        r = self.registrar(); self.assertEqual(r.status_code, 201, r.data)
        self.doc_id = r.data["id"]
        self.factura = BASE+f"documentos-cobro/{self.doc_id}/"

    def test_factura_pdf_roles_reversion_historica_sin_mutar_importes(self):
        from apps.finanzas.models import DocumentoCobro
        antes = DocumentoCobro.objects.values().get(pk=self.doc_id)
        key = uuid4(); archivo = pdf(); original = archivo.read(); archivo.seek(0)
        adj = self.aceptado(archivo=archivo, key=key, ruta=self.factura)
        self.assertEqual(DocumentoCobro.objects.values().get(pk=self.doc_id), antes)
        for actor in (self.gerencia, self.supervisor, self.tecnico, self.finanzas):
            self.autenticar(actor)
            self.assertEqual(self.client.get(self.factura).status_code, 200 if actor in (self.gerencia, self.finanzas) else 403)
        self.autenticar(self.finanzas)
        r = self.client.post(f"/api/finanzas/documentos/{self.doc_id}/revertir/", {"motivo": "Corrección", "referencia_rectificacion_externa": "Nota externa"}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.descargar(adj)
        self.assertEqual(self.subir(archivo=pdf(), ruta=self.factura).status_code, 409)
        self.assertEqual(self.subir(archivo=SimpleUploadedFile("documento.pdf", original, content_type="application/pdf"), key=key, ruta=self.factura).status_code, 200)
