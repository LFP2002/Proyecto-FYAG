"""021: unicidad UUID en PostgreSQL -> Egreso. Sin locks de otros dominios.

Obra es una FK informativa: no se bloquea su raíz, no se exige cierre ni se
modifican costos. La FK usa únicamente el KEY SHARE propio de PostgreSQL.
"""
import hashlib
import json

from django.db import IntegrityError, models
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from apps.obras.models import Obra
from .models import Egreso, EgresoEvento
from .permissions_egresos import revalidar
from .serializers_egresos import EgresoCrearSerializer, EgresoAnularSerializer
from .services_documentos import ConflictoFinanciero, datos, identificador, operacion
from .services_pagos import clave_uuid


def huella(data):
    canonical = {**data, "monto": format(data["monto"], ".2f"), "fecha_pago": data["fecha_pago"].isoformat()}
    return hashlib.sha256(json.dumps(canonical, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode()).hexdigest()


def recuperar(clave, fingerprint):
    previo = Egreso.objects.filter(clave_idempotencia=clave).first()
    if previo is not None and previo.huella_solicitud != fingerprint:
        raise ConflictoFinanciero("idempotencia_conflictiva", "La clave ya identifica una solicitud distinta.")
    return previo


def registrar_egreso(payload, actor, clave):
    revalidar(actor, escritura=True)
    clave = clave_uuid(clave)
    data = datos(EgresoCrearSerializer, payload)
    fingerprint = huella(data)
    previo = recuperar(clave, fingerprint)
    if previo is not None:
        revalidar(actor, escritura=True)
        return previo, False
    try:
        return _registrar(data, actor, clave, fingerprint)
    except IntegrityError as exc:
        name = getattr(getattr(exc.__cause__, "diag", None), "constraint_name", "")
        if name != "fin_egreso_idempotencia_unica":
            raise
        # El atomic perdedor ya revirtió su registro/evento; la unicidad esperó
        # al ganador. No se bloquea ni se vuelve a anular el registro recuperado.
        revalidar(actor, escritura=True)
        previo = recuperar(clave, fingerprint)
        if previo is None:
            raise
        return previo, False


@operacion
def _registrar(data, actor, clave, fingerprint):
    actual = revalidar(actor, escritura=True)
    if data["obra"] is not None and not Obra.objects.filter(pk=data["obra"]).exists():
        raise ValidationError({"obra": "Obra no disponible."})
    campos = {k: v for k, v in data.items() if k != "obra"}
    egreso = Egreso.objects.create(obra_id=data["obra"], registrado_por=actual,
        clave_idempotencia=clave, huella_solicitud=fingerprint, **campos)
    actual = revalidar(actor, escritura=True)  # Incluye cualquier espera por unicidad/FK.
    EgresoEvento.objects.create(egreso=egreso, tipo="CREACION", actor=actual)
    return egreso, True


@operacion
def anular_egreso(pk, payload, actor):
    revalidar(actor, escritura=True)
    data = datos(EgresoAnularSerializer, payload)
    egreso = Egreso.objects.select_for_update().filter(pk=identificador(pk)).first()
    actual = revalidar(actor, escritura=True)
    if egreso is None:
        raise NotFound("Egreso no encontrado.")
    if not egreso.activo:
        raise ConflictoFinanciero("egreso_ya_anulado", "El registro ya fue anulado administrativamente.")
    egreso.activo = False
    egreso.anulado_por = actual
    egreso.anulado_en = timezone.now()
    egreso.motivo_anulacion = data["motivo"]
    egreso.referencia_correccion = data["referencia_correccion"]
    egreso.full_clean(validate_unique=False, validate_constraints=False)
    models.Model.save(egreso, update_fields=["activo", "anulado_por", "anulado_en", "motivo_anulacion", "referencia_correccion"])
    EgresoEvento.objects.create(egreso=egreso, tipo="ANULACION", actor=actual, motivo=data["motivo"])
    return egreso
