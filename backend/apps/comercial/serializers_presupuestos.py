"""Contrato HTTP de Presupuestos; las escrituras se delegan a servicios."""

from collections.abc import Mapping
from decimal import Decimal
import re

from rest_framework import serializers

from .calculos import sumar_monto_neto


class ContratoPresupuestoSerializer(serializers.Serializer):
    campos_administrados = frozenset({
        "id", "codigo", "estado", "presupuesto_origen", "creado_por",
        "creado_en", "actualizado_en", "moneda", "monto_neto", "subtotal",
        "presupuesto", "presupuesto_id", "registrado_por",
    })

    def to_internal_value(self, data):
        if isinstance(data, Mapping):
            errores = {
                campo: (
                    "Campo administrado por el servidor."
                    if campo in self.campos_administrados
                    else "No es un campo permitido."
                )
                for campo in data if campo not in self.fields
            }
            if errores:
                raise serializers.ValidationError(errores)
        return super().to_internal_value(data)


class StringEstrictoField(serializers.CharField):
    def to_internal_value(self, data):
        if not isinstance(data, str):
            self.fail("invalid")
        return super().to_internal_value(data)


class EnteroEstrictoField(serializers.IntegerField):
    def to_internal_value(self, data):
        if type(data) is not int:
            self.fail("invalid")
        return super().to_internal_value(data)


class BooleanoEstrictoField(serializers.BooleanField):
    def to_internal_value(self, data):
        if type(data) is not bool:
            self.fail("invalid", input=data)
        return data


class DecimalTextoField(serializers.DecimalField):
    default_error_messages = {
        "formato": "Envíe un string decimal con dígitos y punto opcional.",
    }

    def to_internal_value(self, data):
        if not isinstance(data, str):
            self.fail("formato")
        texto = data.strip()
        if not re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", texto):
            self.fail("formato")
        # DecimalField valida precisión/escala y convierte sin pasar por float.
        return super().to_internal_value(texto)


class PresupuestoEscrituraSerializer(ContratoPresupuestoSerializer):
    cliente = EnteroEstrictoField(min_value=1, max_value=9223372036854775807)
    descripcion = StringEstrictoField(max_length=2000)
    requiere_aprobacion_gerencia = BooleanoEstrictoField()


class PresupuestoItemEscrituraSerializer(ContratoPresupuestoSerializer):
    descripcion = StringEstrictoField(max_length=2000)
    cantidad = DecimalTextoField(
        max_digits=12, decimal_places=3, min_value=Decimal("0.001")
    )
    unidad = StringEstrictoField(max_length=30)
    precio_unitario = DecimalTextoField(
        max_digits=15, decimal_places=2, min_value=Decimal("0.00")
    )
    orden = EnteroEstrictoField(min_value=1, max_value=2147483647)


class PresupuestoAccionSerializer(ContratoPresupuestoSerializer):
    motivo = StringEstrictoField(
        max_length=2000, required=False, allow_blank=True, default=""
    )


class PresupuestoMotivoObligatorioSerializer(ContratoPresupuestoSerializer):
    motivo = StringEstrictoField(max_length=2000)


class PresupuestoRevisionSerializer(ContratoPresupuestoSerializer):
    """Sin overrides: crear-revision solo recibe un objeto vacío."""


class PresupuestoItemSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    presupuesto = serializers.IntegerField(
        source="presupuesto_id", read_only=True
    )
    descripcion = serializers.CharField(read_only=True)
    cantidad = serializers.DecimalField(
        max_digits=12, decimal_places=3, coerce_to_string=True, read_only=True
    )
    unidad = serializers.CharField(read_only=True)
    precio_unitario = serializers.DecimalField(
        max_digits=15, decimal_places=2, coerce_to_string=True, read_only=True
    )
    orden = serializers.IntegerField(read_only=True)
    subtotal = serializers.DecimalField(
        max_digits=24, decimal_places=2, coerce_to_string=True, read_only=True
    )


class PresupuestoListadoSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    codigo = serializers.CharField(read_only=True)
    cliente = serializers.IntegerField(source="cliente_id", read_only=True)
    descripcion = serializers.CharField(read_only=True)
    estado = serializers.CharField(read_only=True)
    requiere_aprobacion_gerencia = serializers.BooleanField(read_only=True)
    presupuesto_origen = serializers.IntegerField(
        source="presupuesto_origen_id", read_only=True, allow_null=True
    )
    creado_por = serializers.IntegerField(
        source="creado_por_id", read_only=True
    )
    creado_en = serializers.DateTimeField(read_only=True)
    actualizado_en = serializers.DateTimeField(read_only=True)
    moneda = serializers.CharField(read_only=True)
    monto_neto = serializers.SerializerMethodField()

    def get_monto_neto(self, obj):
        neto = sumar_monto_neto(item.subtotal for item in obj.lineas_respuesta)
        return format(neto, ".2f")


class PresupuestoDetalleSerializer(PresupuestoListadoSerializer):
    items = PresupuestoItemSerializer(
        source="lineas_respuesta", many=True, read_only=True
    )


class PresupuestoEventoSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    presupuesto = serializers.IntegerField(
        source="presupuesto_id", read_only=True
    )
    estado_anterior = serializers.CharField(read_only=True, allow_null=True)
    estado_nuevo = serializers.CharField(read_only=True)
    registrado_por = serializers.IntegerField(
        source="registrado_por_id", read_only=True
    )
    motivo = serializers.CharField(read_only=True)
    creado_en = serializers.DateTimeField(read_only=True)
