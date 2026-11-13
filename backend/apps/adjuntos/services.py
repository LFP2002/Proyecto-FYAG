import hashlib
import json
import logging
import os
from uuid import uuid4

from django.db import connection, transaction
from rest_framework.exceptions import NotFound, ValidationError

from apps.comercial.models import Presupuesto
from apps.finanzas.models import DocumentoCobro
from apps.obras.models import Obra
from . import almacen, contenido, scanner
from .exceptions import AlmacenNoDisponible, ConflictoAdjunto
from .models import AdjuntoDocumento
from .permissions import actor_actual, autorizar_tipo, miembro
from .validaciones import nombre_visible

logger = logging.getLogger(__name__)


def registrar(actor, adjunto, evento, resultado, correlacion):
    logger.info(json.dumps({"actor_id": actor.pk if actor else None, "adjunto_id": adjunto,
        "evento": evento, "resultado": resultado, "correlacion": correlacion}, sort_keys=True))


def parent(tipo, ident, actor, escribir=False, bloquear=False, estado=True):
    autorizar_tipo(actor, tipo, escribir)
    if tipo == "RESPALDO_FACTURA":
        doc = DocumentoCobro.objects.filter(pk=ident).first()
        if doc is None:
            raise NotFound("Recurso no disponible.")
        obra_id = doc.obra_id
    else:
        doc = None
        obra_id = ident
    obra = Obra.objects.filter(pk=obra_id).first()
    if obra is None:
        raise NotFound("Recurso no disponible.")
    if bloquear:
        # Orden compatible con Obras/Finanzas: Presupuesto -> Obra -> Documento.
        Presupuesto.objects.select_for_update().get(pk=obra.presupuesto_id)
        obra = Obra.objects.select_for_update().get(pk=obra_id)
        if doc is not None:
            doc = DocumentoCobro.objects.select_for_update().get(pk=ident)
            if doc.obra_id != obra.pk:
                raise ConflictoAdjunto("origen_inconsistente")
    miembro(actor, obra.pk)
    if escribir and estado:
        if doc is not None and doc.estado != "VIGENTE":
            raise ConflictoAdjunto("documento_no_vigente")
        if doc is None and obra.estado not in ({"EN_PROCESO"} if actor.rol == "TECNICO" else {"EN_PROCESO", "SUSPENDIDA", "FINALIZADA"}):
            raise ConflictoAdjunto("obra_no_admite_adjuntos")
    return doc if doc is not None else obra


def autorizado(actor, ident, token=None, editar=False):
    actor = actor_actual(actor, token)
    adjunto = AdjuntoDocumento.objects.filter(pk=ident).first()
    if adjunto is None:
        raise NotFound("Recurso no disponible.")
    # La edición de notas no exige estado de carga; sí membresía activa.
    parent(adjunto.tipo, adjunto.documento_cobro_id or adjunto.obra_id, actor, escribir=editar, estado=False)
    return actor, adjunto


def representar(adjunto):
    return {"id": adjunto.pk, "tipo": adjunto.tipo,
        "destino": {"documento_cobro": adjunto.documento_cobro_id} if adjunto.documento_cobro_id else {"obra": adjunto.obra_id},
        "nombre_visible": adjunto.nombre_visible, "mime": adjunto.mime, "tamano_bytes": adjunto.tamano_bytes,
        "estado": adjunto.estado, "registrado_por": adjunto.registrado_por_id, "registrado_en": adjunto.registrado_en.isoformat()}


def listado(actor, tipo, destino, page, token=None):
    actor = actor_actual(actor, token)
    parent(tipo, destino, actor)
    filtros = {"documento_cobro_id" if tipo == "RESPALDO_FACTURA" else "obra_id": destino}
    # REPEATABLE READ local para count y página, ninguna operación remota.
    if connection.in_atomic_block:
        raise ConflictoAdjunto("transaccion_no_admitida")
    with transaction.atomic():
        with connection.cursor() as cur:
            cur.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        actor = actor_actual(actor, token)
        parent(tipo, destino, actor)
        qs = AdjuntoDocumento.objects.filter(tipo=tipo, **filtros).order_by("-registrado_en", "-pk")
        count = qs.count()
        if page > max(1, (count + 24)//25):
            raise ValidationError({"page": "Página fuera de rango."})
        return {"count": count, "results": [representar(a) for a in qs[(page-1)*25:page*25]]}


def preflight(actor, tipo, destino, key, token=None):
    actor = actor_actual(actor, token)
    existente = AdjuntoDocumento.objects.filter(clave_idempotencia=key).first()
    parent(tipo, destino, actor, escribir=True, estado=existente is None)
    if existente and (existente.registrado_por_id != actor.pk or existente.tipo != tipo or (existente.documento_cobro_id or existente.obra_id) != destino):
        raise ConflictoAdjunto("idempotencia_conflicto")
    return actor


def _replay(existente, huella):
    if existente.huella_solicitud != huella:
        raise ConflictoAdjunto("idempotencia_conflicto")
    # Un replay no acepta como disponible un archivo perdido/corrupto.
    almacen.copia_verificada(existente).close()
    return existente, False


def subir(actor, tipo, destino, key, data, correlacion, token=None):
    if connection.in_atomic_block or not connection.get_autocommit():
        raise ConflictoAdjunto("transaccion_no_admitida")
    actor = preflight(actor, tipo, destino, key, token)
    publicacion = None
    confirmado = False
    try:
        with almacen.Staging() as stage:
            mime, size, sha, raw_sha = contenido.preparar(data["archivo"], stage)
            visible = nombre_visible(data.get("nombre_visible", data["archivo"].name))
            extension = {"application/pdf": ".pdf", "image/jpeg": ".jpg", "image/png": ".png"}[mime]
            if "." not in visible:
                visible = nombre_visible(visible+extension)
            if os.path.splitext(visible)[1].lower() not in ({".jpg", ".jpeg"} if mime == "image/jpeg" else {extension}):
                raise ValidationError({"nombre_visible": "Extensión incompatible con contenido validado."})
            huella = hashlib.sha256(json.dumps([actor.pk, tipo, destino, visible, sha, raw_sha], ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
            existente = AdjuntoDocumento.objects.filter(clave_idempotencia=key).first()
            if existente:
                preflight(actor, tipo, destino, key, token)
                result = _replay(existente, huella)
                registrar(actor, existente.pk, "subida_adjunto", "replay", correlacion)
                return result
            scanner.analizar(stage.file)  # Nunca bajo locks SQL.
            with transaction.atomic(durable=True):
                # Serializa también una misma key que apunte a destinos distintos.
                lock = int.from_bytes(hashlib.sha256(key.bytes).digest()[:8], "big", signed=True)
                with connection.cursor() as cur:
                    cur.execute("SET LOCAL lock_timeout = '5s'")
                    cur.execute("SELECT pg_advisory_xact_lock(%s)", [lock])
                actor = actor_actual(actor, token)
                parent(tipo, destino, actor, escribir=True, bloquear=True, estado=False)
                existente = AdjuntoDocumento.objects.filter(clave_idempotencia=key).first()
                if existente:
                    return _replay(existente, huella)
                parent(tipo, destino, actor, escribir=True)
                fk = {"documento_cobro_id" if tipo == "RESPALDO_FACTURA" else "obra_id": destino}
                if AdjuntoDocumento.objects.filter(tipo=tipo, **fk).count() >= 10:
                    raise ConflictoAdjunto("limite_adjuntos")
                key_interna = uuid4()
                stage.publicar(key_interna)
                publicacion = key_interna
                adjunto = AdjuntoDocumento.objects.create(tipo=tipo, **fk, nombre_visible=visible,
                    clave_interna=key_interna, mime=mime, tamano_bytes=size, sha256=sha,
                    registrado_por=actor, clave_idempotencia=key, huella_solicitud=huella)
            confirmado = True  # Commit exterior terminado, antes de liberar staging.
        registrar(actor, adjunto.pk, "subida_adjunto", "disponible", correlacion)
        return adjunto, True
    except BaseException:
        if publicacion is not None and not confirmado:
            # Si la confirmación SQL fue ambigua (pérdida de conexión al commit),
            # jamás borrar bytes posiblemente referenciados. Conservar huérfano
            # diagnosticable si no se puede determinar el resultado SQL.
            try:
                referenciado = AdjuntoDocumento.objects.filter(clave_interna=publicacion).exists()
            except Exception:
                referenciado = True
            if not referenciado:
                almacen.retirar_publicado_propio(publicacion)
        raise
