"""019A: idempotencia → Artículo → Existencia; sin locks de Obras/Finanzas/TI."""
import hashlib
import re
from decimal import Decimal
from uuid import UUID

from django.db import connection, transaction
from django.utils import timezone
from rest_framework.exceptions import APIException, NotFound, ValidationError

from .models import ArticuloInventario, ExistenciaInventario, MovimientoInventario, MAXIMO
from .permissions import revalidar


class ConflictoInventario(APIException):
    status_code = 409

    def __init__(self, code, detail):
        super().__init__({"code": code, "detail": detail})


def contrato(data, campos, requeridos=()):
    if type(data) is not dict or set(data) - set(campos) or set(requeridos) - set(data):
        raise ValidationError({"body": ["Objeto JSON con campos permitidos y obligatorios requeridos."]})


def texto(value, campo, maximo, *, opcional=False):
    if type(value) is not str or len(value) > maximo or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValidationError({campo: ["Texto inválido o demasiado largo."]})
    value = value.strip()
    if not value and not opcional:
        raise ValidationError({campo: ["Campo obligatorio."]})
    return value


def identificador(value):
    if type(value) is not int or not 0 < value <= 9223372036854775807:
        raise ValidationError({"articulo": ["Entero positivo dentro de BIGINT requerido."]})
    return value


def cantidad(value):
    if type(value) is not str or len(value) > 13 or not re.fullmatch(r"[0-9]{1,9}(?:\.[0-9]{1,3})?", value):
        raise ValidationError({"cantidad": ["Use string decimal positivo, hasta 9 enteros y 3 decimales, sin exponentes."]})
    number = Decimal(value)
    if not 0 < number <= MAXIMO:
        raise ValidationError({"cantidad": ["Cantidad fuera de rango."]})
    return number.quantize(Decimal("0.001"))


def _articulo(pk):
    try:
        return ArticuloInventario.objects.select_for_update().get(pk=identificador(pk))
    except ArticuloInventario.DoesNotExist:
        raise NotFound("Artículo no disponible.") from None


def _campos(data):
    result = {}
    for campo, maximo in (("codigo", 50), ("nombre", 150), ("descripcion", 2000), ("unidad", 30)):
        if campo in data:
            value = texto(data[campo], campo, maximo, opcional=campo == "descripcion")
            result[campo] = value.lower() if campo in {"codigo", "unidad"} else value
    if "codigo" in result and not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,49}", result["codigo"]):
        raise ValidationError({"codigo": ["Use código ASCII alfanumérico con punto, guion o guion bajo."]})
    if "activo" in data:
        if type(data["activo"]) is not bool:
            raise ValidationError({"activo": ["Booleano requerido."]})
        result["activo"] = data["activo"]
    return result


def _codigo_unico(codigo, pk=None):
    # Namespace separado del lock de idempotencia: serializa altas/ediciones del código.
    key = int.from_bytes(hashlib.sha256(codigo.encode()).digest()[:4], "big", signed=True)
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(1901, %s)", [key])
    if ArticuloInventario.objects.filter(codigo=codigo).exclude(pk=pk).exists():
        raise ValidationError({"codigo": ["Ya existe un artículo con este código."]})


@transaction.atomic
def crear_articulo(data, actor):
    revalidar(actor, escritura=True)
    contrato(data, {"codigo", "nombre", "descripcion", "unidad", "activo"}, {"codigo", "nombre", "unidad"})
    fields = _campos(data)
    _codigo_unico(fields["codigo"])
    actor = revalidar(actor, escritura=True)
    return ArticuloInventario.objects.create(**fields, creado_por=actor, actualizado_por=actor)


@transaction.atomic
def editar_articulo(pk, data, actor):
    revalidar(actor, escritura=True)
    contrato(data, {"codigo", "nombre", "descripcion", "unidad", "activo"})
    fields = _campos(data)
    # Código antes de fila, igual que en alta: no invertir el lock asesor.
    if "codigo" in fields:
        _codigo_unico(fields["codigo"], pk)
    article = _articulo(pk)
    actor = revalidar(actor, escritura=True)
    changes = {k: v for k, v in fields.items() if getattr(article, k) != v}
    if {"codigo", "unidad"} & changes.keys() and article.movimientos.exists():
        raise ConflictoInventario("identidad_inmutable", "Código y unidad no pueden cambiar con movimientos registrados.")
    if changes:
        for k, v in changes.items():
            setattr(article, k, v)
        article.actualizado_por = actor
        article.actualizado_en = timezone.now()
        article.save(update_fields=[*changes, "actualizado_por", "actualizado_en"])
    return article


@transaction.atomic
def registrar_ingreso(data, actor):
    actor = revalidar(actor, escritura=True)
    contrato(data, {"articulo", "cantidad", "clave_idempotencia", "referencia", "motivo"}, {"articulo", "cantidad", "clave_idempotencia"})
    pk, amount = identificador(data["articulo"]), cantidad(data["cantidad"])
    try:
        if type(data["clave_idempotencia"]) is not str or len(data["clave_idempotencia"]) != 36:
            raise ValueError
        key = UUID(data["clave_idempotencia"])
    except (ValueError, AttributeError):
        raise ValidationError({"clave_idempotencia": ["UUID canónico requerido."]}) from None
    reference = texto(data.get("referencia", ""), "referencia", 150, opcional=True)
    reason = texto(data.get("motivo", ""), "motivo", 2000, opcional=True)
    lock = int.from_bytes(hashlib.sha256(key.bytes).digest()[:4], "big", signed=True)
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(1900, %s)", [lock])
    actor = revalidar(actor, escritura=True)
    previous = MovimientoInventario.objects.filter(clave_idempotencia=key).first()
    if previous is not None:
        if (previous.articulo_id, previous.cantidad, previous.actor_id, previous.referencia, previous.motivo) != (pk, amount, actor.pk, reference, reason):
            raise ConflictoInventario("idempotencia_conflictiva", "Clave ya utilizada para una operación diferente.")
        return previous, False
    article = _articulo(pk)
    stock = ExistenciaInventario.objects.select_for_update().filter(articulo=article).first()
    actor = revalidar(actor, escritura=True)
    if stock is None:
        raise ConflictoInventario("existencia_no_disponible", "Existencia ausente; no se reconstruye automáticamente.")
    if not article.activo:
        raise ConflictoInventario("articulo_inactivo", "El artículo no admite nuevos ingresos.")
    if stock.saldo + amount > MAXIMO:
        raise ConflictoInventario("saldo_fuera_rango", "El ingreso excedería el saldo máximo.")
    # Trigger valida snapshots y actualiza saldo. No hay una segunda suma en Python.
    movement = MovimientoInventario.objects.create(articulo=article, clave_idempotencia=key, cantidad=amount,
        saldo_anterior=stock.saldo, saldo_posterior=stock.saldo + amount, actor=actor, referencia=reference, motivo=reason)
    return movement, True
