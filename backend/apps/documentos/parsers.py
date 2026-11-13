import json

from rest_framework.exceptions import ParseError
from rest_framework.parsers import BaseParser


class JSONEstricto(BaseParser):
    media_type = "application/json"

    def parse(self, stream, media_type=None, parser_context=None):
        def pares(values):
            out = {}
            for key, value in values:
                if key in out:
                    raise ValueError()
                out[key] = value
            return out
        try:
            raw = stream.read(32769)
            if len(raw) > 32768:
                raise ValueError()
            return json.loads(raw.decode("utf-8"), object_pairs_hook=pares, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        except (ValueError, UnicodeError, RecursionError):
            raise ParseError("JSON UTF-8 inválido, duplicado o demasiado grande.") from None
