from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Length, Trim
from django.db.models.lookups import LessThanOrEqual
from django.utils import timezone

from .catalogo import CATALOGO, ESTADOS, RECURSOS


class ProtegidoQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError("Use el servicio transaccional de alertas.")

    def delete(self):
        raise ValidationError("No se permite eliminar el historial de alertas.")

    def bulk_create(self, objs, **kwargs):
        raise ValidationError("Use el servicio transaccional de alertas.")

    def bulk_update(self, objs, fields, **kwargs):
        raise ValidationError("Use el servicio transaccional de alertas.")


class RegistroProtegido(models.Model):
    objects = ProtegidoQuerySet.as_manager()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("Use el servicio transaccional; el historial es inmutable.")
        self.full_clean(validate_unique=False, validate_constraints=False)
        kwargs["force_insert"] = True
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("No se permite eliminar el historial de alertas.")


ATENCION_NULA = Q(atendida_por__isnull=True, atendida_en__isnull=True, motivo_atencion__isnull=True)
ATENCION_COMPLETA = (Q(atendida_por__isnull=False, atendida_en__isnull=False, motivo_atencion__isnull=False,
                       atendida_en__gte=F("creado_en"), motivo_atencion=Trim("motivo_atencion"))
                     & ~Q(motivo_atencion="") & Q(LessThanOrEqual(Length("motivo_atencion"), 2000)))
CORRESPONDENCIA = Q(pk__isnull=True)  # disyunción inicial imposible para registros persistidos
for _tipo, _regla in CATALOGO.items():
    CORRESPONDENCIA |= Q(tipo=_tipo, recurso_tipo=_regla.recurso, rol_destinatario__in=_regla.roles)


class Alerta(RegistroProtegido):
    tipo = models.CharField(max_length=32, choices=[(x, x) for x in CATALOGO], editable=False)
    rol_destinatario = models.CharField(max_length=20, choices=[(x, x) for x in ("GERENCIA", "SUPERVISOR_OBRAS")], editable=False)
    recurso_tipo = models.CharField(max_length=12, choices=[(x, x) for x in sorted(RECURSOS)], editable=False)
    recurso_id = models.PositiveBigIntegerField(editable=False)
    generacion = models.PositiveIntegerField(editable=False)
    estado = models.CharField(max_length=9, choices=[(x, x) for x in ESTADOS], default="PENDIENTE", editable=False)
    creado_en = models.DateTimeField(default=timezone.now, editable=False)
    atendida_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="alertas_atendidas", editable=False)
    atendida_en = models.DateTimeField(null=True, blank=True, editable=False)
    motivo_atencion = models.CharField(max_length=2000, null=True, blank=True, editable=False)
    resuelta_en = models.DateTimeField(null=True, blank=True, editable=False)
    ultima_comprobacion_en = models.DateTimeField(default=timezone.now, editable=False)

    @property
    def severidad(self):
        return CATALOGO[self.tipo].severidad

    class Meta:
        ordering = ["-creado_en", "-id"]
        indexes = [
            models.Index(fields=["rol_destinatario", "-creado_en", "-id"], name="alerta_rol_fecha_idx"),
            models.Index(fields=["rol_destinatario", "estado", "-creado_en", "-id"], name="alerta_rol_estado_idx"),
        ]
        constraints = [
            models.CheckConstraint(condition=CORRESPONDENCIA, name="alerta_catalogo_coherente"),
            models.CheckConstraint(condition=Q(recurso_id__gt=0, generacion__gt=0), name="alerta_ids_positivos"),
            models.UniqueConstraint(fields=["tipo", "recurso_tipo", "recurso_id", "rol_destinatario", "generacion"], name="alerta_generacion_unica"),
            models.UniqueConstraint(fields=["tipo", "recurso_tipo", "recurso_id", "rol_destinatario"], condition=Q(estado__in=["PENDIENTE", "ATENDIDA"]), name="alerta_abierta_unica"),
            models.CheckConstraint(condition=(
                Q(estado="PENDIENTE", resuelta_en__isnull=True) & ATENCION_NULA
                | Q(estado="ATENDIDA", resuelta_en__isnull=True) & ATENCION_COMPLETA
                | Q(estado="RESUELTA", resuelta_en__isnull=False, resuelta_en__gte=F("creado_en"))
                  & (ATENCION_NULA | ATENCION_COMPLETA & Q(resuelta_en__gte=F("atendida_en")))
            ), name="alerta_estado_coherente"),
            models.CheckConstraint(condition=Q(ultima_comprobacion_en__gte=F("creado_en")), name="alerta_comprobacion_fecha"),
        ]


class AlertaEvento(RegistroProtegido):
    alerta = models.ForeignKey(Alerta, on_delete=models.PROTECT, related_name="eventos")
    tipo = models.CharField(max_length=10, choices=[(x, x) for x in ("CREACION", "ATENCION", "RESOLUCION")])
    estado_anterior = models.CharField(max_length=9, null=True, blank=True)
    estado_nuevo = models.CharField(max_length=9)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="eventos_alertas")
    motivo = models.CharField(max_length=2000, blank=True, default="")
    registrado_en = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        ordering = ["-registrado_en", "-id"]
        indexes = [models.Index(fields=["alerta", "-registrado_en", "-id"], name="alerta_evento_fecha_idx")]
        constraints = [
            models.UniqueConstraint(fields=["alerta", "tipo"], name="alerta_evento_transicion_unica"),
            models.CheckConstraint(condition=(
                Q(tipo="CREACION", estado_anterior__isnull=True, estado_nuevo="PENDIENTE", actor__isnull=True, motivo="")
                | Q(tipo="RESOLUCION", estado_anterior__isnull=False, estado_anterior__in=["PENDIENTE", "ATENDIDA"], estado_nuevo="RESUELTA", actor__isnull=True, motivo="")
                | Q(tipo="ATENCION", estado_anterior__isnull=False, estado_anterior="PENDIENTE", estado_nuevo="ATENDIDA", actor__isnull=False, motivo=Trim("motivo")) & ~Q(motivo="")
            ), name="alerta_evento_coherente"),
        ]


class EstadoReconciliacion(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    ultima_correcta_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=Q(id=1), name="alerta_estado_singleton")]
