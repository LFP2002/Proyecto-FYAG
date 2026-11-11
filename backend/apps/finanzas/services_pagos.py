"""007B: Presupuesto -> Obra -> Documento -> Pago. Idempotencia global en SQL."""
import hashlib
import json
import re
from uuid import UUID

from django.db import IntegrityError, models, transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from . import services_documentos as base
from .consultas_cobranzas import saldo_documento
from .models import DocumentoCobro, PagoDocumento, CierreSinCobro
from .serializers_pagos import PagoCrearSerializer, PagoAnularSerializer


def clave_uuid(value):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", value):
        raise ValidationError({"Idempotency-Key": "Se requiere un UUID en el header Idempotency-Key."})
    return UUID(value)


def huella(documento_id, data):
    canonical = {**data, "documento": documento_id, "monto": format(data["monto"], ".2f"), "fecha_pago": data["fecha_pago"].isoformat()}
    return hashlib.sha256(json.dumps(canonical, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def recuperar(clave, fingerprint):
    pago = PagoDocumento.objects.filter(clave_idempotencia=clave).first()
    if pago is not None and pago.huella_solicitud != fingerprint:
        raise base.ConflictoFinanciero("idempotencia_conflictiva", "La clave ya identifica una solicitud distinta.")
    return pago


def documento_bloqueado(pk):
    obra_id = DocumentoCobro.objects.filter(pk=base.identificador(pk)).values_list("obra_id", flat=True).first()
    if obra_id is None:
        raise NotFound("Documento no encontrado.")
    obra = base.obra_bloqueada(obra_id)
    documento = DocumentoCobro.objects.select_for_update().get(pk=pk)
    if documento.obra_id != obra.pk:
        raise base.ConflictoFinanciero("origen_inconsistente", "La referencia de origen cambió.")
    return documento


def registrar_pago(documento_id, payload, actor, clave):
    """Devuelve (pago, creado). Recupera UUID incluso tras saldo cero/anulación.

    La colisión de UUID entre raíces distintas se resuelve tras rollback de toda
    la transacción perdedora. Nunca bloquear un Pago de otra raíz para recuperar.
    """
    actor = base.actor_financiero(actor)
    documento_id = base.identificador(documento_id)
    clave = clave_uuid(clave)
    data = base.datos(PagoCrearSerializer, payload)
    fingerprint = huella(documento_id, data)
    previo = recuperar(clave, fingerprint)
    if previo is not None:
        return previo, False
    try:
        return _registrar(documento_id, data, actor, clave, fingerprint)
    except IntegrityError as exc:
        name = getattr(getattr(exc.__cause__, "diag", None), "constraint_name", "")
        if name != "fin_pago_idempotencia_unica":
            raise
        # atomic interior ya revirtió pago y evento; la transacción ganadora
        # terminó antes de que PostgreSQL informara esta colisión de unicidad.
        base.actor_financiero(actor)
        previo = recuperar(clave, fingerprint)
        if previo is None:
            raise
        return previo, False


@base.operacion
def _registrar(documento_id, data, actor, clave, fingerprint):
    documento = documento_bloqueado(documento_id)
    actor = base.actor_financiero(actor)
    previo = recuperar(clave, fingerprint)
    if previo is not None:
        return previo, False
    if documento.estado != "VIGENTE":
        raise base.ConflictoFinanciero("documento_revertido", "No se permite pagar un documento revertido.")
    if CierreSinCobro.objects.filter(obra_id=documento.obra_id).exists():
        raise base.ConflictoFinanciero("sin_cobro_ya_registrado", "La Obra tiene cierre administrativo sin cobro.")
    if data["fecha_pago"] < documento.fecha_emision:
        raise ValidationError({"fecha_pago": "No puede preceder a la emisión del documento."})
    _, saldo = saldo_documento(documento)
    if data["monto"] > saldo:
        raise base.ConflictoFinanciero("monto_excede_saldo", "El pago excede el saldo disponible.")
    pago = PagoDocumento.objects.create(documento=documento, registrado_por=actor, clave_idempotencia=clave, huella_solicitud=fingerprint, **data)
    base.evento(pago=pago, tipo="PAGO_REGISTRADO", actor=actor,
                datos_nuevos={"documento": documento.pk, **{key: format(value, ".2f") if key == "monto" else value.isoformat() if key == "fecha_pago" else value for key, value in data.items()}, "activo": True})
    return pago, True


@base.operacion
def anular_pago(documento_id, pago_id, payload, actor):
    actor = base.actor_financiero(actor)
    data = base.datos(PagoAnularSerializer, payload)
    documento = documento_bloqueado(documento_id)
    actor = base.actor_financiero(actor)
    pago = PagoDocumento.objects.select_for_update().filter(pk=base.identificador(pago_id), documento=documento).first()
    if pago is None:
        raise NotFound("Pago no encontrado en el documento.")
    if not pago.activo:
        raise base.ConflictoFinanciero("pago_ya_anulado", "El registro de pago ya está anulado.")
    saldo_documento(documento)
    pago.activo = False
    pago.anulado_por = actor
    pago.anulado_en = timezone.now()
    pago.motivo_anulacion = data["motivo"]
    pago.referencia_reversion_externa = data["referencia_reversion_externa"]
    pago.full_clean(validate_unique=False, validate_constraints=False)
    models.Model.save(pago, update_fields=["activo", "anulado_por", "anulado_en", "motivo_anulacion", "referencia_reversion_externa"])
    base.evento(pago=pago, tipo="PAGO_ANULADO", actor=actor, motivo=data["motivo"], datos_anteriores={"activo": True}, datos_nuevos={"activo": False, "motivo_anulacion": data["motivo"], "referencia_reversion_externa": data["referencia_reversion_externa"]})
    return pago
