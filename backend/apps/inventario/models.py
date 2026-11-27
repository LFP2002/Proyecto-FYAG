from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.functions import Lower, Trim
from django.utils import timezone


MAXIMO = Decimal("999999999.999")


class ArticuloInventario(models.Model):
    codigo = models.CharField(max_length=50, unique=True)
    nombre = models.CharField(max_length=150)
    descripcion = models.CharField(max_length=2000, blank=True, default="")
    unidad = models.CharField(max_length=30)
    activo = models.BooleanField(default=True)
    creado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="articulos_creados")
    actualizado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="articulos_actualizados")
    creado_en = models.DateTimeField(default=timezone.now, editable=False)
    actualizado_en = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(name="inventario_codigo_formato", condition=models.Q(codigo__regex=r"^[a-z0-9][a-z0-9._-]{0,49}$")),
            models.CheckConstraint(name="inventario_unidad_normalizada", condition=models.Q(unidad=Lower(Trim("unidad"))) & ~models.Q(unidad__regex=r"^\s*$")),
            models.CheckConstraint(name="inventario_nombre_no_vacio", condition=~models.Q(nombre__regex=r"^\s*$")),
            models.CheckConstraint(name="inventario_articulo_reloj", condition=models.Q(actualizado_en__gte=models.F("creado_en"))),
        ]


class ExistenciaInventario(models.Model):
    articulo = models.OneToOneField(ArticuloInventario, primary_key=True, on_delete=models.PROTECT, related_name="existencia")
    saldo = models.DecimalField(max_digits=12, decimal_places=3, default=Decimal("0.000"), editable=False)

    class Meta:
        ordering = ["articulo_id"]
        constraints = [models.CheckConstraint(name="inventario_saldo_rango", condition=models.Q(saldo__gte=0, saldo__lte=MAXIMO))]


class MovimientosQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError("El libro de inventario es inmutable.")

    def delete(self):
        raise ValidationError("El libro de inventario es inmutable.")

    def bulk_update(self, *args, **kwargs):
        raise ValidationError("El libro de inventario es inmutable.")


class MovimientoInventario(models.Model):
    class Tipo(models.TextChoices):
        INGRESO = "INGRESO", "Ingreso físico"
        SALIDA = "SALIDA", "Entrega a Obra"
        DEVOLUCION = "DEVOLUCION", "Recepción desde Obra"
        MERMA = "MERMA", "Merma de Bodega aprobada"

    objects = MovimientosQuerySet.as_manager()
    articulo = models.ForeignKey(ArticuloInventario, on_delete=models.PROTECT, related_name="movimientos")
    tipo = models.CharField(max_length=12, choices=Tipo.choices, default=Tipo.INGRESO)
    clave_idempotencia = models.UUIDField(unique=True, editable=False)
    cantidad = models.DecimalField(max_digits=12, decimal_places=3)
    saldo_anterior = models.DecimalField(max_digits=12, decimal_places=3, editable=False)
    saldo_posterior = models.DecimalField(max_digits=12, decimal_places=3, editable=False)
    referencia = models.CharField(max_length=150, blank=True, default="")
    motivo = models.CharField(max_length=2000, blank=True, default="")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="movimientos_inventario")
    creado_en = models.DateTimeField(default=timezone.now, editable=False, db_index=True)
    operacion = models.OneToOneField("OperacionMaterial", on_delete=models.PROTECT, null=True, blank=True, related_name="movimiento", editable=False)

    class Meta:
        ordering = ["creado_en", "id"]
        constraints = [
            models.CheckConstraint(name="inventario_movimiento_tipo", condition=models.Q(tipo__in=["INGRESO", "SALIDA", "DEVOLUCION", "MERMA"])),
            models.CheckConstraint(name="inventario_cantidad_rango", condition=models.Q(cantidad__gt=0, cantidad__lte=MAXIMO)),
            models.CheckConstraint(name="inventario_saldos_rango", condition=models.Q(saldo_anterior__gte=0, saldo_anterior__lte=MAXIMO, saldo_posterior__gte=0, saldo_posterior__lte=MAXIMO)),
            models.CheckConstraint(name="inventario_movimiento_suma", condition=(
                models.Q(tipo__in=["SALIDA", "MERMA"], saldo_posterior=models.F("saldo_anterior") - models.F("cantidad"))
                | models.Q(tipo__in=["INGRESO", "DEVOLUCION"], saldo_posterior=models.F("saldo_anterior") + models.F("cantidad"))
            )),
            models.CheckConstraint(name="inventario_movimiento_enlace", condition=(
                models.Q(tipo="INGRESO", operacion__isnull=True) | models.Q(tipo__in=["SALIDA", "DEVOLUCION", "MERMA"], operacion__isnull=False)
            )),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("El libro de inventario es inmutable.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("El libro de inventario es inmutable.")


class EstadoValoracion(models.Model):
    """Proyección SQL; el corte histórico y el libro 019A nunca se reescriben."""
    articulo = models.OneToOneField(ArticuloInventario, primary_key=True, on_delete=models.PROTECT)
    saldo_historico = models.DecimalField(max_digits=12, decimal_places=3, default=Decimal("0.000"))
    ultimo_movimiento_historico = models.BigIntegerField(null=True, blank=True)
    corte_en = models.DateTimeField(default=timezone.now, editable=False)
    saldo_valorado = models.DecimalField(max_digits=12, decimal_places=3, default=Decimal("0.000"))
    promedio = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(name="inv_val_saldos", condition=models.Q(saldo_historico__gte=0, saldo_historico__lte=MAXIMO, saldo_valorado__gte=0, saldo_valorado__lte=MAXIMO)),
            models.CheckConstraint(name="inv_val_promedio", condition=(models.Q(saldo_valorado=0, promedio__isnull=True) | models.Q(saldo_valorado__gt=0, promedio__isnull=False, promedio__gte=0, promedio__lte=Decimal("9999999999999.99")))),
        ]


class OperacionMaterial(models.Model):
    """Libro 019B consolidado: seis actos inmutables, enlaces explícitos y UUID."""
    class Tipo(models.TextChoices):
        AUTORIZACION_ENTREGA = "AUTORIZACION_ENTREGA", "Autorización de entrega"
        ENTREGA = "ENTREGA", "Despacho físico"
        AUTORIZACION_DEVOLUCION = "AUTORIZACION_DEVOLUCION", "Autorización de retorno"
        DEVOLUCION = "DEVOLUCION", "Recepción física devuelta"
        VALORIZACION = "VALORIZACION", "Valoración de ingreso"
        REGULARIZACION = "REGULARIZACION", "Valoración inicial explícita"
        MERMA = "MERMA", "Baja por merma de Bodega"

    objects = MovimientosQuerySet.as_manager()
    tipo = models.CharField(max_length=24, choices=Tipo.choices)
    articulo = models.ForeignKey(ArticuloInventario, on_delete=models.PROTECT, related_name="operaciones_material")
    obra = models.ForeignKey("obras.Obra", on_delete=models.PROTECT, null=True, blank=True, related_name="operaciones_material")
    autorizacion = models.ForeignKey("self", on_delete=models.PROTECT, null=True, blank=True, related_name="ejecuciones")
    entrega = models.ForeignKey("self", on_delete=models.PROTECT, null=True, blank=True, related_name="retornos")
    ingreso = models.OneToOneField(MovimientoInventario, on_delete=models.PROTECT, null=True, blank=True, related_name="valoracion")
    gasto = models.OneToOneField("obras.GastoObra", on_delete=models.PROTECT, null=True, blank=True, related_name="entrega_bodega")
    solicitud_material = models.OneToOneField("SolicitudMaterialObra", on_delete=models.PROTECT, null=True, blank=True, related_name="autorizacion_generada", editable=False)
    item_presupuesto = models.OneToOneField(
        "comercial.PresupuestoItem", on_delete=models.PROTECT, null=True, blank=True,
        related_name="autorizacion_prevista", editable=False,
    )
    merma_bodega = models.OneToOneField("Merma", on_delete=models.PROTECT, null=True, blank=True, related_name="baja_generada", editable=False)
    cantidad = models.DecimalField(max_digits=12, decimal_places=3)
    unidad = models.CharField(max_length=30)
    costo_unitario_neto = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    saldo_valorado_anterior = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)
    saldo_valorado_posterior = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)
    promedio_anterior = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    promedio_posterior = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    clave_idempotencia = models.UUIDField(unique=True, editable=False)
    huella = models.CharField(max_length=64, editable=False)
    referencia = models.CharField(max_length=150)
    motivo = models.CharField(max_length=2000)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="operaciones_material")
    creado_en = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(name="inv_op_tipo", condition=models.Q(tipo__in=["AUTORIZACION_ENTREGA", "ENTREGA", "AUTORIZACION_DEVOLUCION", "DEVOLUCION", "VALORIZACION", "REGULARIZACION", "MERMA"])),
            models.CheckConstraint(name="inv_op_merma_enlace", condition=models.Q(tipo="MERMA", merma_bodega__isnull=False) | (~models.Q(tipo="MERMA") & models.Q(merma_bodega__isnull=True))),
            models.CheckConstraint(name="inv_op_cantidad", condition=models.Q(cantidad__gt=0, cantidad__lte=MAXIMO)),
            models.CheckConstraint(name="inv_op_precio", condition=models.Q(costo_unitario_neto__isnull=True) | models.Q(costo_unitario_neto__gte=0, costo_unitario_neto__lte=Decimal("9999999999999.99"))),
            models.CheckConstraint(name="inv_op_huella", condition=models.Q(huella__regex=r"^[0-9a-f]{64}$")),
            models.UniqueConstraint(fields=["articulo"], condition=models.Q(tipo="REGULARIZACION"), name="inv_regularizacion_unica"),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("El libro de materiales es inmutable.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("El libro de materiales es inmutable.")


class SolicitudMaterialObra(models.Model):
    """Original inmutable; solo el trigger del evento proyecta una decisión."""
    objects = MovimientosQuerySet.as_manager()
    obra = models.ForeignKey("obras.Obra", on_delete=models.PROTECT, related_name="solicitudes_materiales")
    solicitante = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="solicitudes_materiales", editable=False)
    articulo = models.ForeignKey(ArticuloInventario, on_delete=models.PROTECT, related_name="solicitudes_materiales")
    unidad = models.CharField(max_length=30, editable=False)
    cantidad_solicitada = models.DecimalField(max_digits=12, decimal_places=3)
    justificacion = models.CharField(max_length=2000)
    estado = models.CharField(max_length=9, default="PENDIENTE", choices=[("PENDIENTE", "Pendiente"), ("APROBADA", "Aprobada"), ("RECHAZADA", "Rechazada")], editable=False)
    cantidad_aprobada = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True, editable=False)
    motivo_decision = models.CharField(max_length=2000, default="", blank=True, editable=False)
    decidido_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="decisiones_materiales", editable=False)
    decidido_en = models.DateTimeField(null=True, blank=True, editable=False)
    autorizacion = models.OneToOneField(OperacionMaterial, on_delete=models.PROTECT, null=True, blank=True, related_name="solicitud_aprobada", editable=False)
    clave_idempotencia = models.UUIDField(unique=True, editable=False)
    huella = models.CharField(max_length=64, editable=False)
    creado_en = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(name="inv_sol_cantidad", condition=models.Q(cantidad_solicitada__gt=0, cantidad_solicitada__lte=MAXIMO)),
            models.CheckConstraint(name="inv_sol_huella", condition=models.Q(huella__regex=r"^[0-9a-f]{64}$")),
            models.CheckConstraint(name="inv_sol_textos", condition=(~models.Q(justificacion="") & models.Q(justificacion=Trim("justificacion"), motivo_decision=Trim("motivo_decision")) & ~models.Q(justificacion__regex=r"[[:cntrl:]]") & ~models.Q(motivo_decision__regex=r"[[:cntrl:]]"))),
            models.CheckConstraint(name="inv_sol_decision", condition=(
                models.Q(estado="PENDIENTE", cantidad_aprobada__isnull=True, motivo_decision="", decidido_por__isnull=True, decidido_en__isnull=True, autorizacion__isnull=True)
                | (models.Q(estado="APROBADA", cantidad_aprobada__isnull=False, cantidad_aprobada__gt=0, cantidad_aprobada__lte=models.F("cantidad_solicitada"), decidido_por__isnull=False, decidido_en__isnull=False, decidido_en__gte=models.F("creado_en"), autorizacion__isnull=False) & ~models.Q(motivo_decision=""))
                | (models.Q(estado="RECHAZADA", cantidad_aprobada__isnull=True, decidido_por__isnull=False, decidido_en__isnull=False, decidido_en__gte=models.F("creado_en"), autorizacion__isnull=True) & ~models.Q(motivo_decision=""))
            )),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("La solicitud solo cambia mediante su evento de decisión.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("El historial de solicitudes es inmutable.")


class SolicitudMaterialEvento(models.Model):
    objects = MovimientosQuerySet.as_manager()
    solicitud = models.ForeignKey(SolicitudMaterialObra, on_delete=models.PROTECT, related_name="eventos")
    tipo = models.CharField(max_length=10, choices=[("CREACION", "Creación"), ("APROBACION", "Aprobación"), ("RECHAZO", "Rechazo")])
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="eventos_solicitudes_materiales", editable=False)
    motivo = models.CharField(max_length=2000)
    cantidad_aprobada = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)
    autorizacion = models.OneToOneField(OperacionMaterial, on_delete=models.PROTECT, null=True, blank=True, related_name="evento_solicitud")
    clave_idempotencia = models.UUIDField(unique=True, editable=False)
    huella = models.CharField(max_length=64, editable=False)
    creado_en = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(fields=["solicitud", "tipo"], name="inv_sol_evento_tipo_unico"),
            models.UniqueConstraint(fields=["solicitud"], condition=~models.Q(tipo="CREACION"), name="inv_sol_una_decision"),
            models.CheckConstraint(name="inv_sol_evento_forma", condition=(models.Q(tipo="APROBACION", cantidad_aprobada__isnull=False, cantidad_aprobada__gt=0, cantidad_aprobada__lte=MAXIMO, autorizacion__isnull=False) | models.Q(tipo__in=["CREACION", "RECHAZO"], cantidad_aprobada__isnull=True, autorizacion__isnull=True))),
            models.CheckConstraint(name="inv_sol_evento_texto", condition=~models.Q(motivo="") & models.Q(motivo=Trim("motivo")) & ~models.Q(motivo__regex=r"[[:cntrl:]]")),
            models.CheckConstraint(name="inv_sol_evento_huella", condition=models.Q(huella__regex=r"^[0-9a-f]{64}$")),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("Los eventos de solicitud son inmutables.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Los eventos de solicitud son inmutables.")


TIPOS_MB = ["DANO", "VENCIMIENTO", "EXTRAVIO", "DIFERENCIA_CONTEO", "OTRA"]
TIPOS_MO = ["CORTE_NO_REUTILIZABLE", "DANO_EN_OBRA", "EXTRAVIO_EN_OBRA", "OTRA"]


class Merma(models.Model):
    """Dos ámbitos inequívocos; original inmutable y decisión proyectada por evento."""
    objects = MovimientosQuerySet.as_manager()
    ambito = models.CharField(max_length=6, choices=[("BODEGA", "Bodega"), ("OBRA", "Obra")])
    articulo = models.ForeignKey(ArticuloInventario, on_delete=models.PROTECT, related_name="mermas")
    obra = models.ForeignKey("obras.Obra", on_delete=models.PROTECT, null=True, blank=True, related_name="mermas")
    entrega = models.ForeignKey(OperacionMaterial, on_delete=models.PROTECT, null=True, blank=True, related_name="mermas_informadas")
    unidad = models.CharField(max_length=30, editable=False)
    cantidad = models.DecimalField(max_digits=12, decimal_places=3)
    tipo = models.CharField(max_length=24)
    motivo = models.CharField(max_length=2000)
    referencia = models.CharField(max_length=150, blank=True, default="")
    actividad = models.CharField(max_length=2000, blank=True, default="")
    corte_movimiento = models.ForeignKey(MovimientoInventario, on_delete=models.PROTECT, null=True, blank=True, related_name="mermas_observadas", editable=False)
    informado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="mermas_informadas", editable=False)
    clave_idempotencia = models.UUIDField(unique=True, editable=False)
    huella = models.CharField(max_length=64, editable=False)
    creado_en = models.DateTimeField(default=timezone.now, editable=False)
    estado = models.CharField(max_length=9, default="PENDIENTE", choices=[("PENDIENTE", "Pendiente"), ("APROBADA", "Aprobada"), ("RECHAZADA", "Rechazada")], editable=False)
    decidido_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="mermas_decididas", editable=False)
    decidido_en = models.DateTimeField(null=True, blank=True, editable=False)
    motivo_decision = models.CharField(max_length=2000, blank=True, default="", editable=False)
    operacion = models.OneToOneField(OperacionMaterial, on_delete=models.PROTECT, null=True, blank=True, related_name="merma_aprobada", editable=False)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(name="inv_merma_cantidad", condition=models.Q(cantidad__gt=0, cantidad__lte=MAXIMO)),
            models.CheckConstraint(name="inv_merma_origen", condition=(
                (models.Q(ambito="BODEGA", obra__isnull=True, entrega__isnull=True, actividad="", tipo__in=TIPOS_MB) & ~models.Q(referencia=""))
                | (models.Q(ambito="OBRA", obra__isnull=False, entrega__isnull=False, corte_movimiento__isnull=True, operacion__isnull=True, tipo__in=TIPOS_MO) & ~models.Q(actividad=""))
            )),
            models.CheckConstraint(name="inv_merma_textos", condition=(~models.Q(motivo="") & models.Q(motivo=Trim("motivo"), referencia=Trim("referencia"), actividad=Trim("actividad"), motivo_decision=Trim("motivo_decision")) & ~models.Q(motivo__regex=r"[[:cntrl:]]") & ~models.Q(referencia__regex=r"[[:cntrl:]]") & ~models.Q(actividad__regex=r"[[:cntrl:]]") & ~models.Q(motivo_decision__regex=r"[[:cntrl:]]"))),
            models.CheckConstraint(name="inv_merma_huella", condition=models.Q(huella__regex=r"^[0-9a-f]{64}$")),
            models.CheckConstraint(name="inv_merma_decision", condition=(
                models.Q(estado="PENDIENTE", decidido_por__isnull=True, decidido_en__isnull=True, motivo_decision="", operacion__isnull=True)
                | (models.Q(estado="RECHAZADA", decidido_por__isnull=False, decidido_en__isnull=False, decidido_en__gte=models.F("creado_en"), operacion__isnull=True) & ~models.Q(motivo_decision=""))
                | (models.Q(estado="APROBADA", decidido_por__isnull=False, decidido_en__isnull=False, decidido_en__gte=models.F("creado_en")) & ~models.Q(motivo_decision="") & (models.Q(ambito="BODEGA", operacion__isnull=False) | models.Q(ambito="OBRA", operacion__isnull=True)))
            )),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("La merma solo cambia por su evento de decisión.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("El historial de merma es inmutable.")


class MermaEvento(models.Model):
    objects = MovimientosQuerySet.as_manager()
    merma = models.ForeignKey(Merma, on_delete=models.PROTECT, related_name="eventos")
    tipo = models.CharField(max_length=10, choices=[("CREACION", "Creación"), ("APROBACION", "Aprobación"), ("RECHAZO", "Rechazo")])
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="eventos_mermas", editable=False)
    motivo = models.CharField(max_length=2000)
    operacion = models.OneToOneField(OperacionMaterial, on_delete=models.PROTECT, null=True, blank=True, related_name="evento_merma")
    clave_idempotencia = models.UUIDField(unique=True, editable=False)
    huella = models.CharField(max_length=64, editable=False)
    creado_en = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(fields=["merma", "tipo"], name="inv_merma_evento_tipo_unico"),
            models.UniqueConstraint(fields=["merma"], condition=~models.Q(tipo="CREACION"), name="inv_merma_una_decision"),
            models.CheckConstraint(name="inv_merma_evento_forma", condition=models.Q(tipo="APROBACION") | models.Q(tipo__in=["CREACION", "RECHAZO"], operacion__isnull=True)),
            models.CheckConstraint(name="inv_merma_evento_texto", condition=~models.Q(motivo="") & models.Q(motivo=Trim("motivo")) & ~models.Q(motivo__regex=r"[[:cntrl:]]")),
            models.CheckConstraint(name="inv_merma_evento_huella", condition=models.Q(huella__regex=r"^[0-9a-f]{64}$")),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("Los eventos de merma son inmutables.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Los eventos de merma son inmutables.")
