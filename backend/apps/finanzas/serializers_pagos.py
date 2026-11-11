from rest_framework import serializers

from .models import PagoDocumento
from .serializers_documentos import EstrictoSerializer, Texto, FechaISO, Importe
from .validaciones import hoy_santiago


class PagoCrearSerializer(EstrictoSerializer):
    monto = Importe()
    fecha_pago = FechaISO()
    medio = serializers.ChoiceField(choices=PagoDocumento.Medio.choices)
    referencia_respaldo = Texto(max_length=500)
    observacion = Texto(max_length=2000, required=False, allow_blank=True, default="")

    def validate_monto(self, value):
        if value <= 0:
            raise serializers.ValidationError("Debe ser estrictamente positivo.")
        return value

    def validate_fecha_pago(self, value):
        if value > hoy_santiago():
            raise serializers.ValidationError("No puede ser futura en Santiago.")
        return value


class PagoAnularSerializer(EstrictoSerializer):
    motivo = Texto(max_length=2000)
    referencia_reversion_externa = Texto(max_length=500)


class PagoLecturaSerializer(serializers.ModelSerializer):
    naturaleza = serializers.CharField(read_only=True, default="REGISTRO_ADMINISTRATIVO_DINERO_RECIBIDO")
    monto = Importe(read_only=True)

    class Meta:
        model = PagoDocumento
        fields = ["id", "naturaleza", "documento", "monto", "fecha_pago", "medio", "referencia_respaldo", "observacion", "registrado_por", "registrado_en", "activo", "anulado_por", "anulado_en", "motivo_anulacion", "referencia_reversion_externa"]
        read_only_fields = fields


class PagoRegistroSerializer(PagoLecturaSerializer):
    """Respuesta original reconstruible desde campos inmutables, aun tras anular.

    GET detalle expone el estado actual; POST repetido recupera la operación de
    alta, no cambia el estado actual ni repite el movimiento administrativo.
    """
    def to_representation(self, instance):
        data = super().to_representation(instance)
        data.update(activo=True, anulado_por=None, anulado_en=None, motivo_anulacion=None, referencia_reversion_externa=None)
        return data
