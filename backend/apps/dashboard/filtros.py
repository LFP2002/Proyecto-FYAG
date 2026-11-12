"""Validación de query y fronteras civiles; no comparte reglas de otras APIs."""
from datetime import date, datetime, time, timedelta, timezone as utc
import re
from zoneinfo import ZoneInfo

from rest_framework.exceptions import ValidationError

ZONA = ZoneInfo("America/Santiago")
MAX_PK = 9223372036854775807


def query_estricta(params, permitidos):
    if set(params) - set(permitidos):
        raise ValidationError({"query": "Parámetro no permitido."})
    for key in params:
        if len(params.getlist(key)) != 1 or not params[key]:
            raise ValidationError({key: "Parámetro repetido o vacío."})


def entero(valor, campo, maximo=MAX_PK):
    if not isinstance(valor, str) or not re.fullmatch(r"[1-9][0-9]{0,18}", valor) or int(valor) > maximo:
        raise ValidationError({campo: "Indique un entero decimal positivo dentro de rango, sin ceros iniciales."})
    return int(valor)


def desplazar_mes(dia, cantidad):
    meses = dia.year * 12 + dia.month - 1 + cantidad
    ano, mes = divmod(meses, 12)
    return date(ano, mes + 1, 1)


def inicio_civil(dia):
    # Round-trip resuelve medianoche inexistente al primer instante real del día.
    return datetime.combine(dia, time.min, tzinfo=ZONA).astimezone(utc.utc).astimezone(ZONA)


def periodo(params, hoy):
    query_estricta(params, {"desde", "hasta"})
    if ("desde" in params) != ("hasta" in params):
        raise ValidationError({"desde": "Indique desde y hasta conjuntamente."})
    if not params:
        return desplazar_mes(hoy, -5), hoy
    fechas = {}
    for campo in ("desde", "hasta"):
        try:
            if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", params[campo]):
                raise ValueError()
            fechas[campo] = date.fromisoformat(params[campo])
        except ValueError:
            raise ValidationError({campo: "Use una fecha civil válida YYYY-MM-DD."}) from None
    desde, hasta = fechas["desde"], fechas["hasta"]
    if desde > hasta or (hasta - desde).days >= 366 or hasta > hoy or hasta == date.max:
        raise ValidationError({"hasta": "Rango inválido: máximo 366 días inclusivos y sin fechas futuras."})
    return desde, hasta


def rango(desde, hasta):
    return inicio_civil(desde), inicio_civil(hasta + timedelta(days=1))
