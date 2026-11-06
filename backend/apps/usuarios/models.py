from django.contrib.auth.models import AbstractUser
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

    email = models.EmailField(
        unique=True,
    )

    rol = models.CharField(
        max_length=30,
        choices=Rol.choices,
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    class Meta:
        verbose_name = "user"
        verbose_name_plural = "users"

        constraints = [
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
