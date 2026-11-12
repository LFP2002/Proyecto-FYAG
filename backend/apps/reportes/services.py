"""Materialización dentro del snapshot; la respuesta binaria solo lee un archivo."""
import json
import logging
from tempfile import TemporaryFile
from time import monotonic

from rest_framework.exceptions import ValidationError
from . import catalogo, consultas
from .consistencia import snapshot, ExportacionGrande
from .filtros import validar, query_estricta, ZONA
from .permissions import revalidar, POR_ROL
from .serializers import representar

logger = logging.getLogger(__name__)


def catalogo_visible(actor, params):
    actor = revalidar(actor)
    query_estricta(params, set())
    return {"moneda": "CLP", "zona_horaria": "America/Santiago", "formatos": list(catalogo.FORMATOS),
            "reportes": [{"tipo": t, "titulo": catalogo.TITULOS[t], "filtros": list(catalogo.FILTROS[t]), "formatos": list(catalogo.FORMATOS)} for t in POR_ROL[actor.rol]]}


def informacion(tipo, filtros, corte, totales):
    return {"count": totales["documentos" if tipo == "cobranzas" else "obras"], "totales": totales,
            "periodo": {"desde": filtros["desde"].isoformat(), "hasta": filtros["hasta"].isoformat()},
            "moneda": "CLP", "fecha_corte": corte.astimezone(ZONA).isoformat(),
            "filtros": {k: v.isoformat() if hasattr(v, "isoformat") else v for k, v in filtros.items() if k not in {"page", "formato"}}}


def listar(actor, tipo, params):
    with snapshot() as (corte, tiempo):
        revalidar(actor, tipo)
        filtros = validar(params, tipo, corte.astimezone(ZONA).date())
        qs = consultas.queryset(tipo, filtros, corte)
        info = informacion(tipo, filtros, corte, consultas.totales(tipo, qs, tiempo))
        page = filtros["page"]
        if page > max(1, (info["count"] + 24) // 25):
            raise ValidationError({"page": "Página fuera de rango."})
        offset = (page - 1) * 25
        info["results"] = list(representar(tipo, consultas.filas(tipo, qs[offset:offset + 25], tiempo)))
        tiempo.comprobar()
        return info, page


def registrar(actor, tipo, formato, correlacion, resultado, inicio, info=None, clase=None):
    # Solo valores de catálogo y metadatos operativos; no filtros libres/PII/SQL.
    event = {"evento": "exportacion_reportes", "actor_id": actor.pk, "rol": actor.rol,
             "tipo": tipo if tipo in catalogo.TIPOS else None, "formato": formato if formato in catalogo.FORMATOS else None,
             "fecha_corte": info["fecha_corte"] if info else None, "cantidad_filas": info["count"] if info else None,
             "resultado": resultado, "duracion_ms": round((monotonic() - inicio) * 1000, 3), "correlacion": correlacion}
    if clase:
        event["clase"] = clase
    logger.info(json.dumps(event, ensure_ascii=True, sort_keys=True))


def exportar(actor, tipo, params, correlacion, *, head=False):
    inicio = monotonic()
    formato = params.get("formato")
    info = archivo = None
    registrar(actor, tipo, formato, correlacion, "solicitud", inicio)
    try:
        with snapshot() as (corte, tiempo):
            actor = revalidar(actor, tipo)
            filtros = validar(params, tipo, corte.astimezone(ZONA).date(), exportar=True)
            qs = consultas.queryset(tipo, filtros, corte)
            if qs.count() > catalogo.MAX_FILAS:
                raise ExportacionGrande()
            info = informacion(tipo, filtros, corte, consultas.totales(tipo, qs, tiempo))
            nombre = f"fyag-{tipo}-{corte.astimezone(ZONA):%Y%m%d-%H%M%S}.{formato}"
            if head:
                tiempo.comprobar()
                registrar(actor, tipo, formato, correlacion, "validada_head_sin_generacion", inicio, info)
                return None, nombre, info
            from .exportadores import csv, xlsx, pdf
            from .exportadores.comun import ArchivoLimitado
            archivo = TemporaryFile(mode="w+b", prefix="fyag-reporte-")
            generador = {"csv": csv.generar, "xlsx": xlsx.generar, "pdf": pdf.generar}[formato]
            generador(tipo, representar(tipo, consultas.filas(tipo, qs, tiempo)), info, ArchivoLimitado(archivo, tiempo), tiempo)
            archivo.flush()
            archivo.seek(0, 2)
            if archivo.tell() > catalogo.MAX_BYTES:
                raise ExportacionGrande()
            tiempo.comprobar()
            archivo.seek(0)
        registrar(actor, tipo, formato, correlacion, "archivo_generado_no_confirma_descarga", inicio, info)
        return archivo, nombre, info
    except Exception as exc:
        if archivo is not None:
            archivo.close()
        registrar(actor, tipo, formato, correlacion, "error", inicio, info, type(exc).__name__)
        raise
