"""Multipart acotado conservando el filename original, antes del basename de Django."""
from email import policy
from email.parser import BytesParser
from tempfile import TemporaryFile

from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.exceptions import ParseError
from rest_framework.parsers import BaseParser

from .exceptions import ArchivoGrande
from .validaciones import nombre_visible

MAX_BODY = 8 * 1024 * 1024 + 65536


class MultipartAdjunto(BaseParser):
    media_type = "multipart/form-data"

    def parse(self, stream, media_type=None, parser_context=None):
        try:
            # Lectura de transporte acotada. email mantiene como máximo un cuerpo
            # de 8MiB+64KiB; no depende del límite en memoria de Django.
            with TemporaryFile("w+b") as raw:
                raw.write(("Content-Type: " + media_type + "\r\nMIME-Version: 1.0\r\n\r\n").encode("ascii"))
                size = 0
                while chunk := stream.read(65536):
                    size += len(chunk)
                    if size > MAX_BODY:
                        raise ArchivoGrande()
                    raw.write(chunk)
                raw.seek(0)
                # parse(file) usa TextIOWrapper con universal-newlines y altera
                # bytes binarios. parsebytes preserva CR/LF del payload original.
                message = BytesParser(policy=policy.default).parsebytes(raw.read())
            if message.defects or not message.is_multipart() or len(message.get_payload()) not in (1, 2) or (message.preamble or "").strip() or (message.epilogue or "").strip():
                raise ValueError()
            result = {}
            for part in message.iter_parts():
                if part.defects or any(getattr(value, "defects", ()) for _, value in part.items()) or part.is_multipart() or len(part.get_all("Content-Disposition", [])) != 1 or part.get_content_disposition() != "form-data":
                    raise ValueError()
                params = part.get_params(header="content-disposition")[1:]
                keys = [key.lower() for key, _ in params]
                if len(set(keys)) != len(keys) or set(keys) - {"name", "filename"}:
                    raise ValueError()
                name = part.get_param("name", header="content-disposition")
                if name not in {"archivo", "nombre_visible"} or name in result or part.get("Content-Transfer-Encoding", "binary").lower() not in ("binary", "8bit"):
                    raise ValueError()
                content = part.get_payload(decode=True)
                if name == "archivo":
                    filename = nombre_visible(part.get_filename())
                    if len(part.get_all("Content-Type", [])) > 1:
                        raise ValueError()
                    result[name] = SimpleUploadedFile(filename, content, content_type=part.get_content_type() if part.get("Content-Type") else "application/octet-stream")
                else:
                    if part.get_filename() is not None or len(content) > 640:
                        raise ValueError()
                    result[name] = nombre_visible(content.decode("utf-8"))
            if "archivo" not in result:
                raise ValueError()
            return result
        except (ValueError, TypeError, UnicodeError, AttributeError):
            raise ParseError("Multipart inválido: un único archivo y nombre_visible opcional, sin campos duplicados.") from None
