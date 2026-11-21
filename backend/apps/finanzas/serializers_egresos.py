from rest_framework import serializers

from .models import Egreso, EgresoEvento
from .serializers_documentos import EstrictoSerializer, Identificador, Texto, Importe
from .serializers_pagos import PagoCrearSerializer


class EgresoCrearSerializer(PagoCrearSerializer):
    categoria = serializers.ChoiceField(choices=Egreso.Categoria.choices)
    concepto = Texto(max_length=200)
    beneficiario = Texto(max_length=200)
    obra = Identificador(required=False, allow_null=True, default=None)


class EgresoAnularSerializer(EstrictoSerializer):
    motivo = Texto(max_length=2000)
    referencia_correccion = Texto(max_length=500)


class EgresoLecturaSerializer(serializers.ModelSerializer):
    monto = Importe(read_only=True)
    moneda = serializers.CharField(read_only=True, default="CLP")
    naturaleza = serializers.CharField(read_only=True, default="REGISTRO_ADMINISTRATIVO_DINERO_PAGADO")

    class Meta:
        model = Egreso
        fields = ["id", "naturaleza", "moneda", "monto", "fecha_pago", "categoria", "concepto", "beneficiario", "medio", "referencia_respaldo", "observacion", "obra", "registrado_por", "registrado_en", "activo", "anulado_por", "anulado_en", "motivo_anulacion", "referencia_correccion"]
        read_only_fields = fields


class EgresoRegistroSerializer(EgresoLecturaSerializer):
    """Replay del alta original, no del estado posterior de GET detalle."""
    def to_representation(self, instance):
        data = super().to_representation(instance)
        data.update(activo=True, anulado_por=None, anulado_en=None, motivo_anulacion=None, referencia_correccion=None)
        return data


class EgresoEventoSerializer(serializers.ModelSerializer):
    class Meta:
        model = EgresoEvento
        fields = ["id", "egreso", "tipo", "actor", "motivo", "creado_en"]
        read_only_fields = fields
