"""JPEG/PNG/PDF: estructura, límites, normalización y análisis del original/normalizado."""
import hashlib
from io import BytesIO
from pathlib import Path
import re
import struct
import subprocess
import sys
import warnings
import zipfile

from PIL import Image, UnidentifiedImageError
from rest_framework.exceptions import ValidationError

from apps.adjuntos.contenido import _png, _jpeg
from apps.adjuntos.scanner import analizar as clamav_instream
from apps.adjuntos.exceptions import ContenidoRechazado, ScannerNoDisponible
from .exceptions import ArchivoGrande, NoDisponible
from .validaciones import nombre


def analizar(file):
    try:
        clamav_instream(file)
    except ContenidoRechazado:
        raise ValidationError({'archivo': ['Contenido no permitido.']}) from None
    except ScannerNoDisponible:
        raise NoDisponible() from None


def preparar(upload, stage):
    visible = nombre(upload.name)
    digest = hashlib.sha256(); total = 0
    for chunk in upload.chunks(65536):
        total += len(chunk)
        if total > 8*1024*1024:
            raise ArchivoGrande()
        stage.file.write(chunk); digest.update(chunk)
    if not total:
        raise ValidationError({'archivo': ['Archivo vacío.']})
    stage.file.flush(); stage.file.seek(0)
    data = stage.file.read()
    formato = 'PNG' if data.startswith(b'\x89PNG\r\n\x1a\n') else 'JPEG' if data.startswith(b'\xff\xd8\xff') else 'PDF' if data.startswith(b'%PDF-') else None
    extensiones = {'PNG': {'.png'}, 'JPEG': {'.jpg', '.jpeg'}, 'PDF': {'.pdf'}}
    mimes = {'PNG': 'image/png', 'JPEG': 'image/jpeg', 'PDF': 'application/pdf'}
    if formato is None or Path(visible).suffix.lower() not in extensiones[formato]:
        raise ValidationError({'archivo': ['Formato no permitido; solo JPEG, PNG o PDF validados.']})
    if formato != 'PDF' and total > 5*1024*1024:
        raise ArchivoGrande()
    # Analizar bytes originales antes de retirar metadatos, nunca sanitizar malware para aceptarlo.
    analizar(stage.file)
    try:
        if zipfile.is_zipfile(BytesIO(data)):
            raise ValueError()
        if formato == 'PDF':
            if not re.match(rb'%PDF-[12]\.[0-9][\r\n]', data) or not data.rstrip(b'\r\n \t').endswith(b'%%EOF'):
                raise ValueError()
            # Pasar handle ya abierto al inspector acotado, no reabrir ruta mutable.
            handle = stage.file.fileno()
            result = subprocess.run([sys.executable, '-m', 'apps.adjuntos.pdf_guard', f'/proc/self/fd/{handle}'],
                pass_fds=(handle,), stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=8)
            if result.returncode or result.stdout.strip() != b'PDF_VALIDO':
                raise ValueError()
        else:
            (_png if formato == 'PNG' else _jpeg)(data)
            with warnings.catch_warnings():
                warnings.simplefilter('error')
                with Image.open(BytesIO(data)) as im:
                    if im.format != formato or not 1 <= im.width <= 2048 or not 1 <= im.height <= 2048 or getattr(im, 'n_frames', 1) != 1:
                        raise ValueError()
                    im.verify()
                with Image.open(BytesIO(data)) as im:
                    im.load()
                    limpia = Image.new('RGB' if formato == 'JPEG' else 'RGBA', im.size)
                    limpia.paste(im.convert(limpia.mode))
                    stage.file.seek(0); stage.file.truncate()
                    limpia.save(stage.file, format=formato)
            if stage.file.tell() > 5*1024*1024:
                raise ArchivoGrande()
            stage.file.flush(); analizar(stage.file)
    except (ValueError, OSError, UnidentifiedImageError, Image.DecompressionBombError, Warning, SyntaxError, struct.error, subprocess.TimeoutExpired):
        raise ValidationError({'archivo': ['Estructura de archivo no permitida.']}) from None
    stage.file.seek(0)
    publicado = hashlib.sha256(); size = 0
    while chunk := stage.file.read(65536):
        publicado.update(chunk); size += len(chunk)
    stage.file.seek(0)
    return {'nombre': visible, 'mime': mimes[formato], 'tamano_bytes': size, 'sha256': publicado.hexdigest()}, digest.hexdigest()
