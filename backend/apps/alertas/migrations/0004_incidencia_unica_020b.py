from django.db import migrations, models
from django.db.migrations.exceptions import IrreversibleError


LEGADO = models.Q(pk__isnull=True)
ACTUAL = models.Q(pk__isnull=True)
for tipo, recurso, roles, responsable in [
    ('PRESUPUESTO_PENDIENTE_FINANZAS', 'PRESUPUESTO', ('ADMINISTRATIVO_FINANZAS',), 'ADMINISTRATIVO_FINANZAS'),
    ('PRESUPUESTO_PENDIENTE_GERENCIA', 'PRESUPUESTO', ('GERENCIA',), None),
    ('OBRA_SUSPENDIDA', 'OBRA', ('GERENCIA', 'SUPERVISOR_OBRAS'), 'SUPERVISOR_OBRAS'),
    ('TURNO_PENDIENTE_REVISION', 'TURNO', ('SUPERVISOR_OBRAS',), 'SUPERVISOR_OBRAS'),
    ('COBRANZA_VENCIDA', 'DOCUMENTO', ('GERENCIA',), 'ADMINISTRATIVO_FINANZAS'),
]:
    LEGADO |= models.Q(tipo=tipo, recurso_tipo=recurso, rol_destinatario__in=roles)
    if responsable:
        ACTUAL |= models.Q(tipo=tipo, recurso_tipo=recurso, rol_destinatario=responsable)


def invalidar_salud(apps, schema_editor):
    # El primer ciclo completo observa la continuidad. No reconstruir el pasado.
    apps.get_model('alertas', 'EstadoReconciliacion').objects.using(
        schema_editor.connection.alias,
    ).update(ultima_correcta_en=None)


def comprobar_reversion(apps, schema_editor):
    if apps.get_model('alertas', 'Alerta').objects.using(schema_editor.connection.alias).filter(es_legada=False).exists():
        raise IrreversibleError('Existen episodios 020B; no convertirlos en entregas por rol ni perder su historia.')


class Migration(migrations.Migration):
    dependencies = [('alertas', '0003_flujo_finanzas_020a')]

    operations = [
        migrations.RemoveConstraint('alerta', 'alerta_generacion_unica'),
        migrations.RemoveConstraint('alerta', 'alerta_abierta_unica'),
        migrations.RemoveConstraint('alerta', 'alerta_catalogo_coherente'),
        # PostgreSQL clasifica todas las filas previas, sin alterar sus columnas históricas.
        migrations.AddField('alerta', 'es_legada', models.BooleanField(default=True, editable=False)),
        migrations.AlterField('alerta', 'es_legada', models.BooleanField(default=False, editable=False)),
        migrations.AddIndex('alerta', models.Index(fields=['es_legada', 'tipo', 'estado', '-creado_en', '-id'], name='alerta_tipo_estado_020b_idx')),
        migrations.AddConstraint('alerta', models.CheckConstraint(condition=(models.Q(es_legada=True) & LEGADO | models.Q(es_legada=False) & ACTUAL), name='alerta_catalogo_coherente')),
        migrations.AddConstraint('alerta', models.UniqueConstraint(fields=['tipo', 'recurso_tipo', 'recurso_id', 'rol_destinatario', 'generacion'], condition=models.Q(es_legada=True), name='alerta_generacion_unica')),
        migrations.AddConstraint('alerta', models.UniqueConstraint(fields=['tipo', 'recurso_tipo', 'recurso_id', 'rol_destinatario'], condition=models.Q(es_legada=True, estado__in=['PENDIENTE', 'ATENDIDA']), name='alerta_abierta_unica')),
        migrations.AddConstraint('alerta', models.UniqueConstraint(fields=['tipo', 'recurso_tipo', 'recurso_id', 'generacion'], condition=models.Q(es_legada=False), name='alerta_episodio_unico_020b')),
        migrations.AddConstraint('alerta', models.UniqueConstraint(fields=['tipo', 'recurso_tipo', 'recurso_id'], condition=models.Q(es_legada=False, estado__in=['PENDIENTE', 'ATENDIDA']), name='alerta_activa_unica_020b')),
        migrations.RunPython(invalidar_salud, comprobar_reversion),
    ]
