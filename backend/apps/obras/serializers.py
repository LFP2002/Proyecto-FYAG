"""Contratos HTTP explícitos y proyecciones de mínimo privilegio para Obras 004A."""

from collections.abc import Mapping
import re

from rest_framework import serializers


class ContratoEstrictoSerializer(serializers.Serializer):
    """DRF descarta campos desconocidos por defecto: aquí se rechazan."""

    def to_internal_value(self, data):
        if isinstance(data, Mapping):
            desconocidos = {
                campo: ["Campo no permitido o administrado por el servidor."]
                for campo in data if campo not in self.fields
            }
            if desconocidos:
                raise serializers.ValidationError(desconocidos)
        return super().to_internal_value(data)


class EnteroEstrictoField(serializers.IntegerField):
    def to_internal_value(self, data):
        if type(data) is not int:
            self.fail("invalid")
        return super().to_internal_value(data)


class TextoEstrictoField(serializers.CharField):
    def to_internal_value(self, data):
        if not isinstance(data, str):
            self.fail("invalid")
        return super().to_internal_value(data)


class FechaISOField(serializers.DateField):
    def to_internal_value(self, data):
        if data is None:
            return super().to_internal_value(data)
        if not isinstance(data, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", data):
            self.fail("invalid", format="YYYY-MM-DD")
        return super().to_internal_value(data)


ID = dict(min_value=1, max_value=9223372036854775807)


class ObraCrearSerializer(ContratoEstrictoSerializer):
    presupuesto = EnteroEstrictoField(**ID)
    categoria_servicio = EnteroEstrictoField(**ID)
    descripcion = TextoEstrictoField(max_length=2000)
    tecnico_responsable = EnteroEstrictoField(**ID, required=False, allow_null=True, default=None)
    fecha_programada = FechaISOField(required=False, allow_null=True, default=None)
    motivo = TextoEstrictoField(max_length=2000, allow_blank=True, required=False, default="")


class ObraEditarSerializer(ContratoEstrictoSerializer):
    categoria_servicio = EnteroEstrictoField(**ID, required=False)
    descripcion = TextoEstrictoField(max_length=2000, required=False)
    fecha_programada = FechaISOField(required=False, allow_null=True)
    motivo = TextoEstrictoField(max_length=2000, allow_blank=True, required=False)


class CambioTecnicoSerializer(ContratoEstrictoSerializer):
    tecnico_responsable = EnteroEstrictoField(**ID, allow_null=True)
    motivo = TextoEstrictoField(max_length=2000)


class MotivoObligatorioSerializer(ContratoEstrictoSerializer):
    motivo = TextoEstrictoField(max_length=2000)


class ParticipanteAsignarSerializer(MotivoObligatorioSerializer):
    tecnico = EnteroEstrictoField(**ID)


class ParticipanteSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    obra = serializers.IntegerField(source="obra_id", read_only=True)
    tecnico = serializers.IntegerField(source="tecnico_id", read_only=True)
    tecnico_nombre = serializers.SerializerMethodField()
    activo = serializers.BooleanField(read_only=True)
    es_responsable = serializers.SerializerMethodField()
    origen_registro = serializers.CharField(read_only=True)
    asignado_por = serializers.IntegerField(source="asignado_por_id", read_only=True, allow_null=True)
    asignado_en = serializers.DateTimeField(read_only=True, allow_null=True)
    motivo_asignacion = serializers.CharField(read_only=True)
    desasignado_por = serializers.IntegerField(source="desasignado_por_id", read_only=True, allow_null=True)
    desasignado_en = serializers.DateTimeField(read_only=True, allow_null=True)
    motivo_desasignacion = serializers.CharField(read_only=True)

    def get_tecnico_nombre(self, obj):
        return _nombre_usuario(obj.tecnico)

    def get_es_responsable(self, obj):
        return obj.tecnico_id == obj.obra.tecnico_responsable_id


class ParticipanteEventoSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    participante = serializers.IntegerField(source="participante_id", read_only=True)
    tipo = serializers.CharField(read_only=True)
    registrado_por = serializers.IntegerField(source="registrado_por_id", read_only=True)
    motivo = serializers.CharField(read_only=True)
    datos_anteriores = serializers.JSONField(read_only=True)
    datos_nuevos = serializers.JSONField(read_only=True)
    creado_en = serializers.DateTimeField(read_only=True)


class NombreCategoriaSerializer(ContratoEstrictoSerializer):
    nombre = TextoEstrictoField(max_length=100)


class RenombrarCategoriaSerializer(ContratoEstrictoSerializer):
    nombre = TextoEstrictoField(max_length=100)
    motivo = TextoEstrictoField(max_length=2000, required=False, allow_blank=True, default="")


class MotivoCategoriaSerializer(ContratoEstrictoSerializer):
    motivo = TextoEstrictoField(max_length=2000, required=False, allow_blank=True, default="")


def _nombre_usuario(usuario):
    if usuario is None:
        return None
    return usuario.get_full_name().strip() or usuario.username


class ObraLecturaSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    codigo = serializers.CharField(read_only=True)
    presupuesto = serializers.IntegerField(source="presupuesto_id", read_only=True)
    presupuesto_codigo = serializers.CharField(source="presupuesto.codigo", read_only=True)
    cliente = serializers.IntegerField(source="presupuesto.cliente_id", read_only=True)
    cliente_nombre = serializers.CharField(source="presupuesto.cliente.nombre_legal", read_only=True)
    categoria_servicio = serializers.IntegerField(source="categoria_servicio_id", read_only=True)
    categoria_nombre = serializers.CharField(source="categoria_servicio.nombre", read_only=True)
    descripcion = serializers.CharField(read_only=True)
    tecnico_responsable = serializers.IntegerField(source="tecnico_responsable_id", read_only=True, allow_null=True)
    tecnico_nombre = serializers.SerializerMethodField()
    fecha_programada = serializers.DateField(read_only=True, allow_null=True)
    iniciado_en = serializers.DateTimeField(read_only=True, allow_null=True)
    estado = serializers.CharField(read_only=True)
    finalizado_en = serializers.DateTimeField(read_only=True, allow_null=True)
    cancelado_en = serializers.DateTimeField(read_only=True, allow_null=True)
    creado_por = serializers.IntegerField(source="creado_por_id", read_only=True)
    creado_en = serializers.DateTimeField(read_only=True)
    actualizado_en = serializers.DateTimeField(read_only=True)

    def get_tecnico_nombre(self, obj):
        return _nombre_usuario(obj.tecnico_responsable)


class ObraFinanzasSerializer(serializers.Serializer):
    """AF no ve descripción libre, auditoría ni datos financieros de presupuestos."""

    id = serializers.IntegerField(read_only=True)
    codigo = serializers.CharField(read_only=True)
    presupuesto = serializers.IntegerField(source="presupuesto_id", read_only=True)
    presupuesto_codigo = serializers.CharField(source="presupuesto.codigo", read_only=True)
    cliente = serializers.IntegerField(source="presupuesto.cliente_id", read_only=True)
    cliente_nombre = serializers.CharField(source="presupuesto.cliente.nombre_legal", read_only=True)
    categoria_servicio = serializers.IntegerField(source="categoria_servicio_id", read_only=True)
    categoria_nombre = serializers.CharField(source="categoria_servicio.nombre", read_only=True)
    tecnico_responsable = serializers.IntegerField(source="tecnico_responsable_id", read_only=True, allow_null=True)
    tecnico_nombre = serializers.SerializerMethodField()
    fecha_programada = serializers.DateField(read_only=True, allow_null=True)
    iniciado_en = serializers.DateTimeField(read_only=True, allow_null=True)
    estado = serializers.CharField(read_only=True)
    finalizado_en = serializers.DateTimeField(read_only=True, allow_null=True)

    def get_tecnico_nombre(self, obj):
        return _nombre_usuario(obj.tecnico_responsable)


class ObraEventoSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    obra = serializers.IntegerField(source="obra_id", read_only=True)
    tipo = serializers.CharField(read_only=True)
    estado_anterior = serializers.CharField(read_only=True, allow_null=True)
    estado_nuevo = serializers.CharField(read_only=True)
    datos_anteriores = serializers.JSONField(read_only=True)
    datos_nuevos = serializers.JSONField(read_only=True)
    registrado_por = serializers.IntegerField(source="registrado_por_id", read_only=True)
    motivo = serializers.CharField(read_only=True)
    creado_en = serializers.DateTimeField(read_only=True)


class CategoriaServicioSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    nombre = serializers.CharField(read_only=True)
    activo = serializers.BooleanField(read_only=True)
    creado_por = serializers.IntegerField(source="creado_por_id", read_only=True, allow_null=True)
    creado_en = serializers.DateTimeField(read_only=True)
    actualizado_en = serializers.DateTimeField(read_only=True)


class CategoriaServicioEventoSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    categoria = serializers.IntegerField(source="categoria_id", read_only=True)
    tipo = serializers.CharField(read_only=True)
    datos_anteriores = serializers.JSONField(read_only=True)
    datos_nuevos = serializers.JSONField(read_only=True)
    registrado_por = serializers.IntegerField(source="registrado_por_id", read_only=True)
    motivo = serializers.CharField(read_only=True)
    creado_en = serializers.DateTimeField(read_only=True)


class PresupuestoDisponibleSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    codigo = serializers.CharField(read_only=True)
    cliente = serializers.IntegerField(source="cliente_id", read_only=True)
    cliente_nombre = serializers.CharField(source="cliente.nombre_legal", read_only=True)


class TecnicoDisponibleSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    nombre = serializers.SerializerMethodField()

    def get_nombre(self, obj):
        return _nombre_usuario(obj)
