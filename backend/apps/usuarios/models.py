from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.functions import Lower, Trim


class Usuario(AbstractUser):

    class Rol(models.TextChoices):
        GERENCIA = "GERENCIA", "Gerencia"
        ADMINISTRATIVO_FINANZAS = (
            "ADMINISTRATIVO_FINANZAS",
            "Administrativo / Finanzas",
        )
        SUPERVISOR_OBRAS = (
            "SUPERVISOR_OBRAS",
            "Supervisor de Obras",
        )
        TECNICO = "TECNICO", "Técnico"
        ADMINISTRADOR_TI = "ADMINISTRADOR_TI", "Administrador de TI"

    email = models.EmailField(
        unique=True,
    )

    rol = models.CharField(
        max_length=30,
        choices=Rol.choices,
    )
    sesion_version = models.PositiveBigIntegerField(default=1, editable=False)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    class Meta:
        verbose_name = "user"
        verbose_name_plural = "users"

        constraints = [
            models.CheckConstraint(condition=models.Q(sesion_version__gte=1), name="usuarios_sesion_version_positiva"),
            models.CheckConstraint(
                condition=~models.Q(email=""),
                name="usuarios_email_no_vacio",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    email=Lower(Trim("email"))
                ),
                name="usuarios_email_normalizado",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    rol__in=[
                        "GERENCIA",
                        "ADMINISTRATIVO_FINANZAS",
                        "SUPERVISOR_OBRAS",
                        "TECNICO",
                        "ADMINISTRADOR_TI",
                    ]
                ),
                name="usuarios_rol_valido",
            ),
        ]

    def _normalizar_email(self):
        if self.email:
            self.email = (
                self.email
                .strip()
                .lower()
            )

    def clean(self):
        self._normalizar_email()
        super().clean()

    def save(self, *args, **kwargs):
        self._normalizar_email()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.email


class EventosInmutablesQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError("El historial administrativo no se puede editar.")

    def delete(self):
        raise ValidationError("El historial administrativo no se puede eliminar.")

    def bulk_create(self, objs, **kwargs):
        raise ValidationError("El historial debe registrarse mediante una operación auditada.")

    def bulk_update(self, objs, fields, **kwargs):
        raise ValidationError("El historial administrativo no se puede editar.")


class UsuarioEvento(models.Model):
    objects = EventosInmutablesQuerySet.as_manager()
    class Tipo(models.TextChoices):
        CREACION = "CREACION", "Creación"
        EDICION = "EDICION", "Edición"
        ACTIVACION = "ACTIVACION", "Activación"
        DESACTIVACION = "DESACTIVACION", "Desactivación"
        CAMBIO_ROL = "CAMBIO_ROL", "Cambio de rol"
        ESTABLECER_CLAVE = "ESTABLECER_CLAVE", "Establecimiento de contraseña"
        CAMBIO_CLAVE_PROPIA = "CAMBIO_CLAVE_PROPIA", "Cambio propio de contraseña"

    usuario_objetivo = models.ForeignKey(Usuario, on_delete=models.PROTECT, related_name="eventos_administrativos")
    actor = models.ForeignKey(Usuario, on_delete=models.PROTECT, related_name="acciones_administrativas")
    tipo = models.CharField(max_length=24, choices=Tipo.choices)
    motivo = models.CharField(max_length=2000, blank=True, default="")
    datos_anteriores = models.JSONField(default=dict, blank=True)
    datos_nuevos = models.JSONField(default=dict, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["creado_en", "id"]
        constraints = [models.CheckConstraint(
            condition=models.Q(tipo__in=["CREACION", "EDICION", "ACTIVACION", "DESACTIVACION", "CAMBIO_ROL", "ESTABLECER_CLAVE", "CAMBIO_CLAVE_PROPIA"]),
            name="usuarios_evento_tipo_valido",
        )]

    def clean(self):
        super().clean()
        allowed = {"email", "username", "first_name", "last_name", "rol", "is_active"}
        for data in (self.datos_anteriores, self.datos_nuevos):
            if not isinstance(data, dict) or set(data) - allowed:
                raise ValidationError("Snapshot administrativo no permitido.")
            if any(type(value) is not (bool if key == "is_active" else str) for key, value in data.items()):
                raise ValidationError("Tipos de snapshot no permitidos.")
            if self.tipo in {self.Tipo.ESTABLECER_CLAVE, self.Tipo.CAMBIO_CLAVE_PROPIA} and data:
                raise ValidationError("Los eventos de contraseña no admiten snapshots.")

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValidationError("El historial administrativo no se puede editar.")
        self.full_clean()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("El historial administrativo no se puede eliminar.")
