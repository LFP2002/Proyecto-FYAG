import re

from rest_framework import serializers

from .models import DocumentoCobro, FinanzasEvento, SNAPSHOT_FIELDS
from .validaciones import hoy_santiago, validar_montos
from django.core.exceptions import ValidationError as DjangoValidationError


class EstrictoSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if not isinstance(data, dict):
            raise serializers.ValidationError({"non_field_errors": ["Se requiere un objeto JSON."]})
        unknown = {key: ["Campo no permitido."] for key in data if key not in self.fields}
        if unknown:
            raise serializers.ValidationError(unknown)
        return super().to_internal_value(data)


class Texto(serializers.CharField):
    def to_internal_value(self, data):
        if not isinstance(data, str):
            self.fail("invalid")
        return super().to_internal_value(data)


class Identificador(serializers.IntegerField):
    def __init__(self, **kwargs):
        super().__init__(min_value=1, max_value=9223372036854775807, **kwargs)

    def to_internal_value(self, data):
        if type(data) is not int:
            self.fail("invalid")
        return super().to_internal_value(data)


class FechaISO(serializers.DateField):
    def to_internal_value(self, data):
        if not isinstance(data, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", data):
            self.fail("invalid", format="YYYY-MM-DD")
        return super().to_internal_value(data)


class Importe(serializers.DecimalField):
    def __init__(self, **kwargs):
        super().__init__(max_digits=38, decimal_places=2, coerce_to_string=True, **kwargs)

    def to_internal_value(self, data):
        if not isinstance(data, str) or len(data) > 39 or not re.fullmatch(r"[0-9]+(?:\.[0-9]{1,2})?", data):
            raise serializers.ValidationError("Use un string decimal no negativo de hasta dos decimales, sin exponentes.")
        return super().to_internal_value(data)


class DocumentoCrearSerializer(EstrictoSerializer):
    obra = Identificador()
    tipo_documento = serializers.ChoiceField(choices=DocumentoCobro.Tipo.choices)
    folio_externo = Texto(max_length=100, trim_whitespace=False)
    fecha_emision = FechaISO()
    fecha_vencimiento = FechaISO()
    monto_neto = Importe()
    monto_impuesto = Importe()
    monto_total = Importe()
    referencia_respaldo = Texto(max_length=500)

    def validate_folio_externo(self, value):
        if not re.fullmatch(r"[0-9]+", value):
            raise serializers.ValidationError("Conserve el folio externo exacto, solo dígitos ASCII sin espacios.")
        return value

    def validate(self, attrs):
        if attrs["fecha_emision"] > hoy_santiago():
            raise serializers.ValidationError({"fecha_emision": "No puede ser futura en Santiago."})
        if attrs["fecha_vencimiento"] < attrs["fecha_emision"]:
            raise serializers.ValidationError({"fecha_vencimiento": "No puede preceder a la emisión."})
        try:
            validar_montos(attrs["monto_neto"], attrs["monto_impuesto"], attrs["monto_total"], attrs["tipo_documento"])
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.message_dict if hasattr(exc, "message_dict") else exc.messages) from None
        return attrs


class DocumentoRevertirSerializer(EstrictoSerializer):
    motivo = Texto(max_length=2000)
    referencia_rectificacion_externa = Texto(max_length=500)


class SinCobroCrearSerializer(EstrictoSerializer):
    motivo_registro = Texto(max_length=2000)


def origen_financiero(obra):
    presupuesto = obra.presupuesto
    cliente = presupuesto.cliente
    cortesia = getattr(obra, "cortesia", None)
    return {
        "obra": obra.pk, "codigo_obra": obra.codigo,
        "presupuesto": presupuesto.pk, "codigo_presupuesto": presupuesto.codigo,
        "cliente": {"id": cliente.pk, "nombre_legal": cliente.nombre_legal,
                    "tipo_identificacion": cliente.tipo_identificacion,
                    "numero_identificacion": cliente.numero_identificacion,
                    "pais_identificacion": cliente.pais_identificacion,
                    "tipo_documento_extranjero": cliente.tipo_documento_extranjero},
        "moneda": "CLP", "monto_neto_aprobado": format(presupuesto.monto_neto, ".2f"),
        "finalizado_en": serializers.DateTimeField().to_representation(obra.finalizado_en),
        "cortesia": {"id": cortesia.pk, "tipo": cortesia.tipo} if cortesia else None,
    }


class OrigenFinancieroSerializer(serializers.Serializer):
    def to_representation(self, instance):
        return origen_financiero(instance)


class DocumentoLecturaSerializer(serializers.ModelSerializer):
    naturaleza = serializers.CharField(read_only=True, default="REGISTRO_ADMINISTRATIVO_DOCUMENTO_EXTERNO")
    origen = serializers.SerializerMethodField()
    monto_neto = Importe(read_only=True)
    monto_impuesto = Importe(read_only=True)
    monto_total = Importe(read_only=True)

    def get_origen(self, obj):
        return origen_financiero(obj.obra)

    class Meta:
        model = DocumentoCobro
        fields = ["id", "naturaleza", "origen", "tipo_documento", "folio_externo", "fecha_emision", "fecha_vencimiento", "monto_neto", "monto_impuesto", "monto_total", "referencia_respaldo", "estado", "registrado_por", "registrado_en", "revertido_por", "revertido_en", "motivo_reversion", "referencia_rectificacion_externa"]
        read_only_fields = fields


class FinanzasEventoSerializer(serializers.ModelSerializer):
    datos_anteriores = serializers.SerializerMethodField()
    datos_nuevos = serializers.SerializerMethodField()

    def snapshot(self, obj, field):
        data = getattr(obj, field)
        if not isinstance(data, dict):
            return {}
        return {key: value for key, value in data.items() if key in SNAPSHOT_FIELDS
                and type(value) is (int if key in {"obra", "cortesia"} else str)}

    def get_datos_anteriores(self, obj):
        return self.snapshot(obj, "datos_anteriores")

    def get_datos_nuevos(self, obj):
        return self.snapshot(obj, "datos_nuevos")

    class Meta:
        model = FinanzasEvento
        fields = ["id", "documento", "cierre_sin_cobro", "tipo", "actor", "motivo", "datos_anteriores", "datos_nuevos", "creado_en"]
        read_only_fields = fields
