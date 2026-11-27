from django.db import migrations, models
from django.db.migrations.exceptions import IrreversibleError
import django.db.models.deletion


def proteger_reversion(apps, schema_editor):
    Item = apps.get_model('comercial', 'PresupuestoItem')
    if Item.objects.using(schema_editor.connection.alias).filter(articulo__isnull=False).exists():
        raise IrreversibleError('Existen materiales vinculados a presupuestos; no se puede eliminar su trazabilidad.')


class Migration(migrations.Migration):
    dependencies = [
        ('comercial', '0006_flujo_finanzas_020a'),
        ('inventario', '0001_initial'),
    ]
    operations = [
        migrations.AddField(
            model_name='presupuestoitem', name='articulo',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                                    related_name='items_presupuestados', to='inventario.articuloinventario'),
        ),
        migrations.AddField(
            model_name='presupuestoitem', name='codigo_articulo',
            field=models.CharField(blank=True, default='', editable=False, max_length=50),
        ),
        migrations.AddConstraint(
            model_name='presupuestoitem',
            constraint=models.CheckConstraint(
                condition=models.Q(articulo__isnull=True, codigo_articulo='')
                | (models.Q(articulo__isnull=False) & ~models.Q(codigo_articulo='')),
                name='presupuesto_item_articulo_coherente',
            ),
        ),
        migrations.RunPython(migrations.RunPython.noop, proteger_reversion),
    ]
