"""SPEC-018 A: esquema aditivo; no modifica hashes, cuentas ni sesiones previas."""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def cuentas_historicas(apps, schema_editor):
    User = apps.get_model("usuarios", "Usuario")
    State = apps.get_model("usuarios", "SeguridadCredencial")
    alias = schema_editor.connection.alias
    # Por lotes; solo crea estado PERSONAL sin tocar Usuario ni su historial.
    batch = []
    for pk in User.objects.using(alias).values_list("pk", flat=True).iterator(chunk_size=1000):
        batch.append(State(usuario_id=pk, estado="PERSONAL"))
        if len(batch) == 1000:
            State.objects.using(alias).bulk_create(batch)
            batch = []
    if batch:
        State.objects.using(alias).bulk_create(batch)


class Migration(migrations.Migration):
    dependencies = [("usuarios", "0005_administrador_ti")]
    operations = [
        migrations.CreateModel(
            name="SeguridadCredencial",
            fields=[
                ("usuario", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, primary_key=True, related_name="seguridad_credencial", serialize=False, to=settings.AUTH_USER_MODEL)),
                ("estado", models.CharField(choices=[("PERSONAL", "Personal"), ("INICIAL", "Inicial pendiente"), ("RECUPERACION", "Recuperación pendiente")], default="PERSONAL", max_length=16)),
                ("emitida_en", models.DateTimeField(editable=False, null=True)),
                ("vence_en", models.DateTimeField(editable=False, null=True)),
                ("desafio_digest", models.CharField(editable=False, max_length=64, null=True, unique=True)),
                ("desafio_vence_en", models.DateTimeField(editable=False, null=True)),
                ("desafio_version", models.PositiveBigIntegerField(editable=False, null=True)),
            ],
        ),
        migrations.RemoveConstraint(model_name="usuarioevento", name="usuarios_evento_tipo_valido"),
        migrations.AlterField(
            model_name="usuarioevento", name="tipo",
            field=models.CharField(choices=[("CREACION", "Creación"), ("EDICION", "Edición"), ("ACTIVACION", "Activación"), ("DESACTIVACION", "Desactivación"), ("CAMBIO_ROL", "Cambio de rol"), ("ESTABLECER_CLAVE", "Establecimiento de contraseña"), ("CAMBIO_CLAVE_PROPIA", "Cambio propio de contraseña"), ("CREACION_CREDENCIAL_TEMPORAL", "Emisión inicial temporal"), ("REEMISION", "Restablecimiento temporal por TI"), ("CAMBIO_INICIAL", "Confirmación de contraseña personal")], max_length=32),
        ),
        migrations.AddConstraint(
            model_name="usuarioevento",
            constraint=models.CheckConstraint(condition=models.Q(tipo__in=["CREACION", "EDICION", "ACTIVACION", "DESACTIVACION", "CAMBIO_ROL", "ESTABLECER_CLAVE", "CAMBIO_CLAVE_PROPIA", "CREACION_CREDENCIAL_TEMPORAL", "REEMISION", "CAMBIO_INICIAL"]), name="usuarios_evento_tipo_valido"),
        ),
        migrations.AddConstraint(
            model_name="seguridadcredencial",
            constraint=models.CheckConstraint(name="credencial_estado_coherente", condition=(
                models.Q(estado="PERSONAL", emitida_en__isnull=True, vence_en__isnull=True, desafio_digest__isnull=True, desafio_vence_en__isnull=True, desafio_version__isnull=True)
                | models.Q(estado__in=["INICIAL", "RECUPERACION"], emitida_en__isnull=False, vence_en__isnull=False, vence_en__gt=models.F("emitida_en"))
            )),
        ),
        migrations.AddConstraint(
            model_name="seguridadcredencial",
            constraint=models.CheckConstraint(name="credencial_desafio_coherente", condition=(
                models.Q(desafio_digest__isnull=True, desafio_vence_en__isnull=True, desafio_version__isnull=True)
                | (models.Q(desafio_digest__isnull=False, desafio_digest__regex=r"^[0-9a-f]{64}$", desafio_vence_en__isnull=False, desafio_version__gte=1, desafio_version__isnull=False)
                   & models.Q(desafio_vence_en__lte=models.F("vence_en")))
            )),
        ),
        migrations.RunPython(cuentas_historicas, migrations.RunPython.noop),
    ]
