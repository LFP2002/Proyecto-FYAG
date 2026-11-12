"""Cursores firmados, no cifrados ni credenciales. TTL fijo desde fecha_corte."""
from datetime import datetime, timedelta

from django.core import signing
from django.utils import timezone
from rest_framework.exceptions import APIException

from .serializers import MAX_PK, PARAMETROS, filtros_query

SALT = "fyag.auditoria.cursor.v1"
TTL = 900


class CursorInvalido(APIException):
    status_code = 400

    def __init__(self):
        super().__init__({"code": "cursor_invalido", "detail": "El cursor no es válido o expiró; inicie una nueva consulta."})


def instante(value):
    if not isinstance(value, str):
        raise ValueError()
    result = datetime.fromisoformat(value)
    if timezone.is_naive(result):
        raise ValueError()
    return result


def identidad(actor):
    return {"id": actor.pk, "rol": actor.rol, "sesion_version": actor.sesion_version}


def crear(actor, filtros, corte, marcas, ultima):
    return signing.dumps({"v": 1, "identidad": identidad(actor), "filtros": filtros,
        "corte": corte.isoformat(), "marcas": marcas,
        "ultima": [ultima[0].isoformat(), ultima[1], ultima[2]]}, salt=SALT, compress=True)


def abrir(token, actor):
    try:
        if not isinstance(token, str) or not token or len(token) > 8192:
            raise ValueError()
        payload = signing.loads(token, salt=SALT, max_age=TTL)
        if not isinstance(payload, dict) or set(payload) != {"v", "identidad", "filtros", "corte", "marcas", "ultima"} or type(payload["v"]) is not int or payload["v"] != 1:
            raise ValueError()
        who = payload["identidad"]
        if (not isinstance(who, dict) or type(who.get("id")) is not int or type(who.get("sesion_version")) is not int or who != identidad(actor)):
            raise ValueError()
        corte = instante(payload["corte"])
        if not corte <= timezone.now() <= corte + timedelta(seconds=TTL):
            raise ValueError()
        raw = payload["filtros"]
        if not isinstance(raw, dict) or set(raw) - PARAMETROS or any(type(value) not in (str, int) for value in raw.values()):
            raise ValueError()
        filtros = filtros_query({k: str(v) for k, v in raw.items()})
        if filtros != raw:
            raise ValueError()
        marcas = payload["marcas"]
        if not isinstance(marcas, dict) or any(type(pk) is not int or not 0 <= pk <= MAX_PK for pk in marcas.values()):
            raise ValueError()
        ultima = payload["ultima"]
        if not isinstance(ultima, list) or len(ultima) != 3 or ultima[1] not in marcas or type(ultima[2]) is not int or not 0 < ultima[2] <= marcas[ultima[1]]:
            raise ValueError()
        fecha = instante(ultima[0])
        if fecha > corte:
            raise ValueError()
        return filtros, corte, marcas, (fecha, ultima[1], ultima[2])
    except (signing.BadSignature, ValueError, TypeError, KeyError, OverflowError, APIException):
        raise CursorInvalido() from None
