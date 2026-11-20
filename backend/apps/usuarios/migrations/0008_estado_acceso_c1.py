"""SPEC-018C C1: agregado aislado; no modifica autenticación ni credenciales."""
import django.contrib.postgres.fields
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


def inicializar(apps, schema_editor):
    User = apps.get_model("usuarios", "Usuario")
    State = apps.get_model("usuarios", "EstadoAcceso")
    alias = schema_editor.connection.alias
    batch = []
    for pk in User.objects.using(alias).values_list("pk", flat=True).iterator(chunk_size=1000):
        batch.append(State(usuario_id=pk))
        if len(batch) == 1000:
            State.objects.using(alias).bulk_create(batch)
            batch = []
    if batch:
        State.objects.using(alias).bulk_create(batch)


SQL = """
CREATE FUNCTION fyag_acceso_tiempos_validos(valores timestamptz[], maximo integer)
RETURNS boolean LANGUAGE sql IMMUTABLE STRICT AS $$
  SELECT cardinality(valores) <= maximo AND
    (cardinality(valores) = 0 OR
     (array_ndims(valores) = 1 AND array_lower(valores, 1) = 1
      AND NOT EXISTS (SELECT 1 FROM unnest(valores) AS t WHERE t IS NULL)
      AND NOT EXISTS (SELECT 1 FROM generate_subscripts(valores, 1) AS i
                      WHERE valores[i] > valores[i+1])))
$$;
ALTER TABLE usuarios_estadoacceso ADD CONSTRAINT acceso_fechas_detalladas CHECK (
  fyag_acceso_tiempos_validos(fallos_en, 4)
  AND fyag_acceso_tiempos_validos(ciclos_en, 4)
  AND (cardinality(fallos_en) = 0 OR
       (ventana_inicio = fallos_en[1]
        AND ventana_hasta = ventana_inicio + interval '15 minutes'
        AND fallos_en[cardinality(fallos_en)] < ventana_hasta
        AND fallos_en[cardinality(fallos_en)] <= actualizado_en))
  AND (cardinality(ciclos_en) = 0 OR ciclos_en[cardinality(ciclos_en)] <= actualizado_en)
  AND (estado = 'NORMAL' OR bloqueo_inicio = ciclos_en[cardinality(ciclos_en)])
  AND (estado <> 'BLOQUEO_TEMPORAL' OR bloqueado_hasta = bloqueo_inicio +
       CASE cardinality(ciclos_en) WHEN 1 THEN interval '15 minutes'
       WHEN 2 THEN interval '60 minutes' WHEN 3 THEN interval '240 minutes' END)
);
CREATE FUNCTION fyag_usuario_acceso_inicial() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE instante timestamptz := clock_timestamp();
BEGIN
  INSERT INTO usuarios_estadoacceso
    (usuario_id, estado, intentos, fallos_en, ciclos_en, version, creado_en, actualizado_en)
  VALUES (NEW.id, 'NORMAL', 0, '{}', '{}', 1, instante, instante);
  RETURN NEW;
END;
$$;
CREATE TRIGGER fyag_usuario_acceso_inicial AFTER INSERT ON usuarios_usuario
FOR EACH ROW EXECUTE FUNCTION fyag_usuario_acceso_inicial();
CREATE FUNCTION fyag_evento_acceso_inmutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'Los eventos de seguridad son inmutables' USING ERRCODE = '23514';
END;
$$;
CREATE TRIGGER fyag_evento_acceso_inmutable BEFORE UPDATE OR DELETE ON usuarios_eventoacceso
FOR EACH ROW EXECUTE FUNCTION fyag_evento_acceso_inmutable();
"""

REVERSE_SQL = """
DROP TRIGGER fyag_evento_acceso_inmutable ON usuarios_eventoacceso;
DROP FUNCTION fyag_evento_acceso_inmutable();
DROP TRIGGER fyag_usuario_acceso_inicial ON usuarios_usuario;
DROP FUNCTION fyag_usuario_acceso_inicial();
ALTER TABLE usuarios_estadoacceso DROP CONSTRAINT acceso_fechas_detalladas;
DROP FUNCTION fyag_acceso_tiempos_validos(timestamptz[], integer);
"""


class Migration(migrations.Migration):
    dependencies = [("usuarios", "0007_estado_seguridad_al_insertar")]
    operations = [
        migrations.CreateModel(
            name="EstadoAcceso",
            fields=[
                ("usuario", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, primary_key=True, related_name="estado_acceso", serialize=False, to=settings.AUTH_USER_MODEL)),
                ("estado", models.CharField(choices=[("NORMAL", "Normal"), ("BLOQUEO_TEMPORAL", "Bloqueo temporal"), ("REQUIERE_TI", "Requiere TI")], default="NORMAL", max_length=20)),
                ("intentos", models.PositiveSmallIntegerField(default=0)),
                ("fallos_en", django.contrib.postgres.fields.ArrayField(base_field=models.DateTimeField(), default=list, size=4)),
                ("ventana_inicio", models.DateTimeField(null=True)),
                ("ventana_hasta", models.DateTimeField(null=True)),
                ("bloqueo_inicio", models.DateTimeField(null=True)),
                ("bloqueado_hasta", models.DateTimeField(null=True)),
                ("ciclos_en", django.contrib.postgres.fields.ArrayField(base_field=models.DateTimeField(), default=list, size=4)),
                ("version", models.PositiveBigIntegerField(default=1)),
                ("creado_en", models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ("actualizado_en", models.DateTimeField(default=django.utils.timezone.now, editable=False)),
            ],
            options={"constraints": [
                models.CheckConstraint(name="acceso_intentos_coherentes", condition=(models.Q(intentos__lte=4, fallos_en__len=models.F("intentos")) & (models.Q(intentos=0, ventana_inicio__isnull=True, ventana_hasta__isnull=True) | models.Q(intentos__gte=1, ventana_inicio__isnull=False, ventana_hasta__isnull=False, ventana_hasta__gt=models.F("ventana_inicio"))))),
                models.CheckConstraint(name="acceso_estado_coherente", condition=(models.Q(estado="NORMAL", bloqueo_inicio__isnull=True, bloqueado_hasta__isnull=True, ciclos_en__len__lte=3) | models.Q(estado="BLOQUEO_TEMPORAL", intentos=0, bloqueo_inicio__isnull=False, bloqueado_hasta__isnull=False, bloqueado_hasta__gt=models.F("bloqueo_inicio"), ciclos_en__len__gte=1, ciclos_en__len__lte=3) | models.Q(estado="REQUIERE_TI", intentos=0, bloqueo_inicio__isnull=False, bloqueado_hasta__isnull=True, ciclos_en__len=4))),
                models.CheckConstraint(name="acceso_version_positiva", condition=models.Q(version__gte=1)),
                models.CheckConstraint(name="acceso_reloj_coherente", condition=models.Q(actualizado_en__gte=models.F("creado_en"))),
            ]},
        ),
        migrations.CreateModel(
            name="EventoAcceso",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("tipo", models.CharField(choices=[("BLOQUEO_TEMPORAL", "Ciclo temporal (cinco fallos)"), ("BLOQUEO_TI", "Cuarto ciclo (cinco fallos)"), ("EXPIRACION", "Expiración temporal"), ("REINICIO_RACHA", "Racha reiniciada por acierto")], max_length=24)),
                ("actor_tipo", models.CharField(choices=[("SISTEMA", "Sistema"), ("TITULAR", "Titular")], max_length=8)),
                ("version", models.PositiveBigIntegerField()),
                ("cantidad_fallos", models.PositiveSmallIntegerField(default=0)),
                ("creado_en", models.DateTimeField()),
                ("actor", models.ForeignKey(null=True, blank=True, on_delete=django.db.models.deletion.PROTECT, related_name="acciones_acceso", to=settings.AUTH_USER_MODEL)),
                ("usuario", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="eventos_acceso", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["creado_en", "id"], "constraints": [
                models.UniqueConstraint(fields=("usuario", "version", "tipo"), name="acceso_evento_unico"),
                models.CheckConstraint(name="acceso_evento_contenido", condition=(models.Q(tipo__in=["BLOQUEO_TEMPORAL", "BLOQUEO_TI"], actor_tipo="SISTEMA", actor__isnull=True, cantidad_fallos=5) | models.Q(tipo="EXPIRACION", actor_tipo="SISTEMA", actor__isnull=True, cantidad_fallos=0) | models.Q(tipo="REINICIO_RACHA", actor_tipo="TITULAR", actor=models.F("usuario"), actor__isnull=False, cantidad_fallos__gte=1, cantidad_fallos__lte=4))),
                models.CheckConstraint(name="acceso_evento_version", condition=models.Q(version__gte=2)),
            ]},
        ),
        # Evitar INSERT concurrente entre snapshot histórico y creación del trigger.
        migrations.RunSQL("LOCK TABLE usuarios_usuario IN SHARE ROW EXCLUSIVE MODE", migrations.RunSQL.noop),
        migrations.RunPython(inicializar, migrations.RunPython.noop),
        migrations.RunSQL(SQL, REVERSE_SQL),
    ]
