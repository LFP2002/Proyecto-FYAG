import json
from email import policy
from email.parser import BytesParser

from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.exceptions import ParseError
from rest_framework.parsers import BaseParser

from .exceptions import ArchivoGrande
from .validaciones import nombre


def _objeto(pares):
    data = {}
    for k, v in pares:
        if k in data:
            raise ValueError()
        data[k] = v
    return data


class JSONEstricto(BaseParser):
    media_type = 'application/json'

    def parse(self, stream, media_type=None, parser_context=None):
        raw = stream.read(32769)
        if len(raw) > 32768:
            raise ArchivoGrande()
        try:
            return json.loads(raw.decode('utf-8'), object_pairs_hook=_objeto, parse_constant=lambda v: (_ for _ in ()).throw(ValueError()))
        except (UnicodeError, ValueError, RecursionError):
            raise ParseError('JSON inválido o con claves repetidas.') from None


class MultipartChat(BaseParser):
    media_type = 'multipart/form-data'

    def parse(self, stream, media_type=None, parser_context=None):
        raw = stream.read(8*1024*1024+65537)
        if len(raw) > 8*1024*1024+65536:
            raise ArchivoGrande()
        try:
            message = BytesParser(policy=policy.default).parsebytes(('Content-Type: '+media_type+'\r\nMIME-Version: 1.0\r\n\r\n').encode('ascii')+raw)
            if message.defects or not message.is_multipart() or len(message.get_payload()) not in (1, 2) or (message.preamble or '').strip() or (message.epilogue or '').strip():
                raise ValueError()
            data = {}
            for part in message.iter_parts():
                if part.defects or part.is_multipart() or any(getattr(v, 'defects', ()) for _, v in part.items()) or len(part.get_all('Content-Disposition', [])) != 1 or part.get_content_disposition() != 'form-data':
                    raise ValueError()
                params = part.get_params(header='content-disposition')[1:]
                keys = [k.lower() for k, _ in params]
                if len(set(keys)) != len(keys) or set(keys)-{'name', 'filename'} or part.get('Content-Transfer-Encoding', 'binary').lower() not in {'binary', '8bit'}:
                    raise ValueError()
                campo = part.get_param('name', header='content-disposition')
                if campo not in {'archivo', 'texto'} or campo in data:
                    raise ValueError()
                content = part.get_payload(decode=True)
                if campo == 'archivo':
                    if len(part.get_all('Content-Type', [])) > 1:
                        raise ValueError()
                    data[campo] = SimpleUploadedFile(nombre(part.get_filename()), content, content_type=part.get_content_type())
                else:
                    if part.get_filename() is not None or len(content) > 8000:
                        raise ValueError()
                    data[campo] = content.decode('utf-8')
            if 'archivo' not in data:
                raise ValueError()
            return data
        except (ValueError, UnicodeError, AttributeError, TypeError):
            raise ParseError('Multipart inválido; archivo obligatorio y texto opcional, sin duplicados.') from None
