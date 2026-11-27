from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('usuarios', '0014_version_desafio_correo')]
    operations = [
        migrations.AddField(model_name='instalacionfyag', name='clave_digest',
                            field=models.CharField(max_length=64, null=True, editable=False)),
        migrations.AddField(model_name='instalacionfyag', name='clave_vence_en',
                            field=models.DateTimeField(null=True, editable=False)),
        migrations.AddConstraint(model_name='instalacionfyag', constraint=models.CheckConstraint(condition=(
            models.Q(clave_digest__isnull=True, clave_vence_en__isnull=True)
            | models.Q(inicializada_en__isnull=True, clave_digest__isnull=False,
                       clave_digest__regex=r'^[0-9a-f]{64}$', clave_vence_en__isnull=False)
        ), name='instalacion_fyag_clave_coherente')),
        migrations.CreateModel(name='EventoInstalacionFYAG', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
            ('tipo', models.CharField(max_length=20, choices=[
                ('EMISION', 'Clave emitida'), ('RENOVACION', 'Clave renovada'),
                ('INICIALIZACION_WEB', 'Inicializada por clave de infraestructura'),
                ('INICIALIZACION_CLI', 'Inicializada por terminal de infraestructura'),
            ])),
            ('operador', models.CharField(blank=True, max_length=64)),
            ('referencia', models.CharField(blank=True, max_length=64)),
            ('creado_en', models.DateTimeField(auto_now_add=True)),
        ]),
        migrations.RunSQL(
            sql="""
                CREATE FUNCTION fyag_consumir_clave_instalacion() RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN
                    IF NEW.inicializada_en IS NOT NULL THEN
                        NEW.clave_digest := NULL;
                        NEW.clave_vence_en := NULL;
                    END IF;
                    RETURN NEW;
                END;
                $$;
                CREATE TRIGGER fyag_consumir_clave_instalacion
                BEFORE UPDATE OF inicializada_en ON usuarios_instalacionfyag
                FOR EACH ROW EXECUTE FUNCTION fyag_consumir_clave_instalacion();
            """,
            reverse_sql="""
                DROP TRIGGER fyag_consumir_clave_instalacion ON usuarios_instalacionfyag;
                DROP FUNCTION fyag_consumir_clave_instalacion();
            """,
        ),
    ]
