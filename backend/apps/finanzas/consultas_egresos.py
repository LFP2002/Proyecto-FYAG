"""Consultas 021 sin efectos laterales ni locks de los dominios propietarios."""
from decimal import Decimal, localcontext

from django.db import connection
from django.http import QueryDict
from rest_framework.exceptions import NotFound, ValidationError

from .models import Egreso, PagoDocumento
from .permissions_egresos import revalidar
from .serializers_documentos import FechaISO
from .services_documentos import ConflictoFinanciero, identificador
from .views_documentos import pk_url, query_estricta


def validar_query(params, permitidos=()):
    if not hasattr(params, "getlist"):
        normalizados = QueryDict(mutable=True)
        normalizados.update(params)
        params = normalizados
    query_estricta(params, permitidos)
    if set(params) - set(permitidos) or any(params[k] == "" for k in params):
        raise ValidationError({"query": "Parámetro vacío o no permitido."})
    if "page" in params:
        pk_url(params["page"])


def periodo(params, *, obligatorio=False):
    if ("desde" in params) != ("hasta" in params) or obligatorio and "desde" not in params:
        raise ValidationError({"desde": "Indique desde y hasta conjuntamente."})
    if "desde" not in params:
        return None
    inicio, fin = (FechaISO().run_validation(params[k]) for k in ("desde", "hasta"))
    if inicio > fin or (fin - inicio).days >= 366:
        raise ValidationError({"desde": "Rango inclusivo máximo de 366 días."})
    return inicio, fin


def listado(actor, params):
    revalidar(actor)
    validar_query(params, {"categoria", "medio", "obra", "activo", "desde", "hasta", "page"})
    fechas = periodo(params)
    qs = Egreso.objects.order_by("-fecha_pago", "-id")
    for campo, opciones in [("categoria", Egreso.Categoria.values), ("medio", PagoDocumento.Medio.values)]:
        if campo in params:
            if params[campo] not in opciones:
                raise ValidationError({campo: "Valor no permitido."})
            qs = qs.filter(**{campo: params[campo]})
    if "activo" in params:
        if params["activo"] not in {"true", "false"}:
            raise ValidationError({"activo": "Use true o false."})
        qs = qs.filter(activo=params["activo"] == "true")
    if "obra" in params:
        qs = qs.filter(obra_id=pk_url(params["obra"]))
    if fechas:
        qs = qs.filter(fecha_pago__range=fechas)
    return qs


def obtener(actor, pk):
    revalidar(actor)
    egreso = Egreso.objects.filter(pk=identificador(pk)).first()
    if egreso is None:
        raise NotFound("Egreso no encontrado.")
    return egreso


def historial(actor, pk, params):
    revalidar(actor)
    validar_query(params, {"page"})
    return obtener(actor, pk).eventos.order_by("creado_en", "id")


def resumen(actor, params):
    revalidar(actor)
    validar_query(params, {"desde", "hasta"})
    inicio, fin = periodo(params, obligatorio=True)
    # Una sola sentencia = un único snapshot MVCC, incluso dentro de un atomic
    # READ COMMITTED exterior. Sin joins que multipliquen importes, ni escrituras.
    with connection.cursor() as cursor:
        cursor.execute("""/* SPEC-021 snapshot */
            SELECT
              (SELECT COALESCE(SUM(p.monto), 0) FROM finanzas_pagodocumento p
               WHERE p.activo AND p.fecha_pago BETWEEN %s AND %s),
              (SELECT COALESCE(SUM(e.monto), 0) FROM finanzas_egreso e
               WHERE e.activo AND e.fecha_pago BETWEEN %s AND %s),
              EXISTS (
                SELECT 1 FROM finanzas_pagodocumento p
                JOIN finanzas_documentocobro d ON d.id = p.documento_id
                WHERE p.activo AND p.fecha_pago BETWEEN %s AND %s AND
                  (d.estado <> 'VIGENTE' OR p.fecha_pago < d.fecha_emision OR
                   (SELECT COALESCE(SUM(a.monto), 0) FROM finanzas_pagodocumento a
                    WHERE a.documento_id = d.id AND a.activo) > d.monto_total)
              )
        """, [inicio, fin, inicio, fin, inicio, fin])
        ingresos, egresos, inconsistente = cursor.fetchone()
    if inconsistente:
        raise ConflictoFinanciero("origen_inconsistente", "Existen pagos activos incompatibles con su documento de origen.")
    ingresos, egresos = Decimal(ingresos), Decimal(egresos)
    if not all(n.is_finite() and n >= 0 for n in (ingresos, egresos)):
        raise ConflictoFinanciero("importe_fuera_rango", "El agregado financiero requiere revisión de integridad.")
    # NUMERIC de PostgreSQL suma sin la precisión de contexto de Python. Hasta
    # BIGINT registros de NUMERIC(38,2) caben en 80 dígitos, sin limitar el agregado
    # artificialmente al máximo de un movimiento individual.
    with localcontext() as ctx:
        ctx.prec = 80
        flujo = ingresos - egresos
    return {"periodo": {"desde": inicio.isoformat(), "hasta": fin.isoformat()}, "moneda": "CLP",
            "ingresos_recibidos": format(ingresos, ".2f"), "egresos_pagados": format(egresos, ".2f"),
            "flujo_neto_registrado": format(flujo, ".2f"), "naturaleza": "REGISTROS_ADMINISTRATIVOS_NO_CONCILIADOS"}
