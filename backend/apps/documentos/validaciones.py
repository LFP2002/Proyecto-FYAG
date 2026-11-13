"""Dominio documental acotado; nunca construir operadores desde input del cliente."""
import json
import re
import unicodedata

from rest_framework.exceptions import ValidationError

BIGINT = 9223372036854775807
CLAVES_ATRIBUTOS = frozenset({
    "ubicacion_general", "vista", "componente", "condicion", "tipo_evidencia",
    "fase_trabajo", "iluminacion", "orientacion", "equipo_tipo", "zona_tecnica",
    "requiere_revision", "estado_visual",
})
# No clasificador de PII: reglas conservadoras + vocabulario de claves cerrado.
SENSIBLE = re.compile(
    r"[<>]|[\w.+-]+@[\w.-]+\.[a-z]{2,}|(?:https?://|file:|data:|mongodb:|postgres(?:ql)?:)|"
    r"(?:[a-z]:[\\/]|/(?:var|home|app|etc|data|users)/)|"
    r"\b(?:bearer|password|contrase[ñn]a|token|rut|iban|cuenta_bancaria|monto|saldo|folio|tarifa)\b|"
    r"\b\d{1,2}(?:\.\d{3}){2}-[0-9k]\b|\b\d{7,8}-[0-9k]\b|"
    r"eyJ[A-Za-z0-9_-]+\.|[A-Za-z0-9+/]{80,}={0,2}|\$\s*\d", re.I,
)


def entero_ascii(value, campo):
    if not isinstance(value, str) or not re.fullmatch(r"[1-9][0-9]{0,18}", value) or int(value) > BIGINT:
        raise ValidationError({campo: "Use un entero positivo ASCII sin ceros iniciales, dentro de BIGINT."})
    return int(value)


def query(params, campos, obligatorios=()):
    if set(params) - set(campos) or set(obligatorios) - set(params):
        raise ValidationError({"query": "Parámetros no permitidos o requeridos ausentes."})
    for key in params:
        if len(params.getlist(key)) != 1 or not params[key]:
            raise ValidationError({key: "Parámetro repetido o vacío."})


def texto(value, maximo, campo):
    if type(value) is not str or len(value) > maximo:
        raise ValidationError({campo: "Texto inválido o demasiado largo."})
    if any(unicodedata.category(c).startswith("C") or c in "\u2028\u2029" for c in value):
        raise ValidationError({campo: "No se permiten caracteres de control u ocultos."})
    value = " ".join(unicodedata.normalize("NFKC", value).split())
    if len(value) > maximo or SENSIBLE.search(value):
        raise ValidationError({campo: "Solo anotaciones técnicas, sin HTML, datos sensibles, enlaces o archivos."})
    return value


def anotaciones(data):
    out = {}
    if "descripcion" in data:
        out["descripcion"] = texto(data["descripcion"], 1000, "descripcion")
    if "etiquetas" in data:
        values = data["etiquetas"]
        if type(values) is not list or len(values) > 12:
            raise ValidationError({"etiquetas": "Use hasta 12 etiquetas."})
        etiquetas = [texto(v, 40, "etiquetas").casefold() for v in values]
        if any(not v or len(v) > 40 or not all(c.isalnum() or c in " _-" for c in v) for v in etiquetas) or len(set(etiquetas)) != len(etiquetas):
            raise ValidationError({"etiquetas": "Etiquetas legibles y únicas tras normalización."})
        out["etiquetas"] = sorted(etiquetas)
    if "atributos" in data:
        values = data["atributos"]
        if type(values) is not dict or len(values) > 12 or set(values) - CLAVES_ATRIBUTOS:
            raise ValidationError({"atributos": "Use únicamente las claves técnicas documentadas, hasta 12 pares."})
        out["atributos"] = {}
        for key, value in sorted(values.items()):
            if not re.fullmatch(r"[a-z][a-z0-9_]{0,39}", key):
                raise ValidationError({"atributos": "Clave inválida."})
            out["atributos"][key] = value if type(value) is bool else texto(value, 200, "atributos")
        if len(json.dumps(out["atributos"], ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")) > 4096:
            raise ValidationError({"atributos": "Máximo 4 KiB de JSON UTF-8 compacto."})
    return out


def patch_documento(data):
    if type(data) is not dict or set(data) - {"revision", "descripcion", "etiquetas", "atributos"} or not {"descripcion", "etiquetas", "atributos"} & set(data):
        raise ValidationError({"body": "Objeto con revision y al menos un campo documental, sin campos adicionales."})
    revision = data.get("revision")
    if type(revision) is not int or not 0 <= revision < BIGINT:
        raise ValidationError({"revision": "Entero no negativo obligatorio, menor que BIGINT máximo."})
    return revision, anotaciones(data)
