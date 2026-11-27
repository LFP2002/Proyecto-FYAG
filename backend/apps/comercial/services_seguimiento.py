"""Lectura gerencial de presupuestos: cohortes por creación, estados actuales."""
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP, localcontext
import re

from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .models import Presupuesto

HISTORICOS = {"PENDIENTE_GERENCIA": "PENDIENTE_FINANZAS", "APROBADO_GERENCIA": "APROBADO_FINANZAS", "RECHAZADO_GERENCIA": "RECHAZADO_FINANZAS"}
ESTADOS = tuple(e for e in Presupuesto.Estado.values if e not in HISTORICOS)
ABIERTOS = {"PENDIENTE_FINANZAS", "APROBADO_FINANZAS", "ENVIADO_CLIENTE"}
DIAS = 7


def _fecha(value, key):
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        raise ValidationError({key: ["Use YYYY-MM-DD."]})
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValidationError({key: ["Fecha inválida."]}) from exc


def seguimiento_comercial(queryset, params):
    if set(params) - {"page", "estado", "desde", "hasta", "buscar", "sin_actualizar"} or any(
        len(params.getlist(key)) != 1 for key in params
    ):
        raise ValidationError({"query": ["Parámetros desconocidos o repetidos."]})
    if "page" in params and (not re.fullmatch(r"[1-9][0-9]{0,18}", params["page"]) or int(params["page"]) > 9223372036854775807):
        raise ValidationError({"page": ["Página inválida."]})
    estado = params.get("estado", "")
    buscar = params.get("buscar", "").strip().casefold()
    sin_actualizar = params.get("sin_actualizar", "")
    if estado and estado not in ESTADOS:
        raise ValidationError({"estado": ["Estado desconocido."]})
    if sin_actualizar not in {"", "true"}:
        raise ValidationError({"sin_actualizar": ["Use true."]})
    if len(buscar) > 100:
        raise ValidationError({"buscar": ["Máximo 100 caracteres."]})
    desde = _fecha(params["desde"], "desde") if "desde" in params else None
    hasta = _fecha(params["hasta"], "hasta") if "hasta" in params else None
    if desde and hasta and desde > hasta:
        raise ValidationError({"hasta": ["Debe ser igual o posterior a desde."]})
    if desde:
        queryset = queryset.filter(creado_en__date__gte=desde)
    if hasta:
        queryset = queryset.filter(creado_en__date__lte=hasta)
    resumen = {e: {"cantidad": 0, "monto_neto": Decimal("0.00"), "sin_precio": 0} for e in ESTADOS}
    total = estancados = 0
    rows = []
    limite = timezone.now() - timedelta(days=DIAS)
    with localcontext() as ctx:
        ctx.prec = 60
        for presupuesto in queryset.select_related("cliente").prefetch_related("items").iterator(chunk_size=100):
            actual = HISTORICOS.get(presupuesto.estado, presupuesto.estado)
            monto = presupuesto.monto_neto
            pendiente = actual in ABIERTOS and presupuesto.actualizado_en <= limite
            resumen[actual]["cantidad"] += 1
            if monto is None:
                resumen[actual]["sin_precio"] += 1
            else:
                resumen[actual]["monto_neto"] += monto
            total += 1
            estancados += pendiente
            if (estado and actual != estado) or (sin_actualizar and not pendiente):
                continue
            cliente = presupuesto.cliente.nombre_legal
            if buscar and buscar not in " ".join((presupuesto.codigo, cliente, presupuesto.descripcion)).casefold():
                continue
            rows.append({
                "id": presupuesto.pk, "codigo": presupuesto.codigo, "cliente_nombre": cliente,
                "descripcion": presupuesto.descripcion, "estado": actual, "estado_original": presupuesto.estado,
                "monto_neto": format(monto, ".2f") if monto is not None else None,
                "creado_en": presupuesto.creado_en.isoformat(),
                "actualizado_en": presupuesto.actualizado_en.isoformat(), "sin_actualizar": pendiente,
            })
        aceptados = resumen["APROBADO_CLIENTE"]["cantidad"]
        respuestas = aceptados + resumen["RECHAZADO_CLIENTE"]["cantidad"]
        tasa = (Decimal(aceptados) * 100 / respuestas).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP) if respuestas else None
        resultado = {
            "total": total, "sin_actualizar": estancados, "dias_sin_actualizar": DIAS,
            "respuestas_cliente": respuestas, "tasa_aceptacion": format(tasa, ".1f") if tasa is not None else None,
            "estados": {e: {**r, "monto_neto": (None if r["sin_precio"] else format(r["monto_neto"], ".2f"))}
                        for e, r in resumen.items()},
        }
    rows.sort(key=lambda r: not r["sin_actualizar"])
    return rows, resultado
