"""Evento de desbloqueo TI solo asociado a una reemisión autorizada."""
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("usuarios", "0008_estado_acceso_c1")]
    operations = [
        migrations.CreateModel(
            name="RecuperacionAcceso",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("estado_anterior", models.CharField(choices=[("NORMAL", "Normal"), ("BLOQUEO_TEMPORAL", "Bloqueo temporal"), ("REQUIERE_TI", "Requiere TI")], max_length=20)),
                ("version_anterior", models.PositiveBigIntegerField()),
                ("version_nueva", models.PositiveBigIntegerField()),
                ("creado_en", models.DateTimeField()),
                ("actor", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="recuperaciones_autorizadas", to=settings.AUTH_USER_MODEL)),
                ("usuario", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="recuperaciones_acceso", to=settings.AUTH_USER_MODEL)),
                ("reemision", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, to="usuarios.usuarioevento")),
            ],
            options={"constraints": [
                models.CheckConstraint(name="recuperacion_actor_ajeno", condition=~models.Q(actor=models.F("usuario"))),
                models.CheckConstraint(name="recuperacion_versiones", condition=models.Q(version_anterior__gte=1, version_nueva=models.F("version_anterior") + 1)),
                models.CheckConstraint(name="recuperacion_estado", condition=models.Q(estado_anterior__in=["NORMAL", "BLOQUEO_TEMPORAL", "REQUIERE_TI"])),
            ]},
        ),
        migrations.RunSQL("""
            CREATE FUNCTION fyag_validar_recuperacion_c2() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
              IF NOT EXISTS (
                SELECT 1 FROM usuarios_usuarioevento e
                JOIN usuarios_usuario a ON a.id = NEW.actor_id
                JOIN usuarios_seguridadcredencial c ON c.usuario_id = NEW.usuario_id
                WHERE e.id = NEW.reemision_id AND e.tipo = 'REEMISION'
                  AND e.actor_id = NEW.actor_id AND e.usuario_objetivo_id = NEW.usuario_id
                  AND length(btrim(e.motivo)) > 0 AND a.is_active AND a.rol = 'ADMINISTRADOR_TI'
                  AND c.estado = 'RECUPERACION'
              ) THEN
                RAISE EXCEPTION 'Recuperacion requiere reemision TI autorizada' USING ERRCODE = '23514';
              END IF;
              RETURN NEW;
            END; $$;
            CREATE TRIGGER fyag_validar_recuperacion_c2 BEFORE INSERT ON usuarios_recuperacionacceso
            FOR EACH ROW EXECUTE FUNCTION fyag_validar_recuperacion_c2();
            CREATE TRIGGER fyag_recuperacion_c2_inmutable BEFORE UPDATE OR DELETE ON usuarios_recuperacionacceso
            FOR EACH ROW EXECUTE FUNCTION fyag_evento_acceso_inmutable();
            CREATE FUNCTION fyag_reemision_c2_inmutable() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
              IF EXISTS (SELECT 1 FROM usuarios_recuperacionacceso WHERE reemision_id = OLD.id) THEN
                RAISE EXCEPTION 'La reemision vinculada a recuperacion TI es inmutable' USING ERRCODE = '23514';
              END IF;
              IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
              RETURN NEW;
            END; $$;
            CREATE TRIGGER fyag_reemision_c2_inmutable BEFORE UPDATE OR DELETE ON usuarios_usuarioevento
            FOR EACH ROW EXECUTE FUNCTION fyag_reemision_c2_inmutable();
        """, """
            DROP TRIGGER IF EXISTS fyag_reemision_c2_inmutable ON usuarios_usuarioevento;
            DROP FUNCTION IF EXISTS fyag_reemision_c2_inmutable();
            DROP TRIGGER fyag_recuperacion_c2_inmutable ON usuarios_recuperacionacceso;
            DROP TRIGGER fyag_validar_recuperacion_c2 ON usuarios_recuperacionacceso;
            DROP FUNCTION fyag_validar_recuperacion_c2();
        """),
    ]
