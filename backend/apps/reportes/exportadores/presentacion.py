"""Presentación corporativa; nunca modifica importes ni reglas de negocio."""
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from ..catalogo import COLUMNAS, MONETARIOS
from ..filtros import ZONA
from .comun import texto

LOGO = Path(__file__).with_name("logo-fyag.jpg")
NAVY = "16324D"
BLUE = "24598E"
CYAN = "009AD8"
MUTED = "526578"
LIGHT = "EDF2F7"
GREEN = "176B4A"
RED = "A62631"
LABELS = {
    "obras": "Obras", "documentos": "Documentos",
    "presupuesto_neto": "Presupuesto neto", "costo_real_neto": "Costo real neto",
    "margen_neto": "Margen neto", "monto_documentado_bruto": "Total documentado bruto",
    "abonado": "Total cobrado", "saldo": "Saldo pendiente", "saldo_vencido": "Saldo vencido",
}
ESTADOS = {
    "PLANIFICADA": "Planificada", "EN_PROCESO": "En proceso", "SUSPENDIDA": "Suspendida",
    "FINALIZADA": "Finalizada", "CANCELADA": "Cancelada", "PENDIENTE": "Pendiente",
    "PARCIAL": "Pago parcial", "PAGADA": "Pagada", "VENCIDA": "Vencida",
    "CREACION": "Creación", "FINALIZACION": "Finalización",
    "FACTURA_AFECTA": "Factura afecta", "FACTURA_EXENTA": "Factura exenta",
}
NOTAS = {
    "obras": "El presupuesto neto no equivale a ingresos recibidos ni mide avance físico.",
    "rentabilidad": "Margen neto: presupuesto menos costo real. No equivale a utilidad contable ni a cobros.",
    "cobranzas": "Saldos actuales de documentos vigentes emitidos en el período; no es una cartera histórica.",
}
IDS = {"obra", "cliente", "documento", "tecnico_responsable"}


def clp(value):
    # No usar float ni cuantizar con el contexto Decimal de 28 dígitos.
    entero, fraccion = str(value).split(".")
    signo = "-" if entero.startswith("-") else ""
    entero = entero.lstrip("-")
    agrupado = ".".join([entero[:len(entero) % 3]] * bool(len(entero) % 3)
                        + [entero[i:i+3] for i in range(len(entero) % 3, len(entero), 3)])
    return signo + "$" + agrupado + ("," + fraccion if fraccion != "00" else "")


def fecha(value):
    if not value:
        return "—"
    if len(value) == 10:
        return date.fromisoformat(value).strftime("%d/%m/%Y")
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(ZONA).strftime("%d/%m/%Y %H:%M")


def mostrar(key, value):
    if value is None:
        return "—"
    if key in MONETARIOS:
        return clp(value)
    if key.endswith("_en") or key.startswith("fecha_") and key != "fecha_base":
        return fecha(value)
    if key in ("estado", "estado_cobranza", "tipo_documento", "fecha_base"):
        return ESTADOS.get(value, texto(value))
    if type(value) is bool:
        return "Sí" if value else "No"
    return texto(value)


def indicadores(info):
    return [(LABELS[k], mostrar(k, v), RED if k == "saldo_vencido" or k == "costo_real_neto" or (k == "margen_neto" and Decimal(v) < 0) else GREEN if k in ("margen_neto", "abonado") else NAVY)
            for k, v in info["totales"].items()]


def filtros_visibles(info):
    f = info["filtros"]
    parts = []
    if "cliente" in f:
        parts.append("Cliente ID: " + texto(f["cliente"]))
    if "estado" in f:
        parts.append("Estado: " + mostrar("estado", f["estado"]))
    if "fecha_base" in f:
        parts.append("Fecha base: " + mostrar("fecha_base", f["fecha_base"]))
    return " · ".join(parts) if parts else "Sin filtros adicionales"


def columnas_detalle(tipo):
    return [(k, label.replace(" (texto)", "")) for k, label in COLUMNAS[tipo] if k not in IDS and k != "moneda"]
