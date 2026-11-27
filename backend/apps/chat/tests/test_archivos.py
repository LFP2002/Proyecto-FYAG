from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO, StringIO
import os
import struct
import zlib
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4
from threading import Event, current_thread

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import connection, transaction, IntegrityError, close_old_connections
from django.test import TransactionTestCase, override_settings
from django.utils import timezone
from PIL import Image, PngImagePlugin
from reportlab.pdfgen.canvas import Canvas
from rest_framework.exceptions import APIException

from apps.chat import almacen, services
from apps.chat.exceptions import NoDisponible
from apps.chat.models import ArchivoChat as Archivo, MensajeChat as Mensaje, ActoChat
from apps.chat.purga import purgar
from .base import ChatBase, URL, imagen


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class ArchivosTests(ChatBase, TransactionTestCase):
    def setUp(self):
        self.preparar()
        self.root = Path(self.storage().name)
        self.conv = self.directa()

    def bytes_publicados(self):
        path = self.root/'archivos'
        return list(path.iterdir()) if path.exists() else []

    def test_solo_archivo_descarga_privada_integridad_y_no_metadatos_internos(self):
        mensaje, nuevo = self.subir(self.conv)
        self.assertTrue(nuevo)
        self.assertEqual(mensaje.texto, '')
        row = Archivo.objects.get(mensaje=mensaje)
        r = self.client.get(f'{URL}archivos/{row.pk}/descargar/')
        self.assertEqual(r.status_code, 200)
        data = b''.join(r.streaming_content); r.close()
        self.assertTrue(data.startswith(b'\x89PNG'))
        self.assertIn('attachment', r['Content-Disposition'])
        self.assertEqual(r['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(r['Cache-Control'], 'private, no-store')
        metadata = self.client.get(f'{URL}conversaciones/{self.conv.pk}/mensajes/').data['results'][0]['archivo']
        self.assertEqual(set(metadata), {'id', 'nombre', 'mime', 'tamano_bytes'})
        self.autenticar(self.ajeno)
        self.assertEqual(self.client.get(f'{URL}archivos/{row.pk}/descargar/').status_code, 404)

    def test_multipart_texto_archivo_y_replay_no_duplica_fichero(self):
        key = str(uuid4())
        ruta = f'{URL}conversaciones/{self.conv.pk}/archivos/'
        with patch('apps.chat.archivos.analizar'):
            r = self.client.post(ruta, {'archivo': imagen(), 'texto': ' Imagen QA '}, format='multipart', HTTP_IDEMPOTENCY_KEY=key)
            self.assertEqual(r.status_code, 201, r.data)
            replay = self.client.post(ruta, {'archivo': imagen(), 'texto': 'Imagen QA'}, format='multipart', HTTP_IDEMPOTENCY_KEY=key)
            self.assertEqual(replay.status_code, 200, replay.data)
            self.assertEqual(r.data, replay.data)
            conflicto = self.client.post(ruta, {'archivo': imagen(), 'texto': 'Otra carga'}, format='multipart', HTTP_IDEMPOTENCY_KEY=key)
            self.assertEqual(conflicto.status_code, 409)
        self.assertEqual(len(self.bytes_publicados()), 1)
        self.assertEqual(Archivo.objects.filter(mensaje__conversacion=self.conv).count(), 1)
        self.assertFalse(Archivo.objects.filter(estado='RESERVADO').exists())

    def test_escaneo_indisponible_falla_cerrado_sin_publicacion(self):
        with patch('apps.chat.archivos.analizar', side_effect=NoDisponible()):
            with self.assertRaises(NoDisponible):
                services.publicar_archivo(self.conv.pk, {'archivo': imagen()}, str(uuid4()), self.actor)
        self.assertFalse(Mensaje.objects.filter(conversacion=self.conv).exists())
        self.assertEqual(self.bytes_publicados(), [])
        self.assertFalse(Archivo.objects.exists())

    def test_fallo_publicacion_compensa_y_fallo_retiro_conserva_recibo(self):
        with patch.object(almacen.Staging, 'publicar', side_effect=NoDisponible()):
            with self.assertRaises(NoDisponible):
                self.subir(self.conv)
        self.assertFalse(Mensaje.objects.filter(conversacion=self.conv).exists())
        self.assertEqual(self.bytes_publicados(), [])
        with patch('apps.chat.archivos.analizar', side_effect=NoDisponible()), patch('apps.chat.almacen.retirar', side_effect=NoDisponible()):
            with self.assertRaises(NoDisponible):
                services.publicar_archivo(self.conv.pk, {'archivo': imagen()}, str(uuid4()), self.actor)
        self.assertTrue(Archivo.objects.filter(estado='RETIRAR').exists())
        purgar()
        self.assertFalse(Archivo.objects.filter(estado='RETIRAR').exists())

    def test_commit_falla_tras_publicar_compensa_objeto_sin_huerfano(self):
        # Provocar fallo diferido real: recibo no existe al confirmar mensaje.
        original = services.Acto.objects.create
        def fallar(**kwargs):
            if kwargs.get('accion') == 'MENSAJE':
                return None
            return original(**kwargs)
        with patch.object(services.Acto.objects, 'create', side_effect=fallar):
            with self.assertRaises(IntegrityError):
                self.subir(self.conv)
        self.assertEqual(self.bytes_publicados(), [])
        self.assertFalse(Mensaje.objects.filter(conversacion=self.conv).exists())

    def test_limpieza_staging_fallida_no_falsea_commit_confirmado(self):
        original = almacen.retirar
        def fallo_stage(key, *, publicado=True):
            if not publicado:
                raise NoDisponible()
            return original(key, publicado=publicado)
        with patch('apps.chat.almacen.retirar', side_effect=fallo_stage):
            m, nuevo = self.subir(self.conv)
        self.assertTrue(nuevo)
        self.assertTrue(Mensaje.objects.filter(pk=m.pk).exists())
        self.assertTrue(list((self.root/'staging').iterdir()))
        purgar()
        self.assertFalse(list((self.root/'staging').iterdir()))
        self.assertEqual(len(self.bytes_publicados()), 1)

    def test_imagen_estatica_maximo2048_y_sin_metadata(self):
        data = BytesIO(); meta = PngImagePlugin.PngInfo(); meta.add_text('comentario', 'dato privado')
        Image.new('RGB', (100, 50)).save(data, format='PNG', pnginfo=meta)
        m, _ = self.subir(self.conv, upload=SimpleUploadedFile('limpia.png', data.getvalue()))
        row = Archivo.objects.get(mensaje=m)
        with Image.open(self.root/'archivos'/row.clave_interna.hex) as im:
            self.assertEqual(im.size, (100, 50))
            self.assertNotIn('comentario', im.info)
        with self.assertRaises(APIException):
            self.subir(self.conv, upload=imagen(size=(2049, 1)))

    def test_formatos_corruptos_poliglotas_animados_y_ooxml_denegados(self):
        archivos = [SimpleUploadedFile('falso.png', b'not an image'),
                    SimpleUploadedFile('falso.png', imagen().read()+b'<script>'),
                    SimpleUploadedFile('x.docx', b'PK\x03\x04no validacion segura'),
                    SimpleUploadedFile('x.xlsx', b'PK\x03\x04no validacion segura'),
                    SimpleUploadedFile('x.svg', b'<svg/>'),
                    SimpleUploadedFile('x.pdf', b'%PDF-1.7\ncorrupto\n%%EOF')]
        data = BytesIO(); Image.new('RGB', (2, 2)).save(data, format='PNG', save_all=True, append_images=[Image.new('RGB', (2, 2), 'red')])
        archivos.append(SimpleUploadedFile('animado.png', data.getvalue()))
        for upload in archivos:
            with self.assertRaises(APIException):
                self.subir(self.conv, upload=upload)
        self.assertEqual(self.bytes_publicados(), [])

    def test_tamano_excesivo_y_multipart_cerrado(self):
        ruta = f'{URL}conversaciones/{self.conv.pk}/archivos/'
        r = self.client.post(ruta, {'archivo': SimpleUploadedFile('grande.pdf', b'%PDF-1.7\n'+b'x'*(8*1024*1024))}, format='multipart', HTTP_IDEMPOTENCY_KEY=str(uuid4()))
        self.assertEqual(r.status_code, 413, r.data)
        for extra in ['autor', 'clave_idempotencia', 'nombre_visible']:
            r = self.client.post(ruta, {'archivo': imagen(), extra: 'x'}, format='multipart', HTTP_IDEMPOTENCY_KEY=str(uuid4()))
            self.assertEqual(r.status_code, 400, r.data)
        self.assertEqual(self.client.post(ruta, {'archivo': imagen()}, format='multipart').status_code, 400)

    def test_integridad_y_symlinks_descarga_fallan_cerrado(self):
        m, _ = self.subir(self.conv)
        row = Archivo.objects.get(mensaje=m)
        path = self.root/'archivos'/row.clave_interna.hex
        path.write_bytes(b'alterado')
        self.assertEqual(self.client.get(f'{URL}archivos/{row.pk}/descargar/').status_code, 503)
        path.unlink()
        ajeno = self.root/'secreto'; ajeno.write_bytes(b'no exponer')
        path.symlink_to(ajeno)
        self.assertEqual(self.client.get(f'{URL}archivos/{row.pk}/descargar/').status_code, 503)
        self.assertEqual(ajeno.read_bytes(), b'no exponer')

    def test_symlink_raiz_no_se_sigue(self):
        target = self.root/'target'; target.mkdir()
        link = self.root/'link'; link.symlink_to(target, target_is_directory=True)
        with override_settings(CHAT_ARCHIVOS_ROOT=link):
            with self.assertRaises(NoDisponible):
                self.subir(self.conv)
        self.assertEqual(list(target.iterdir()), [])

    def test_expirado_invisible_antes_de_purga_y_replay_no_republica(self):
        key = str(uuid4())
        viejo = timezone.now()-timedelta(days=31)
        with patch('apps.chat.services.timezone.now', return_value=viejo):
            m, _ = self.subir(self.conv, key=key)
        row = Archivo.objects.get(mensaje=m)
        self.assertEqual(self.client.get(f'{URL}archivos/{row.pk}/descargar/').status_code, 404)
        self.assertEqual(self.client.get(f'{URL}conversaciones/{self.conv.pk}/mensajes/').data['results'], [])
        self.assertEqual(len(self.bytes_publicados()), 1)
        conteo = purgar(dry_run=True)
        self.assertEqual(conteo['registros']['mensajes']['identificados'], 1)
        self.assertTrue(Mensaje.objects.filter(pk=m.pk).exists())
        purgar(); purgar()
        self.assertFalse(Mensaje.objects.filter(pk=m.pk).exists())
        self.assertEqual(self.bytes_publicados(), [])
        acto = ActoChat.objects.get(autor=self.actor, accion='MENSAJE', clave=key)
        self.assertTrue(acto.caducado)
        self.assertEqual(acto.huella, '')
        self.assertIsNone(acto.mensaje_id)
        with self.assertRaises(APIException) as error:
            self.subir(self.conv, key=key)
        self.assertEqual(error.exception.status_code, 409)

    def test_purga_fallo_fisico_reintenta_y_no_toca_vigentes_otros_almacenes(self):
        with patch('apps.chat.services.timezone.now', return_value=timezone.now()-timedelta(days=31)):
            m, _ = self.subir(self.conv)
        vigente, _ = self.subir(self.conv)
        fuera = self.root/'otros'; fuera.mkdir(); (fuera/'evidencia').write_bytes(b'no borrar')
        with patch('apps.chat.almacen.retirar', side_effect=NoDisponible()):
            self.assertGreater(purgar()['registros']['retiros']['fallidos'], 0)
        self.assertFalse(Mensaje.objects.filter(pk=m.pk).exists())
        self.assertTrue(Archivo.objects.filter(estado='RETIRAR').exists())
        purgar()
        self.assertFalse(Archivo.objects.filter(estado='RETIRAR').exists())
        self.assertTrue(Archivo.objects.filter(mensaje=vigente).exists())
        self.assertEqual((fuera/'evidencia').read_bytes(), b'no borrar')
        self.assertEqual(len(self.bytes_publicados()), 1)

    def test_reserva_abandonada_recuperable_tras_interrupcion(self):
        row = Archivo.objects.create(creado_en=timezone.now()-timedelta(hours=2))
        with almacen.Staging(row.clave_interna) as stage:
            stage.file.write(b'archivo interrumpido'); stage.publicar()
        purgar()
        self.assertFalse(Archivo.objects.filter(pk=row.pk).exists())
        self.assertEqual(self.bytes_publicados(), [])

    def test_comando_dry_run_y_once(self):
        out = StringIO()
        call_command('purgar_chat', '--dry-run', stdout=out)
        self.assertIn('mensajes', out.getvalue())
        call_command('purgar_chat', '--once', stdout=StringIO())

    def test_clamav_real_png_y_pdf_validos(self):
        m, _ = self.subir(self.conv, real=True)
        self.assertTrue(Archivo.objects.filter(mensaje=m).exists())
        data = BytesIO(); canvas = Canvas(data); canvas.drawString(20, 30, 'Chat QA'); canvas.save()
        m, _ = self.subir(self.conv, real=True, upload=SimpleUploadedFile('documento.pdf', data.getvalue(), content_type='image/png'))
        self.assertEqual(Archivo.objects.get(mensaje=m).mime, 'application/pdf')  # MIME detectado, no declarado.

    def test_clamav_real_eicar_no_publica(self):
        eicar = b'X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*'
        upload = SimpleUploadedFile('eicar.pdf', b'%PDF-1.7\n'+eicar+b'\n%%EOF')
        with self.assertRaises(APIException) as error:
            self.subir(self.conv, real=True, upload=upload)
        self.assertEqual(error.exception.status_code, 400)
        self.assertEqual(self.bytes_publicados(), [])

    def test_clamav_inaccesible_fail_closed_real(self):
        with override_settings(ADJUNTOS_SCANNER={'host': '127.0.0.1', 'puerto': 1, 'timeout': 1}):
            with self.assertRaises(NoDisponible):
                self.subir(self.conv, real=True)
        self.assertEqual(self.bytes_publicados(), [])

    def test_pdf_cifrado_y_activo_denegados(self):
        from pypdf import PdfWriter
        from pypdf.generic import NameObject, DictionaryObject, TextStringObject
        for activo in [False, True]:
            writer = PdfWriter(); writer.add_blank_page(width=100, height=100)
            if activo:
                writer._root_object.update({NameObject('/OpenAction'): DictionaryObject({NameObject('/S'): NameObject('/JavaScript'), NameObject('/JS'): TextStringObject('app.alert("no ejecutar")')})})
            else:
                writer.encrypt('secreto-qa')
            data = BytesIO(); writer.write(data)
            with self.assertRaises(APIException) as error:
                self.subir(self.conv, upload=SimpleUploadedFile('rechazado.pdf', data.getvalue()))
            self.assertEqual(error.exception.status_code, 400)

    def test_imagen_bomba_sin_descomprimir_no_publica(self):
        def chunk(tipo, data):
            return struct.pack('!I', len(data))+tipo+data+struct.pack('!I', zlib.crc32(tipo+data))
        data = b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR', struct.pack('!IIBBBBB', 100000, 100000, 8, 2, 0, 0, 0))+chunk(b'IDAT', zlib.compress(b'\x00'))+chunk(b'IEND', b'')
        with self.assertRaises(APIException):
            self.subir(self.conv, upload=SimpleUploadedFile('bomba.png', data))
        self.assertEqual(self.bytes_publicados(), [])

    def test_descarga_iniciada_vigente_y_purga_concurrente_skip_locked(self):
        real_now = timezone.now
        creado = real_now()-timedelta(days=31)
        with patch('apps.chat.services.timezone.now', return_value=creado):
            m, _ = self.subir(self.conv)
        row = Archivo.objects.get(mensaje=m)
        ready, release = Event(), Event()
        def clock():
            return creado+timedelta(days=1) if current_thread().name.startswith('chat-descarga') else real_now()
        def descargar():
            close_old_connections()
            try:
                with transaction.atomic():
                    _, copia = services.descargar(row.pk, self.actor)
                    ready.set()
                    if not release.wait(10):
                        copia.close(); raise AssertionError('No se liberó descarga')
                return copia
            finally:
                connection.close()
        with patch('apps.chat.services.timezone.now', side_effect=clock), ThreadPoolExecutor(max_workers=1, thread_name_prefix='chat-descarga') as pool:
            future = pool.submit(descargar)
            try:
                self.assertTrue(ready.wait(10))
                purgar()  # Conversación bloqueada: se omite, no se rompe descarga.
                self.assertTrue(Mensaje.objects.filter(pk=m.pk).exists())
            finally:
                release.set()
            copia = future.result(timeout=15)
        try:
            purgar()
            self.assertFalse(Mensaje.objects.filter(pk=m.pk).exists())
            self.assertEqual(self.bytes_publicados(), [])
            self.assertTrue(copia.read().startswith(b'\x89PNG'))
        finally:
            copia.close()
