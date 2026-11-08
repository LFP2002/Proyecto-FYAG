"""Archivos privados locales; nunca se publican mediante MEDIA_URL."""
from io import BytesIO
from pathlib import Path
import hashlib
import re
import warnings
from uuid import uuid4

from django.conf import settings
from PIL import Image, UnidentifiedImageError

from .exceptions import DatosInvalidos

MAX_BYTES = 5 * 1024 * 1024
MAX_PIXELES = 12_000_000
FORMATOS = {"JPEG": ("jpg", "image/jpeg"), "PNG": ("png", "image/png"), "WEBP": ("webp", "image/webp")}


def _validar_dimensiones(imagen):
    if imagen.width * imagen.height > MAX_PIXELES:
        raise DatosInvalidos({"fotos[]": ["Cada fotografía admite como máximo 12.000.000 de píxeles."]})


def validar_fotos(archivos):
    if not isinstance(archivos, (list, tuple)) or len(archivos) > 5:
        raise DatosInvalidos({"fotos[]": ["Máximo 5 fotografías por turno."]})
    resultado = []
    for archivo in archivos:
        if not hasattr(archivo, "read"):
            raise DatosInvalidos({"fotos[]": ["Adjunte archivos de imagen."]})
        contenido = archivo.read(MAX_BYTES + 1)
        if not contenido or len(contenido) > MAX_BYTES:
            raise DatosInvalidos({"fotos[]": ["Cada fotografía debe medir entre 1 byte y 5 MiB."]})
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(BytesIO(contenido)) as imagen:
                    _validar_dimensiones(imagen)
                    formato = imagen.format
                    if formato not in FORMATOS:
                        raise ValueError("Formato no permitido")
                    imagen.verify()
                with Image.open(BytesIO(contenido)) as imagen:
                    _validar_dimensiones(imagen)
                    imagen.load()  # Detectar contenido truncado, no solo cabecera.
                    salida = BytesIO()
                    # Copiar píxeles elimina EXIF/GPS y cargas anexadas al archivo.
                    limpia = Image.new("RGB" if formato == "JPEG" else "RGBA", imagen.size)
                    limpia.paste(imagen.convert(limpia.mode))
                    limpia.save(salida, format=formato)
                    contenido = salida.getvalue()
        except (UnidentifiedImageError, OSError, ValueError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
            raise DatosInvalidos({"fotos[]": ["Imagen JPEG, PNG o WebP inválida."]}) from exc
        if len(contenido) > MAX_BYTES:
            raise DatosInvalidos({"fotos[]": ["La imagen procesada supera 5 MiB."]})
        extension, mime = FORMATOS[formato]
        resultado.append((contenido, extension, mime))
    return resultado


def ruta_privada(nombre):
    if not re.fullmatch(r"[0-9a-f]{32}\.(jpg|png|webp)", nombre):
        raise ValueError("Nombre interno inválido")
    raiz = Path(settings.EVIDENCIAS_ROOT).resolve()
    ruta = raiz / nombre
    if ruta.is_symlink() or ruta.resolve().parent != raiz:
        raise ValueError("Ruta de evidencia inválida")
    return ruta


def guardar_foto(contenido, extension, creados):
    nombre = f"{uuid4().hex}.{extension}"
    ruta = ruta_privada(nombre)
    ruta.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with ruta.open("xb") as destino:
        creados.append(nombre)  # Incluye fallos durante la escritura.
        ruta.chmod(0o600)
        destino.write(contenido)
    return nombre, hashlib.sha256(contenido).hexdigest()


def limpiar_archivos(nombres):
    for nombre in nombres:
        ruta_privada(nombre).unlink(missing_ok=True)
