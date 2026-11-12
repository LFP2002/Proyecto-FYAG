from functools import lru_cache
from pathlib import Path
from xml.sax.saxutils import escape

import reportlab
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A3, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Paragraph, Table, TableStyle

from ..catalogo import COLUMNAS, MONETARIOS
from ..consistencia import ExportacionGrande
from .comun import AVISO, metadatos, texto


@lru_cache(maxsize=1)
def fuente():
    # Vera y su licencia se distribuyen con ReportLab; ninguna URL ni fuente de
    # sistema recibida del cliente. Embebida para acentos reproducibles.
    pdfmetrics.registerFont(TTFont("FYAGVera", str(Path(reportlab.__file__).parent / "fonts" / "Vera.ttf")))
    return "FYAGVera"


def generar(tipo, filas, info, archivo, tiempo):
    ancho, alto = landscape(A3)
    margen = 25
    disponible = ancho - margen * 2
    font = fuente()
    estilo = ParagraphStyle("Celda", fontName=font, fontSize=7, leading=9, wordWrap="CJK", alignment=TA_LEFT)
    meta = ParagraphStyle("Meta", parent=estilo, fontSize=8, leading=10)
    pesos = [2 if key == "cliente_nombre" else 1.6 if key in MONETARIOS else 1.4 if key.endswith("_en") else 1 for key, _ in COLUMNAS[tipo]]
    anchos = [disponible * p / sum(pesos) for p in pesos]
    canvas = Canvas(archivo, pagesize=(ancho, alto), pageCompression=1)
    canvas.setTitle("FYAG - " + tipo)
    pagina = 0
    def parrafo(value, style=estilo):
        return Paragraph(escape(texto(value)), style)
    def tabla(values, cabecera=False):
        t = Table([[parrafo(value) for value in values]], colWidths=anchos)
        t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3), ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3), ("GRID", (0, 0), (-1, -1), 0.25, colors.grey)] + ([("BACKGROUND", (0, 0), (-1, -1), colors.lightgrey)] if cabecera else [])))
        return t
    def nueva_pagina(primera=False):
        nonlocal pagina
        tiempo.comprobar()
        if pagina:
            canvas.showPage()
        pagina += 1
        if pagina > 2000:
            raise ExportacionGrande()
        canvas.setFont(font, 7)
        canvas.drawString(margen, 12, f"FYAG - Página {pagina} - Reporte de gestión, no DTE")
        y = alto - margen
        datos = metadatos(tipo, info) if primera else [("Aviso", AVISO), ("Reporte", tipo), ("Periodo", f"{info['periodo']['desde']} a {info['periodo']['hasta']}"), ("Corte", info["fecha_corte"])]
        for key, value in datos:
            p = parrafo(f"{key}: {value}", meta)
            _, h = p.wrap(disponible, alto)
            p.drawOn(canvas, margen, y - h)
            y -= h + 2
        y -= 7
        t = tabla([label for _, label in COLUMNAS[tipo]], True)
        _, h = t.wrap(disponible, alto)
        t.drawOn(canvas, margen, y - h)
        return y - h
    y = nueva_pagina(True)
    for row in filas:
        tiempo.comprobar()
        t = tabla([row[key] for key, _ in COLUMNAS[tipo]])
        _, h = t.wrap(disponible, alto)
        if h > alto - 180:
            raise ExportacionGrande()
        if y - h < margen:
            y = nueva_pagina()
        t.drawOn(canvas, margen, y - h)
        y -= h
    tiempo.comprobar()
    canvas.save()
