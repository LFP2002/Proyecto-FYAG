from rest_framework import serializers

from .models import Merma, MermaEvento
from .services_mermas import importe


class MermaEventoSerializer(serializers.ModelSerializer):
    class Meta:
        model = MermaEvento
        fields = ['id', 'tipo', 'actor', 'motivo', 'creado_en']
        read_only_fields = fields


class MermaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Merma
        fields = ['id', 'ambito', 'articulo', 'obra', 'entrega', 'unidad', 'cantidad', 'tipo', 'motivo', 'referencia',
                  'actividad', 'corte_movimiento', 'informado_por', 'clave_idempotencia', 'creado_en', 'estado',
                  'decidido_por', 'decidido_en', 'motivo_decision', 'operacion']
        read_only_fields = fields

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if self.context.get('creacion'):
            data.update(estado='PENDIENTE', decidido_por=None, decidido_en=None, motivo_decision='', operacion=None)
        if self.context.get('detalle'):
            data['historial'] = MermaEventoSerializer(instance.eventos.all(), many=True).data
        return data


class MermaCostoSerializer(MermaSerializer):
    """Elegido exclusivamente después de RBAC; no usar como serializer público."""
    def to_representation(self, instance):
        data = super().to_representation(instance)
        op = None if self.context.get('creacion') else instance.operacion
        costo = op.costo_unitario_neto if instance.ambito == 'BODEGA' and op else (
            instance.entrega.costo_unitario_neto if instance.ambito == 'OBRA' else None)
        data['costo_unitario_neto'] = format(costo, '.2f') if costo is not None else None
        data['importe_perdida' if instance.ambito == 'BODEGA' else 'importe_informativo_no_aditivo'] = (
            format(importe(instance.cantidad, costo, estricto=False), '.2f') if costo is not None else None)
        return data
