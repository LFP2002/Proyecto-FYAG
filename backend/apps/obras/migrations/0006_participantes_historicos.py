from django.db import migrations


def incorporar_principales(apps, schema_editor):
    Obra = apps.get_model("obras", "Obra")
    Participante = apps.get_model("obras", "ObraParticipante")
    alias = schema_editor.connection.alias
    for obra in Obra.objects.using(alias).exclude(tecnico_responsable_id=None).iterator():
        Participante.objects.using(alias).get_or_create(
            obra_id=obra.pk, tecnico_id=obra.tecnico_responsable_id,
            defaults={"activo": True, "origen_registro": "MIGRACION_004B"},
        )


class Migration(migrations.Migration):
    dependencies = [("obras", "0005_participantes")]
    # No borrar membresías ni su historia al revertir solamente el backfill.
    operations = [migrations.RunPython(incorporar_principales, migrations.RunPython.noop)]
