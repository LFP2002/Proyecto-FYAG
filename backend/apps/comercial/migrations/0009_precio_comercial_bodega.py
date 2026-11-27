import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.db.migrations.exceptions import IrreversibleError


def proteger_historia(apps, schema_editor):
    db = schema_editor.connection.alias
    eventos = apps.get_model('comercial', 'PresupuestoPrecioEvento')
    items = apps.get_model('comercial', 'PresupuestoItem')
    if (eventos.objects.using(db).exists()
            or items.objects.using(db).filter(precio_unitario__isnull=True).exists()):
        raise IrreversibleError('No se puede retirar el esquema con precios pendientes o historial de fijaciones.')


class Migration(migrations.Migration):
    dependencies = [
        ('comercial', '0008_merge_identidad_articulo'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name='presupuestoitem', name='precio_unitario',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=15, null=True),
        ),
        migrations.AddConstraint(
            model_name='presupuestoitem',
            constraint=models.CheckConstraint(
                condition=models.Q(precio_unitario__isnull=False) | models.Q(articulo__isnull=False),
                name='pres_item_precio_pendiente_vinculado',
            ),
        ),
        migrations.CreateModel(
            name='PresupuestoPrecioEvento',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('item_id_historico', models.PositiveBigIntegerField()),
                ('codigo_articulo', models.CharField(max_length=50)),
                ('precio_anterior', models.DecimalField(decimal_places=2, max_digits=15, null=True)),
                ('precio_nuevo', models.DecimalField(decimal_places=2, max_digits=15)),
                ('actor_username_historico', models.CharField(max_length=150)),
                ('creado_en', models.DateTimeField(auto_now_add=True)),
                ('presupuesto', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='eventos_precio', to='comercial.presupuesto')),
                ('registrado_por', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.RunPython(migrations.RunPython.noop, proteger_historia),
    ]
