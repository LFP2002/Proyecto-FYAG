"""Protocolo clamd INSTREAM: nunca enviar rutas al escáner ni montar archivos allí."""
import socket
import struct
from time import monotonic

from django.conf import settings

from .exceptions import ContenidoRechazado, ScannerNoDisponible


def analizar(archivo):
    conf = settings.ADJUNTOS_SCANNER
    deadline = monotonic() + conf["timeout"]
    try:
        if conf.get("socket"):
            conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            try:
                conn.settimeout(min(3, conf["timeout"]))
                conn.connect(conf["socket"])
            except BaseException:
                conn.close()
                raise
        else:
            conn = socket.create_connection((conf["host"], int(conf["puerto"])), timeout=min(3, conf["timeout"]))
        with conn:
            def tiempo():
                remaining = deadline - monotonic()
                if remaining <= 0:
                    raise TimeoutError()
                conn.settimeout(remaining)
            tiempo()
            conn.sendall(b"zINSTREAM\0")
            archivo.seek(0)
            while chunk := archivo.read(65536):
                tiempo()
                conn.sendall(struct.pack("!I", len(chunk)) + chunk)
            tiempo()
            conn.sendall(b"\0\0\0\0")
            response = b""
            while b"\0" not in response:
                tiempo()
                chunk = conn.recv(4096)
                if not chunk or len(response) + len(chunk) > 4096:
                    raise OSError()
                response += chunk
            if response == b"stream: OK\0":
                archivo.seek(0)
                return
            if response.startswith(b"stream: ") and response.endswith(b" FOUND\0"):
                raise ContenidoRechazado()
            # Cualquier ERROR, límite de análisis o respuesta desconocida: fail closed.
            raise ScannerNoDisponible()
    except (OSError, ValueError, TypeError):
        raise ScannerNoDisponible() from None
