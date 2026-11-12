"""Lecturas puras de los propietarios; ninguna función crea controles u objetos."""
from apps.comercial.models import Presupuesto
from apps.obras.models import Obra, TurnoObra
from apps.finanzas.models import DocumentoCobro
from apps.finanzas.consultas_cobranzas import con_cobranza

MODELOS = {"PRESUPUESTO_PENDIENTE_GERENCIA": Presupuesto, "OBRA_SUSPENDIDA": Obra,
           "TURNO_PENDIENTE_REVISION": TurnoObra, "COBRANZA_VENCIDA": DocumentoCobro}


def vigentes(tipo, queryset=None):
    qs = MODELOS[tipo].objects.all() if queryset is None else queryset
    if tipo == "PRESUPUESTO_PENDIENTE_GERENCIA":
        return qs.filter(estado="PENDIENTE_GERENCIA")
    if tipo == "OBRA_SUSPENDIDA":
        return qs.filter(estado="SUSPENDIDA")
    if tipo == "TURNO_PENDIENTE_REVISION":
        return qs.filter(estado_revision="PENDIENTE_REVISION")
    return con_cobranza(qs.filter(estado="VIGENTE")).filter(saldo_calculado__gt=0, estado_cobranza_calculado="VENCIDA")


def condicion(tipo, pk):
    return vigentes(tipo, MODELOS[tipo].objects.filter(pk=pk)).exists()


def contexto(alertas):
    """Como máximo dos consultas por tipo en una página; sin PII ni importes."""
    out = {}
    for tipo, modelo in MODELOS.items():
        ids = {a.recurso_id for a in alertas if a.tipo == tipo}
        if not ids:
            continue
        qs = modelo.objects.filter(pk__in=ids)
        activos = set(vigentes(tipo, qs).values_list("pk", flat=True))
        if modelo is Presupuesto:
            rows = qs.values("pk", "obra__pk")
            for row in rows:
                out[(tipo, row["pk"])] = {"recurso_codigo": f"PRE-{row['pk']:06d}", "obra": row["obra__pk"], "vigente": row["pk"] in activos}
        elif modelo is Obra:
            for row in qs.values("pk"):
                out[(tipo, row["pk"])] = {"recurso_codigo": f"OB-{row['pk']:06d}", "obra": row["pk"], "vigente": row["pk"] in activos}
        else:
            fields = ["pk", "obra_id"] + (["folio_externo"] if modelo is DocumentoCobro else [])
            for row in qs.values(*fields):
                out[(tipo, row["pk"])] = {"recurso_codigo": row.get("folio_externo"), "obra": row["obra_id"], "vigente": row["pk"] in activos}
    return out
