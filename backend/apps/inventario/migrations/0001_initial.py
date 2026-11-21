"""Esquema 019A, derivado de makemigrations Django 5.2; sin datos de ejemplo."""
from decimal import Decimal
import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models
from django.db.models.functions import Lower, Trim


class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(name="ArticuloInventario", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("codigo", models.CharField(max_length=50, unique=True)),
            ("nombre", models.CharField(max_length=150)),
            ("descripcion", models.CharField(blank=True, default="", max_length=2000)),
            ("unidad", models.CharField(max_length=30)),
            ("activo", models.BooleanField(default=True)),
            ("creado_en", models.DateTimeField(default=django.utils.timezone.now, editable=False)),
            ("actualizado_en", models.DateTimeField(default=django.utils.timezone.now, editable=False)),
            ("creado_por", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="articulos_creados", to=settings.AUTH_USER_MODEL)),
            ("actualizado_por", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="articulos_actualizados", to=settings.AUTH_USER_MODEL)),
        ], options={"ordering": ["id"], "constraints": [
            models.CheckConstraint(name="inventario_codigo_formato", condition=models.Q(codigo__regex=r"^[a-z0-9][a-z0-9._-]{0,49}$")),
            models.CheckConstraint(name="inventario_unidad_normalizada", condition=models.Q(unidad=Lower(Trim("unidad"))) & ~models.Q(unidad__regex=r"^\s*$")),
            models.CheckConstraint(name="inventario_nombre_no_vacio", condition=~models.Q(nombre__regex=r"^\s*$")),
            models.CheckConstraint(name="inventario_articulo_reloj", condition=models.Q(actualizado_en__gte=models.F("creado_en"))),
        ]}),
        migrations.CreateModel(name="ExistenciaInventario", fields=[
            ("articulo", models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, primary_key=True, serialize=False, related_name="existencia", to="inventario.articuloinventario")),
            ("saldo", models.DecimalField(decimal_places=3, default=Decimal("0.000"), editable=False, max_digits=12)),
        ], options={"ordering": ["articulo_id"], "constraints": [
            models.CheckConstraint(name="inventario_saldo_rango", condition=models.Q(saldo__gte=0, saldo__lte=Decimal("999999999.999"))),
        ]}),
        migrations.CreateModel(name="MovimientoInventario", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("tipo", models.CharField(choices=[("INGRESO", "Ingreso físico")], default="INGRESO", max_length=12)),
            ("clave_idempotencia", models.UUIDField(editable=False, unique=True)),
            ("cantidad", models.DecimalField(decimal_places=3, max_digits=12)),
            ("saldo_anterior", models.DecimalField(decimal_places=3, editable=False, max_digits=12)),
            ("saldo_posterior", models.DecimalField(decimal_places=3, editable=False, max_digits=12)),
            ("referencia", models.CharField(blank=True, default="", max_length=150)),
            ("motivo", models.CharField(blank=True, default="", max_length=2000)),
            ("creado_en", models.DateTimeField(db_index=True, default=django.utils.timezone.now, editable=False)),
            ("actor", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="movimientos_inventario", to=settings.AUTH_USER_MODEL)),
            ("articulo", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="movimientos", to="inventario.articuloinventario")),
        ], options={"ordering": ["creado_en", "id"], "constraints": [
            models.CheckConstraint(name="inventario_movimiento_tipo", condition=models.Q(tipo="INGRESO")),
            models.CheckConstraint(name="inventario_cantidad_rango", condition=models.Q(cantidad__gt=0, cantidad__lte=Decimal("999999999.999"))),
            models.CheckConstraint(name="inventario_saldos_rango", condition=models.Q(saldo_anterior__gte=0, saldo_anterior__lte=Decimal("999999999.999"), saldo_posterior__gte=0, saldo_posterior__lte=Decimal("999999999.999"))),
            models.CheckConstraint(name="inventario_movimiento_suma", condition=models.Q(saldo_posterior=models.F("saldo_anterior") + models.F("cantidad"))),
        ]}),
    ]
