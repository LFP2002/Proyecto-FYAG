"""Atribución histórica al insertar; sin reconstrucción de nombres anteriores."""
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("usuarios", "0010_bodeguero")]
    operations = [
        migrations.AddField(model_name="usuarioevento", name="actor_nombre_historico", field=models.CharField(max_length=301, null=True, blank=True, editable=False)),
        migrations.AddField(model_name="usuarioevento", name="actor_username_historico", field=models.CharField(max_length=150, null=True, blank=True, editable=False)),
        migrations.RunSQL(sql="""
CREATE FUNCTION fyag_usuarios_identidad_evento() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'UPDATE' THEN
        IF NEW.actor_id IS DISTINCT FROM OLD.actor_id
            OR NEW.actor_nombre_historico IS DISTINCT FROM OLD.actor_nombre_historico
            OR NEW.actor_username_historico IS DISTINCT FROM OLD.actor_username_historico THEN
            RAISE EXCEPTION 'La identidad del evento es inmutable' USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
    END IF;
    SELECT NULLIF(concat_ws(' ', NULLIF(btrim(first_name), ''), NULLIF(btrim(last_name), '')), ''), username
        INTO NEW.actor_nombre_historico, NEW.actor_username_historico
        FROM usuarios_usuario WHERE id = NEW.actor_id;
    RETURN NEW;
END;
$$;
CREATE TRIGGER fyag_identidad_evento BEFORE INSERT OR UPDATE OF actor_id, actor_nombre_historico, actor_username_historico ON usuarios_usuarioevento FOR EACH ROW EXECUTE FUNCTION fyag_usuarios_identidad_evento();
        """, reverse_sql="""
DROP TRIGGER fyag_identidad_evento ON usuarios_usuarioevento;
DROP FUNCTION fyag_usuarios_identidad_evento();
        """),
    ]
