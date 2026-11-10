from rest_framework import serializers

from .models import Usuario, UsuarioEvento


class ContratoEstrictoSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if not isinstance(data, dict):
            raise serializers.ValidationError({"non_field_errors": ["Se requiere un objeto JSON."]})
        unknown = {key: ["Campo no permitido o administrado por el servidor."] for key in data if key not in self.fields}
        if unknown:
            raise serializers.ValidationError(unknown)
        return super().to_internal_value(data)


class TextoEstricto(serializers.CharField):
    def to_internal_value(self, data):
        if not isinstance(data, str):
            self.fail("invalid")
        return super().to_internal_value(data)


class EmailEstricto(TextoEstricto, serializers.EmailField):
    def to_internal_value(self, data):
        return super().to_internal_value(data).strip().lower()


class PerfilUsuarioSerializer(ContratoEstrictoSerializer):
    email = EmailEstricto(max_length=254, required=False)
    username = TextoEstricto(max_length=150, required=False)
    first_name = TextoEstricto(max_length=150, required=False, allow_blank=True)
    last_name = TextoEstricto(max_length=150, required=False, allow_blank=True)


class CrearUsuarioSerializer(PerfilUsuarioSerializer):
    email = EmailEstricto(max_length=254)
    username = TextoEstricto(max_length=150)
    rol = serializers.ChoiceField(choices=Usuario.Rol.choices)
    password = TextoEstricto(write_only=True, trim_whitespace=False, max_length=4096)


class MotivoUsuarioSerializer(ContratoEstrictoSerializer):
    motivo = TextoEstricto(max_length=2000)


class RolUsuarioSerializer(MotivoUsuarioSerializer):
    rol = serializers.ChoiceField(choices=Usuario.Rol.choices)


class EstablecerClaveSerializer(MotivoUsuarioSerializer):
    nueva_clave = TextoEstricto(write_only=True, trim_whitespace=False, max_length=4096)


class CambiarClavePropiaSerializer(ContratoEstrictoSerializer):
    clave_actual = TextoEstricto(write_only=True, trim_whitespace=False, max_length=4096)
    nueva_clave = TextoEstricto(write_only=True, trim_whitespace=False, max_length=4096)


class UsuarioLecturaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Usuario
        fields = ["id", "username", "email", "first_name", "last_name", "rol", "is_active", "date_joined"]
        read_only_fields = fields


class UsuarioEventoSerializer(serializers.ModelSerializer):
    datos_anteriores = serializers.SerializerMethodField()
    datos_nuevos = serializers.SerializerMethodField()

    def _publico(self, obj, field):
        if obj.tipo in {UsuarioEvento.Tipo.ESTABLECER_CLAVE, UsuarioEvento.Tipo.CAMBIO_CLAVE_PROPIA}:
            return {}
        data = getattr(obj, field)
        if not isinstance(data, dict):
            return {}
        return {key: value for key, value in data.items()
                if key in {"email", "username", "first_name", "last_name", "rol", "is_active"}
                and type(value) is (bool if key == "is_active" else str)}

    def get_datos_anteriores(self, obj):
        return self._publico(obj, "datos_anteriores")

    def get_datos_nuevos(self, obj):
        return self._publico(obj, "datos_nuevos")

    class Meta:
        model = UsuarioEvento
        fields = ["id", "usuario_objetivo", "actor", "tipo", "motivo", "datos_anteriores", "datos_nuevos", "creado_en"]
        read_only_fields = fields
