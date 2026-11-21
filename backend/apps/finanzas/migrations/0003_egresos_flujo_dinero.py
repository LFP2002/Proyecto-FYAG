from decimal import Decimal

from django.conf import settings
from django.db import migrations, models
from django.db.models import F, Q
from django.db.models.deletion import PROTECT
from django.db.models.functions import Trim
from django.db.migrations.exceptions import IrreversibleError


def comprobar_reversion(apps, schema_editor):
    if apps.get_model('finanzas', 'Egreso').objects.using(schema_editor.connection.alias).exists():
        raise IrreversibleError('Hay egresos registrados: preservar sus datos e historial; no retirar SPEC-021 destruyendo registros.')


class Migration(migrations.Migration):
    dependencies = [
        ('finanzas', '0002_pagos_cobranzas'),
        ('obras', '0011_cierre_costos_finalizacion'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(name='Egreso', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('monto', models.DecimalField(max_digits=38, decimal_places=2)),
            ('fecha_pago', models.DateField()),
            ('categoria', models.CharField(max_length=10, choices=[('MATERIALES', 'Materiales'), ('TRANSPORTE', 'Transporte'), ('SERVICIOS', 'Servicios'), ('ARRIENDO', 'Arriendo'), ('OTROS', 'Otros')])),
            ('concepto', models.CharField(max_length=200)),
            ('beneficiario', models.CharField(max_length=200)),
            ('medio', models.CharField(max_length=13, choices=[('TRANSFERENCIA', 'Transferencia'), ('EFECTIVO', 'Efectivo'), ('TARJETA', 'Tarjeta'), ('OTRO', 'Otro')])),
            ('referencia_respaldo', models.CharField(max_length=500)),
            ('observacion', models.CharField(max_length=2000, blank=True, default='')),
            ('obra', models.ForeignKey(to='obras.obra', on_delete=PROTECT, null=True, blank=True, related_name='egresos')),
            ('registrado_por', models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=PROTECT, related_name='egresos_registrados', editable=False)),
            ('registrado_en', models.DateTimeField(auto_now_add=True)),
            ('clave_idempotencia', models.UUIDField(editable=False)),
            ('huella_solicitud', models.CharField(max_length=64, editable=False)),
            ('activo', models.BooleanField(default=True, editable=False)),
            ('anulado_por', models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=PROTECT, null=True, blank=True, related_name='egresos_anulados', editable=False)),
            ('anulado_en', models.DateTimeField(null=True, blank=True, editable=False)),
            ('motivo_anulacion', models.CharField(max_length=2000, null=True, blank=True, editable=False)),
            ('referencia_correccion', models.CharField(max_length=500, null=True, blank=True, editable=False)),
        ], options={'ordering': ['-fecha_pago', '-id']}),
        migrations.CreateModel(name='EgresoEvento', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('egreso', models.ForeignKey(to='finanzas.egreso', on_delete=PROTECT, related_name='eventos')),
            ('tipo', models.CharField(max_length=9, choices=[('CREACION', 'Creación'), ('ANULACION', 'Anulación administrativa')])),
            ('actor', models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=PROTECT, related_name='eventos_egresos', editable=False)),
            ('motivo', models.CharField(max_length=2000, blank=True, default='')),
            ('creado_en', models.DateTimeField(auto_now_add=True)),
        ], options={'ordering': ['creado_en', 'id']}),
        migrations.AddIndex('egreso', models.Index(fields=['fecha_pago', 'id'], name='fin_egreso_fecha_idx')),
        migrations.AddConstraint('egreso', models.UniqueConstraint(fields=['clave_idempotencia'], name='fin_egreso_idempotencia_unica')),
        migrations.AddConstraint('egreso', models.CheckConstraint(condition=Q(monto__gt=0, monto__lte=Decimal('999999999999999999999999999999999999.99')), name='fin_egreso_monto_valido')),
        migrations.AddConstraint('egreso', models.CheckConstraint(condition=Q(categoria__in=['MATERIALES', 'TRANSPORTE', 'SERVICIOS', 'ARRIENDO', 'OTROS']), name='fin_egreso_categoria_valida')),
        migrations.AddConstraint('egreso', models.CheckConstraint(condition=Q(medio__in=['TRANSFERENCIA', 'EFECTIVO', 'TARJETA', 'OTRO']), name='fin_egreso_medio_valido')),
        migrations.AddConstraint('egreso', models.CheckConstraint(condition=Q(huella_solicitud__regex=r'^[0-9a-f]{64}$'), name='fin_egreso_huella_valida')),
        migrations.AddConstraint('egreso', models.CheckConstraint(condition=Q(fecha_pago__lte=models.Func('registrado_en', template="(%(expressions)s AT TIME ZONE 'America/Santiago')::date", output_field=models.DateField())), name='fin_egreso_fecha_valida')),
        migrations.AddConstraint('egreso', models.CheckConstraint(condition=(
            ~Q(concepto='') & ~Q(beneficiario='') & ~Q(referencia_respaldo='')
            & Q(concepto=Trim('concepto'), beneficiario=Trim('beneficiario'), referencia_respaldo=Trim('referencia_respaldo'), observacion=Trim('observacion'))
        ), name='fin_egreso_textos_validos')),
        migrations.AddConstraint('egreso', models.CheckConstraint(condition=(
            Q(activo=True, anulado_por__isnull=True, anulado_en__isnull=True, motivo_anulacion__isnull=True, referencia_correccion__isnull=True)
            | (Q(activo=False, anulado_por__isnull=False, anulado_en__isnull=False, motivo_anulacion__isnull=False, referencia_correccion__isnull=False,
                 anulado_en__gte=F('registrado_en'), motivo_anulacion=Trim('motivo_anulacion'), referencia_correccion=Trim('referencia_correccion')) & ~Q(motivo_anulacion='') & ~Q(referencia_correccion=''))
        ), name='fin_egreso_anulacion_coherente')),
        migrations.AddConstraint('egresoevento', models.UniqueConstraint(fields=['egreso', 'tipo'], name='fin_egreso_evento_unico')),
        migrations.AddConstraint('egresoevento', models.CheckConstraint(condition=(Q(tipo='CREACION', motivo='') | (Q(tipo='ANULACION', motivo=Trim('motivo')) & ~Q(motivo=''))), name='fin_egreso_evento_coherente')),
        migrations.RunPython(migrations.RunPython.noop, comprobar_reversion),
    ]
