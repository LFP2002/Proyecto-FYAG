"""Modelos de Gestión de Obras FYAG (incremento 004A).

Las transiciones y sus permisos se aplicarán en servicios, NO mediante save().
FINALIZADA y CANCELADA existen para el ciclo completo, pero sus acciones no
forman parte de 004A. No exponer endpoints hasta entregar el guard de Presupuestos.
"""

from decimal import Decimal, ROUND_HALF_UP, localcontext

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import F, Q
from django.db.models.functions import Lower, Trim
from django.utils import timezone

from apps.comercial.calculos import CANTIDAD_MAXIMA, CENTAVO, PRECIO_MAXIMO


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
                            | Q(estado_anterior="EN_PROCESO", estado_nuevo="FINALIZADA")
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


class ObraParticipante(_TextoValidado):
    class Origen(models.TextChoices):
        OPERACION = "OPERACION", "Operación"
        MIGRACION_004B = "MIGRACION_004B", "Migración 004B"

    campos_texto = ("motivo_asignacion", "motivo_desasignacion")
    obra = models.ForeignKey(Obra, on_delete=models.PROTECT, related_name="participantes")
    tecnico = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="participaciones_obra")
    activo = models.BooleanField(default=True)
    origen_registro = models.CharField(max_length=20, choices=Origen.choices, default=Origen.OPERACION)
    asignado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="participantes_asignados", null=True, blank=True)
    asignado_en = models.DateTimeField(null=True, blank=True)
    motivo_asignacion = models.CharField(max_length=2000, blank=True, default="")
    desasignado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="participantes_desasignados", null=True, blank=True)
    desasignado_en = models.DateTimeField(null=True, blank=True)
    motivo_desasignacion = models.CharField(max_length=2000, blank=True, default="")

    class Meta:
        ordering = ("id",)
        constraints = [
            models.UniqueConstraint(fields=("obra", "tecnico"), name="obra_participante_unico"),
            models.CheckConstraint(condition=Q(origen_registro__in=["OPERACION", "MIGRACION_004B"]), name="participante_origen_valido"),
            models.CheckConstraint(
                condition=Q(origen_registro="MIGRACION_004B") | Q(asignado_por__isnull=False, asignado_en__isnull=False, motivo_asignacion__gt=""),
                name="participante_asignacion_auditada",
            ),
            models.CheckConstraint(
                condition=(Q(activo=True, desasignado_por__isnull=True, desasignado_en__isnull=True, motivo_desasignacion="") | Q(activo=False, desasignado_por__isnull=False, desasignado_en__isnull=False, motivo_desasignacion__gt="")),
                name="participante_baja_coherente",
            ),
            models.CheckConstraint(condition=Q(motivo_asignacion=Trim("motivo_asignacion")) & Q(motivo_desasignacion=Trim("motivo_desasignacion")), name="participante_motivos_trim"),
        ]


class ObraParticipanteEvento(_TextoValidado):
    class Tipo(models.TextChoices):
        ASIGNACION = "ASIGNACION", "Asignación"
        DESASIGNACION = "DESASIGNACION", "Desasignación"
        REACTIVACION = "REACTIVACION", "Reactivación"

    campos_texto = ("motivo",)
    participante = models.ForeignKey(ObraParticipante, on_delete=models.PROTECT, related_name="eventos")
    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    registrado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="eventos_participantes")
    motivo = models.CharField(max_length=2000)
    datos_anteriores = models.JSONField(default=dict, blank=True)
    datos_nuevos = models.JSONField(default=dict)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("creado_en", "id")
        constraints = [
            models.CheckConstraint(condition=Q(tipo__in=["ASIGNACION", "DESASIGNACION", "REACTIVACION"]), name="participante_evento_tipo_valido"),
            models.CheckConstraint(condition=~Q(motivo="") & Q(motivo=Trim("motivo")), name="participante_evento_motivo"),
        ]

    def clean(self):
        super().clean()
        for campo in ("datos_anteriores", "datos_nuevos"):
            if not isinstance(getattr(self, campo), dict):
                raise ValidationError({campo: "Debe ser un objeto JSON."})


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


class TurnoObra(_TextoValidado):
    class ModoCierre(models.TextChoices):
        TECNICO = "TECNICO", "Técnico"
        SUPERVISOR = "SUPERVISOR", "Supervisor"

    class Estado(models.TextChoices):
        ABIERTO = "ABIERTO", "Abierto"
        PENDIENTE_REVISION = "PENDIENTE_REVISION", "Pendiente de revisión"
        OBSERVADO = "OBSERVADO", "Observado"
        VALIDADO = "VALIDADO", "Validado"

    campos_texto = ("descripcion_trabajo", "observacion_revision")
    obra = models.ForeignKey(Obra, on_delete=models.PROTECT, related_name="turnos")
    tecnico = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="turnos_obra")
    iniciado_en = models.DateTimeField(editable=False)
    terminado_en = models.DateTimeField(null=True, blank=True, editable=False)
    modo_cierre = models.CharField(max_length=10, choices=ModoCierre.choices, null=True, blank=True, editable=False)
    cerrado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="turnos_cerrados", null=True, blank=True, editable=False)
    # Microsegundos exactos del reloj del servidor, sin redondear horas/segundos.
    duracion_segundos = models.DecimalField(max_digits=20, decimal_places=6, null=True, blank=True, editable=False)
    duracion_ajustada_segundos = models.PositiveBigIntegerField(null=True, blank=True)
    descripcion_trabajo = models.CharField(max_length=2000, blank=True, default="")
    estado_revision = models.CharField(max_length=20, choices=Estado.choices, default=Estado.ABIERTO)
    costo_hora_neto = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    revisado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="turnos_revisados", null=True, blank=True)
    revisado_en = models.DateTimeField(null=True, blank=True)
    observacion_revision = models.CharField(max_length=2000, blank=True, default="")
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("iniciado_en", "id")
        constraints = [
            models.UniqueConstraint(fields=("tecnico",), condition=Q(terminado_en__isnull=True), name="turno_abierto_tecnico_unico"),
            models.CheckConstraint(condition=(
                Q(terminado_en__isnull=True, modo_cierre__isnull=True, cerrado_por__isnull=True)
                | Q(terminado_en__isnull=False, modo_cierre__isnull=False, modo_cierre__in=["TECNICO", "SUPERVISOR"], cerrado_por__isnull=False)
            ), name="turno_cierre_identificado"),
            models.CheckConstraint(condition=Q(terminado_en__isnull=True) | Q(terminado_en__gt=F("iniciado_en")), name="turno_fin_tras_inicio"),
            models.CheckConstraint(condition=Q(duracion_ajustada_segundos__isnull=True) | Q(duracion_ajustada_segundos__gt=0), name="turno_ajuste_positivo"),
            models.CheckConstraint(condition=Q(costo_hora_neto__isnull=True) | Q(costo_hora_neto__gte=0, costo_hora_neto__lte=Decimal("9999999999999.99")), name="turno_tarifa_finita"),
            models.CheckConstraint(condition=(
                Q(estado_revision="ABIERTO", terminado_en__isnull=True, duracion_segundos__isnull=True, duracion_ajustada_segundos__isnull=True, costo_hora_neto__isnull=True, descripcion_trabajo="")
                | (Q(estado_revision__in=["PENDIENTE_REVISION", "OBSERVADO", "VALIDADO"], terminado_en__isnull=False, duracion_segundos__isnull=False, duracion_segundos__gt=0, duracion_segundos__lte=Decimal("99999999999999.999999")) & ~Q(descripcion_trabajo=""))
            ), name="turno_estado_coherente"),
            models.CheckConstraint(condition=(
                Q(estado_revision__in=["ABIERTO", "PENDIENTE_REVISION"], revisado_por__isnull=True, revisado_en__isnull=True, observacion_revision="")
                | (Q(estado_revision__in=["OBSERVADO", "VALIDADO"], revisado_por__isnull=False, revisado_en__isnull=False) & ~Q(observacion_revision=""))
            ), name="turno_revision_auditada"),
            models.CheckConstraint(condition=~Q(estado_revision="VALIDADO") | Q(costo_hora_neto__isnull=False), name="turno_validado_con_tarifa"),
            models.CheckConstraint(condition=Q(descripcion_trabajo=Trim("descripcion_trabajo")) & Q(observacion_revision=Trim("observacion_revision")), name="turno_textos_trim"),
        ]

    @property
    def costo_mano_obra(self):
        segundos = self.duracion_ajustada_segundos or self.duracion_segundos
        if self.modo_cierre == self.ModoCierre.SUPERVISOR:
            segundos = self.duracion_ajustada_segundos
        if segundos is None or self.costo_hora_neto is None:
            return None
        with localcontext() as ctx:
            ctx.prec = 50
            return (Decimal(segundos) / Decimal(3600) * self.costo_hora_neto).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class EvidenciaTurno(_TextoValidado):
    turno = models.ForeignKey(TurnoObra, on_delete=models.PROTECT, related_name="fotos")
    obra = models.ForeignKey(Obra, on_delete=models.PROTECT, related_name="evidencias_turnos")
    nombre_interno = models.CharField(max_length=80, unique=True, editable=False)
    tipo_mime = models.CharField(max_length=20)
    tamano = models.PositiveIntegerField()
    sha256 = models.CharField(max_length=64)
    registrado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="evidencias_turnos")
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("id",)
        constraints = [
            models.CheckConstraint(condition=Q(tamano__gt=0, tamano__lte=5 * 1024 * 1024), name="evidencia_tamano_valido"),
            models.CheckConstraint(condition=Q(tipo_mime__in=["image/jpeg", "image/png", "image/webp"]), name="evidencia_mime_valido"),
        ]

    def clean(self):
        super().clean()
        if self.turno_id and self.obra_id != self.turno.obra_id:
            raise ValidationError({"obra": "La evidencia debe pertenecer a la Obra del turno."})


class TurnoObraEvento(_TextoValidado):
    class Tipo(models.TextChoices):
        INICIO = "INICIO", "Inicio"
        CIERRE = "CIERRE", "Cierre"
        CIERRE_ADMINISTRATIVO = "CIERRE_ADMINISTRATIVO", "Cierre administrativo"
        OBSERVACION = "OBSERVACION", "Observación"
        SUBSANACION = "SUBSANACION", "Subsanación"
        VALIDACION = "VALIDACION", "Validación"
        CORRECCION = "CORRECCION", "Corrección"

    campos_texto = ("motivo",)
    turno = models.ForeignKey(TurnoObra, on_delete=models.PROTECT, related_name="eventos")
    registrado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="eventos_turnos")
    tipo = models.CharField(max_length=24, choices=Tipo.choices)
    motivo = models.CharField(max_length=2000)
    datos_anteriores = models.JSONField(default=dict, blank=True)
    datos_nuevos = models.JSONField(default=dict)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("creado_en", "id")
        constraints = [
            models.CheckConstraint(condition=Q(tipo__in=["INICIO", "CIERRE", "CIERRE_ADMINISTRATIVO", "OBSERVACION", "SUBSANACION", "VALIDACION", "CORRECCION"]), name="turno_evento_tipo_valido"),
            models.CheckConstraint(condition=~Q(motivo="") & Q(motivo=Trim("motivo")), name="turno_evento_motivo_valido"),
        ]

    def clean(self):
        super().clean()
        for campo in ("datos_anteriores", "datos_nuevos"):
            if not isinstance(getattr(self, campo), dict):
                raise ValidationError({campo: "Debe ser un objeto JSON."})


class GastoObra(_TextoValidado):
    """Materiales y otros gastos directos; los subtotales se calculan, no se guardan."""

    class Tipo(models.TextChoices):
        MATERIAL = "MATERIAL", "Material"
        TRANSPORTE = "TRANSPORTE", "Transporte"
        ARRIENDO_EQUIPO = "ARRIENDO_EQUIPO", "Arriendo de equipo"
        SERVICIO_EXTERNO = "SERVICIO_EXTERNO", "Servicio externo"
        OTRO = "OTRO", "Otro"

    campos_texto = (
        "descripcion", "unidad", "referencia_respaldo", "observacion",
        "motivo_anulacion",
    )
    obra = models.ForeignKey(Obra, on_delete=models.PROTECT, related_name="gastos")
    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    descripcion = models.CharField(max_length=500)
    unidad = models.CharField(max_length=30)
    cantidad = models.DecimalField(max_digits=12, decimal_places=3)
    cantidad_devuelta = models.DecimalField(
        max_digits=12, decimal_places=3, default=Decimal("0.000"),
    )
    costo_unitario_neto = models.DecimalField(max_digits=15, decimal_places=2)
    fecha_gasto = models.DateField()
    referencia_respaldo = models.CharField(max_length=500, blank=True, default="")
    observacion = models.CharField(max_length=2000, blank=True, default="")
    vigente = models.BooleanField(default=True)
    anulado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="gastos_anulados", null=True, blank=True,
    )
    anulado_en = models.DateTimeField(null=True, blank=True)
    motivo_anulacion = models.CharField(max_length=2000, blank=True, default="")
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="gastos_registrados",
    )
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-creado_en", "-id")
        constraints = [
            models.CheckConstraint(condition=Q(tipo__in=[
                "MATERIAL", "TRANSPORTE", "ARRIENDO_EQUIPO",
                "SERVICIO_EXTERNO", "OTRO",
            ]), name="gasto_tipo_valido"),
            # Cota superior también excluye NaN de NUMERIC en PostgreSQL.
            models.CheckConstraint(condition=Q(
                cantidad__gt=0, cantidad__lte=CANTIDAD_MAXIMA,
                cantidad_devuelta__gte=0, cantidad_devuelta__lte=CANTIDAD_MAXIMA,
            ), name="gasto_cantidades_rango"),
            models.CheckConstraint(condition=Q(
                costo_unitario_neto__gte=0, costo_unitario_neto__lte=PRECIO_MAXIMO,
            ), name="gasto_costo_rango"),
            models.CheckConstraint(
                condition=Q(cantidad_devuelta__lte=F("cantidad")),
                name="gasto_devolucion_acumulada",
            ),
            models.CheckConstraint(
                condition=Q(tipo="MATERIAL") | Q(cantidad_devuelta=0),
                name="gasto_devolucion_solo_material",
            ),
            models.CheckConstraint(condition=(
                Q(vigente=True, anulado_por__isnull=True, anulado_en__isnull=True,
                  motivo_anulacion="")
                | (Q(vigente=False, anulado_por__isnull=False, anulado_en__isnull=False)
                   & ~Q(motivo_anulacion=""))
            ), name="gasto_baja_auditada"),
            models.CheckConstraint(condition=(
                ~Q(descripcion="") & ~Q(unidad="")
                & Q(descripcion=Trim("descripcion"))
                & Q(unidad=Trim("unidad"))
                & Q(referencia_respaldo=Trim("referencia_respaldo"))
                & Q(observacion=Trim("observacion"))
                & Q(motivo_anulacion=Trim("motivo_anulacion"))
            ), name="gasto_textos_validos"),
        ]

    @property
    def subtotal(self):
        """Costo interno neto: materiales descontados por devolución, ROUND_HALF_UP."""
        cantidad = self.cantidad
        if self.tipo == self.Tipo.MATERIAL:
            cantidad -= self.cantidad_devuelta
        with localcontext() as contexto:
            contexto.prec = 50
            return (cantidad * self.costo_unitario_neto).quantize(
                CENTAVO, rounding=ROUND_HALF_UP,
            )


class CostoObraEvento(_TextoValidado):
    """Historial económico append-only de gastos; nunca se expone al técnico."""

    class Tipo(models.TextChoices):
        ALTA = "ALTA", "Alta"
        CORRECCION = "CORRECCION", "Corrección"
        DEVOLUCION = "DEVOLUCION", "Devolución"
        ANULACION = "ANULACION", "Anulación"
        DECLARACION = "DECLARACION", "Declaración"
        VALIDACION = "VALIDACION", "Validación"
        CORTESIA = "CORTESIA", "Cortesía"

    campos_texto = ("motivo",)
    obra = models.ForeignKey(Obra, on_delete=models.PROTECT, related_name="eventos_costos")
    gasto = models.ForeignKey(GastoObra, on_delete=models.PROTECT, related_name="eventos", null=True, blank=True)
    control = models.ForeignKey("ControlCostosObra", on_delete=models.PROTECT, related_name="eventos", null=True, blank=True)
    cortesia = models.ForeignKey("CortesiaObra", on_delete=models.PROTECT, related_name="eventos", null=True, blank=True)
    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="eventos_costos",
    )
    motivo = models.CharField(max_length=2000)
    datos_anteriores = models.JSONField(default=dict, blank=True)
    datos_nuevos = models.JSONField(default=dict)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("creado_en", "id")
        constraints = [
            models.CheckConstraint(condition=Q(tipo__in=[
                "ALTA", "CORRECCION", "DEVOLUCION", "ANULACION",
                "DECLARACION", "VALIDACION", "CORTESIA",
            ]), name="costo_evento_tipo_valido"),
            models.CheckConstraint(condition=(
                Q(tipo__in=["ALTA", "CORRECCION", "DEVOLUCION", "ANULACION"], gasto__isnull=False, control__isnull=True, cortesia__isnull=True)
                | Q(tipo__in=["DECLARACION", "VALIDACION"], gasto__isnull=True, control__isnull=False, cortesia__isnull=True)
                | Q(tipo="CORTESIA", gasto__isnull=True, control__isnull=True, cortesia__isnull=False)
            ), name="costo_evento_recurso_coherente"),
            models.CheckConstraint(
                condition=~Q(motivo="") & Q(motivo=Trim("motivo")),
                name="costo_evento_motivo_valido",
            ),
        ]

    def clean(self):
        super().clean()
        for campo in ("datos_anteriores", "datos_nuevos"):
            if not isinstance(getattr(self, campo), dict):
                raise ValidationError({campo: "Debe ser un objeto JSON."})
        for campo in ("gasto", "control", "cortesia"):
            if getattr(self, f"{campo}_id") and getattr(self, campo).obra_id != self.obra_id:
                raise ValidationError({campo: "El recurso debe pertenecer a la misma Obra."})


class ControlCostosObra(_TextoValidado):
    class Estado(models.TextChoices):
        PENDIENTE = "PENDIENTE", "Pendiente"
        CON_REGISTROS = "CON_REGISTROS", "Con registros"
        NO_APLICA = "NO_APLICA", "No aplica"

    campos_texto = ("materiales_justificacion", "otros_justificacion")
    obra = models.OneToOneField(Obra, on_delete=models.PROTECT, related_name="control_costos")
    materiales_estado = models.CharField(max_length=13, choices=Estado.choices, default=Estado.PENDIENTE)
    otros_estado = models.CharField(max_length=13, choices=Estado.choices, default=Estado.PENDIENTE)
    materiales_justificacion = models.CharField(max_length=2000, blank=True, default="")
    otros_justificacion = models.CharField(max_length=2000, blank=True, default="")
    version_actual = models.PositiveBigIntegerField(default=0, editable=False)
    version_validada = models.PositiveBigIntegerField(null=True, blank=True, editable=False)
    validado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="controles_costos_validados", null=True, blank=True, editable=False)
    validado_en = models.DateTimeField(null=True, blank=True, editable=False)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(version_actual__gte=0), name="control_version_no_negativa"),
            models.CheckConstraint(condition=(
                Q(version_validada__isnull=True, validado_por__isnull=True, validado_en__isnull=True)
                | Q(version_validada__isnull=False, version_validada=F("version_actual"), validado_por__isnull=False, validado_en__isnull=False)
            ), name="control_validacion_coherente"),
            *[
                models.CheckConstraint(condition=(
                    Q(**{f"{rubro}_estado__in": ["PENDIENTE", "CON_REGISTROS"], f"{rubro}_justificacion": ""})
                    | (Q(**{f"{rubro}_estado": "NO_APLICA"}) & ~Q(**{f"{rubro}_justificacion": ""}))
                ) & Q(**{f"{rubro}_justificacion": Trim(f"{rubro}_justificacion")}), name=f"control_{rubro}_coherente")
                for rubro in ("materiales", "otros")
            ],
        ]

    @property
    def costos_validados(self):
        return (self.version_validada is not None
                and self.version_validada == self.version_actual
                and self.validado_por_id is not None and self.validado_en is not None)


class CortesiaObra(_TextoValidado):
    campos_texto = ("justificacion",)
    obra = models.OneToOneField(Obra, on_delete=models.PROTECT, related_name="cortesia")
    tipo = models.CharField(max_length=10, default="SIN_COBRO", editable=False)
    justificacion = models.CharField(max_length=2000)
    autorizado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="cortesias_autorizadas")
    autorizado_en = models.DateTimeField(default=timezone.now, editable=False)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(tipo="SIN_COBRO"), name="cortesia_tipo_valido"),
            models.CheckConstraint(condition=~Q(justificacion="") & Q(justificacion=Trim("justificacion")), name="cortesia_justificacion_valida"),
        ]


class _CierreInmutableQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError("La fotografía de cierre es inmutable.")

    def delete(self):
        raise ValidationError("La fotografía de cierre no se puede eliminar.")


class CierreCostosObra(_TextoValidado):
    """Fotografía económica de servidor; sin API ni registro editable en Admin."""

    # 36 enteros: margen para sumar productos y tarifas de múltiples registros.
    LIMITE_IMPORTE = Decimal("999999999999999999999999999999999999.99")
    obra = models.OneToOneField(Obra, on_delete=models.PROTECT, related_name="cierre_costos")
    materiales_total = models.DecimalField(max_digits=38, decimal_places=2, editable=False)
    otros_total = models.DecimalField(max_digits=38, decimal_places=2, editable=False)
    mano_obra_total = models.DecimalField(max_digits=38, decimal_places=2, editable=False)
    costo_total = models.DecimalField(max_digits=38, decimal_places=2, editable=False)
    version_validada = models.PositiveBigIntegerField(editable=False)
    validado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="cierres_costos_validados", editable=False)
    finalizado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="cierres_obras_finalizados", editable=False)
    creado_en = models.DateTimeField(auto_now_add=True)
    objects = _CierreInmutableQuerySet.as_manager()

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(
                materiales_total__gte=0, materiales_total__lte=Decimal("999999999999999999999999999999999999.99"),
                otros_total__gte=0, otros_total__lte=Decimal("999999999999999999999999999999999999.99"),
                mano_obra_total__gte=0, mano_obra_total__lte=Decimal("999999999999999999999999999999999999.99"),
                costo_total__gte=0, costo_total__lte=Decimal("999999999999999999999999999999999999.99"),
            ), name="cierre_importes_finitos"),
            models.CheckConstraint(condition=Q(
                costo_total=F("materiales_total") + F("otros_total") + F("mano_obra_total"),
            ), name="cierre_total_suma_rubros"),
            models.CheckConstraint(condition=Q(version_validada__gte=0), name="cierre_version_no_negativa"),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("La fotografía de cierre es inmutable.")
        kwargs["force_insert"] = True  # Nunca usar save() para sobrescribir una PK.
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("La fotografía de cierre no se puede eliminar.")
