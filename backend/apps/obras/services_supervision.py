"""Lectura gerencial consolidada, sin escrituras ni consultas por obra."""
from decimal import Decimal, ROUND_HALF_UP, localcontext

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Prefetch
from rest_framework.exceptions import ValidationError

from .models import GastoObra, Obra, TurnoObra
from .services_costos import _totales


def _relacion(obra, nombre):
    try:
        return getattr(obra, nombre)
    except ObjectDoesNotExist:
        return None


def supervision_gerencial(queryset, params):
    estado = params.get("estado", "")
    atencion = params.get("atencion", "todas")
    prioridad = params.get("prioridad", "")
    buscar = params.get("buscar", "").strip().casefold()
    if estado and estado not in Obra.Estado.values:
        raise ValidationError({"estado": ["Estado desconocido."]})
    if atencion not in {"todas", "requiere", "sin_alertas"}:
        raise ValidationError({"atencion": ["Filtro desconocido."]})
    if prioridad not in {"", "sin_programar", "presupuesto_superado", "suspendidas"}:
        raise ValidationError({"prioridad": ["Filtro desconocido."]})
    if len(buscar) > 100:
        raise ValidationError({"buscar": ["Máximo 100 caracteres."]})

    resumen = dict(total=0, en_ejecucion=0, sin_programar=0, presupuesto_superado=0,
                   suspendidas=0, requieren_atencion=0)
    rows = []
    queryset = queryset.select_related("control_costos", "cierre_costos", "cortesia").prefetch_related(
        "presupuesto__items",
        Prefetch("gastos", queryset=GastoObra.objects.filter(vigente=True), to_attr="gastos_vigentes"),
        Prefetch("turnos", queryset=TurnoObra.objects.filter(estado_revision="VALIDADO"), to_attr="turnos_validados"),
    )
    # Reutiliza las mismas reglas Decimal y redondeo que la ficha individual.
    # Se procesan lotes, sin N+1, y se conservan solo las filas proyectadas.
    for obra in queryset.iterator(chunk_size=100):
        presupuesto = obra.presupuesto.monto_neto
        cierre = _relacion(obra, "cierre_costos") if obra.estado == "FINALIZADA" else None
        control = _relacion(obra, "control_costos")
        cortesia = _relacion(obra, "cortesia") is not None
        costo = cierre.costo_total if cierre else _totales(obra.gastos_vigentes, obra.turnos_validados)["costo_total"]
        validado = bool(control and control.costos_validados)
        provisional = not validado or obra.estado == "SUSPENDIDA" or (obra.estado == "FINALIZADA" and cierre is None)
        sin_programar = obra.estado == "PLANIFICADA" and obra.fecha_programada is None
        superado = costo > presupuesto
        suspendida = obra.estado == "SUSPENDIDA"
        sin_responsable = obra.estado in {"PLANIFICADA", "EN_PROCESO", "SUSPENDIDA"} and obra.tecnico_responsable_id is None
        alertas = []
        if superado:
            alertas.append("PRESUPUESTO_SUPERADO")
        if suspendida:
            alertas.append("SUSPENDIDA")
        if sin_programar:
            alertas.append("SIN_PROGRAMAR")
        if sin_responsable:
            alertas.append("SIN_RESPONSABLE")
        if obra.estado == "FINALIZADA" and cierre is None:
            alertas.append("CIERRE_NO_DISPONIBLE")
        nivel = "critica" if superado or "CIERRE_NO_DISPONIBLE" in alertas else "atencion" if alertas else "normal"
        resumen["total"] += 1
        resumen["en_ejecucion"] += obra.estado == "EN_PROCESO"
        resumen["sin_programar"] += sin_programar
        resumen["presupuesto_superado"] += superado
        resumen["suspendidas"] += suspendida
        resumen["requieren_atencion"] += bool(alertas)

        if estado and obra.estado != estado:
            continue
        if atencion == "requiere" and not alertas or atencion == "sin_alertas" and alertas:
            continue
        if prioridad and not {"sin_programar": sin_programar, "presupuesto_superado": superado, "suspendidas": suspendida}[prioridad]:
            continue
        cliente = obra.presupuesto.cliente.nombre_legal
        responsable = (obra.tecnico_responsable.get_full_name().strip() or obra.tecnico_responsable.username) if obra.tecnico_responsable_id else None
        if buscar and buscar not in " ".join((obra.codigo, cliente, obra.categoria_servicio.nombre, responsable or "")).casefold():
            continue
        with localcontext() as ctx:
            ctx.prec = 60
            porcentaje = (costo * 100 / presupuesto).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP) if presupuesto > 0 else None
            diferencia = presupuesto - costo
        rows.append({
            "id": obra.pk, "codigo": obra.codigo, "cliente_nombre": cliente,
            "categoria_nombre": obra.categoria_servicio.nombre, "tecnico_nombre": responsable,
            "estado": obra.estado, "fecha_programada": obra.fecha_programada.isoformat() if obra.fecha_programada else None,
            "presupuesto_neto": format(presupuesto, ".2f"), "costo_total": format(costo, ".2f"),
            "diferencia_neta": format(diferencia, ".2f"),
            "porcentaje_utilizado": format(porcentaje, ".1f") if porcentaje is not None else None,
            "costos_provisionales": provisional, "sin_cobro": cortesia,
            "alertas": alertas, "nivel": nivel,
        })
    # Orden estable dentro de cada prioridad: conserva el orden original por creación.
    rows.sort(key=lambda row: {"critica": 0, "atencion": 1, "normal": 2}[row["nivel"]])
    return rows, resumen
