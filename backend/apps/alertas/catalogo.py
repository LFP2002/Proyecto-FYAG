"""Catálogo público cerrado: no depende de precios ni indicadores inventados."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Regla:
    recurso: str
    roles: tuple
    severidad: str
    titulo: str
    descripcion: str


CATALOGO = {
    "PRESUPUESTO_PENDIENTE_GERENCIA": Regla("PRESUPUESTO", ("GERENCIA",), "MEDIA", "Presupuesto pendiente de Gerencia", "El presupuesto requiere revisión de Gerencia."),
    "OBRA_SUSPENDIDA": Regla("OBRA", ("GERENCIA", "SUPERVISOR_OBRAS"), "ALTA", "Obra suspendida", "La obra se encuentra suspendida."),
    "TURNO_PENDIENTE_REVISION": Regla("TURNO", ("SUPERVISOR_OBRAS",), "MEDIA", "Turno pendiente de revisión", "El turno requiere revisión del Supervisor."),
    "COBRANZA_VENCIDA": Regla("DOCUMENTO", ("GERENCIA",), "ALTA", "Cobranza vencida", "Existe un documento vigente con cobranza vencida."),
}
RECURSOS = {regla.recurso for regla in CATALOGO.values()}
ESTADOS = ("PENDIENTE", "ATENDIDA", "RESUELTA")
MAX_PK = 9223372036854775807
