"""Contratos de query y salida; nunca exponer un JSONField crudo."""
from datetime import date, datetime, time, timedelta, timezone as utc_timezone
from decimal import Decimal, InvalidOperation, localcontext
import re
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from django.utils import timezone

from apps.finanzas.serializers_documentos import FinanzasEventoSerializer
from apps.usuarios.serializers_usuarios import UsuarioEventoSerializer
from .adapters import FUENTES

ZONA = ZoneInfo("America/Santiago")
MAX_PK = 9223372036854775807
PARAMETROS = {"modulo", "fuente", "tipo", "actor", "recurso_tipo", "recurso_id", "desde", "hasta", "limit"}
RECURSOS = {tipo for f in FUENTES.values() for tipo, _ in f.recursos}


def entero(value, nombre, minimo=1, maximo=MAX_PK):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{1,19}", value) or not minimo <= int(value) <= maximo:
        raise ValidationError({nombre: "Entero fuera de rango o mal formado."})
    return int(value)


def fecha(value, nombre):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        raise ValidationError({nombre: "Use YYYY-MM-DD."})
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValidationError({nombre: "Fecha civil inválida."}) from None


def filtros_query(params):
    desconocidos = set(params) - PARAMETROS
    if desconocidos:
        raise ValidationError({"query": "Parámetro desconocido."})
    if hasattr(params, "getlist") and any(len(params.getlist(k)) != 1 for k in params):
        raise ValidationError({"query": "Parámetro repetido."})
    out = dict(params.items())
    for key, opciones in [("modulo", {"COMERCIAL", "OBRAS", "FINANZAS", "USUARIOS"}), ("fuente", set(FUENTES)), ("recurso_tipo", RECURSOS)]:
        if key in out and out[key] not in opciones:
            raise ValidationError({key: "Valor no permitido."})
    for key in ("actor", "recurso_id"):
        if key in out:
            out[key] = entero(out[key], key)
    if "recurso_id" in out and "recurso_tipo" not in out:
        raise ValidationError({"recurso_id": "Requiere recurso_tipo."})
    if "tipo" in out and (not isinstance(out["tipo"], str) or not out["tipo"] or len(out["tipo"]) > 24):
        raise ValidationError({"tipo": "Tipo de evento inválido."})
    hoy = timezone.localdate(timezone=ZONA)
    hasta = fecha(out["hasta"], "hasta") if "hasta" in out else hoy
    try:
        desde = fecha(out["desde"], "desde") if "desde" in out else hasta - timedelta(days=29)
    except OverflowError:
        raise ValidationError({"desde": "Fecha civil fuera de rango."}) from None
    if desde > hasta or (hasta - desde).days + 1 > 366 or hasta == date.max:
        raise ValidationError({"desde": "Rango civil inválido; máximo 366 días inclusivos."})
    out.update(desde=desde.isoformat(), hasta=hasta.isoformat(), limit=entero(out.get("limit", "25"), "limit", maximo=50))
    return out


def inicio_civil(dia):
    # En el salto de medianoche, fold=0 y el round-trip resuelven el inicio
    # inexistente al primer instante real del día (01:00 en Santiago).
    candidato = datetime.combine(dia, time.min, tzinfo=ZONA)
    return candidato.astimezone(utc_timezone.utc).astimezone(ZONA)


def rango(filtros):
    return inicio_civil(date.fromisoformat(filtros["desde"])), inicio_civil(date.fromisoformat(filtros["hasta"]) + timedelta(days=1))


def decimal_publico(value, escala):
    if not isinstance(value, str) or len(value) > 80 or not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", value):
        return None
    try:
        numero = Decimal(value)
        partes = numero.as_tuple()
        enteros = max(len(partes.digits) + partes.exponent, 0)
        if not numero.is_finite() or len(partes.digits) > 38 or partes.exponent < -escala or enteros > 38 - escala:
            return None
        with localcontext() as ctx:
            ctx.prec = 50
            return format(numero, f".{escala}f")
    except (ValueError, InvalidOperation):
        return None


def proyectar(data, campos):
    if not isinstance(data, dict):
        return {}
    out = {}
    for key, tipo in campos.items():
        if key not in data:
            continue
        value = data[key]
        if value is None:
            out[key] = None
        elif type(tipo) is int:
            normal = decimal_publico(value, tipo)
            if normal is not None:
                out[key] = normal
        elif type(value) is tipo:
            out[key] = value
    return out


OBRA = {"estado": str, "categoria_servicio": int, "tecnico_responsable": int, "fecha_programada": str, "iniciado_en": str, "finalizado_en": str, "cancelado_en": str}
PARTICIPANTE = {"tecnico": int, "activo": bool, "asignado_por": int, "asignado_en": str, "desasignado_por": int, "desasignado_en": str, "origen_registro": str}
TURNO_OPERATIVO = {"iniciado_en": str, "terminado_en": str, "modo_cierre": str, "cerrado_por": int, "duracion_segundos": 6}
TURNO_SUPERVISOR = {**TURNO_OPERATIVO, "estado_revision": str, "descripcion_trabajo": str, "duracion_ajustada_segundos": int, "costo_hora_neto": 2, "revisado_por": int, "revisado_en": str, "observacion_revision": str}
COSTOS = {
    "GASTO": {"tipo": str, "cantidad": 3, "cantidad_devuelta": 3, "costo_unitario_neto": 2, "fecha_gasto": str, "vigente": bool},
    "CONTROL_COSTOS": {"materiales_estado": str, "otros_estado": str, "costos_validados": bool, "validado_por": int, "validado_en": str},
    "CORTESIA": {"tipo": str, "autorizado_por": int, "autorizado_en": str},
}


def snapshots(fuente, row, rol, recurso):
    if fuente.nombre == "PRESUPUESTO_EVENTO":
        return ({} if row["estado_anterior"] is None else {"estado": row["estado_anterior"]}, {"estado": row["estado_nuevo"]})
    obj = SimpleNamespace(**row)
    if fuente.nombre == "USUARIO_EVENTO":
        serial = UsuarioEventoSerializer()
        return serial.get_datos_anteriores(obj), serial.get_datos_nuevos(obj)
    if fuente.nombre == "FINANZAS_EVENTO":
        serial = FinanzasEventoSerializer()
        antes, despues = serial.get_datos_anteriores(obj), serial.get_datos_nuevos(obj)
        for data in (antes, despues):
            for key in ("monto", "monto_neto", "monto_impuesto", "monto_total"):
                if key in data:
                    value = decimal_publico(data[key], 2)
                    if value is None:
                        del data[key]
                    else:
                        data[key] = value
        return antes, despues
    campos = {"OBRA_EVENTO": OBRA, "PARTICIPANTE_EVENTO": PARTICIPANTE,
              "CATEGORIA_SERVICIO_EVENTO": {"nombre": str, "activo": bool},
              "TURNO_EVENTO": TURNO_SUPERVISOR if rol == "SUPERVISOR_OBRAS" else TURNO_OPERATIVO,
              "COSTO_OBRA_EVENTO": COSTOS.get(recurso, {})}[fuente.nombre]
    return proyectar(row["datos_anteriores"], campos), proyectar(row["datos_nuevos"], campos)


def normalizar_evento(fuente, row, rol):
    recurso, pk = fuente.recurso(row)
    antes, despues = snapshots(fuente, row, rol, recurso)
    etiqueta = None
    if rol == "ADMINISTRADOR_TI" and fuente.nombre == "USUARIO_EVENTO":
        etiqueta = " ".join(filter(None, (row["actor__first_name"].strip(), row["actor__last_name"].strip()))) or row["actor__username"]
    return {"id": f"{fuente.nombre}:{row['id']}", "evento_id": row["id"], "fuente": fuente.nombre,
            "modulo": fuente.modulo, "recurso_tipo": recurso, "recurso_id": pk, "tipo": fuente.tipo(row),
            "actor": row[fuente.actor], "actor_etiqueta": etiqueta, "motivo": row["motivo"] or "",
            "creado_en": row["creado_en"], "datos_anteriores": antes, "datos_nuevos": despues}


class FechaSantiago(serializers.DateTimeField):
    def __init__(self, **kwargs):
        super().__init__(default_timezone=ZONA, **kwargs)


class EventoPublicoSerializer(serializers.Serializer):
    id = serializers.CharField()
    evento_id = serializers.IntegerField()
    fuente = serializers.CharField()
    modulo = serializers.CharField()
    recurso_tipo = serializers.CharField()
    recurso_id = serializers.IntegerField()
    tipo = serializers.CharField()
    actor = serializers.IntegerField()
    actor_etiqueta = serializers.CharField(allow_null=True)
    motivo = serializers.CharField(allow_blank=True)
    creado_en = FechaSantiago()
    datos_anteriores = serializers.JSONField()
    datos_nuevos = serializers.JSONField()
