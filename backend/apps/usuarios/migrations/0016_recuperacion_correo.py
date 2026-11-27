import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.db.models import Exists, OuterRef


def conservar_evidencia(apps, schema_editor):
    alias = schema_editor.connection.alias
    credenciales = apps.get_model('usuarios', 'SeguridadCredencial').objects.using(alias)
    eventos = apps.get_model('usuarios', 'UsuarioEvento').objects.using(alias)
    credenciales.filter(estado='RECUPERACION').filter(Exists(eventos.filter(
        usuario_objetivo_id=OuterRef('usuario_id'), tipo='CAMBIO_INICIAL',
    ))).update(personal_previa=True)


class Migration(migrations.Migration):
    dependencies = [('usuarios', '0015_autorizacion_instalacion')]
    operations = [
        migrations.CreateModel(name='DesafioRecuperacionCorreo', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('digest', models.CharField(editable=False, max_length=64, unique=True)),
            ('vinculo', models.CharField(editable=False, max_length=64)),
            ('vence_en', models.DateTimeField(db_index=True)),
            ('usuario', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
        ]),
        migrations.CreateModel(name='RecuperacionCorreoEvento', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('creado_en', models.DateTimeField(auto_now_add=True)),
            ('acceso_anterior', models.CharField(blank=True, max_length=20)),
            ('acceso_version_nueva', models.PositiveBigIntegerField(null=True)),
            ('usuario', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
        ]),
        migrations.AddField(model_name='seguridadcredencial', name='personal_previa',
                            field=models.BooleanField(default=False, db_default=False, editable=False)),
        migrations.RunPython(conservar_evidencia, migrations.RunPython.noop),
        migrations.AddConstraint(model_name='seguridadcredencial', constraint=models.CheckConstraint(
            condition=models.Q(personal_previa=False) | models.Q(estado='RECUPERACION'),
            name='credencial_personal_previa_reemision')),
    ]
