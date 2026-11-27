import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


TIPOS = [
    ('CREACION', 'Creación'), ('EDICION', 'Edición'), ('ACTIVACION', 'Activación'),
    ('DESACTIVACION', 'Desactivación'), ('CAMBIO_ROL', 'Cambio de rol'),
    ('ESTABLECER_CLAVE', 'Establecimiento de contraseña'), ('CAMBIO_CLAVE_PROPIA', 'Cambio propio de contraseña'),
    ('CREACION_CREDENCIAL_TEMPORAL', 'Emisión inicial temporal'), ('REEMISION', 'Restablecimiento temporal por TI'),
    ('CAMBIO_INICIAL', 'Confirmación de contraseña personal'), ('CORREO_SOLICITADO', 'Solicitud de cambio de correo'),
    ('CORREO_VERIFICADO', 'Titularidad de correo confirmada'), ('CORREO_CAMBIADO', 'Nuevo correo confirmado'),
]


class Migration(migrations.Migration):
    dependencies = [('usuarios', '0012_instalacionfyag')]
    operations = [
        migrations.AddField(model_name='usuario', name='correo_pendiente', field=models.EmailField(blank=True, default='', editable=False, max_length=254)),
        migrations.AddField(model_name='usuario', name='correo_verificado_en', field=models.DateTimeField(editable=False, null=True)),
        migrations.CreateModel(name='DesafioCorreo', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('digest', models.CharField(editable=False, max_length=64, unique=True)),
            ('email', models.EmailField(max_length=254)),
            ('proposito', models.CharField(choices=[('TITULARIDAD', 'Verificar correo vigente'), ('CAMBIO', 'Confirmar correo nuevo')], max_length=12)),
            ('emitido_en', models.DateTimeField()),
            ('vence_en', models.DateTimeField(db_index=True)),
            ('usuario', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
        ], options={'constraints': [
            models.CheckConstraint(condition=models.Q(proposito__in=['TITULARIDAD', 'CAMBIO']), name='correo_proposito_valido'),
            models.CheckConstraint(condition=models.Q(vence_en__gt=models.F('emitido_en')), name='correo_vigencia_positiva'),
        ]}),
        migrations.RemoveConstraint(model_name='usuarioevento', name='usuarios_evento_tipo_valido'),
        migrations.AlterField(model_name='usuarioevento', name='tipo', field=models.CharField(choices=TIPOS, max_length=32)),
        migrations.AddConstraint(model_name='usuarioevento', constraint=models.CheckConstraint(
            condition=models.Q(tipo__in=[key for key, label in TIPOS]), name='usuarios_evento_tipo_valido')),
    ]
