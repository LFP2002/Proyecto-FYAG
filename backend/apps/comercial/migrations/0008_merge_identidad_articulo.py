"""Unifica las ramas independientes de Comercial sin modificar datos."""
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("comercial", "0007_presupuestoitem_articulo"),
        ("comercial", "0007_identidad_evento"),
    ]
    operations = []
