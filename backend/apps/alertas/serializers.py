from datetime import date, datetime, time, timedelta, timezone as utc
import re
from zoneinfo import ZoneInfo

from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from .catalogo import CATALOGO, ESTADOS, RECURSOS, MAX_PK

ZONA = ZoneInfo("America/Santiago")
FILTROS = {"estado", "tipo", "recurso_tipo", "recurso_id", "desde", "hasta", "page"}


def entero(valor, campo):
    if type(valor) is not str or not re.fullmatch(r"[0-9]{1,19}", valor) or not 0 < int(valor) <= MAX_PK:
        raise ValidationError({campo: "Indique un entero decimal positivo dentro de rango."})
    return int(valor)


def inicio_civil(dia):
    return datetime.combine(dia, time.min, tzinfo=ZONA).astimezone(utc.utc).astimezone(ZONA)


def validar_query(params, permitidos):
    if set(params) - set(permitidos):
        raise ValidationError({"query": "Parámetro no permitido."})
    if any(len(params.getlist(k)) != 1 or params[k] == "" for k in params):
        raise ValidationError({"query": "Parámetro repetido o vacío."})
    out = dict(params.items())
    for campo, opciones in [("estado", {*ESTADOS, "TODAS"}), ("tipo", CATALOGO), ("recurso_tipo", RECURSOS)]:
        if campo in out and out[campo] not in opciones:
            raise ValidationError({campo: "Valor no permitido."})
    for campo in ("page", "recurso_id"):
        if campo in out:
            out[campo] = entero(out[campo], campo)
    if "recurso_id" in out and "recurso_tipo" not in out:
        raise ValidationError({"recurso_id": "Requiere recurso_tipo."})
    if "tipo" in out and "recurso_tipo" in out and CATALOGO[out["tipo"]].recurso != out["recurso_tipo"]:
        raise ValidationError({"recurso_tipo": "No corresponde al tipo de alerta."})
    if ("desde" in out) != ("hasta" in out):
        raise ValidationError({"desde": "Indique desde y hasta conjuntamente."})
    if "desde" in out:
        try:
            for campo in ("desde", "hasta"):
                if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", out[campo]):
                    raise ValueError()
                out[campo] = date.fromisoformat(out[campo])
            if out["desde"] > out["hasta"] or (out["hasta"] - out["desde"]).days >= 366 or out["hasta"] == date.max:
                raise ValueError()
        except ValueError:
            raise ValidationError({"desde": "Rango civil inválido; máximo 366 días inclusivos."}) from None
    return out


def filtrar(qs, filtros):
    estado = filtros.get("estado")
    if estado is None:
        qs = qs.filter(estado__in=["PENDIENTE", "ATENDIDA"])
    elif estado != "TODAS":
        qs = qs.filter(estado=estado)
    for campo in ("tipo", "recurso_tipo", "recurso_id"):
        if campo in filtros:
            qs = qs.filter(**{campo: filtros[campo]})
    if "desde" in filtros:
        qs = qs.filter(creado_en__gte=inicio_civil(filtros["desde"]), creado_en__lt=inicio_civil(filtros["hasta"] + timedelta(days=1)))
    return qs


class AtenderSerializer(serializers.Serializer):
    motivo = serializers.CharField(max_length=2000, trim_whitespace=True)

    def to_internal_value(self, data):
        if type(data) is not dict or set(data) != {"motivo"} or type(data["motivo"]) is not str:
            raise ValidationError({"motivo": "Se requiere únicamente motivo como string."})
        # La longitud contractual se aplica después del trim.
        return super().to_internal_value({"motivo": data["motivo"].strip()})


class FechaSantiago(serializers.DateTimeField):
    def __init__(self, **kwargs):
        super().__init__(default_timezone=ZONA, **kwargs)


class AlertaSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    tipo = serializers.CharField()
    estado = serializers.CharField()
    severidad = serializers.CharField()
    rol_destinatario = serializers.CharField()
    recurso_tipo = serializers.CharField()
    recurso_id = serializers.IntegerField()
    recurso_codigo = serializers.SerializerMethodField()
    obra = serializers.SerializerMethodField()
    titulo = serializers.SerializerMethodField()
    descripcion = serializers.SerializerMethodField()
    creado_en = FechaSantiago()
    atendida_por = serializers.IntegerField(source="atendida_por_id", allow_null=True)
    atendida_en = FechaSantiago(allow_null=True)
    motivo_atencion = serializers.CharField(allow_null=True)
    resuelta_en = FechaSantiago(allow_null=True)
    acciones_permitidas = serializers.SerializerMethodField()

    def _contexto(self, obj):
        return self.context["recursos"].get((obj.tipo, obj.recurso_id), {})

    def get_recurso_codigo(self, obj):
        return self._contexto(obj).get("recurso_codigo")

    def get_obra(self, obj):
        return self._contexto(obj).get("obra")

    def get_titulo(self, obj):
        return CATALOGO[obj.tipo].titulo

    def get_descripcion(self, obj):
        return CATALOGO[obj.tipo].descripcion

    def get_acciones_permitidas(self, obj):
        return ["ATENDER"] if obj.estado == "PENDIENTE" and self._contexto(obj).get("vigente", False) else []


class AlertaEventoSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    alerta = serializers.IntegerField(source="alerta_id")
    tipo = serializers.CharField()
    estado_anterior = serializers.CharField(allow_null=True)
    estado_nuevo = serializers.CharField()
    actor = serializers.IntegerField(source="actor_id", allow_null=True)
    motivo = serializers.CharField(allow_blank=True)
    registrado_en = FechaSantiago()
