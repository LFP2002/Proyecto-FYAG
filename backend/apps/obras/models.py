"""Modelos de Gestión de Obras FYAG (incremento 004A).

Las transiciones y sus permisos se aplicarán en servicios, NO mediante save().
FINALIZADA y CANCELADA existen para el ciclo completo, pero sus acciones no
forman parte de 004A. No exponer endpoints hasta entregar el guard de Presupuestos.
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower, Trim


class _TextoValidado(models.Model):
    campos_texto = ()

    class Meta:
        abstract = True

    def clean_fields(self, exclude=None):
        errores = {}
        for campo in self.campos_texto:
            if campo in (exclude or ()):
                continue
            valor = getattr(self, campo)
            if not isinstance(valor, str):
                errores[campo] = "Debe ser texto."
            else:
                setattr(self, campo, valor.strip())
        if errores:
            raise ValidationError(errores)
        super().clean_fields(exclude=exclude)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class CategoriaServicio(_TextoValidado):
    campos_texto = ("nombre",)

    nombre = models.CharField(max_length=100)
    activo = models.BooleanField(default=True)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="categorias_servicio_creadas", null=True, blank=True,
    )
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("nombre", "id")
        constraints = [
            models.CheckConstraint(
                condition=~Q(nombre="") & Q(nombre=Trim("nombre")),
                name="obra_categoria_nombre_valido",
            ),
            models.UniqueConstraint(
                Lower("nombre"), name="obra_categoria_nombre_unico",
            ),
        ]

    def __str__(self):
        return self.nombre


class Obra(_TextoValidado):
    """Una sola Obra por Presupuesto, incluso en estados terminales."""

    class Estado(models.TextChoices):
        PLANIFICADA = "PLANIFICADA", "Planificada"
        EN_PROCESO = "EN_PROCESO", "En proceso"
        SUSPENDIDA = "SUSPENDIDA", "Suspendida"
        FINALIZADA = "FINALIZADA", "Finalizada"
        CANCELADA = "CANCELADA", "Cancelada"

    campos_texto = ("descripcion",)

    presupuesto = models.OneToOneField(
        "comercial.Presupuesto", on_delete=models.PROTECT, related_name="obra",
    )
    categoria_servicio = models.ForeignKey(
        CategoriaServicio, on_delete=models.PROTECT, related_name="obras",
    )
    descripcion = models.CharField(max_length=2000)
    tecnico_responsable = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="obras_asignadas", null=True, blank=True,
    )
    fecha_programada = models.DateField(null=True, blank=True)
    iniciado_en = models.DateTimeField(null=True, blank=True, editable=False)
    estado = models.CharField(
        max_length=12, choices=Estado.choices, default=Estado.PLANIFICADA,
        editable=False,
    )
    finalizado_en = models.DateTimeField(null=True, blank=True, editable=False)
    cancelado_en = models.DateTimeField(null=True, blank=True, editable=False)
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="obras_creadas",
    )
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-creado_en", "-id")
        indexes = [
            models.Index(fields=("tecnico_responsable", "estado"), name="obra_tecnico_estado_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=Q(estado__in=["PLANIFICADA", "EN_PROCESO", "SUSPENDIDA", "FINALIZADA", "CANCELADA"]), name="obra_estado_valido",
            ),
            models.CheckConstraint(
                condition=~Q(descripcion="") & Q(descripcion=Trim("descripcion")),
                name="obra_descripcion_valida",
            ),
            models.CheckConstraint(
                condition=(
                    Q(estado="PLANIFICADA", iniciado_en__isnull=True,
                      finalizado_en__isnull=True, cancelado_en__isnull=True)
                    | Q(estado__in=["EN_PROCESO", "SUSPENDIDA"],
                        tecnico_responsable__isnull=False, iniciado_en__isnull=False,
                        finalizado_en__isnull=True, cancelado_en__isnull=True)
                    | Q(estado="FINALIZADA", tecnico_responsable__isnull=False,
                        iniciado_en__isnull=False, finalizado_en__isnull=False,
                        cancelado_en__isnull=True)
                    | Q(estado="CANCELADA", finalizado_en__isnull=True,
                        cancelado_en__isnull=False)
                ),
                name="obra_estado_fechas_coherentes",
            ),
            models.CheckConstraint(
                condition=Q(iniciado_en__isnull=True) | Q(iniciado_en__gte=F("creado_en")),
                name="obra_inicio_tras_alta",
            ),
            models.CheckConstraint(
                condition=Q(finalizado_en__isnull=True) | Q(finalizado_en__gte=F("iniciado_en")),
                name="obra_fin_tras_inicio",
            ),
            models.CheckConstraint(
                condition=Q(cancelado_en__isnull=True) | Q(cancelado_en__gte=F("creado_en")),
                name="obra_cancelacion_tras_alta",
            ),
        ]

    @property
    def codigo(self):
        return f"OB-{self.pk:06d}" if self.pk is not None else None

    @property
    def cliente_id(self):
        return self.presupuesto.cliente_id if self.presupuesto_id else None

    def __str__(self):
        return self.codigo or "Obra sin guardar"


class ObraEvento(_TextoValidado):
    class Tipo(models.TextChoices):
        CREACION = "CREACION", "Creación"
        CAMBIO_ESTADO = "CAMBIO_ESTADO", "Cambio de estado"
        CAMBIO_TECNICO = "CAMBIO_TECNICO", "Cambio de técnico"
        EDICION = "EDICION", "Edición de ficha"

    campos_texto = ("motivo",)

    obra = models.ForeignKey(Obra, on_delete=models.PROTECT, related_name="eventos")
    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    estado_anterior = models.CharField(
        max_length=12, choices=Obra.Estado.choices, null=True, blank=True,
    )
    estado_nuevo = models.CharField(max_length=12, choices=Obra.Estado.choices)
    datos_anteriores = models.JSONField(default=dict, blank=True)
    datos_nuevos = models.JSONField(default=dict)
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="eventos_obra",
    )
    motivo = models.CharField(max_length=2000, blank=True, default="")
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("creado_en", "id")
        constraints = [
            models.CheckConstraint(
                condition=Q(tipo__in=["CREACION", "CAMBIO_ESTADO", "CAMBIO_TECNICO", "EDICION"]), name="obra_evento_tipo_valido",
            ),
            models.CheckConstraint(
                condition=Q(estado_anterior__isnull=True) | Q(estado_anterior__in=Obra.Estado.values),
                name="obra_evento_estado_prev_valido",
            ),
            models.CheckConstraint(
                condition=Q(estado_nuevo__in=Obra.Estado.values),
                name="obra_evento_estado_nuevo_valido",
            ),
            models.CheckConstraint(
                condition=(
                    Q(tipo="CREACION", estado_anterior__isnull=True,
                      estado_nuevo="PLANIFICADA")
                    | (
                        Q(tipo="CAMBIO_ESTADO", motivo__gt="")
                        & (
                            Q(estado_anterior="PLANIFICADA", estado_nuevo="EN_PROCESO")
                            | Q(estado_anterior="EN_PROCESO", estado_nuevo="SUSPENDIDA")
                            | Q(estado_anterior="SUSPENDIDA", estado_nuevo="EN_PROCESO")
                        )
                    )
                    | (
                        Q(tipo__in=["CAMBIO_TECNICO", "EDICION"], motivo__gt="")
                        & Q(estado_anterior=F("estado_nuevo"))
                    )
                ),
                name="obra_evento_transicion_valida",
            ),
            models.UniqueConstraint(
                fields=("obra",), condition=Q(tipo="CREACION"),
                name="obra_evento_creacion_unica",
            ),
            models.CheckConstraint(
                condition=Q(motivo=Trim("motivo")),
                name="obra_evento_motivo_trim",
            ),
        ]

    def clean(self):
        super().clean()
        errores = {}
        for campo in ("datos_anteriores", "datos_nuevos"):
            if not isinstance(getattr(self, campo), dict):
                errores[campo] = "Debe ser un objeto JSON."
        if (
            self.tipo == self.Tipo.CREACION
            and isinstance(self.datos_nuevos, dict)
            and self.datos_nuevos.get("tecnico_responsable") is not None
            and not self.motivo
        ):
            errores["motivo"] = "Obligatorio al asignar técnico al crear."
        if errores:
            raise ValidationError(errores)


class CategoriaServicioEvento(_TextoValidado):
    class Tipo(models.TextChoices):
        CREACION = "CREACION", "Creación"
        EDICION = "EDICION", "Edición"
        ACTIVACION = "ACTIVACION", "Activación"
        DESACTIVACION = "DESACTIVACION", "Desactivación"

    campos_texto = ("motivo",)
    categoria = models.ForeignKey(
        CategoriaServicio, on_delete=models.PROTECT, related_name="eventos",
    )
    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    datos_anteriores = models.JSONField(default=dict, blank=True)
    datos_nuevos = models.JSONField(default=dict)
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="eventos_categoria_servicio",
    )
    motivo = models.CharField(max_length=2000, blank=True, default="")
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("creado_en", "id")
        constraints = [
            models.CheckConstraint(condition=Q(tipo__in=["CREACION", "EDICION", "ACTIVACION", "DESACTIVACION"]), name="obra_cat_evento_tipo_valido"),
            models.CheckConstraint(
                condition=Q(motivo=Trim("motivo")),
                name="obra_cat_evento_motivo_trim",
            ),
            models.CheckConstraint(
                condition=Q(tipo="CREACION") | ~Q(motivo=""),
                name="obra_cat_evento_motivo_oblig",
            ),
        ]

    def clean(self):
        super().clean()
        errores = {}
        for campo in ("datos_anteriores", "datos_nuevos"):
            if not isinstance(getattr(self, campo), dict):
                errores[campo] = "Debe ser un objeto JSON."
        if errores:
            raise ValidationError(errores)
