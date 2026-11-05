from django.contrib.auth.models import AbstractUser
from django.db import models


class Usuario(AbstractUser):

    class Rol(models.TextChoices):
        GERENCIA = "GERENCIA", "Gerencia"
        ADMINISTRATIVO_FINANZAS = (
            "ADMINISTRATIVO_FINANZAS",
            "Administrativo / Finanzas",
        )
        SUPERVISOR_OBRAS = "SUPERVISOR_OBRAS", "Supervisor de Obras"
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

    def __str__(self):
        return self.email