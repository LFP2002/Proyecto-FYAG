from datetime import date, datetime, time, timedelta, timezone as utc
import re
from zoneinfo import ZoneInfo

from rest_framework.exceptions import ValidationError
from .catalogo import FILTROS, FORMATOS, ESTADOS_OBRA, ESTADOS_COBRANZA

ZONA = ZoneInfo("America/Santiago")


def query_estricta(params, permitidos):
    if set(params) - set(permitidos):
        raise ValidationError({"query": "Parámetro no permitido."})
    for key in params:
        if len(params.getlist(key)) != 1 or not params[key]:
            raise ValidationError({key: "Parámetro repetido o vacío."})


def entero(value, campo):
    if not re.fullmatch(r"[1-9][0-9]{0,18}", value) or int(value) > 9223372036854775807:
        raise ValidationError({campo: "Use un entero positivo dentro de rango, sin signos ni ceros iniciales."})
    return int(value)


def inicio_civil(dia):
    return datetime.combine(dia, time.min, tzinfo=ZONA).astimezone(utc.utc).astimezone(ZONA)


def validar(params, tipo, hoy, *, exportar=False):
    query_estricta(params, {*FILTROS[tipo], "formato" if exportar else "page"})
    out = dict(params.items())
    if ("desde" in out) != ("hasta" in out):
        raise ValidationError({"desde": "Indique desde y hasta conjuntamente."})
    if "desde" not in out:
        out.update(desde=hoy.replace(day=1), hasta=hoy)
    else:
        for key in ("desde", "hasta"):
            try:
                if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", out[key]):
                    raise ValueError()
                out[key] = date.fromisoformat(out[key])
            except ValueError:
                raise ValidationError({key: "Use una fecha civil válida YYYY-MM-DD."}) from None
    if out["desde"] > out["hasta"] or (out["hasta"] - out["desde"]).days > 365 or out["hasta"] > hoy or out["hasta"] == date.max:
        raise ValidationError({"hasta": "Rango inválido: máximo 366 días inclusivos, sin futuro."})
    if "cliente" in out:
        out["cliente"] = entero(out["cliente"], "cliente")
    if "estado" in out and out["estado"] not in (ESTADOS_OBRA if tipo == "obras" else ESTADOS_COBRANZA):
        raise ValidationError({"estado": "Estado no permitido."})
    if tipo == "obras":
        out.setdefault("fecha_base", "CREACION")
        if out["fecha_base"] not in ("CREACION", "FINALIZACION"):
            raise ValidationError({"fecha_base": "Use CREACION o FINALIZACION."})
        if out["fecha_base"] == "FINALIZACION" and out.get("estado", "FINALIZADA") != "FINALIZADA":
            raise ValidationError({"estado": "FINALIZACION requiere estado FINALIZADA."})
    if exportar:
        if out.get("formato") not in FORMATOS:
            raise ValidationError({"formato": "Indique csv, xlsx o pdf."})
    else:
        out["page"] = entero(out.get("page", "1"), "page")
    return out


def limites(filtros):
    return inicio_civil(filtros["desde"]), inicio_civil(filtros["hasta"] + timedelta(days=1))
