from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('usuarios', '0011_identidad_evento')]
    operations = [
        migrations.CreateModel(
            name='InstalacionFYAG',
            fields=[
                ('id', models.PositiveSmallIntegerField(default=1, editable=False, primary_key=True, serialize=False)),
                ('inicializada_en', models.DateTimeField(editable=False, null=True)),
            ],
            options={'constraints': [models.CheckConstraint(condition=models.Q(id=1), name='instalacion_fyag_unica')]},
        ),
        migrations.RunSQL(
            sql="""
            INSERT INTO usuarios_instalacionfyag (id, inicializada_en)
            VALUES (1, CASE WHEN EXISTS (SELECT 1 FROM usuarios_usuario) THEN statement_timestamp() END);
            CREATE FUNCTION fyag_marcar_instalacion_usuario() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                IF NOT EXISTS (SELECT 1 FROM usuarios_instalacionfyag WHERE id = 1 AND inicializada_en IS NOT NULL) THEN
                    INSERT INTO usuarios_instalacionfyag (id, inicializada_en) VALUES (1, statement_timestamp())
                    ON CONFLICT (id) DO UPDATE SET inicializada_en = EXCLUDED.inicializada_en
                    WHERE usuarios_instalacionfyag.inicializada_en IS NULL;
                END IF;
                RETURN NEW;
            END;
            $$;
            CREATE TRIGGER fyag_marcar_instalacion_usuario AFTER INSERT ON usuarios_usuario
            FOR EACH ROW EXECUTE FUNCTION fyag_marcar_instalacion_usuario();
            """,
            reverse_sql="""
            DROP TRIGGER fyag_marcar_instalacion_usuario ON usuarios_usuario;
            DROP FUNCTION fyag_marcar_instalacion_usuario();
            """,
        ),
    ]
