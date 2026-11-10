from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Trim

from .validaciones import LIMITE, hoy_santiago, validar_montos


class InmutableQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError("Use el servicio financiero transaccional.")

    def delete(self):
        raise ValidationError("El historial financiero no se puede eliminar.")

    def bulk_create(self, objs, **kwargs):
        raise ValidationError("Use el servicio financiero transaccional.")

    def bulk_update(self, objs, fields, **kwargs):
        raise ValidationError("Use el servicio financiero transaccional.")


class RegistroInmutable(models.Model):
    objects = InmutableQuerySet.as_manager()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("El registro financiero es inmutable.")
        self.full_clean(validate_unique=False, validate_constraints=False)
        kwargs["force_insert"] = True
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("El historial financiero no se puede eliminar.")


class DocumentoCobro(RegistroInmutable):
    class Tipo(models.TextChoices):
        FACTURA_AFECTA = "FACTURA_AFECTA", "Factura afecta externa"
        FACTURA_EXENTA = "FACTURA_EXENTA", "Factura exenta externa"

    class Estado(models.TextChoices):
        VIGENTE = "VIGENTE", "Vigente"
        REVERTIDO = "REVERTIDO", "Revertido administrativamente"

    obra = models.ForeignKey("obras.Obra", on_delete=models.PROTECT, related_name="documentos_cobro")
    tipo_documento = models.CharField(max_length=14, choices=Tipo.choices)
    folio_externo = models.CharField(max_length=100)
    fecha_emision = models.DateField()
    fecha_vencimiento = models.DateField()
    monto_neto = models.DecimalField(max_digits=38, decimal_places=2)
    monto_impuesto = models.DecimalField(max_digits=38, decimal_places=2)
    monto_total = models.DecimalField(max_digits=38, decimal_places=2)
    referencia_respaldo = models.CharField(max_length=500)
    estado = models.CharField(max_length=9, choices=Estado.choices, default=Estado.VIGENTE, editable=False)
    registrado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="documentos_financieros_registrados", editable=False)
    registrado_en = models.DateTimeField(auto_now_add=True)
    revertido_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="documentos_financieros_revertidos", null=True, blank=True, editable=False)
    revertido_en = models.DateTimeField(null=True, blank=True, editable=False)
    motivo_reversion = models.CharField(max_length=2000, null=True, blank=True, editable=False)
    referencia_rectificacion_externa = models.CharField(max_length=500, null=True, blank=True, editable=False)

    class Meta:
        ordering = ["-registrado_en", "-id"]
        indexes = [models.Index(fields=["fecha_emision", "id"], name="fin_doc_emision_idx")]
        constraints = [
            models.UniqueConstraint(fields=["tipo_documento", "folio_externo"], name="fin_documento_folio_unico"),
            models.UniqueConstraint(fields=["obra"], condition=Q(estado="VIGENTE"), name="fin_documento_vigente_unico"),
            models.CheckConstraint(condition=Q(tipo_documento__in=["FACTURA_AFECTA", "FACTURA_EXENTA"]), name="fin_documento_tipo_valido"),
            models.CheckConstraint(condition=Q(folio_externo__regex=r"^[0-9]+$"), name="fin_documento_folio_valido"),
            models.CheckConstraint(condition=Q(fecha_vencimiento__gte=F("fecha_emision")), name="fin_documento_fechas_validas"),
            models.CheckConstraint(condition=Q(monto_neto__gte=0, monto_neto__lte=LIMITE, monto_impuesto__gte=0, monto_impuesto__lte=LIMITE, monto_total__gt=0, monto_total__lte=LIMITE), name="fin_documento_importes_rango"),
            models.CheckConstraint(condition=Q(monto_total=F("monto_neto") + F("monto_impuesto")), name="fin_documento_total_suma"),
            models.CheckConstraint(condition=Q(tipo_documento="FACTURA_EXENTA", monto_impuesto=0) | Q(tipo_documento="FACTURA_AFECTA", monto_impuesto__gt=0), name="fin_documento_impuesto_tipo"),
            models.CheckConstraint(condition=~Q(referencia_respaldo="") & Q(referencia_respaldo=Trim("referencia_respaldo")), name="fin_documento_respaldo_valido"),
            models.CheckConstraint(condition=(
                Q(estado="VIGENTE", revertido_por__isnull=True, revertido_en__isnull=True, motivo_reversion__isnull=True, referencia_rectificacion_externa__isnull=True)
                | (Q(estado="REVERTIDO", revertido_por__isnull=False, revertido_en__isnull=False, motivo_reversion__isnull=False, referencia_rectificacion_externa__isnull=False, revertido_en__gte=F("registrado_en"), motivo_reversion=Trim("motivo_reversion"), referencia_rectificacion_externa=Trim("referencia_rectificacion_externa")) & ~Q(motivo_reversion="") & ~Q(referencia_rectificacion_externa=""))
            ), name="fin_documento_estado_coherente"),
        ]

    @property
    def presupuesto(self):
        return self.obra.presupuesto

    @property
    def cliente(self):
        return self.presupuesto.cliente

    def clean(self):
        super().clean()
        validar_montos(self.monto_neto, self.monto_impuesto, self.monto_total, self.tipo_documento)
        if self.fecha_emision and self.fecha_emision > hoy_santiago():
            raise ValidationError({"fecha_emision": "No puede ser futura en Santiago."})


class CierreSinCobro(RegistroInmutable):
    obra = models.OneToOneField("obras.Obra", on_delete=models.PROTECT, related_name="cierre_sin_cobro")
    cortesia = models.ForeignKey("obras.CortesiaObra", on_delete=models.PROTECT, related_name="cierres_financieros")
    registrado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="cierres_sin_cobro_registrados", editable=False)
    registrado_en = models.DateTimeField(auto_now_add=True)
    motivo_registro = models.CharField(max_length=2000)

    class Meta:
        constraints = [models.CheckConstraint(condition=~Q(motivo_registro="") & Q(motivo_registro=Trim("motivo_registro")), name="fin_sin_cobro_motivo_valido")]

    def clean(self):
        super().clean()
        if self.cortesia_id and self.cortesia.obra_id != self.obra_id:
            raise ValidationError({"cortesia": "Debe pertenecer a la misma Obra."})


SNAPSHOT_FIELDS = {
    "obra", "tipo_documento", "folio_externo", "fecha_emision", "fecha_vencimiento",
    "monto_neto", "monto_impuesto", "monto_total", "referencia_respaldo", "estado",
    "motivo_reversion", "referencia_rectificacion_externa", "cortesia", "motivo_registro",
}


class FinanzasEvento(RegistroInmutable):
    class Tipo(models.TextChoices):
        DOCUMENTO_REGISTRADO = "DOCUMENTO_REGISTRADO", "Documento externo registrado"
        DOCUMENTO_REVERTIDO = "DOCUMENTO_REVERTIDO", "Documento revertido administrativamente"
        SIN_COBRO_REGISTRADO = "SIN_COBRO_REGISTRADO", "Cierre administrativo sin cobro"

    documento = models.ForeignKey(DocumentoCobro, on_delete=models.PROTECT, related_name="eventos", null=True, blank=True)
    cierre_sin_cobro = models.ForeignKey(CierreSinCobro, on_delete=models.PROTECT, related_name="eventos", null=True, blank=True)
    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="eventos_financieros", editable=False)
    motivo = models.CharField(max_length=2000, blank=True, default="")
    datos_anteriores = models.JSONField(default=dict, blank=True)
    datos_nuevos = models.JSONField(default=dict, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["creado_en", "id"]
        constraints = [models.CheckConstraint(condition=(
            Q(tipo__in=["DOCUMENTO_REGISTRADO", "DOCUMENTO_REVERTIDO"], documento__isnull=False, cierre_sin_cobro__isnull=True)
            | Q(tipo="SIN_COBRO_REGISTRADO", documento__isnull=True, cierre_sin_cobro__isnull=False)
        ), name="fin_evento_referencia_coherente")]

    def clean(self):
        super().clean()
        for data in (self.datos_anteriores, self.datos_nuevos):
            if not isinstance(data, dict) or set(data) - SNAPSHOT_FIELDS:
                raise ValidationError("Snapshot financiero no permitido.")
            if any(type(value) is not (int if key in {"obra", "cortesia"} else str) for key, value in data.items()):
                raise ValidationError("Tipo de snapshot financiero no permitido.")
