import json
import logging
from datetime import datetime, timezone

from bson import BSON, Int64
from django.db import connection
from django.db.models import F
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError, PyMongoError
from rest_framework.exceptions import NotFound, ValidationError

from apps.obras.models import EvidenciaTurno, Obra
from . import mongo
from .exceptions import MetadataPendiente, MongoNoDisponible, RevisionObsoleta
from .permissions import revalidar
from .validaciones import anotaciones, BIGINT

logger = logging.getLogger(__name__)
CAMPOS_SQL = ("id", "obra_id", "turno_id", "tipo_mime", "tamano", "sha256", "creado_en")
PUBLICOS = ("evidencia_id", "obra_id", "turno_id", "tipo_mime", "tamano_bytes", "creado_en", "descripcion", "etiquetas", "atributos", "revision", "sincronizado_en")
TECNICOS = {"_id", "version_esquema", "origen", "evidencia_id", "obra_id", "turno_id", "tipo_mime", "tamano_bytes", "sha256", "creado_en", "sincronizado_en"}
EDITABLES = {"descripcion", "etiquetas", "atributos", "revision", "anotado_en", "anotado_por_id"}


def registrar(actor, evidencia, resultado, revision, correlacion):
    logger.info(json.dumps({"evento": "metadata_documental", "actor_id": actor.pk if actor else None,
        "evidencia_id": evidencia, "resultado": resultado, "revision": revision, "correlacion": correlacion}, sort_keys=True))


def fuera_transaccion():
    if connection.in_atomic_block or not connection.get_autocommit():
        raise MongoNoDisponible()


def fuentes():
    # Confirmar las dos relaciones SQL, no una FK Mongo del cliente.
    return EvidenciaTurno.objects.filter(obra_id=F("turno__obra_id"))


def fuente(evidencia):
    row = fuentes().filter(pk=evidencia).values(*CAMPOS_SQL).first()
    if row is None:
        raise NotFound("Recurso no disponible.")
    return row


def milisegundo(value):
    return value.astimezone(timezone.utc).replace(microsecond=(value.microsecond // 1000) * 1000)


def tecnico(row):
    return {"_id": f"evidencia_turno:{row['id']}", "version_esquema": 1, "origen": "EVIDENCIA_TURNO",
        "evidencia_id": Int64(row["id"]), "obra_id": Int64(row["obra_id"]), "turno_id": Int64(row["turno_id"]),
        "tipo_mime": row["tipo_mime"], "tamano_bytes": Int64(row["tamano"]), "sha256": row["sha256"],
        "creado_en": milisegundo(row["creado_en"])}


def validar_documento(doc, row):
    try:
        if set(doc) != TECNICOS | EDITABLES or len(BSON.encode(doc)) > 16384:
            raise ValueError()
        tech = tecnico(row)
        if any(doc.get(k) != v or (isinstance(v, Int64) and not isinstance(doc[k], Int64)) for k, v in tech.items()):
            raise ValueError()
        if type(doc["version_esquema"]) is not int or type(doc["revision"]) not in (int, Int64) or not 0 <= doc["revision"] <= BIGINT:
            raise ValueError()
        for key in ("creado_en", "sincronizado_en"):
            if not isinstance(doc[key], datetime) or doc[key].tzinfo is None:
                raise ValueError()
        if doc["revision"] == 0:
            if doc["anotado_en"] is not None or doc["anotado_por_id"] is not None or doc["descripcion"] or doc["etiquetas"] or doc["atributos"]:
                raise ValueError()
        elif not isinstance(doc["anotado_en"], datetime) or doc["anotado_en"].tzinfo is None or not isinstance(doc["anotado_por_id"], Int64) or not 0 < doc["anotado_por_id"] <= BIGINT:
            raise ValueError()
        validated = anotaciones(doc)
        if any(doc[key] != value for key, value in validated.items()):
            raise ValueError()
        return doc
    except (ValueError, TypeError, KeyError, ValidationError, OverflowError):
        raise MongoNoDisponible() from None


def representar(doc):
    return {key: doc[key].isoformat() if isinstance(doc[key], datetime) else doc[key] for key in PUBLICOS}


def sincronizar(row, col=None):
    fuera_transaccion()
    try:
        col = mongo.coleccion() if col is None else col
        tech = tecnico(row)
        ident = tech.pop("_id")
        tech["sincronizado_en"] = datetime.now(timezone.utc)
        defaults = {"descripcion": "", "etiquetas": [], "atributos": {}, "revision": 0, "anotado_en": None, "anotado_por_id": None}
        try:
            col.update_one({"_id": ident}, {"$set": tech, "$setOnInsert": defaults}, upsert=True)
        except DuplicateKeyError:
            # Dos inserciones simultáneas: solo refrescar espejo técnico.
            col.update_one({"_id": ident}, {"$set": tech})
    except PyMongoError:
        raise MongoNoDisponible() from None


def detalle(actor, evidencia, token=None):
    fuera_transaccion()
    revalidar(actor, token)
    row = fuente(evidencia)
    try:
        doc = mongo.coleccion().find_one({"_id": f"evidencia_turno:{evidencia}", "origen": "EVIDENCIA_TURNO"})
        if doc is None:
            raise MetadataPendiente()
        return representar(validar_documento(doc, row))
    except PyMongoError:
        raise MongoNoDisponible() from None


def editar(actor, evidencia, revision, cambios, correlacion, token=None):
    fuera_transaccion()
    actor = revalidar(actor, token)
    row = fuente(evidencia)
    try:
        col = mongo.coleccion()
        doc = col.find_one({"_id": f"evidencia_turno:{evidencia}"})
        if doc is None:
            raise MetadataPendiente()
        validar_documento(doc, row)
        candidato = {**doc, **cambios, "revision": revision + 1, "anotado_en": datetime.now(timezone.utc), "anotado_por_id": Int64(actor.pk)}
        validar_documento(candidato, row)
        actualizado = col.find_one_and_update({"_id": doc["_id"], "revision": revision},
            {"$set": {**cambios, "anotado_en": candidato["anotado_en"], "anotado_por_id": candidato["anotado_por_id"]}, "$inc": {"revision": 1}}, return_document=ReturnDocument.AFTER)
        if actualizado is None:
            raise RevisionObsoleta()
        registrar(actor, evidencia, "anotacion_actualizada", actualizado["revision"], correlacion)
        return representar(validar_documento(actualizado, row))
    except PyMongoError:
        raise MongoNoDisponible() from None


def listar(actor, obra, page, token=None):
    fuera_transaccion()
    revalidar(actor, token)
    if not Obra.objects.filter(pk=obra).exists():
        raise NotFound("Recurso no disponible.")
    try:
        # No autorizar por BSON: verificar cada candidato por lotes SQL. Evita
        # incluir huérfanos en count y mantiene memoria O(lote+25), no O(obra).
        col = mongo.coleccion()
        cursor = col.find({"obra_id": Int64(obra), "origen": "EVIDENCIA_TURNO"}).sort([("creado_en", -1), ("evidencia_id", -1)]).batch_size(200)
        count, results, lote = 0, [], []
        def consumir(lote):
            nonlocal count
            ids = [d.get("evidencia_id") for d in lote]
            if any(type(i) not in (int, Int64) or not 0 < i <= BIGINT for i in ids):
                raise MongoNoDisponible()
            rows = {r["id"]: r for r in fuentes().filter(obra_id=obra, pk__in=ids).values(*CAMPOS_SQL)}
            for doc in lote:
                row = rows.get(doc["evidencia_id"])
                if row is None:
                    # Un BSON no puede autorizar ni filtrar datos de otra obra.
                    raise MongoNoDisponible()
                validar_documento(doc, row)
                if (page - 1) * 25 <= count < page * 25:
                    results.append(representar(doc))
                count += 1
        try:
            for doc in cursor:
                lote.append(doc)
                if len(lote) == 200:
                    consumir(lote)
                    lote = []
            if lote:
                consumir(lote)
        finally:
            cursor.close()
        if page > max(1, (count + 24) // 25):
            raise ValidationError({"page": "Página fuera de rango."})
        return {"count": count, "results": results, "proyeccion": "EVENTUAL", "fuente_autoritativa": "POSTGRESQL"}
    except PyMongoError:
        raise MongoNoDisponible() from None
