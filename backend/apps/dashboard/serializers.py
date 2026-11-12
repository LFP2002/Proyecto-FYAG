from rest_framework import serializers

from apps.obras.serializers import ObraLecturaSerializer
from .filtros import ZONA


class PeriodoSerializer(serializers.Serializer):
    desde = serializers.DateField()
    hasta = serializers.DateField()


class EstadosObraSerializer(serializers.Serializer):
    PLANIFICADA = serializers.IntegerField()
    EN_PROCESO = serializers.IntegerField()
    SUSPENDIDA = serializers.IntegerField()
    FINALIZADA = serializers.IntegerField()
    CANCELADA = serializers.IntegerField()


class OperacionSerializer(serializers.Serializer):
    obras_por_estado_actual = EstadosObraSerializer()
    presupuestos_pendientes_gerencia_actual = serializers.IntegerField()
    obras_finalizadas_periodo = serializers.IntegerField()


class RentabilidadSerializer(serializers.Serializer):
    obras_con_cierre = serializers.IntegerField()
    presupuesto_neto = serializers.CharField()
    costo_real_neto = serializers.CharField()
    margen_real_neto = serializers.CharField()


class CobranzaSerializer(serializers.Serializer):
    documentos_vigentes = serializers.IntegerField()
    monto_documentado_bruto = serializers.CharField()
    abonado = serializers.CharField()
    saldo = serializers.CharField()
    saldo_vencido = serializers.CharField()


class ResumenSerializer(serializers.Serializer):
    generado_en = serializers.DateTimeField(default_timezone=ZONA)
    zona_horaria = serializers.CharField()
    moneda = serializers.CharField()
    periodo = PeriodoSerializer()
    operacion = OperacionSerializer()
    rentabilidad_cerrada_periodo = RentabilidadSerializer()
    cobranza_actual = CobranzaSerializer()


class PuntoSerializer(serializers.Serializer):
    mes = serializers.CharField()
    cantidad = serializers.IntegerField()


class SerieSerializer(serializers.Serializer):
    metrica = serializers.CharField()
    zona_horaria = serializers.CharField()
    puntos = PuntoSerializer(many=True)


class ObraActivaSerializer(ObraLecturaSerializer):
    """Reutiliza código, atribución laboral y relaciones del serializer de Obras."""
    presupuesto_neto = serializers.SerializerMethodField()
    PUBLICOS = ("id", "codigo", "cliente", "cliente_nombre", "categoria_nombre", "estado",
                "tecnico_responsable", "tecnico_nombre", "fecha_programada", "presupuesto_neto")

    def get_fields(self):
        fields = super().get_fields()
        return {name: fields[name] for name in self.PUBLICOS}

    def get_presupuesto_neto(self, obj):
        return format(obj.presupuesto.monto_neto, ".2f")
