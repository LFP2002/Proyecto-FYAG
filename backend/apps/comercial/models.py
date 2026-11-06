from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.functions import Lower, Trim, Upper

from .validators import validar_rut


class Cliente(models.Model):
    class TipoCliente(models.TextChoices):
        PERSONA = "PERSONA", "Persona"
        EMPRESA = "EMPRESA", "Empresa"

    class TipoIdentificacion(models.TextChoices):
        RUT = "RUT", "RUT"
        DOCUMENTO_EXTRANJERO = "DOCUMENTO_EXTRANJERO", "Documento extranjero"
        SIN_IDENTIFICACION = "SIN_IDENTIFICACION", "Sin identificación"

    tipo_cliente = models.CharField(max_length=7, choices=TipoCliente.choices)
    tipo_identificacion = models.CharField(
        max_length=20, choices=TipoIdentificacion.choices
    )
    numero_identificacion = models.CharField(
        max_length=100, null=True, blank=True
    )
    pais_identificacion = models.CharField(max_length=2, null=True, blank=True)
    tipo_documento_extranjero = models.CharField(
        max_length=50, null=True, blank=True
    )
    nombre_legal = models.CharField(max_length=200)
    nombre_contacto = models.CharField(max_length=200, blank=True, default="")
    correo = models.EmailField(blank=True, default="")
    telefono = models.CharField(max_length=50, blank=True, default="")
    activo = models.BooleanField(default=True)
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(tipo_cliente__in=["PERSONA", "EMPRESA"]),
                name="cliente_tipo_valido",
            ),
            models.CheckConstraint(
                condition=models.Q(tipo_identificacion__in=[
                    "RUT", "DOCUMENTO_EXTRANJERO", "SIN_IDENTIFICACION",
                ]),
                name="cliente_identificacion_valida",
            ),
            models.CheckConstraint(
                condition=(
                    ~models.Q(nombre_legal="")
                    & models.Q(nombre_legal=Trim("nombre_legal"))
                ),
                name="cliente_nombre_normalizado",
            ),
            models.CheckConstraint(
                condition=~models.Q(correo="", telefono=""),
                name="cliente_contacto_obligatorio",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(correo=Lower(Trim("correo")))
                    & models.Q(telefono=Trim("telefono"))
                    & models.Q(nombre_contacto=Trim("nombre_contacto"))
                ),
                name="cliente_contacto_normalizado",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        tipo_identificacion="RUT",
                        numero_identificacion__isnull=False,
                        numero_identificacion__regex=r"^[1-9][0-9]*-[0-9K]$",
                        pais_identificacion__isnull=True,
                        tipo_documento_extranjero__isnull=True,
                    )
                    | (
                        models.Q(
                            tipo_identificacion="DOCUMENTO_EXTRANJERO",
                            numero_identificacion__isnull=False,
                            pais_identificacion__isnull=False,
                            pais_identificacion__regex=r"^[A-Z]{2}$",
                            tipo_documento_extranjero__isnull=False,
                            numero_identificacion=Upper(
                                Trim("numero_identificacion")
                            ),
                            tipo_documento_extranjero=Upper(
                                Trim("tipo_documento_extranjero")
                            ),
                        )
                        & ~models.Q(numero_identificacion="")
                        & ~models.Q(tipo_documento_extranjero="")
                    )
                    | models.Q(
                        tipo_identificacion="SIN_IDENTIFICACION",
                        numero_identificacion__isnull=True,
                        pais_identificacion__isnull=True,
                        tipo_documento_extranjero__isnull=True,
                    )
                ),
                name="cliente_identificacion_coherente",
            ),
            models.UniqueConstraint(
                fields=["numero_identificacion"],
                condition=models.Q(tipo_identificacion="RUT"),
                name="cliente_rut_unico",
            ),
            models.UniqueConstraint(
                fields=[
                    "pais_identificacion", "tipo_documento_extranjero",
                    "numero_identificacion",
                ],
                condition=models.Q(
                    tipo_identificacion="DOCUMENTO_EXTRANJERO"
                ),
                name="cliente_documento_unico",
            ),
        ]

    def _normalizar(self):
        for campo in (
            "nombre_legal", "nombre_contacto", "correo", "telefono",
            "numero_identificacion", "pais_identificacion",
            "tipo_documento_extranjero",
        ):
            valor = getattr(self, campo)
            if isinstance(valor, str):
                valor = valor.strip()
                if campo == "correo":
                    valor = valor.lower()
                elif campo in (
                    "pais_identificacion", "tipo_documento_extranjero",
                ):
                    valor = valor.upper()
                elif (
                    campo == "numero_identificacion"
                    and self.tipo_identificacion
                    == self.TipoIdentificacion.DOCUMENTO_EXTRANJERO
                ):
                    valor = valor.upper()
                setattr(self, campo, valor)

    def clean_fields(self, exclude=None):
        # Normalizar antes de validar longitudes y formato de EmailField.
        self._normalizar()
        if not isinstance(self.nombre_legal, str):
            raise ValidationError({
                "nombre_legal": "El nombre legal debe ser un string.",
            })
        super().clean_fields(exclude=exclude)

    def clean(self):
        super().clean()
        self._normalizar()
        errores = {}
        if not isinstance(self.nombre_legal, str) or not self.nombre_legal:
            errores["nombre_legal"] = "Ingrese un nombre legal no vacío."
        if not self.correo and not self.telefono:
            errores["correo"] = "Indique un correo o teléfono de contacto."

        campos = (
            "numero_identificacion", "pais_identificacion",
            "tipo_documento_extranjero",
        )
        if self.tipo_identificacion == self.TipoIdentificacion.RUT:
            try:
                self.numero_identificacion = validar_rut(
                    self.numero_identificacion
                )
            except ValidationError as exc:
                errores["numero_identificacion"] = exc.messages
            for campo in campos[1:]:
                if getattr(self, campo) is not None:
                    errores[campo] = "Debe ser null para identificación RUT."
        elif (
            self.tipo_identificacion
            == self.TipoIdentificacion.DOCUMENTO_EXTRANJERO
        ):
            for campo in campos:
                if not getattr(self, campo):
                    errores[campo] = "Obligatorio para documento extranjero."
            pais = self.pais_identificacion
            if pais and (
                not isinstance(pais, str)
                or len(pais) != 2
                or not pais.isascii()
                or not pais.isalpha()
            ):
                errores["pais_identificacion"] = (
                    "Ingrese un país de dos letras ASCII."
                )
        elif (
            self.tipo_identificacion
            == self.TipoIdentificacion.SIN_IDENTIFICACION
        ):
            for campo in campos:
                if getattr(self, campo) is not None:
                    errores[campo] = "Debe ser null para SIN_IDENTIFICACION."
        if errores:
            raise ValidationError(errores)

    def save(self, *args, **kwargs):
        # La base resuelve unicidad, incluidas escrituras concurrentes.
        self.full_clean(validate_unique=False, validate_constraints=False)
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.nombre_legal
