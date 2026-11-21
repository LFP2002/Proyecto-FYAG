from django.db import migrations, models
from django.db.migrations.exceptions import IrreversibleError


ESTADOS = [
    ('BORRADOR', 'Borrador'), ('PENDIENTE_FINANZAS', 'Pendiente Finanzas'),
    ('APROBADO_FINANZAS', 'Aprobado Finanzas'), ('RECHAZADO_FINANZAS', 'Rechazado Finanzas'),
    ('PENDIENTE_GERENCIA', 'Pendiente Gerencia'), ('APROBADO_GERENCIA', 'Aprobado Gerencia'),
    ('RECHAZADO_GERENCIA', 'Rechazado Gerencia'), ('ENVIADO_CLIENTE', 'Enviado al cliente'),
    ('APROBADO_CLIENTE', 'Aprobado por cliente'), ('RECHAZADO_CLIENTE', 'Rechazado por cliente'),
    ('ANULADO', 'Anulado'),
]
POLITICAS = [('GERENCIA_LEGADA', 'Gerencia (histórica)'), ('FINANZAS', 'Finanzas')]
VALORES = [valor for valor, _ in ESTADOS]


def comprobar_reversion(apps, schema_editor):
    Presupuesto = apps.get_model('comercial', 'Presupuesto')
    Evento = apps.get_model('comercial', 'PresupuestoEvento')
    nuevos = ['PENDIENTE_FINANZAS', 'APROBADO_FINANZAS', 'RECHAZADO_FINANZAS']
    alias = schema_editor.connection.alias
    if (Presupuesto.objects.using(alias).filter(models.Q(politica_aprobacion='FINANZAS') | models.Q(estado__in=nuevos)).exists()
        or Evento.objects.using(alias).filter(models.Q(estado_anterior__in=nuevos) | models.Q(estado_nuevo__in=nuevos)).exists()):
        raise IrreversibleError('020A tiene datos financieros: no se puede volver al flujo gerencial sin perder historia.')


class Migration(migrations.Migration):
    dependencies = [('comercial', '0005_remove_presupuesto_presupuesto_gerencia_coherente_and_more')]

    operations = [
        migrations.RemoveConstraint('presupuesto', 'presupuesto_estado_valido'),
        migrations.RemoveConstraint('presupuesto', 'presupuesto_aprobacion_gerencia_obligatoria'),
        migrations.RemoveConstraint('presupuestoevento', 'pres_evento_anterior_valido'),
        migrations.RemoveConstraint('presupuestoevento', 'pres_evento_nuevo_valido'),
        migrations.RemoveConstraint('presupuestoevento', 'pres_evento_motivo_obligatorio'),
        # El default de backfill identifica historia, sin modificar estados ni eventos.
        migrations.AddField('presupuesto', 'politica_aprobacion', models.CharField(
            choices=POLITICAS, default='GERENCIA_LEGADA', editable=False, max_length=20)),
        migrations.AlterField('presupuesto', 'politica_aprobacion', models.CharField(
            choices=POLITICAS, default='FINANZAS', editable=False, max_length=20)),
        migrations.AlterField('presupuesto', 'estado', models.CharField(choices=ESTADOS, default='BORRADOR', max_length=20)),
        migrations.AlterField('presupuesto', 'requiere_aprobacion_gerencia', models.BooleanField(default=False, editable=False)),
        migrations.AlterField('presupuestoevento', 'estado_anterior', models.CharField(choices=ESTADOS, max_length=20, null=True, blank=True)),
        migrations.AlterField('presupuestoevento', 'estado_nuevo', models.CharField(choices=ESTADOS, max_length=20)),
        migrations.AddConstraint('presupuesto', models.CheckConstraint(condition=models.Q(estado__in=VALORES), name='presupuesto_estado_valido')),
        migrations.AddConstraint('presupuesto', models.CheckConstraint(condition=(
            models.Q(politica_aprobacion='GERENCIA_LEGADA', requiere_aprobacion_gerencia=True)
            | (models.Q(politica_aprobacion='FINANZAS', requiere_aprobacion_gerencia=False)
               & ~models.Q(estado__in=['PENDIENTE_GERENCIA', 'APROBADO_GERENCIA', 'RECHAZADO_GERENCIA']))
        ), name='presupuesto_politica_coherente')),
        migrations.AddConstraint('presupuestoevento', models.CheckConstraint(condition=(models.Q(estado_anterior__isnull=True) | models.Q(estado_anterior__in=VALORES)), name='pres_evento_anterior_valido')),
        migrations.AddConstraint('presupuestoevento', models.CheckConstraint(condition=models.Q(estado_nuevo__in=VALORES), name='pres_evento_nuevo_valido')),
        migrations.AddConstraint('presupuestoevento', models.CheckConstraint(condition=(
            ~models.Q(estado_nuevo__in=['RECHAZADO_FINANZAS', 'RECHAZADO_GERENCIA', 'RECHAZADO_CLIENTE', 'ANULADO']) | ~models.Q(motivo='')
        ), name='pres_evento_motivo_obligatorio')),
        migrations.RunPython(migrations.RunPython.noop, comprobar_reversion),
    ]
