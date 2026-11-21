from rest_framework import serializers

from .models import OperacionMaterial


class OperacionSerializer(serializers.ModelSerializer):
    cantidad = serializers.DecimalField(max_digits=12, decimal_places=3, coerce_to_string=True)
    movimiento = serializers.PrimaryKeyRelatedField(read_only=True, allow_null=True)
    class Meta:
        model = OperacionMaterial
        fields = ['id', 'tipo', 'articulo', 'obra', 'autorizacion', 'entrega', 'ingreso', 'movimiento', 'cantidad', 'unidad',
                  'clave_idempotencia', 'referencia', 'motivo', 'actor', 'creado_en']
        read_only_fields = fields


class OperacionCostoSerializer(OperacionSerializer):
    class Meta(OperacionSerializer.Meta):
        fields = OperacionSerializer.Meta.fields + ['gasto', 'costo_unitario_neto', 'saldo_valorado_anterior',
            'saldo_valorado_posterior', 'promedio_anterior', 'promedio_posterior']
        read_only_fields = fields
