"""Atribución histórica al insertar; sin reconstrucción de nombres anteriores."""
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("obras", "0012_origen_gasto_bodega")]
    operations = [
        migrations.AddField(model_name="obraevento", name="actor_nombre_historico", field=models.CharField(max_length=301, null=True, blank=True, editable=False)),
        migrations.AddField(model_name="obraevento", name="actor_username_historico", field=models.CharField(max_length=150, null=True, blank=True, editable=False)),
        migrations.AddField(model_name="obraparticipanteevento", name="actor_nombre_historico", field=models.CharField(max_length=301, null=True, blank=True, editable=False)),
        migrations.AddField(model_name="obraparticipanteevento", name="actor_username_historico", field=models.CharField(max_length=150, null=True, blank=True, editable=False)),
        migrations.AddField(model_name="categoriaservicioevento", name="actor_nombre_historico", field=models.CharField(max_length=301, null=True, blank=True, editable=False)),
        migrations.AddField(model_name="categoriaservicioevento", name="actor_username_historico", field=models.CharField(max_length=150, null=True, blank=True, editable=False)),
        migrations.AddField(model_name="turnoobraevento", name="actor_nombre_historico", field=models.CharField(max_length=301, null=True, blank=True, editable=False)),
        migrations.AddField(model_name="turnoobraevento", name="actor_username_historico", field=models.CharField(max_length=150, null=True, blank=True, editable=False)),
        migrations.AddField(model_name="costoobraevento", name="actor_nombre_historico", field=models.CharField(max_length=301, null=True, blank=True, editable=False)),
        migrations.AddField(model_name="costoobraevento", name="actor_username_historico", field=models.CharField(max_length=150, null=True, blank=True, editable=False)),
        migrations.RunSQL(sql="""
CREATE FUNCTION fyag_obras_identidad_evento() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'UPDATE' THEN
        IF NEW.registrado_por_id IS DISTINCT FROM OLD.registrado_por_id
            OR NEW.actor_nombre_historico IS DISTINCT FROM OLD.actor_nombre_historico
            OR NEW.actor_username_historico IS DISTINCT FROM OLD.actor_username_historico THEN
            RAISE EXCEPTION 'La identidad del evento es inmutable' USING ERRCODE = '23514';
        END IF;
        RETURN NEW;
    END IF;
    SELECT NULLIF(concat_ws(' ', NULLIF(btrim(first_name), ''), NULLIF(btrim(last_name), '')), ''), username
        INTO NEW.actor_nombre_historico, NEW.actor_username_historico
        FROM usuarios_usuario WHERE id = NEW.registrado_por_id;
    RETURN NEW;
END;
$$;
CREATE TRIGGER fyag_identidad_evento BEFORE INSERT OR UPDATE OF registrado_por_id, actor_nombre_historico, actor_username_historico ON obras_obraevento FOR EACH ROW EXECUTE FUNCTION fyag_obras_identidad_evento();
CREATE TRIGGER fyag_identidad_evento BEFORE INSERT OR UPDATE OF registrado_por_id, actor_nombre_historico, actor_username_historico ON obras_obraparticipanteevento FOR EACH ROW EXECUTE FUNCTION fyag_obras_identidad_evento();
CREATE TRIGGER fyag_identidad_evento BEFORE INSERT OR UPDATE OF registrado_por_id, actor_nombre_historico, actor_username_historico ON obras_categoriaservicioevento FOR EACH ROW EXECUTE FUNCTION fyag_obras_identidad_evento();
CREATE TRIGGER fyag_identidad_evento BEFORE INSERT OR UPDATE OF registrado_por_id, actor_nombre_historico, actor_username_historico ON obras_turnoobraevento FOR EACH ROW EXECUTE FUNCTION fyag_obras_identidad_evento();
CREATE TRIGGER fyag_identidad_evento BEFORE INSERT OR UPDATE OF registrado_por_id, actor_nombre_historico, actor_username_historico ON obras_costoobraevento FOR EACH ROW EXECUTE FUNCTION fyag_obras_identidad_evento();
        """, reverse_sql="""
DROP TRIGGER fyag_identidad_evento ON obras_obraevento;
DROP TRIGGER fyag_identidad_evento ON obras_obraparticipanteevento;
DROP TRIGGER fyag_identidad_evento ON obras_categoriaservicioevento;
DROP TRIGGER fyag_identidad_evento ON obras_turnoobraevento;
DROP TRIGGER fyag_identidad_evento ON obras_costoobraevento;
DROP FUNCTION fyag_obras_identidad_evento();
        """),
    ]
