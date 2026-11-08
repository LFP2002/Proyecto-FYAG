"""Contratos estrictos 004B-3: importes netos solo para Gerencia/Supervisor."""

from decimal import Decimal

from rest_framework import serializers

from apps.comercial.serializers_presupuestos import DecimalTextoField

from .models import GastoObra
from .serializers import (
    ContratoEstrictoSerializer, FechaISOField, TextoEstrictoField,
)


class GastoCrearSerializer(ContratoEstrictoSerializer):
    tipo = serializers.ChoiceField(choices=GastoObra.Tipo.choices)
    descripcion = TextoEstrictoField(max_length=500)
    unidad = TextoEstrictoField(max_length=30)
    cantidad = DecimalTextoField(
        max_digits=12, decimal_places=3, min_value=Decimal("0.001"),
    )
    costo_unitario_neto = DecimalTextoField(
        max_digits=15, decimal_places=2, min_value=Decimal("0.00"),
    )
    fecha_gasto = FechaISOField()
    referencia_respaldo = TextoEstrictoField(
        max_length=500, required=False, allow_blank=True, default="",
    )
    observacion = TextoEstrictoField(
        max_length=2000, required=False, allow_blank=True, default="",
    )


class GastoEditarSerializer(ContratoEstrictoSerializer):
    tipo = serializers.ChoiceField(
        choices=GastoObra.Tipo.choices, required=False,
    )
    descripcion = TextoEstrictoField(max_length=500, required=False)
    unidad = TextoEstrictoField(max_length=30, required=False)
    cantidad = DecimalTextoField(
        max_digits=12, decimal_places=3, min_value=Decimal("0.001"),
        required=False,
    )
    costo_unitario_neto = DecimalTextoField(
        max_digits=15, decimal_places=2, min_value=Decimal("0.00"),
        required=False,
    )
    fecha_gasto = FechaISOField(required=False)
    referencia_respaldo = TextoEstrictoField(
        max_length=500, required=False, allow_blank=True,
    )
    observacion = TextoEstrictoField(
        max_length=2000, required=False, allow_blank=True,
    )
    motivo = TextoEstrictoField(
        max_length=2000, required=False, allow_blank=True, default="",
    )


class DevolucionSerializer(ContratoEstrictoSerializer):
    cantidad = DecimalTextoField(
        max_digits=12, decimal_places=3, min_value=Decimal("0.001"),
    )
    fecha_devolucion = FechaISOField()
    motivo = TextoEstrictoField(max_length=2000)


class GastoLecturaSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    obra = serializers.IntegerField(source="obra_id", read_only=True)
    tipo = serializers.CharField(read_only=True)
    descripcion = serializers.CharField(read_only=True)
    unidad = serializers.CharField(read_only=True)
    cantidad = serializers.DecimalField(
        max_digits=12, decimal_places=3, coerce_to_string=True, read_only=True,
    )
    cantidad_devuelta = serializers.DecimalField(
        max_digits=12, decimal_places=3, coerce_to_string=True, read_only=True,
    )
    costo_unitario_neto = serializers.DecimalField(
        max_digits=15, decimal_places=2, coerce_to_string=True, read_only=True,
    )
    subtotal = serializers.SerializerMethodField()
    fecha_gasto = serializers.DateField(read_only=True)
    referencia_respaldo = serializers.CharField(read_only=True)
    observacion = serializers.CharField(read_only=True)
    vigente = serializers.BooleanField(read_only=True)
    anulado_por = serializers.IntegerField(
        source="anulado_por_id", read_only=True, allow_null=True,
    )
    anulado_en = serializers.DateTimeField(read_only=True, allow_null=True)
    motivo_anulacion = serializers.CharField(read_only=True)
    registrado_por = serializers.IntegerField(
        source="registrado_por_id", read_only=True,
    )
    creado_en = serializers.DateTimeField(read_only=True)
    actualizado_en = serializers.DateTimeField(read_only=True)

    def get_subtotal(self, gasto):
        return str(gasto.subtotal)


class CostoObraEventoSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    obra = serializers.IntegerField(source="obra_id", read_only=True)
    gasto = serializers.IntegerField(source="gasto_id", read_only=True, allow_null=True)
    control = serializers.IntegerField(source="control_id", read_only=True, allow_null=True)
    cortesia = serializers.IntegerField(source="cortesia_id", read_only=True, allow_null=True)
    tipo = serializers.CharField(read_only=True)
    registrado_por = serializers.IntegerField(
        source="registrado_por_id", read_only=True,
    )
    motivo = serializers.CharField(read_only=True)
    datos_anteriores = serializers.JSONField(read_only=True)
    datos_nuevos = serializers.JSONField(read_only=True)
    creado_en = serializers.DateTimeField(read_only=True)
