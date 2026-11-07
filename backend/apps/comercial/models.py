from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.functions import Lower, Trim, Upper

from .calculos import (
    CANTIDAD_MAXIMA,
    PRECIO_MAXIMO,
    calcular_subtotal,
    normalizar_cantidad,
    normalizar_precio,
    sumar_monto_neto,
)
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


class _ModeloPresupuestoValidado(models.Model):
    """Validación estructural compartida, sin ejecutar acciones de dominio."""

    campos_texto = ()

    class Meta:
        abstract = True

    def _preparar_campos(self, exclude=None):
        errores = {}
        for campo in self.campos_texto:
            if campo in (exclude or ()):
                continue
            valor = getattr(self, campo)
            if not isinstance(valor, str):
                errores[campo] = "Debe ser un string."
            else:
                setattr(self, campo, valor.strip())
        if errores:
            raise ValidationError(errores)

    def clean_fields(self, exclude=None):
        self._preparar_campos(exclude)
        super().clean_fields(exclude=exclude)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class Presupuesto(_ModeloPresupuestoValidado):
    class Estado(models.TextChoices):
        BORRADOR = "BORRADOR", "Borrador"
        PENDIENTE_GERENCIA = "PENDIENTE_GERENCIA", "Pendiente Gerencia"
        APROBADO_GERENCIA = "APROBADO_GERENCIA", "Aprobado Gerencia"
        RECHAZADO_GERENCIA = "RECHAZADO_GERENCIA", "Rechazado Gerencia"
        ENVIADO_CLIENTE = "ENVIADO_CLIENTE", "Enviado al cliente"
        APROBADO_CLIENTE = "APROBADO_CLIENTE", "Aprobado por cliente"
        RECHAZADO_CLIENTE = "RECHAZADO_CLIENTE", "Rechazado por cliente"
        ANULADO = "ANULADO", "Anulado"

    campos_texto = ("descripcion",)

    cliente = models.ForeignKey(Cliente, on_delete=models.PROTECT)
    descripcion = models.CharField(max_length=2000)
    estado = models.CharField(
        max_length=20, choices=Estado.choices, default=Estado.BORRADOR
    )
    requiere_aprobacion_gerencia = models.BooleanField(default=True, editable=False)
    presupuesto_origen = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, blank=True,
        related_name="revisiones",
    )
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="presupuestos_creados",
    )
    creado_en = models.DateTimeField(auto_now_add=True)
    actualizado_en = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(estado__in=[
                    "BORRADOR", "PENDIENTE_GERENCIA", "APROBADO_GERENCIA",
                    "RECHAZADO_GERENCIA", "ENVIADO_CLIENTE",
                    "APROBADO_CLIENTE", "RECHAZADO_CLIENTE", "ANULADO",
                ]),
                name="presupuesto_estado_valido",
            ),
            models.CheckConstraint(
                condition=(~models.Q(descripcion="") & models.Q(
                    descripcion=Trim("descripcion")
                )),
                name="presupuesto_descripcion_valida",
            ),
            models.CheckConstraint(
                condition=models.Q(requiere_aprobacion_gerencia=True),
                name="presupuesto_aprobacion_gerencia_obligatoria",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(presupuesto_origen__isnull=True)
                    | ~models.Q(presupuesto_origen=models.F("id"))
                ),
                name="presupuesto_origen_distinto",
            ),
        ]

    def _preparar_campos(self, exclude=None):
        super()._preparar_campos(exclude)
        if "requiere_aprobacion_gerencia" not in (exclude or ()):
            if self.requiere_aprobacion_gerencia is not True:
                raise ValidationError({
                    "requiere_aprobacion_gerencia": "Debe ser True en este MVP.",
                })

    @property
    def codigo(self):
        return f"PRE-{self.pk:06d}" if self.pk is not None else None

    @property
    def moneda(self):
        return "CLP"

    @property
    def monto_neto(self):
        if self.pk is None:
            return sumar_monto_neto(())
        return sumar_monto_neto(item.subtotal for item in self.items.all())


class PresupuestoItem(_ModeloPresupuestoValidado):
    campos_texto = ("descripcion", "unidad")

    presupuesto = models.ForeignKey(
        Presupuesto, on_delete=models.PROTECT, related_name="items"
    )
    descripcion = models.CharField(max_length=2000)
    cantidad = models.DecimalField(max_digits=12, decimal_places=3)
    unidad = models.CharField(max_length=30)
    precio_unitario = models.DecimalField(max_digits=15, decimal_places=2)
    orden = models.IntegerField()

    class Meta:
        ordering = ["orden", "id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    cantidad__gt=0, cantidad__lte=CANTIDAD_MAXIMA
                ),
                name="presupuesto_item_cantidad_rango",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    precio_unitario__gte=0, precio_unitario__lte=PRECIO_MAXIMO
                ),
                name="presupuesto_item_precio_rango",
            ),
            models.CheckConstraint(
                condition=(~models.Q(descripcion="") & models.Q(
                    descripcion=Trim("descripcion")
                )),
                name="presupuesto_item_desc_valida",
            ),
            models.CheckConstraint(
                condition=(~models.Q(unidad="") & models.Q(
                    unidad=Trim("unidad")
                )),
                name="presupuesto_item_unidad_valida",
            ),
            models.CheckConstraint(
                condition=models.Q(orden__gte=1, orden__lte=2147483647),
                name="presupuesto_item_orden_rango",
            ),
            models.UniqueConstraint(
                fields=["presupuesto", "orden"],
                name="presupuesto_item_orden_unico",
            ),
        ]

    def _preparar_campos(self, exclude=None):
        super()._preparar_campos(exclude)
        errores = {}
        for campo, normalizar in (
            ("cantidad", normalizar_cantidad),
            ("precio_unitario", normalizar_precio),
        ):
            if campo in (exclude or ()):
                continue
            try:
                setattr(self, campo, normalizar(getattr(self, campo)))
            except ValidationError as exc:
                errores[campo] = exc.messages
        if "orden" not in (exclude or ()):
            if type(self.orden) is not int:
                errores["orden"] = "Debe ser un entero."
        if errores:
            raise ValidationError(errores)

    @property
    def subtotal(self):
        return calcular_subtotal(self.cantidad, self.precio_unitario)


class PresupuestoEvento(_ModeloPresupuestoValidado):
    campos_texto = ("motivo",)

    presupuesto = models.ForeignKey(
        Presupuesto, on_delete=models.PROTECT, related_name="eventos"
    )
    estado_anterior = models.CharField(
        max_length=20, choices=Presupuesto.Estado.choices,
        null=True, blank=True,
    )
    estado_nuevo = models.CharField(
        max_length=20, choices=Presupuesto.Estado.choices
    )
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="eventos_presupuesto",
    )
    motivo = models.CharField(max_length=2000, default="", blank=True)
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["creado_en", "id"]
        constraints = [
            models.CheckConstraint(
                condition=(models.Q(estado_anterior__isnull=True) | models.Q(
                    estado_anterior__in=Presupuesto.Estado.values
                )),
                name="pres_evento_anterior_valido",
            ),
            models.CheckConstraint(
                condition=models.Q(estado_nuevo__in=Presupuesto.Estado.values),
                name="pres_evento_nuevo_valido",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        estado_anterior__isnull=True, estado_nuevo="BORRADOR"
                    )
                    | (
                        models.Q(estado_anterior__isnull=False)
                        & ~models.Q(estado_nuevo="BORRADOR")
                    )
                ),
                name="pres_evento_inicial_coherente",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(estado_anterior__isnull=True)
                    | ~models.Q(estado_anterior=models.F("estado_nuevo"))
                ),
                name="pres_evento_estados_distintos",
            ),
            models.UniqueConstraint(
                fields=["presupuesto"],
                condition=models.Q(estado_anterior__isnull=True),
                name="pres_evento_inicial_unico",
            ),
            models.CheckConstraint(
                condition=models.Q(motivo=Trim("motivo")),
                name="pres_evento_motivo_normalizado",
            ),
            models.CheckConstraint(
                condition=(
                    ~models.Q(estado_nuevo__in=[
                        "RECHAZADO_GERENCIA", "RECHAZADO_CLIENTE", "ANULADO",
                    ])
                    | ~models.Q(motivo="")
                ),
                name="pres_evento_motivo_obligatorio",
            ),
        ]
