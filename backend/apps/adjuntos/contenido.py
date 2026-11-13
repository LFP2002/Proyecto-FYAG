import hashlib
from io import BytesIO
from pathlib import Path
import re
import struct
import subprocess
import sys
import warnings
import zlib
import zipfile

from django.conf import settings
from PIL import Image, UnidentifiedImageError

from .exceptions import ArchivoGrande, ContenidoRechazado

MIMES = {"PDF": "application/pdf", "PNG": "image/png", "JPEG": "image/jpeg"}
EXTENSIONES = {"PDF": {".pdf"}, "PNG": {".png"}, "JPEG": {".jpg", ".jpeg"}}


def _png(data):
    pos = 8
    while pos + 12 <= len(data):
        size = struct.unpack("!I", data[pos:pos+4])[0]
        tipo = data[pos+4:pos+8]
        end = pos + 12 + size
        if end > len(data) or zlib.crc32(data[pos+4:pos+8+size]) != struct.unpack("!I", data[pos+8+size:end])[0]:
            raise ValueError()
        if tipo == b"IEND":
            if size or end != len(data):
                raise ValueError()
            return
        if tipo not in {b"IHDR", b"PLTE", b"IDAT", b"tRNS", b"cHRM", b"gAMA", b"iCCP", b"sRGB", b"sBIT", b"bKGD", b"hIST", b"pHYs", b"sPLT", b"tIME", b"tEXt", b"zTXt", b"iTXt", b"eXIf"}:
            raise ValueError()
        pos = end
    raise ValueError()


def _jpeg(data):
    pos = 2
    scan = False
    while pos < len(data):
        if data[pos] != 255:
            if not scan:
                raise ValueError()
            pos += 1
            continue
        while pos < len(data) and data[pos] == 255:
            pos += 1
        if pos >= len(data):
            raise ValueError()
        marker = data[pos]; pos += 1
        if scan and (marker == 0 or 0xD0 <= marker <= 0xD7):
            continue
        if marker == 0xD9:
            if pos != len(data):
                raise ValueError()
            return
        if marker in (0, 0xD8) or pos + 2 > len(data):
            raise ValueError()
        length = int.from_bytes(data[pos:pos+2], "big")
        if length < 2 or pos + length > len(data):
            raise ValueError()
        pos += length
        scan = marker == 0xDA
    raise ValueError()


def preparar(upload, stage):
    raw_hash = hashlib.sha256()
    total = 0
    for chunk in upload.chunks(65536):
        total += len(chunk)
        if total > 8*1024*1024:
            raise ArchivoGrande()
        stage.file.write(chunk)
        raw_hash.update(chunk)
    if not total:
        raise ContenidoRechazado()
    stage.file.seek(0)
    header = stage.file.read(8)
    formato = "PDF" if header.startswith(b"%PDF-") else "PNG" if header == b"\x89PNG\r\n\x1a\n" else "JPEG" if header.startswith(b"\xff\xd8\xff") else None
    if formato is None or upload.content_type not in {MIMES[formato], "application/octet-stream"} or Path(upload.name).suffix.lower() not in EXTENSIONES[formato]:
        raise ContenidoRechazado()
    if formato == "PDF":
        stage.file.seek(0)
        data = stage.file.read()
        if not re.match(rb"%PDF-[12]\.[0-9][\r\n]", data) or not data.rstrip(b"\r\n \t").endswith(b"%%EOF") or zipfile.is_zipfile(BytesIO(data)):
            raise ContenidoRechazado()
        stage.file.flush()
        path = str(settings.ADJUNTOS_ROOT / "staging" / stage.nombre)
        try:
            result = subprocess.run([sys.executable, "-m", "apps.adjuntos.pdf_guard", path], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=8)
            if result.returncode or result.stdout.strip() != b"PDF_VALIDO":
                raise ContenidoRechazado()
        except (subprocess.TimeoutExpired, OSError):
            raise ContenidoRechazado() from None
    else:
        if total > 5*1024*1024:
            raise ArchivoGrande()
        stage.file.seek(0)
        data = stage.file.read()
        try:
            if zipfile.is_zipfile(BytesIO(data)):
                raise ValueError()
            (_png if formato == "PNG" else _jpeg)(data)
            with warnings.catch_warnings():
                warnings.simplefilter("error")
                with Image.open(BytesIO(data)) as im:
                    if im.format != formato or im.width * im.height > 12_000_000 or getattr(im, "n_frames", 1) != 1:
                        raise ValueError()
                    im.verify()
                with Image.open(BytesIO(data)) as im:
                    im.load()
                    limpia = Image.new("RGB" if formato == "JPEG" else "RGBA", im.size)
                    limpia.paste(im.convert(limpia.mode))
                    stage.file.seek(0); stage.file.truncate()
                    limpia.save(stage.file, format=formato)
        except (ValueError, OSError, UnidentifiedImageError, Warning, SyntaxError, struct.error):
            raise ContenidoRechazado() from None
        if stage.file.tell() > 5*1024*1024:
            raise ArchivoGrande()
    stage.file.flush()
    stage.file.seek(0)
    digest = hashlib.sha256()
    size = 0
    while chunk := stage.file.read(65536):
        digest.update(chunk); size += len(chunk)
    stage.file.seek(0)
    return MIMES[formato], size, digest.hexdigest(), raw_hash.hexdigest()
