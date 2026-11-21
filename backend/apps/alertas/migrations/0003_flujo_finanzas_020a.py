from django.db import migrations, models
from django.db.migrations.exceptions import IrreversibleError


TIPOS = ['PRESUPUESTO_PENDIENTE_FINANZAS', 'PRESUPUESTO_PENDIENTE_GERENCIA', 'OBRA_SUSPENDIDA', 'TURNO_PENDIENTE_REVISION', 'COBRANZA_VENCIDA']
ROLES = ['GERENCIA', 'SUPERVISOR_OBRAS', 'ADMINISTRATIVO_FINANZAS']
CORRESPONDENCIA = models.Q(pk__isnull=True)
for tipo, recurso, roles in [
    ('PRESUPUESTO_PENDIENTE_FINANZAS', 'PRESUPUESTO', ('ADMINISTRATIVO_FINANZAS',)),
    ('PRESUPUESTO_PENDIENTE_GERENCIA', 'PRESUPUESTO', ('GERENCIA',)),
    ('OBRA_SUSPENDIDA', 'OBRA', ('GERENCIA', 'SUPERVISOR_OBRAS')),
    ('TURNO_PENDIENTE_REVISION', 'TURNO', ('SUPERVISOR_OBRAS',)),
    ('COBRANZA_VENCIDA', 'DOCUMENTO', ('GERENCIA',)),
]:
    CORRESPONDENCIA |= models.Q(tipo=tipo, recurso_tipo=recurso, rol_destinatario__in=roles)


def comprobar_reversion(apps, schema_editor):
    Alerta = apps.get_model('alertas', 'Alerta')
    if Alerta.objects.using(schema_editor.connection.alias).filter(tipo='PRESUPUESTO_PENDIENTE_FINANZAS').exists():
        raise IrreversibleError('020A tiene alertas de Finanzas; preservar sus registros e historial.')


class Migration(migrations.Migration):
    dependencies = [('alertas', '0002_endurecer_transicion_evento'), ('comercial', '0006_flujo_finanzas_020a')]

    operations = [
        migrations.RemoveConstraint('alerta', 'alerta_catalogo_coherente'),
        migrations.AlterField('alerta', 'rol_destinatario', models.CharField(choices=[(x, x) for x in ROLES], editable=False, max_length=30)),
        migrations.AlterField('alerta', 'tipo', models.CharField(choices=[(x, x) for x in TIPOS], editable=False, max_length=32)),
        migrations.AddConstraint('alerta', models.CheckConstraint(condition=CORRESPONDENCIA, name='alerta_catalogo_coherente')),
        migrations.RunPython(migrations.RunPython.noop, comprobar_reversion),
    ]
