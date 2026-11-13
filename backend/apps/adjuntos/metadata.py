import json
import re
from datetime import datetime, timezone
from pathlib import Path

from bson import BSON, Int64
from django.conf import settings
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError, PyMongoError
from rest_framework.exceptions import ValidationError

from apps.documentos import mongo
from apps.documentos.exceptions import MetadataPendiente, MongoNoDisponible, RevisionObsoleta
from apps.documentos.services import fuera_transaccion, milisegundo
from apps.documentos.validaciones import anotaciones, texto, BIGINT
from . import services
from .models import AdjuntoDocumento

COL = "adjuntos_metadata"
INDICE = "adjuntos_tipo_destino_fecha"
ORDEN = [("tipo", 1), ("destino_id", 1), ("registrado_en", -1), ("adjunto_id", -1)]
CLAVES = {
    "RESPALDO_FACTURA": frozenset({"estado_documental", "legibilidad", "orientacion", "caras", "requiere_revision", "tipo_copia", "integridad_visual", "soporte", "idioma", "calidad_imagen", "color", "observacion_tecnica"}),
    "INFORME_TECNICO": frozenset({"ubicacion_general", "vista", "componente", "condicion", "tipo_evidencia", "fase_trabajo", "iluminacion", "orientacion", "equipo_tipo", "zona_tecnica", "requiere_revision", "estado_visual"}),
}
EDITABLES = {"descripcion", "etiquetas", "atributos", "revision", "anotado_en", "anotado_por_id"}
PUBLICOS = {"adjunto_id", "tipo", "destino_id", "mime", "tamano_bytes", "registrado_en", "sincronizado_en", "descripcion", "etiquetas", "atributos", "revision"}
# Reglas 012B independientes: no modificar validación de evidencias 012A.
DATOS_NO_DOCUMENTALES = re.compile(
    r"\b(?:\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{4})\b|"
    r"\b\d{13,19}\b|\+\s*56[\s-]*9(?:[\s-]*\d){8}\b|"
    r"\b(?:ocr|cuenta|pasaporte|cedula|vencimiento|monto_neto|monto_total|fecha_emision)\b|"
    r"\b(?:CLP|USD|EUR)\s*\d|\d\s*(?:CLP|USD|EUR)\b", re.I,
)


def esquema():
    return json.loads(Path(__file__).with_name("esquema.json").read_text(encoding="utf-8"))


def coleccion():
    try:
        db = mongo.cliente()[settings.DOCUMENTOS_MONGO["db"]]
        info = list(db.list_collections(filter={"name": COL}))
        if not info or info[0]["options"].get("validator") != esquema() or info[0]["options"].get("validationLevel") != "strict" or info[0]["options"].get("validationAction") != "error":
            raise MongoNoDisponible()
        col = db[COL]
        if list(col.index_information().get(INDICE, {}).get("key", [])) != ORDEN:
            raise MongoNoDisponible()
        return col
    except PyMongoError:
        raise MongoNoDisponible() from None


def validar_anotaciones(data, tipo):
    out = anotaciones({k: v for k, v in data.items() if k in {"descripcion", "etiquetas"}})
    if "atributos" in data:
        attrs = data["atributos"]
        if type(attrs) is not dict or len(attrs) > 12 or set(attrs) - CLAVES[tipo]:
            raise ValidationError({"atributos": "Use el vocabulario técnico del tipo documental."})
        out["atributos"] = {k: v if type(v) is bool else texto(v, 200, "atributos") for k, v in sorted(attrs.items())}
        if len(json.dumps(out["atributos"], ensure_ascii=False, separators=(",", ":")).encode("utf-8")) > 4096:
            raise ValidationError({"atributos": "Máximo 4 KiB de JSON UTF-8 compacto."})
    values = [out.get("descripcion", ""), *out.get("etiquetas", []), *out.get("atributos", {}).values()]
    if any(type(value) is str and DATOS_NO_DOCUMENTALES.search(value) for value in values):
        raise ValidationError({"anotaciones": "Solo información técnica, sin datos personales, fechas, importes ni OCR."})
    return out


def tecnico(adjunto):
    return {"_id": f"adjunto:{adjunto.pk}", "version_esquema": 1, "adjunto_id": Int64(adjunto.pk),
        "tipo": adjunto.tipo, "destino_id": Int64(adjunto.documento_cobro_id or adjunto.obra_id),
        "mime": adjunto.mime, "tamano_bytes": Int64(adjunto.tamano_bytes), "registrado_en": milisegundo(adjunto.registrado_en)}


def validar_documento(doc, adjunto):
    try:
        tech = tecnico(adjunto)
        if set(doc) != set(tech) | EDITABLES | {"sincronizado_en"} or len(BSON.encode(doc)) > 16384:
            raise ValueError()
        if any(doc.get(k) != v or (isinstance(v, Int64) and not isinstance(doc[k], Int64)) for k, v in tech.items()):
            raise ValueError()
        if type(doc["version_esquema"]) is not int or type(doc["revision"]) not in (int, Int64) or not 0 <= doc["revision"] <= BIGINT:
            raise ValueError()
        if not isinstance(doc["sincronizado_en"], datetime) or doc["sincronizado_en"].tzinfo is None:
            raise ValueError()
        if doc["revision"] == 0:
            if any(doc[k] for k in EDITABLES):
                raise ValueError()
        elif not isinstance(doc["anotado_en"], datetime) or doc["anotado_en"].tzinfo is None or not isinstance(doc["anotado_por_id"], Int64) or not 0 < doc["anotado_por_id"] <= BIGINT:
            raise ValueError()
        validated = validar_anotaciones(doc, adjunto.tipo)
        if any(doc[k] != v for k, v in validated.items()):
            raise ValueError()
        return doc
    except (TypeError, KeyError, ValueError, OverflowError, ValidationError):
        raise MongoNoDisponible() from None


def representar(doc):
    return {k: v.isoformat() if isinstance(v, datetime) else v for k, v in doc.items() if k in PUBLICOS}


def sincronizar(adjunto, col=None):
    fuera_transaccion()
    try:
        col = coleccion() if col is None else col
        tech = tecnico(adjunto)
        ident = tech.pop("_id")
        tech["sincronizado_en"] = datetime.now(timezone.utc)
        defaults = {"descripcion": "", "etiquetas": [], "atributos": {}, "revision": 0, "anotado_en": None, "anotado_por_id": None}
        try:
            col.update_one({"_id": ident}, {"$set": tech, "$setOnInsert": defaults}, upsert=True)
        except DuplicateKeyError:
            col.update_one({"_id": ident}, {"$set": tech})
    except PyMongoError:
        raise MongoNoDisponible() from None


def leer(adjunto):
    fuera_transaccion()
    try:
        doc = coleccion().find_one({"_id": f"adjunto:{adjunto.pk}"})
        if doc is None:
            raise MetadataPendiente()
        return representar(validar_documento(doc, adjunto))
    except PyMongoError:
        raise MongoNoDisponible() from None


def editar(adjunto, actor, data, correlacion):
    fuera_transaccion()
    if type(data) is not dict or set(data) - {"revision", "descripcion", "etiquetas", "atributos"} or not {"descripcion", "etiquetas", "atributos"} & set(data):
        raise ValidationError({"body": "Objeto con revisión y al menos un campo documental, sin extras."})
    revision = data.get("revision")
    if type(revision) is not int or not 0 <= revision < BIGINT:
        raise ValidationError({"revision": "Entero no negativo obligatorio, menor que BIGINT máximo."})
    cambios = validar_anotaciones(data, adjunto.tipo)
    try:
        col = coleccion()
        anterior = col.find_one({"_id": f"adjunto:{adjunto.pk}"})
        if anterior is None:
            raise MetadataPendiente()
        validar_documento(anterior, adjunto)
        nuevo = {**anterior, **cambios, "revision": revision+1, "anotado_en": datetime.now(timezone.utc), "anotado_por_id": Int64(actor.pk)}
        validar_documento(nuevo, adjunto)
        doc = col.find_one_and_update({"_id": anterior["_id"], "revision": revision},
            {"$set": {**cambios, "anotado_en": nuevo["anotado_en"], "anotado_por_id": nuevo["anotado_por_id"]}, "$inc": {"revision": 1}}, return_document=ReturnDocument.AFTER)
        if doc is None:
            raise RevisionObsoleta()
        services.registrar(actor, adjunto.pk, "anotacion_adjunto", "revision_actualizada", correlacion)
        return representar(validar_documento(doc, adjunto))
    except PyMongoError:
        raise MongoNoDisponible() from None
