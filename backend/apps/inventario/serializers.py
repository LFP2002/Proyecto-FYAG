from rest_framework import serializers

from .models import ArticuloInventario, ExistenciaInventario, MovimientoInventario


class ArticuloSerializer(serializers.ModelSerializer):
    class Meta:
        model = ArticuloInventario
        fields = ["id", "codigo", "nombre", "descripcion", "unidad", "activo", "creado_por", "actualizado_por", "creado_en", "actualizado_en"]
        read_only_fields = fields


class ExistenciaSerializer(serializers.ModelSerializer):
    codigo = serializers.CharField(source="articulo.codigo")
    unidad = serializers.CharField(source="articulo.unidad")
    saldo = serializers.DecimalField(max_digits=12, decimal_places=3, coerce_to_string=True)

    class Meta:
        model = ExistenciaInventario
        fields = ["articulo", "codigo", "unidad", "saldo"]
        read_only_fields = fields


class MovimientoSerializer(serializers.ModelSerializer):
    cantidad = serializers.DecimalField(max_digits=12, decimal_places=3, coerce_to_string=True)
    saldo_anterior = serializers.DecimalField(max_digits=12, decimal_places=3, coerce_to_string=True)
    saldo_posterior = serializers.DecimalField(max_digits=12, decimal_places=3, coerce_to_string=True)

    class Meta:
        model = MovimientoInventario
        fields = ["id", "articulo", "tipo", "clave_idempotencia", "cantidad", "saldo_anterior", "saldo_posterior", "referencia", "motivo", "actor", "creado_en"]
        read_only_fields = fields
