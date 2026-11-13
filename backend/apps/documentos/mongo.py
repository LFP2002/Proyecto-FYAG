"""Cliente perezoso por proceso: ninguna conexión desde ready/import/migrate."""
import atexit
import json
import os
import re
from pathlib import Path
from threading import Lock

from django.conf import settings
from pymongo import MongoClient
from pymongo.errors import PyMongoError

from .exceptions import MongoNoDisponible

_lock = Lock()
_cliente = None
_clave = None
INDICE = "documentos_obra_creacion_evidencia"
ORDEN = [("obra_id", 1), ("creado_en", -1), ("evidencia_id", -1)]
COL = "documentos_metadata"


def esquema():
    return json.loads(Path(__file__).with_name("esquema.json").read_text(encoding="utf-8"))


def cerrar():
    global _cliente, _clave
    with _lock:
        if _cliente is not None:
            _cliente.close()
        _cliente = _clave = None


atexit.register(cerrar)


def cliente():
    global _cliente, _clave
    conf = settings.DOCUMENTOS_MONGO
    key = (os.getpid(), tuple(sorted(conf.items())))
    with _lock:
        if _clave != key:
            if _cliente is not None:
                _cliente.close()
            # Una configuración inválida no puede dejar un cliente cerrado
            # reutilizable al volver a la configuración anterior.
            _cliente = _clave = None
            if not conf["usuario"] or not conf["password"] or conf["db"] not in ("fyag_documentos", "fyag_documentos_test"):
                raise MongoNoDisponible()
            try:
                puerto = int(conf["puerto"])
                if not 1 <= puerto <= 65535 or not re.fullmatch(r"[a-zA-Z0-9_.-]{1,253}", conf["host"]):
                    raise ValueError()
            except (ValueError, TypeError):
                raise MongoNoDisponible() from None
            _cliente = MongoClient(host=conf["host"], port=puerto, username=conf["usuario"], password=conf["password"],
                authSource=conf["db"], connect=False, tz_aware=True, retryWrites=False,
                serverSelectionTimeoutMS=conf["timeout_ms"], connectTimeoutMS=conf["timeout_ms"],
                socketTimeoutMS=conf["timeout_ms"], timeoutMS=conf["timeout_ms"], waitQueueTimeoutMS=conf["timeout_ms"],
                maxPoolSize=10, minPoolSize=0, appname="fyag-documentos-012a")
            _clave = key
        return _cliente


def coleccion():
    try:
        db = cliente()[settings.DOCUMENTOS_MONGO["db"]]
        info = list(db.list_collections(filter={"name": COL}))
        if not info or info[0]["options"].get("validator") != esquema() or info[0]["options"].get("validationLevel") != "strict" or info[0]["options"].get("validationAction") != "error":
            raise MongoNoDisponible()
        col = db[COL]
        idx = col.index_information().get(INDICE, {})
        if list(idx.get("key", [])) != ORDEN:
            raise MongoNoDisponible()
        return col
    except PyMongoError:
        raise MongoNoDisponible() from None
