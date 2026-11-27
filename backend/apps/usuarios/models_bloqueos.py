"""Persistencia C1. No concede ni deniega autenticación en esta fase."""
from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class EstadoAcceso(models.Model):
    class Estado(models.TextChoices):
        NORMAL = "NORMAL", "Normal"
        BLOQUEO_TEMPORAL = "BLOQUEO_TEMPORAL", "Bloqueo temporal"
        REQUIERE_TI = "REQUIERE_TI", "Requiere TI"

    usuario = models.OneToOneField("usuarios.Usuario", on_delete=models.CASCADE,
                                  primary_key=True, related_name="estado_acceso")
    estado = models.CharField(max_length=20, choices=Estado.choices, default=Estado.NORMAL)
    intentos = models.PositiveSmallIntegerField(default=0)
    # Hasta cuatro fallos pendientes; el quinto se agrega en el evento de ciclo.
    fallos_en = ArrayField(models.DateTimeField(), default=list, size=4)
    ventana_inicio = models.DateTimeField(null=True)
    ventana_hasta = models.DateTimeField(null=True)
    bloqueo_inicio = models.DateTimeField(null=True)
    bloqueado_hasta = models.DateTimeField(null=True)
    # Hasta tres ciclos temporales y uno TI; evidencia histórica en EventoAcceso.
    ciclos_en = ArrayField(models.DateTimeField(), default=list, size=4)
    version = models.PositiveBigIntegerField(default=1)
    creado_en = models.DateTimeField(default=timezone.now, editable=False)
    actualizado_en = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        constraints = [
            models.CheckConstraint(name="acceso_intentos_coherentes", condition=(
                models.Q(intentos__lte=4, fallos_en__len=models.F("intentos"))
                & (models.Q(intentos=0, ventana_inicio__isnull=True, ventana_hasta__isnull=True)
                   | models.Q(intentos__gte=1, ventana_inicio__isnull=False,
                              ventana_hasta__isnull=False, ventana_hasta__gt=models.F("ventana_inicio")))
            )),
            models.CheckConstraint(name="acceso_estado_coherente", condition=(
                models.Q(estado="NORMAL", bloqueo_inicio__isnull=True, bloqueado_hasta__isnull=True, ciclos_en__len__lte=3)
                | models.Q(estado="BLOQUEO_TEMPORAL", intentos=0, bloqueo_inicio__isnull=False,
                           bloqueado_hasta__isnull=False, bloqueado_hasta__gt=models.F("bloqueo_inicio"),
                           ciclos_en__len__gte=1, ciclos_en__len__lte=3)
                | models.Q(estado="REQUIERE_TI", intentos=0, bloqueo_inicio__isnull=False,
                           bloqueado_hasta__isnull=True, ciclos_en__len=4)
            )),
            models.CheckConstraint(name="acceso_version_positiva", condition=models.Q(version__gte=1)),
            models.CheckConstraint(name="acceso_reloj_coherente", condition=models.Q(actualizado_en__gte=models.F("creado_en"))),
        ]


class EventosAccesoQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError("Los eventos de seguridad son inmutables.")

    def delete(self):
        raise ValidationError("Los eventos de seguridad son inmutables.")

    def bulk_update(self, objs, fields, **kwargs):
        raise ValidationError("Los eventos de seguridad son inmutables.")


class EventoAcceso(models.Model):
    """Sin JSON, texto libre, IP, hashes, contraseñas o tokens. Separado de TI."""
    objects = EventosAccesoQuerySet.as_manager()
    FUENTE = 'EVENTO_ACCESO'
    TIPOS_PUBLICOS = ('BLOQUEO_TEMPORAL', 'BLOQUEO_TI', 'EXPIRACION')
    ESTADOS = {'BLOQUEO_TEMPORAL': ('NORMAL', 'BLOQUEO_TEMPORAL'),
               'BLOQUEO_TI': ('NORMAL', 'REQUIERE_TI'), 'EXPIRACION': ('BLOQUEO_TEMPORAL', 'NORMAL')}

    class Tipo(models.TextChoices):
        BLOQUEO_TEMPORAL = "BLOQUEO_TEMPORAL", "Ciclo temporal (cinco fallos)"
        BLOQUEO_TI = "BLOQUEO_TI", "Cuarto ciclo (cinco fallos)"
        EXPIRACION = "EXPIRACION", "Expiración temporal"
        REINICIO_RACHA = "REINICIO_RACHA", "Racha reiniciada por acierto"

    usuario = models.ForeignKey("usuarios.Usuario", on_delete=models.PROTECT, related_name="eventos_acceso")
    tipo = models.CharField(max_length=24, choices=Tipo.choices)
    actor_tipo = models.CharField(max_length=8, choices=[("SISTEMA", "Sistema"), ("TITULAR", "Titular")])
    actor = models.ForeignKey("usuarios.Usuario", null=True, blank=True, on_delete=models.PROTECT, related_name="acciones_acceso")
    version = models.PositiveBigIntegerField()
    cantidad_fallos = models.PositiveSmallIntegerField(default=0)
    creado_en = models.DateTimeField()

    class Meta:
        ordering = ["creado_en", "id"]
        constraints = [
            models.UniqueConstraint(fields=["usuario", "version", "tipo"], name="acceso_evento_unico"),
            models.CheckConstraint(name="acceso_evento_contenido", condition=(
                models.Q(tipo__in=["BLOQUEO_TEMPORAL", "BLOQUEO_TI"], actor_tipo="SISTEMA", actor__isnull=True, cantidad_fallos=5)
                | models.Q(tipo="EXPIRACION", actor_tipo="SISTEMA", actor__isnull=True, cantidad_fallos=0)
                | models.Q(tipo="REINICIO_RACHA", actor_tipo="TITULAR", actor=models.F("usuario"),
                           actor__isnull=False, cantidad_fallos__gte=1, cantidad_fallos__lte=4)
            )),
            models.CheckConstraint(name="acceso_evento_version", condition=models.Q(version__gte=2)),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("Los eventos de seguridad son inmutables.")
        self.full_clean()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Los eventos de seguridad son inmutables.")


class RecuperacionAcceso(models.Model):
    """Desbloqueo TI exclusivamente ligado a reemisión, sin texto/secretos nuevos."""
    objects = EventosAccesoQuerySet.as_manager()
    usuario = models.ForeignKey("usuarios.Usuario", on_delete=models.PROTECT, related_name="recuperaciones_acceso")
    actor = models.ForeignKey("usuarios.Usuario", on_delete=models.PROTECT, related_name="recuperaciones_autorizadas")
    reemision = models.OneToOneField("usuarios.UsuarioEvento", on_delete=models.PROTECT)
    estado_anterior = models.CharField(max_length=20, choices=EstadoAcceso.Estado.choices)
    version_anterior = models.PositiveBigIntegerField()
    version_nueva = models.PositiveBigIntegerField()
    creado_en = models.DateTimeField()

    class Meta:
        constraints = [
            models.CheckConstraint(name="recuperacion_actor_ajeno", condition=~models.Q(actor=models.F("usuario"))),
            models.CheckConstraint(name="recuperacion_versiones", condition=models.Q(version_anterior__gte=1, version_nueva=models.F("version_anterior") + 1)),
            models.CheckConstraint(name="recuperacion_estado", condition=models.Q(estado_anterior__in=EstadoAcceso.Estado.values)),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("El desbloqueo TI es inmutable.")
        self.full_clean()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("El desbloqueo TI es inmutable.")
