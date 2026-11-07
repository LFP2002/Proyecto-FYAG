"""Catálogo inicial de tipos de servicio de FYAG, sin suplantar actor humano."""

from django.db import migrations


CATEGORIAS = (
    "Proyecto",
    "Mantención",
    "Climatización",
    "Proyecto eléctrico",
    "Emergencia",
    "Garantía",
    "Venta de repuestos",
    "Mejoras",
)


def agregar_categorias(apps, schema_editor):
    CategoriaServicio = apps.get_model("obras", "CategoriaServicio")
    db = schema_editor.connection.alias
    for nombre in CATEGORIAS:
        CategoriaServicio.objects.using(db).get_or_create(
            nombre=nombre,
            defaults={"activo": True, "creado_por_id": None},
        )


class Migration(migrations.Migration):
    dependencies = [("obras", "0001_initial")]
    operations = [migrations.RunPython(agregar_categorias, migrations.RunPython.noop)]
