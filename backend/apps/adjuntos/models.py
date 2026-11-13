from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.db.models.functions import Trim


class AdjuntoQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError("Los adjuntos disponibles son inmutables.")

    def delete(self):
        raise ValidationError("No se eliminan adjuntos en SPEC-012B.")

    def bulk_update(self, *args, **kwargs):
        raise ValidationError("Los adjuntos disponibles son inmutables.")


class AdjuntoDocumento(models.Model):
    class Tipo(models.TextChoices):
        RESPALDO_FACTURA = "RESPALDO_FACTURA", "Respaldo de factura externa"
        INFORME_TECNICO = "INFORME_TECNICO", "Informe técnico"

    tipo = models.CharField(max_length=16, choices=Tipo.choices, editable=False)
    documento_cobro = models.ForeignKey("finanzas.DocumentoCobro", on_delete=models.PROTECT, null=True, blank=True, related_name="adjuntos_documentales", editable=False)
    obra = models.ForeignKey("obras.Obra", on_delete=models.PROTECT, null=True, blank=True, related_name="adjuntos_documentales", editable=False)
    nombre_visible = models.CharField(max_length=160, editable=False)
    clave_interna = models.UUIDField(default=uuid4, unique=True, editable=False)
    mime = models.CharField(max_length=16, editable=False)
    tamano_bytes = models.PositiveIntegerField(editable=False)
    sha256 = models.CharField(max_length=64, editable=False)
    estado = models.CharField(max_length=10, default="DISPONIBLE", editable=False)
    registrado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="adjuntos_documentales", editable=False)
    registrado_en = models.DateTimeField(auto_now_add=True)
    clave_idempotencia = models.UUIDField(unique=True, editable=False)
    huella_solicitud = models.CharField(max_length=64, editable=False)
    objects = AdjuntoQuerySet.as_manager()

    class Meta:
        ordering = ["-registrado_en", "-id"]
        indexes = [
            models.Index(fields=["documento_cobro", "-registrado_en", "-id"], name="adj_documento_fecha_idx"),
            models.Index(fields=["obra", "-registrado_en", "-id"], name="adj_obra_fecha_idx"),
        ]
        constraints = [
            models.CheckConstraint(condition=(Q(tipo="RESPALDO_FACTURA", documento_cobro__isnull=False, obra__isnull=True) | Q(tipo="INFORME_TECNICO", documento_cobro__isnull=True, obra__isnull=False)), name="adj_tipo_parent_exclusivo"),
            models.CheckConstraint(condition=Q(estado="DISPONIBLE"), name="adj_estado_seguro"),
            models.CheckConstraint(condition=(Q(mime="application/pdf", tamano_bytes__gt=0, tamano_bytes__lte=8*1024*1024) | Q(mime__in=["image/png", "image/jpeg"], tamano_bytes__gt=0, tamano_bytes__lte=5*1024*1024)), name="adj_mime_tamano_valido"),
            models.CheckConstraint(condition=Q(sha256__regex=r"^[0-9a-f]{64}$", huella_solicitud__regex=r"^[0-9a-f]{64}$"), name="adj_digest_valido"),
            models.CheckConstraint(condition=(~Q(nombre_visible="") & Q(nombre_visible=Trim("nombre_visible")) & ~Q(nombre_visible__regex=r"[\\/\x00-\x1f\x7f]")), name="adj_nombre_seguro"),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("Los adjuntos disponibles son inmutables.")
        self.full_clean(validate_unique=False, validate_constraints=False)
        kwargs["force_insert"] = True
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("No se eliminan adjuntos en SPEC-012B.")
