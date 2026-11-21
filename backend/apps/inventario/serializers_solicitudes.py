from rest_framework import serializers

from .models import ArticuloInventario, SolicitudMaterialObra, SolicitudMaterialEvento


class ArticuloSolicitableSerializer(serializers.ModelSerializer):
    class Meta:
        model = ArticuloInventario
        fields = ['id', 'codigo', 'nombre', 'unidad']
        read_only_fields = fields


class SolicitudSerializer(serializers.ModelSerializer):
    class Meta:
        model = SolicitudMaterialObra
        fields = ['id', 'obra', 'solicitante', 'articulo', 'unidad', 'cantidad_solicitada', 'justificacion', 'estado',
                  'cantidad_aprobada', 'motivo_decision', 'decidido_por', 'decidido_en', 'autorizacion', 'clave_idempotencia', 'creado_en']
        read_only_fields = fields


class SolicitudCreacionSerializer(SolicitudSerializer):
    """Replay de creación = imagen original, no proyección mutable de decisión."""
    def to_representation(self, instance):
        data = super().to_representation(instance)
        data.update(estado='PENDIENTE', cantidad_aprobada=None, motivo_decision='', decidido_por=None, decidido_en=None, autorizacion=None)
        return data


class SolicitudEventoSerializer(serializers.ModelSerializer):
    class Meta:
        model = SolicitudMaterialEvento
        fields = ['id', 'tipo', 'actor', 'motivo', 'cantidad_aprobada', 'autorizacion', 'creado_en']
        read_only_fields = fields


class SolicitudDetalleSerializer(SolicitudSerializer):
    historial = SolicitudEventoSerializer(source='eventos', many=True, read_only=True)

    class Meta(SolicitudSerializer.Meta):
        fields = SolicitudSerializer.Meta.fields + ['historial']
        read_only_fields = fields
