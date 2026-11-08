"""Entradas 004B-4: sin importes, versiones ni auditoría del cliente."""
from rest_framework import serializers

from .models import ControlCostosObra
from .serializers import ContratoEstrictoSerializer, TextoEstrictoField


class DeclaracionCostosSerializer(ContratoEstrictoSerializer):
    materiales_estado = serializers.ChoiceField(choices=["CON_REGISTROS", "NO_APLICA"], required=False)
    otros_estado = serializers.ChoiceField(choices=["CON_REGISTROS", "NO_APLICA"], required=False)
    materiales_justificacion = TextoEstrictoField(max_length=2000, allow_blank=True, required=False)
    otros_justificacion = TextoEstrictoField(max_length=2000, allow_blank=True, required=False)
    motivo = TextoEstrictoField(max_length=2000, allow_blank=True, required=False)


class CortesiaEntradaSerializer(ContratoEstrictoSerializer):
    justificacion = TextoEstrictoField(max_length=2000)
    motivo = TextoEstrictoField(max_length=2000, allow_blank=True, required=False)


class ControlCostosSerializer(serializers.ModelSerializer):
    obra = serializers.IntegerField(source="obra_id", read_only=True)
    validado_por = serializers.IntegerField(source="validado_por_id", read_only=True, allow_null=True)
    costos_validados = serializers.BooleanField(read_only=True)

    class Meta:
        model = ControlCostosObra
        fields = ("id", "obra", "materiales_estado", "materiales_justificacion",
                  "otros_estado", "otros_justificacion", "version_actual", "version_validada",
                  "validado_por", "validado_en", "costos_validados", "creado_en", "actualizado_en")
        read_only_fields = fields


class ResumenFinanzasSerializer(serializers.Serializer):
    obra = serializers.IntegerField(read_only=True)
    materiales_total = serializers.CharField(read_only=True)
    otros_total = serializers.CharField(read_only=True)
    mano_obra_total = serializers.CharField(read_only=True)
    costo_total = serializers.CharField(read_only=True)
    costos_validados = serializers.BooleanField(read_only=True)
    cortesia_sin_cobro = serializers.BooleanField(read_only=True)


class ResumenCostosSerializer(ResumenFinanzasSerializer):
    materiales_estado = serializers.CharField(read_only=True)
    otros_estado = serializers.CharField(read_only=True)
    materiales_justificacion = serializers.CharField(read_only=True)
    otros_justificacion = serializers.CharField(read_only=True)
    version_actual = serializers.IntegerField(read_only=True)
    version_validada = serializers.IntegerField(read_only=True, allow_null=True)
    validado_por = serializers.IntegerField(read_only=True, allow_null=True)
    validado_en = serializers.CharField(read_only=True, allow_null=True)
    cortesia_justificacion = serializers.CharField(read_only=True, allow_null=True)
    provisional = serializers.BooleanField(read_only=True)
