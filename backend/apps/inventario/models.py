from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.functions import Lower, Trim
from django.utils import timezone


MAXIMO = Decimal("999999999.999")


class ArticuloInventario(models.Model):
    codigo = models.CharField(max_length=50, unique=True)
    nombre = models.CharField(max_length=150)
    descripcion = models.CharField(max_length=2000, blank=True, default="")
    unidad = models.CharField(max_length=30)
    activo = models.BooleanField(default=True)
    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="articulos_creados")
    actualizado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="articulos_actualizados")
    creado_en = models.DateTimeField(default=timezone.now, editable=False)
    actualizado_en = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(name="inventario_codigo_formato", condition=models.Q(codigo__regex=r"^[a-z0-9][a-z0-9._-]{0,49}$")),
            models.CheckConstraint(name="inventario_unidad_normalizada", condition=models.Q(unidad=Lower(Trim("unidad"))) & ~models.Q(unidad__regex=r"^\s*$")),
            models.CheckConstraint(name="inventario_nombre_no_vacio", condition=~models.Q(nombre__regex=r"^\s*$")),
            models.CheckConstraint(name="inventario_articulo_reloj", condition=models.Q(actualizado_en__gte=models.F("creado_en"))),
        ]


class ExistenciaInventario(models.Model):
    articulo = models.OneToOneField(ArticuloInventario, primary_key=True, on_delete=models.PROTECT, related_name="existencia")
    saldo = models.DecimalField(max_digits=12, decimal_places=3, default=Decimal("0.000"), editable=False)

    class Meta:
        ordering = ["articulo_id"]
        constraints = [models.CheckConstraint(name="inventario_saldo_rango", condition=models.Q(saldo__gte=0, saldo__lte=MAXIMO))]


class MovimientosQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError("El libro de inventario es inmutable.")

    def delete(self):
        raise ValidationError("El libro de inventario es inmutable.")

    def bulk_update(self, *args, **kwargs):
        raise ValidationError("El libro de inventario es inmutable.")


class MovimientoInventario(models.Model):
    class Tipo(models.TextChoices):
        INGRESO = "INGRESO", "Ingreso físico"

    objects = MovimientosQuerySet.as_manager()
    articulo = models.ForeignKey(ArticuloInventario, on_delete=models.PROTECT, related_name="movimientos")
    tipo = models.CharField(max_length=12, choices=Tipo.choices, default=Tipo.INGRESO)
    clave_idempotencia = models.UUIDField(unique=True, editable=False)
    cantidad = models.DecimalField(max_digits=12, decimal_places=3)
    saldo_anterior = models.DecimalField(max_digits=12, decimal_places=3, editable=False)
    saldo_posterior = models.DecimalField(max_digits=12, decimal_places=3, editable=False)
    referencia = models.CharField(max_length=150, blank=True, default="")
    motivo = models.CharField(max_length=2000, blank=True, default="")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="movimientos_inventario")
    creado_en = models.DateTimeField(default=timezone.now, editable=False, db_index=True)

    class Meta:
        ordering = ["creado_en", "id"]
        constraints = [
            models.CheckConstraint(name="inventario_movimiento_tipo", condition=models.Q(tipo="INGRESO")),
            models.CheckConstraint(name="inventario_cantidad_rango", condition=models.Q(cantidad__gt=0, cantidad__lte=MAXIMO)),
            models.CheckConstraint(name="inventario_saldos_rango", condition=models.Q(saldo_anterior__gte=0, saldo_anterior__lte=MAXIMO, saldo_posterior__gte=0, saldo_posterior__lte=MAXIMO)),
            models.CheckConstraint(name="inventario_movimiento_suma", condition=models.Q(saldo_posterior=models.F("saldo_anterior") + models.F("cantidad"))),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("El libro de inventario es inmutable.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("El libro de inventario es inmutable.")
