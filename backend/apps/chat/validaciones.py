import hashlib
import json
import re
import unicodedata
from uuid import UUID

from rest_framework.exceptions import ValidationError


def contrato(data, permitidos, requeridos):
    if type(data) is not dict or set(data)-set(permitidos) or set(requeridos)-set(data):
        raise ValidationError({'body': ['Campos desconocidos, ausentes o cuerpo inválido.']})


def identificador(value):
    if type(value) is not int or not 0 < value <= 9223372036854775807:
        raise ValidationError({'id': ['Entero positivo BIGINT requerido.']})
    return value


def id_url(value):
    if type(value) is not str or not re.fullmatch(r'[1-9][0-9]{0,18}', value):
        raise ValidationError({'id': ['Identificador canónico requerido.']})
    return identificador(int(value))


def clave(value):
    if type(value) is not str or not re.fullmatch(r'[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}', value):
        raise ValidationError({'clave_idempotencia': ['UUID canónica requerida.']})
    return UUID(value)


def texto(value, limite=2000, *, vacio=False):
    if type(value) is not str or any(unicodedata.category(c) in {'Cc', 'Cs'} for c in value):
        raise ValidationError({'texto': ['Texto Unicode sin controles requerido.']})
    value = unicodedata.normalize('NFC', value).strip()
    if len(value) > limite or not vacio and not value:
        raise ValidationError({'texto': ['Longitud de texto inválida.']})
    return value


def nombre(value):
    value = texto(value, 150)
    if value in {'.', '..'} or '/' in value or '\\' in value or ':' in value or any(unicodedata.category(c) == 'Cf' for c in value):
        raise ValidationError({'archivo': ['Nombre de archivo inválido.']})
    return value


def huella(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode()).hexdigest()
