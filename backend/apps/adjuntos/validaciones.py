import re
import unicodedata
from uuid import UUID

from rest_framework.exceptions import ValidationError


def nombre_visible(value):
    if type(value) is not str or not 1 <= len(value) <= 160:
        raise ValidationError({"nombre_visible": "Nombre legible de 1 a 160 caracteres."})
    value = unicodedata.normalize("NFKC", value).strip()
    if not value or len(value) > 160 or ".." in value or value.startswith(".") or any(not (c.isalnum() or c in " ._-()") for c in value):
        raise ValidationError({"nombre_visible": "Nombre sin rutas, controles ni caracteres especiales."})
    return value


def idempotencia(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", value):
        raise ValidationError({"Idempotency-Key": "Encabezado UUID canónico obligatorio."})
    return UUID(value)
