from collections.abc import Mapping
from copy import copy

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import Cliente
from .services import guardar_cliente, validar_cliente


def ejecutar_validacion_modelo(operacion, *args, **kwargs):
    try:
        return operacion(*args, **kwargs)
    except DjangoValidationError as exc:
        errores = (
            exc.message_dict if hasattr(exc, "message_dict")
            else {"non_field_errors": exc.messages}
        )
        if "__all__" in errores:
            errores["non_field_errors"] = errores.pop("__all__")
        raise serializers.ValidationError(errores) from exc


class ClienteSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    tipo_cliente = serializers.ChoiceField(choices=Cliente.TipoCliente.choices)
    tipo_identificacion = serializers.ChoiceField(
        choices=Cliente.TipoIdentificacion.choices
    )
    numero_identificacion = serializers.CharField(
        required=False, allow_null=True, allow_blank=True
    )
    pais_identificacion = serializers.CharField(
        required=False, allow_null=True, allow_blank=True
    )
    tipo_documento_extranjero = serializers.CharField(
        required=False, allow_null=True, allow_blank=True
    )
    nombre_legal = serializers.CharField()
    nombre_contacto = serializers.CharField(required=False, allow_blank=True)
    correo = serializers.CharField(required=False, allow_blank=True)
    telefono = serializers.CharField(required=False, allow_blank=True)
    activo = serializers.BooleanField(read_only=True)
    creado_en = serializers.DateTimeField(read_only=True)
    actualizado_en = serializers.DateTimeField(read_only=True)

    def to_internal_value(self, data):
        if isinstance(data, Mapping):
            errores = {
                campo: "No es un campo permitido."
                for campo in data if campo not in self.fields
            }
            if "activo" in data:
                errores["activo"] = (
                    "Utilice la operación de activación/desactivación."
                )
            if errores:
                raise serializers.ValidationError(errores)
        return super().to_internal_value(data)

    def validate(self, attrs):
        candidato = copy(self.instance) if self.instance else Cliente()
        for campo, valor in attrs.items():
            setattr(candidato, campo, valor)
        ejecutar_validacion_modelo(validar_cliente, candidato)
        # Solo devuelve campos recibidos para no sobrescribir cambios ajenos.
        return {campo: getattr(candidato, campo) for campo in attrs}

    def create(self, validated_data):
        return ejecutar_validacion_modelo(guardar_cliente, validated_data)

    def update(self, instance, validated_data):
        return ejecutar_validacion_modelo(
            guardar_cliente, validated_data, instancia=instance
        )
