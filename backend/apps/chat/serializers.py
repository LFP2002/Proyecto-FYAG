from datetime import timezone as utc

from rest_framework import serializers

from .models import ConversacionChat, MensajeChat, ArchivoChat


def usuario_minimo(user):
    return {'id': user.pk, 'nombre': user.get_full_name().strip() or user.username, 'rol': user.rol}


class FechaUTC(serializers.DateTimeField):
    def __init__(self, **kwargs):
        super().__init__(default_timezone=utc.utc, **kwargs)


class ConversacionSerializer(serializers.ModelSerializer):
    creado_en = FechaUTC(read_only=True)
    no_leidos = serializers.IntegerField(read_only=True, default=0)
    ultimo_mensaje = serializers.SerializerMethodField()

    def get_ultimo_mensaje(self, obj):
        if getattr(obj, 'preview_id', None) is None:
            return None
        return {'id': obj.preview_id, 'autor': obj.preview_autor, 'texto': obj.preview_texto,
                'creado_en': FechaUTC().to_representation(obj.preview_creado),
                'vence_en': FechaUTC().to_representation(obj.preview_vence)}

    class Meta:
        model = ConversacionChat
        fields = ['id', 'tipo', 'titulo', 'creador', 'creado_en', 'no_leidos', 'ultimo_mensaje']
        read_only_fields = fields


class ArchivoSerializer(serializers.ModelSerializer):
    class Meta:
        model = ArchivoChat
        fields = ['id', 'nombre', 'mime', 'tamano_bytes']
        read_only_fields = fields


class MensajeSerializer(serializers.ModelSerializer):
    creado_en = FechaUTC(read_only=True)
    vence_en = FechaUTC(read_only=True)
    archivo = ArchivoSerializer(read_only=True, allow_null=True)

    class Meta:
        model = MensajeChat
        fields = ['id', 'conversacion', 'autor', 'texto', 'creado_en', 'vence_en', 'archivo', 'clave_idempotencia']
        read_only_fields = fields
