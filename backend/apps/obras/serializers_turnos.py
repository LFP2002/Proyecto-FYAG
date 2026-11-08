from rest_framework import serializers

from .serializers import ContratoEstrictoSerializer, EnteroEstrictoField, TextoEstrictoField
from .services_turnos import tarifa_decimal
from .exceptions import DatosInvalidos


class InicioTurnoSerializer(ContratoEstrictoSerializer):
    pass


class EvidenciaEntradaSerializer(ContratoEstrictoSerializer):
    descripcion_trabajo = TextoEstrictoField(max_length=2000)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["fotos[]"] = serializers.ListField(
            child=serializers.FileField(), max_length=5, required=False,
            default=list, source="fotos",
        )

    def to_internal_value(self, data):
        if hasattr(data, "getlist"):
            repetidos = [k for k in data if k != "fotos[]" and len(data.getlist(k)) != 1]
            if repetidos:
                raise serializers.ValidationError({k: ["Campo repetido."] for k in repetidos})
            data = {k: data.getlist(k) if k == "fotos[]" else data[k] for k in data}
        return super().to_internal_value(data)


class SubsanarTurnoSerializer(EvidenciaEntradaSerializer):
    descripcion_trabajo = TextoEstrictoField(max_length=2000, required=False)


class TarifaField(TextoEstrictoField):
    def to_internal_value(self, data):
        try:
            tarifa_decimal(data)
        except DatosInvalidos as exc:
            raise serializers.ValidationError(exc.errores["costo_hora_neto"]) from exc
        return data


class RevisarTurnoSerializer(ContratoEstrictoSerializer):
    decision = serializers.ChoiceField(choices=("VALIDAR", "OBSERVAR"))
    motivo = TextoEstrictoField(max_length=2000)
    costo_hora_neto = TarifaField(required=False)


class CorregirTurnoSerializer(ContratoEstrictoSerializer):
    descripcion_trabajo = TextoEstrictoField(max_length=2000, required=False)
    motivo = TextoEstrictoField(max_length=2000)
    duracion_ajustada_segundos = EnteroEstrictoField(min_value=1, max_value=9223372036854775807, allow_null=True, required=False)
    costo_hora_neto = TarifaField(required=False)


class CierreAdministrativoSerializer(ContratoEstrictoSerializer):
    motivo = TextoEstrictoField(max_length=2000)
    descripcion_trabajo = TextoEstrictoField(max_length=2000)
    duracion_ajustada_segundos = EnteroEstrictoField(min_value=1, max_value=9223372036854775807, allow_null=True, required=False)


class FotoTurnoSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    tipo_mime = serializers.CharField(read_only=True)
    tamano = serializers.IntegerField(read_only=True)
    creado_en = serializers.DateTimeField(read_only=True)
    descarga = serializers.SerializerMethodField()

    def get_descarga(self, foto):
        return f"/api/obras/{foto.obra_id}/turnos/{foto.turno_id}/fotos/{foto.pk}/"


class TurnoLecturaSerializer(serializers.Serializer):
    modo_cierre = serializers.CharField(read_only=True, allow_null=True)
    cerrado_por = serializers.IntegerField(source="cerrado_por_id", read_only=True, allow_null=True)
    turno_id = serializers.IntegerField(source="pk", read_only=True)
    obra = serializers.IntegerField(source="obra_id", read_only=True)
    tecnico = serializers.IntegerField(source="tecnico_id", read_only=True)
    iniciado_en = serializers.DateTimeField(read_only=True)
    terminado_en = serializers.DateTimeField(read_only=True, allow_null=True)
    duracion_segundos = serializers.DecimalField(max_digits=20, decimal_places=6, read_only=True, allow_null=True)
    duracion_ajustada_segundos = serializers.IntegerField(read_only=True, allow_null=True)
    descripcion_trabajo = serializers.CharField(read_only=True)
    estado_revision = serializers.CharField(read_only=True)
    # Solo observaciones operativas para permitir subsanar. Motivos económicos y
    # snapshots de revisión/corrección nunca se serializan para el técnico.
    observacion = serializers.SerializerMethodField()
    fotos = FotoTurnoSerializer(many=True, read_only=True)

    def get_observacion(self, turno):
        return turno.observacion_revision if turno.estado_revision == "OBSERVADO" else ""


class TurnoSupervisorSerializer(TurnoLecturaSerializer):
    costo_hora_neto = serializers.DecimalField(max_digits=15, decimal_places=2, read_only=True, allow_null=True)
    costo_mano_obra = serializers.SerializerMethodField()
    revisado_por = serializers.IntegerField(source="revisado_por_id", read_only=True, allow_null=True)
    revisado_en = serializers.DateTimeField(read_only=True, allow_null=True)
    observacion_revision = serializers.CharField(read_only=True)

    def get_costo_mano_obra(self, turno):
        valor = turno.costo_mano_obra
        return format(valor, ".2f") if valor is not None else None
