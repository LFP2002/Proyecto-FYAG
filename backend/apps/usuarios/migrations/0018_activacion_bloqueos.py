from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('usuarios', '0017_recuperacion_ti_infraestructura')]

    operations = [
        migrations.CreateModel(
            name='ActivacionBloqueos',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('creado_en', models.DateTimeField(auto_now_add=True)),
                ('autorizacion', models.CharField(max_length=120, unique=True)),
                ('entrega_smtp', models.CharField(max_length=120)),
                ('autorizacion_remitente', models.CharField(max_length=120)),
                ('huella_configuracion', models.CharField(max_length=64)),
            ],
        ),
        migrations.RunSQL(
            'CREATE TRIGGER fyag_activacion_bloqueos_inmutable BEFORE UPDATE OR DELETE ON usuarios_activacionbloqueos '
            'FOR EACH ROW EXECUTE FUNCTION fyag_evento_acceso_inmutable()',
            'DROP TRIGGER fyag_activacion_bloqueos_inmutable ON usuarios_activacionbloqueos',
        ),
    ]
