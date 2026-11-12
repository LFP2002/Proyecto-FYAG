"""Registro cerrado de columnas, proyecciones y permisos. Sin URLs de descarga."""
FORMATOS = ("csv", "xlsx", "pdf")
TIPOS = ("obras", "rentabilidad", "cobranzas")
ESTADOS_OBRA = ("PLANIFICADA", "EN_PROCESO", "SUSPENDIDA", "FINALIZADA", "CANCELADA")
ESTADOS_COBRANZA = ("PENDIENTE", "PARCIAL", "PAGADA", "VENCIDA")
TITULOS = {"obras": "Reporte de obras", "rentabilidad": "Rentabilidad de obras finalizadas", "cobranzas": "Cobranzas de documentos vigentes"}
FILTROS = {"obras": ("desde", "hasta", "cliente", "estado", "fecha_base"),
           "rentabilidad": ("desde", "hasta", "cliente"), "cobranzas": ("desde", "hasta", "cliente", "estado")}
COLUMNAS = {
    "obras": (("obra", "Obra ID"), ("codigo_obra", "Código obra"), ("cliente", "Cliente ID"), ("cliente_nombre", "Cliente"), ("categoria_nombre", "Categoría"), ("estado", "Estado"), ("tecnico_responsable", "Responsable ID"), ("tecnico_nombre", "Responsable"), ("fecha_programada", "Programada"), ("creado_en", "Creación Santiago"), ("finalizado_en", "Finalización Santiago"), ("presupuesto_neto", "Presupuesto neto CLP")),
    "rentabilidad": (("obra", "Obra ID"), ("codigo_obra", "Código obra"), ("cliente", "Cliente ID"), ("cliente_nombre", "Cliente"), ("finalizado_en", "Finalización Santiago"), ("moneda", "Moneda"), ("presupuesto_neto", "Presupuesto neto CLP"), ("costo_real_neto", "Costo real neto CLP"), ("margen_neto", "Margen neto CLP"), ("tiene_cortesia_sin_cobro", "Cortesía sin cobro")),
    "cobranzas": (("documento", "Documento ID"), ("obra", "Obra ID"), ("codigo_obra", "Código obra"), ("cliente", "Cliente ID"), ("cliente_nombre", "Cliente"), ("tipo_documento", "Tipo documento"), ("folio_externo", "Folio externo (texto)"), ("fecha_emision", "Emisión"), ("fecha_vencimiento", "Vencimiento"), ("moneda", "Moneda"), ("monto_documentado_bruto", "Documentado bruto CLP"), ("abonado", "Abonado bruto CLP"), ("saldo", "Saldo bruto CLP"), ("estado_cobranza", "Estado cobranza")),
}
MONETARIOS = {"presupuesto_neto", "costo_real_neto", "margen_neto", "monto_documentado_bruto", "abonado", "saldo", "saldo_vencido"}
MAX_FILAS = 10_000
MAX_BYTES = 50 * 1024 * 1024
LOTE = 200
MAX_SEGUNDOS = 60
