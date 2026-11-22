"""Almacén POSIX del chat, sin rutas públicas ni dependencia de AdjuntoDocumento.

Cada nombre tiene un recibo ArchivoChat previo al primer byte. Dirfd/O_NOFOLLOW,
publicación no-clobber y copia verificada evitan symlinks/TOCTOU/lecturas rotas.
"""
from contextlib import contextmanager
import hashlib
import os
import stat
from pathlib import Path
from tempfile import TemporaryFile
from uuid import UUID

from django.conf import settings

from .exceptions import NoDisponible


@contextmanager
def directorio(nombre, *, crear=True):
    root = Path(settings.CHAT_ARCHIVOS_ROOT)
    fd = target = None
    try:
        if not root.is_absolute() or not hasattr(os, 'O_NOFOLLOW') or not os.supports_dir_fd:
            raise NoDisponible()
        # No aceptar configuración solapada con otros almacenes o rutas públicas.
        otros = [Path(settings.ADJUNTOS_ROOT), Path(settings.EVIDENCIAS_ROOT), Path(settings.BASE_DIR)/'static', Path(settings.BASE_DIR)/'media']
        if any(root == x or root in x.parents or x in root.parents for x in otros):
            raise NoDisponible()
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        fd = os.open(root.anchor, flags)
        for parte in root.parts[1:]:
            if parte in {'.', '..'}:
                raise NoDisponible()
            if crear:
                try:
                    os.mkdir(parte, 0o700, dir_fd=fd)
                except FileExistsError:
                    pass
            siguiente = os.open(parte, flags, dir_fd=fd)
            os.close(fd); fd = siguiente
        if crear:
            try:
                os.mkdir(nombre, 0o700, dir_fd=fd)
            except FileExistsError:
                pass
        target = os.open(nombre, flags, dir_fd=fd)
        yield target
    except OSError:
        raise NoDisponible() from None
    finally:
        if target is not None:
            os.close(target)
        if fd is not None:
            os.close(fd)


class Staging:
    def __init__(self, key):
        self.nombre = UUID(str(key)).hex
        self.file = None

    def __enter__(self):
        try:
            with directorio('staging') as fd:
                handle = os.open(self.nombre, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
            self.file = os.fdopen(handle, 'w+b')
            return self
        except OSError:
            raise NoDisponible() from None

    def __exit__(self, *exc):
        if self.file is not None:
            self.file.close()
        # La limpieza física se hace después del commit/rollback vía recibo.

    def publicar(self):
        try:
            self.file.flush(); os.fsync(self.file.fileno())
            with directorio('staging') as source, directorio('archivos') as target:
                os.link(self.nombre, self.nombre, src_dir_fd=source, dst_dir_fd=target, follow_symlinks=False)
                abierto = os.fstat(self.file.fileno())
                publicado = os.stat(self.nombre, dir_fd=target, follow_symlinks=False)
                if not stat.S_ISREG(publicado.st_mode) or (abierto.st_dev, abierto.st_ino) != (publicado.st_dev, publicado.st_ino):
                    os.unlink(self.nombre, dir_fd=target)
                    raise NoDisponible()
                os.fsync(target)
        except OSError:
            raise NoDisponible() from None


def retirar(key, *, publicado=True):
    for carpeta in (['staging', 'archivos'] if publicado else ['staging']):
        with directorio(carpeta) as fd:
            nombre = UUID(str(key)).hex
            try:
                # unlink de la entrada bajo dirfd: nunca seguir un symlink.
                os.unlink(nombre, dir_fd=fd)
                os.fsync(fd)
            except FileNotFoundError:
                pass
            except OSError:
                raise NoDisponible() from None


def copia_verificada(archivo):
    copia = TemporaryFile('w+b', prefix='fyag-chat-descarga-')
    try:
        with directorio('archivos', crear=False) as fd:
            handle = os.open(archivo.clave_interna.hex, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        with os.fdopen(handle, 'rb') as original:
            info = os.fstat(original.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size != archivo.tamano_bytes:
                raise NoDisponible()
            digest = hashlib.sha256(); total = 0
            while chunk := original.read(65536):
                total += len(chunk)
                if total > archivo.tamano_bytes:
                    raise NoDisponible()
                digest.update(chunk); copia.write(chunk)
            if total != archivo.tamano_bytes or digest.hexdigest() != archivo.sha256:
                raise NoDisponible()
        copia.seek(0)
        return copia
    except BaseException as exc:
        copia.close()
        if isinstance(exc, OSError):
            raise NoDisponible() from None
        raise
