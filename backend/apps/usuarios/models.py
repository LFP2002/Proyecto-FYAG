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
        CREACION_CREDENCIAL_TEMPORAL = "CREACION_CREDENCIAL_TEMPORAL", "Emisión inicial temporal"
        REEMISION = "REEMISION", "Restablecimiento temporal por TI"
        CAMBIO_INICIAL = "CAMBIO_INICIAL", "Confirmación de contraseña personal"

    usuario_objetivo = models.ForeignKey(Usuario, on_delete=models.PROTECT, related_name="eventos_administrativos")
    actor = models.ForeignKey(Usuario, on_delete=models.PROTECT, related_name="acciones_administrativas")
    tipo = models.CharField(max_length=32, choices=Tipo.choices)
    motivo = models.CharField(max_length=2000, blank=True, default="")
    datos_anteriores = models.JSONField(default=dict, blank=True)
    datos_nuevos = models.JSONField(default=dict, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["creado_en", "id"]
        constraints = [models.CheckConstraint(
            condition=models.Q(tipo__in=["CREACION", "EDICION", "ACTIVACION", "DESACTIVACION", "CAMBIO_ROL", "ESTABLECER_CLAVE", "CAMBIO_CLAVE_PROPIA", "CREACION_CREDENCIAL_TEMPORAL", "REEMISION", "CAMBIO_INICIAL"]),
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
            if self.tipo in {self.Tipo.ESTABLECER_CLAVE, self.Tipo.CAMBIO_CLAVE_PROPIA,
                            self.Tipo.CREACION_CREDENCIAL_TEMPORAL, self.Tipo.REEMISION, self.Tipo.CAMBIO_INICIAL} and data:
                raise ValidationError("Los eventos de contraseña no admiten snapshots.")

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValidationError("El historial administrativo no se puede editar.")
        self.full_clean()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("El historial administrativo no se puede eliminar.")


class SeguridadCredencial(models.Model):
    """Estado SQL; nunca almacena credenciales o desafíos en texto claro."""
    class Estado(models.TextChoices):
        PERSONAL = "PERSONAL", "Personal"
        INICIAL = "INICIAL", "Inicial pendiente"
        RECUPERACION = "RECUPERACION", "Recuperación pendiente"

    usuario = models.OneToOneField(Usuario, on_delete=models.CASCADE, primary_key=True, related_name="seguridad_credencial")
    estado = models.CharField(max_length=16, choices=Estado.choices, default=Estado.PERSONAL)
    emitida_en = models.DateTimeField(null=True, editable=False)
    vence_en = models.DateTimeField(null=True, editable=False)
    desafio_digest = models.CharField(max_length=64, null=True, unique=True, editable=False)
    desafio_vence_en = models.DateTimeField(null=True, editable=False)
    desafio_version = models.PositiveBigIntegerField(null=True, editable=False)

    class Meta:
        constraints = [
            models.CheckConstraint(name="credencial_estado_coherente", condition=(
                models.Q(estado="PERSONAL", emitida_en__isnull=True, vence_en__isnull=True,
                         desafio_digest__isnull=True, desafio_vence_en__isnull=True, desafio_version__isnull=True)
                | models.Q(estado__in=["INICIAL", "RECUPERACION"], emitida_en__isnull=False,
                           vence_en__isnull=False, vence_en__gt=models.F("emitida_en"))
            )),
            models.CheckConstraint(name="credencial_desafio_coherente", condition=(
                models.Q(desafio_digest__isnull=True, desafio_vence_en__isnull=True, desafio_version__isnull=True)
                | (models.Q(desafio_digest__isnull=False, desafio_digest__regex=r"^[0-9a-f]{64}$", desafio_vence_en__isnull=False,
                            desafio_version__gte=1, desafio_version__isnull=False)
                   & models.Q(desafio_vence_en__lte=models.F("vence_en")))
            )),
        ]


# Registro Django del agregado independiente SPEC-018C; sin hooks de autenticación.
from .models_bloqueos import EstadoAcceso, EventoAcceso  # noqa: E402,F401
