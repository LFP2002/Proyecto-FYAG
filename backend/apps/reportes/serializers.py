from rest_framework import serializers
from .filtros import ZONA


class ObraSerializer(serializers.Serializer):
    obra = serializers.IntegerField()
    codigo_obra = serializers.CharField()
    cliente = serializers.IntegerField()
    cliente_nombre = serializers.CharField()
    categoria_nombre = serializers.CharField()
    estado = serializers.CharField()
    tecnico_responsable = serializers.IntegerField(allow_null=True)
    tecnico_nombre = serializers.CharField(allow_null=True)
    fecha_programada = serializers.DateField(allow_null=True)
    creado_en = serializers.DateTimeField(default_timezone=ZONA)
    finalizado_en = serializers.DateTimeField(default_timezone=ZONA, allow_null=True)
    presupuesto_neto = serializers.CharField()


class RentabilidadSerializer(serializers.Serializer):
    obra = serializers.IntegerField()
    codigo_obra = serializers.CharField()
    cliente = serializers.IntegerField()
    cliente_nombre = serializers.CharField()
    finalizado_en = serializers.DateTimeField(default_timezone=ZONA)
    moneda = serializers.CharField()
    presupuesto_neto = serializers.CharField()
    costo_real_neto = serializers.CharField()
    margen_neto = serializers.CharField()
    tiene_cortesia_sin_cobro = serializers.BooleanField()


class CobranzaSerializer(serializers.Serializer):
    documento = serializers.IntegerField()
    obra = serializers.IntegerField()
    codigo_obra = serializers.CharField()
    cliente = serializers.IntegerField()
    cliente_nombre = serializers.CharField()
    tipo_documento = serializers.CharField()
    folio_externo = serializers.CharField()
    fecha_emision = serializers.DateField()
    fecha_vencimiento = serializers.DateField()
    moneda = serializers.CharField()
    monto_documentado_bruto = serializers.CharField()
    abonado = serializers.CharField()
    saldo = serializers.CharField()
    estado_cobranza = serializers.CharField()


SERIALIZERS = {"obras": ObraSerializer, "rentabilidad": RentabilidadSerializer, "cobranzas": CobranzaSerializer}


def representar(tipo, filas):
    serializer = SERIALIZERS[tipo]()
    for fila in filas:
        yield dict(serializer.to_representation(fila))
