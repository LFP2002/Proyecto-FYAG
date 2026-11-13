"""Almacén privado POSIX: handles sin symlinks, staging propio y publicación no-clobber."""
from contextlib import contextmanager
import hashlib
import os
import stat
from tempfile import TemporaryFile
from uuid import uuid4, UUID

from django.conf import settings

from .exceptions import AlmacenNoDisponible, ConflictoAdjunto


def _flags():
    if not hasattr(os, "O_NOFOLLOW") or not os.supports_dir_fd:
        raise AlmacenNoDisponible()  # No degradar silenciosamente la garantía POSIX.
    return os.O_NOFOLLOW | os.O_DIRECTORY


@contextmanager
def directorio(nombre, crear=True):
    root = settings.ADJUNTOS_ROOT
    try:
        # Crear raíz solamente bajo su padre configurado; todos los accesos usan
        # luego dirfd y O_NOFOLLOW, no resolve seguido de open vulnerable a TOCTOU.
        if not root.is_absolute():
            raise AlmacenNoDisponible()
        rfd = os.open(root.anchor, os.O_RDONLY | _flags())
        try:
            for component in root.parts[1:]:
                if component in {".", ".."}:
                    raise AlmacenNoDisponible()
                if crear:
                    try:
                        os.mkdir(component, mode=0o700, dir_fd=rfd)
                    except FileExistsError:
                        pass
                child = os.open(component, os.O_RDONLY | _flags(), dir_fd=rfd)
                os.close(rfd)
                rfd = child
        except BaseException:
            os.close(rfd)
            raise
        try:
            if crear:
                try:
                    os.mkdir(nombre, mode=0o700, dir_fd=rfd)
                except FileExistsError:
                    pass
            fd = os.open(nombre, os.O_RDONLY | _flags(), dir_fd=rfd)
            try:
                yield fd
            finally:
                os.close(fd)
        finally:
            os.close(rfd)
    except OSError:
        raise AlmacenNoDisponible() from None


def clave(value):
    return UUID(str(value)).hex


class Staging:
    def __init__(self):
        self.nombre = uuid4().hex
        self.file = None

    def __enter__(self):
        with directorio("staging") as fd:
            handle = os.open(self.nombre, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
        self.file = os.fdopen(handle, "w+b")
        return self

    def __exit__(self, *exc):
        try:
            if self.file is not None:
                self.file.close()
        finally:
            # Solo archivo creado por ESTA operación; no barrer staging ajeno.
            with directorio("staging") as fd:
                try:
                    os.unlink(self.nombre, dir_fd=fd)
                except FileNotFoundError:
                    pass

    def publicar(self, key):
        self.file.flush()
        os.fsync(self.file.fileno())
        with directorio("staging") as source, directorio("archivos") as target:
            # link no reemplaza un archivo existente, a diferencia de rename.
            os.link(self.nombre, clave(key), src_dir_fd=source, dst_dir_fd=target, follow_symlinks=False)
            try:
                os.fsync(target)
            except OSError:
                os.unlink(clave(key), dir_fd=target)
                raise


def retirar_publicado_propio(key):
    with directorio("archivos", crear=False) as fd:
        try:
            os.unlink(clave(key), dir_fd=fd)
            os.fsync(fd)
        except FileNotFoundError:
            pass


def copia_verificada(adjunto):
    copia = TemporaryFile("w+b", prefix="fyag-adjunto-descarga-")
    try:
        with directorio("archivos", crear=False) as fd:
            handle = os.open(clave(adjunto.clave_interna), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        with os.fdopen(handle, "rb") as archivo:
            info = os.fstat(archivo.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size != adjunto.tamano_bytes:
                raise ConflictoAdjunto("archivo_no_integro")
            h = hashlib.sha256()
            total = 0
            while chunk := archivo.read(65536):
                total += len(chunk)
                if total > adjunto.tamano_bytes:
                    raise ConflictoAdjunto("archivo_no_integro")
                h.update(chunk)
                copia.write(chunk)
            if total != adjunto.tamano_bytes or h.hexdigest() != adjunto.sha256:
                raise ConflictoAdjunto("archivo_no_integro")
        copia.seek(0)
        return copia
    except (OSError, ValueError, AlmacenNoDisponible):
        copia.close()
        raise ConflictoAdjunto("archivo_no_integro") from None
    except BaseException:
        copia.close()
        raise
