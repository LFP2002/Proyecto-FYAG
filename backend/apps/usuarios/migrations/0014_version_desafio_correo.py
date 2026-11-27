from django.db import migrations, models


def invalidar_cambios_previos(apps, schema_editor):
    apps.get_model('usuarios', 'DesafioCorreo').objects.using(schema_editor.connection.alias).filter(proposito='CAMBIO').delete()


class Migration(migrations.Migration):
    dependencies = [('usuarios', '0013_verificacion_correo')]
    operations = [
        migrations.AddField(model_name='desafiocorreo', name='sesion_version',
                            field=models.PositiveBigIntegerField(null=True, editable=False)),
        migrations.RunPython(invalidar_cambios_previos, migrations.RunPython.noop),
        migrations.AddConstraint(model_name='desafiocorreo', constraint=models.CheckConstraint(condition=(
            models.Q(proposito='TITULARIDAD', sesion_version__isnull=True)
            | models.Q(proposito='CAMBIO', sesion_version__isnull=False, sesion_version__gte=1)
        ), name='correo_version_por_proposito')),
    ]
