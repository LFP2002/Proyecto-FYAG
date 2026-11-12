import codecs

from django.conf import settings
from rest_framework.exceptions import ParseError
from rest_framework.parsers import JSONParser
from rest_framework.utils import json


def objeto_unico(pares):
    out = {}
    for key, value in pares:
        if key in out:
            raise ValueError("Clave repetida")
        out[key] = value
    return out


class JSONEstrictoParser(JSONParser):
    def parse(self, stream, media_type=None, parser_context=None):
        encoding = (parser_context or {}).get("encoding", settings.DEFAULT_CHARSET)
        try:
            return json.load(codecs.getreader(encoding)(stream), parse_constant=json.strict_constant, object_pairs_hook=objeto_unico)
        except (ValueError, UnicodeError):
            raise ParseError("JSON inválido o con claves repetidas.") from None
