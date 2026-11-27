from django.contrib.auth.models import AbstractUser
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.functions import Lower, Trim


class InstalacionFYAG(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    inicializada_en = models.DateTimeField(null=True, editable=False)
    clave_digest = models.CharField(max_length=64, null=True, editable=False)
    clave_vence_en = models.DateTimeField(null=True, editable=False)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(id=1), name='instalacion_fyag_unica'),
            models.CheckConstraint(condition=(
                models.Q(clave_digest__isnull=True, clave_vence_en__isnull=True)
                | models.Q(inicializada_en__isnull=True, clave_digest__isnull=False,
                           clave_digest__regex=r'^[0-9a-f]{64}$', clave_vence_en__isnull=False)
            ), name='instalacion_fyag_clave_coherente'),
        ]


class EventoInstalacionFYAG(models.Model):
    class Tipo(models.TextChoices):
        EMISION = 'EMISION', 'Clave emitida'
        RENOVACION = 'RENOVACION', 'Clave renovada'
        INICIALIZACION_WEB = 'INICIALIZACION_WEB', 'Inicializada por clave de infraestructura'
        INICIALIZACION_CLI = 'INICIALIZACION_CLI', 'Inicializada por terminal de infraestructura'

    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    operador = models.CharField(max_length=64, blank=True)
    referencia = models.CharField(max_length=64, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)


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
        BODEGUERO = "BODEGUERO", "Bodeguero"

    email = models.EmailField(
        unique=True,
    )
    correo_verificado_en = models.DateTimeField(null=True, editable=False)
    correo_pendiente = models.EmailField(blank=True, default='', editable=False)

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
                        "BODEGUERO",
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

    def _get_session_auth_hash(self, secret=None):
        original = super()._get_session_auth_hash(secret=secret)
        from .configuracion_c2 import habilitado
        if not habilitado():
            return original
        from django.utils.crypto import salted_hmac
        return salted_hmac("fyag.c2.sesion_version", f"{original}:{self.sesion_version}",
                           secret=secret, algorithm="sha256").hexdigest()


class EventosInmutablesQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError("El historial administrativo no se puede editar.")

    def delete(self):
        raise ValidationError("El historial administrativo no se puede eliminar.")

    def bulk_create(self, objs, **kwargs):
        raise ValidationError("El historial debe registrarse mediante una operación auditada.")

    def bulk_update(self, objs, fields, **kwargs):
        raise ValidationError("El historial administrativo no se puede editar.")


class DesafioCorreo(models.Model):
    class Proposito(models.TextChoices):
        TITULARIDAD = 'TITULARIDAD', 'Verificar correo vigente'
        CAMBIO = 'CAMBIO', 'Confirmar correo nuevo'

    usuario = models.ForeignKey(Usuario, on_delete=models.CASCADE)
    digest = models.CharField(max_length=64, unique=True, editable=False)
    email = models.EmailField()
    proposito = models.CharField(max_length=12, choices=Proposito.choices)
    emitido_en = models.DateTimeField()
    vence_en = models.DateTimeField(db_index=True)
    sesion_version = models.PositiveBigIntegerField(null=True, editable=False)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(proposito__in=['TITULARIDAD', 'CAMBIO']), name='correo_proposito_valido'),
            models.CheckConstraint(condition=models.Q(vence_en__gt=models.F('emitido_en')), name='correo_vigencia_positiva'),
            models.CheckConstraint(condition=(
                models.Q(proposito='TITULARIDAD', sesion_version__isnull=True)
                | models.Q(proposito='CAMBIO', sesion_version__isnull=False, sesion_version__gte=1)
            ), name='correo_version_por_proposito'),
        ]


class DesafioRecuperacionCorreo(models.Model):
    """Propósito exclusivo de recuperación; nunca aceptado como verificación."""
    usuario = models.OneToOneField(Usuario, on_delete=models.CASCADE)
    digest = models.CharField(max_length=64, unique=True, editable=False)
    vinculo = models.CharField(max_length=64, editable=False)
    vence_en = models.DateTimeField(db_index=True)


class RecuperacionCorreoEvento(models.Model):
    """Autoridad: titularidad del buzón del usuario, no sesión ni reemisión TI."""
    FUENTE = 'RECUPERACION_CORREO_EVENTO'
    TIPO = 'RECUPERACION_CORREO'
    AUTORIDAD = 'TITULARIDAD_CORREO'
    objects = EventosInmutablesQuerySet.as_manager()
    usuario = models.ForeignKey(Usuario, on_delete=models.PROTECT)
    creado_en = models.DateTimeField(auto_now_add=True)
    acceso_anterior = models.CharField(max_length=20, blank=True)
    acceso_version_nueva = models.PositiveBigIntegerField(null=True)

    @staticmethod
    def acceso_publico(value):
        return value if value in ('NORMAL', 'BLOQUEO_TEMPORAL', 'REQUIERE_TI') else None

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError('El historial de seguridad es inmutable.')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('El historial de seguridad es inmutable.')


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
        CORREO_SOLICITADO = 'CORREO_SOLICITADO', 'Solicitud de cambio de correo'
        CORREO_VERIFICADO = 'CORREO_VERIFICADO', 'Titularidad de correo confirmada'
        CORREO_CAMBIADO = 'CORREO_CAMBIADO', 'Nuevo correo confirmado'

    usuario_objetivo = models.ForeignKey(Usuario, on_delete=models.PROTECT, related_name="eventos_administrativos")
    actor = models.ForeignKey(Usuario, on_delete=models.PROTECT, related_name="acciones_administrativas")
    tipo = models.CharField(max_length=32, choices=Tipo.choices)
    motivo = models.CharField(max_length=2000, blank=True, default="")
    datos_anteriores = models.JSONField(default=dict, blank=True)
    datos_nuevos = models.JSONField(default=dict, blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    actor_nombre_historico = models.CharField(max_length=301, null=True, blank=True, editable=False)
    actor_username_historico = models.CharField(max_length=150, null=True, blank=True, editable=False)

    class Meta:
        ordering = ["creado_en", "id"]
        constraints = [models.CheckConstraint(
            condition=models.Q(tipo__in=["CREACION", "EDICION", "ACTIVACION", "DESACTIVACION", "CAMBIO_ROL", "ESTABLECER_CLAVE", "CAMBIO_CLAVE_PROPIA", "CREACION_CREDENCIAL_TEMPORAL", "REEMISION", "CAMBIO_INICIAL", "CORREO_SOLICITADO", "CORREO_VERIFICADO", "CORREO_CAMBIADO"]),
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
    personal_previa = models.BooleanField(default=False, db_default=False, editable=False)

    class Meta:
        constraints = [
            models.CheckConstraint(name='credencial_personal_previa_reemision', condition=(
                models.Q(personal_previa=False) | models.Q(estado='RECUPERACION'))),
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
from .models_bloqueos import EstadoAcceso, EventoAcceso, RecuperacionAcceso  # noqa: E402,F401
