from functools import lru_cache
from pathlib import Path
from xml.sax.saxutils import escape

import reportlab
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A3, A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Paragraph, Table, TableStyle

from ..catalogo import COLUMNAS, MONETARIOS, TITULOS
from ..consistencia import ExportacionGrande
from .comun import AVISO, texto
from .presentacion import LOGO, NAVY, BLUE, CYAN, MUTED, LIGHT, NOTAS, IDS, fecha, mostrar, indicadores, filtros_visibles


@lru_cache(maxsize=1)
def fuente():
    fonts = Path(reportlab.__file__).parent / "fonts"
    pdfmetrics.registerFont(TTFont("FYAGVera", str(fonts / "Vera.ttf")))
    pdfmetrics.registerFont(TTFont("FYAGVeraBold", str(fonts / "VeraBd.ttf")))
    return "FYAGVera"


def color(value):
    return colors.HexColor("#" + value)


def generar(tipo, filas, info, archivo, tiempo):
    # A4 para rentabilidad; A3 para las tablas de mayor cantidad de columnas.
    ancho, alto = landscape(A4 if tipo == "rentabilidad" else A3)
    margen = 32
    disponible = ancho - 2 * margen
    font = fuente()
    bold = "FYAGVeraBold"
    base = ParagraphStyle("Celda", fontName=font, fontSize=8.5, leading=11, wordWrap="CJK", textColor=color(NAVY), alignment=TA_LEFT)
    numero = ParagraphStyle("Importe", parent=base, alignment=TA_RIGHT)
    header = ParagraphStyle("Cabecera", parent=base, fontName=bold, textColor=colors.white)
    caption = ParagraphStyle("Etiqueta", parent=base, fontSize=8, leading=10, textColor=color(MUTED))
    title = ParagraphStyle("Titulo", parent=base, fontName=bold, fontSize=19, leading=23)
    cols = COLUMNAS[tipo]
    pesos = [0.58 if k in IDS else 0.65 if k == "moneda" else 2.1 if k == "cliente_nombre" else 1.5 if k in MONETARIOS else 1.2 if k.endswith("_en") or k.endswith("_nombre") else 1 for k, _ in cols]
    anchos = [disponible * p / sum(pesos) for p in pesos]
    canvas = Canvas(archivo, pagesize=(ancho, alto), pageCompression=1)
    canvas.setTitle("FYAG - " + TITULOS[tipo])
    canvas.setAuthor("Frío y Agroindustria SpA")
    pagina = 0
    def p(value, style=base):
        return Paragraph(escape(texto(value)), style)
    def draw(value, style, x, top, width):
        par = p(value, style)
        _, h = par.wrap(width, alto)
        par.drawOn(canvas, x, top-h)
        return top-h
    def tabla(values, cabecera=False, zebra=False):
        t = Table([[p(v, header if cabecera else numero if k in MONETARIOS else base) for v, (k, _) in zip(values, cols)]], colWidths=anchos)
        t.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 7),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ("BACKGROUND", (0, 0), (-1, -1), color(NAVY) if cabecera else color(LIGHT) if zebra else colors.white),
            ("LINEBELOW", (0, 0), (-1, -1), 0.35, color("CFDAE5")),
        ]))
        return t
    def nueva_pagina(primera=False):
        nonlocal pagina
        tiempo.comprobar()
        if pagina:
            canvas.showPage()
        pagina += 1
        if pagina > 2000:
            raise ExportacionGrande()
        canvas.setFillColor(color(CYAN))
        canvas.rect(0, alto-6, ancho, 6, fill=1, stroke=0)
        canvas.drawImage(str(LOGO), margen, alto-margen-47, width=69, height=47, preserveAspectRatio=True, mask="auto")
        x = margen + 85
        y = draw("FRÍO Y AGROINDUSTRIA SpA · INFORME INTERNO", caption, x, alto-margen, disponible-85)-3
        y = draw(TITULOS[tipo], title, x, y, disponible-85)-4
        y = draw("Período: " + fecha(info["periodo"]["desde"]) + " al " + fecha(info["periodo"]["hasta"]) + "   |   Corte Santiago: " + fecha(info["fecha_corte"]) + "   |   Filas: " + str(info["count"]), caption, x, y, disponible-85)-10
        y = min(y, alto-margen-58)
        canvas.setStrokeColor(color("CFDAE5"))
        canvas.line(margen, y, ancho-margen, y)
        y -= 12
        if primera:
            y = draw(filtros_visibles(info) + "   |   Moneda: CLP" + ("   |   Emisor: " + info["emisor"] if info.get("emisor") else ""), caption, margen, y, disponible)-10
            items = indicadores(info)
            gap = 8
            w = (disponible-gap*(len(items)-1))/len(items)
            rendered = []
            for label, value, tone in items:
                style = ParagraphStyle("KPI", parent=base, fontName=bold, fontSize=15, leading=18, textColor=color(tone))
                pl, pv = p(label, caption), p(value, style)
                _, lh = pl.wrap(w-18, alto)
                _, vh = pv.wrap(w-18, alto)
                rendered.append((pl, pv, lh, vh, tone))
            h = max(58, max(lh+vh+24 for _, _, lh, vh, _ in rendered))
            for i, (pl, pv, lh, vh, tone) in enumerate(rendered):
                xx = margen+i*(w+gap)
                canvas.setFillColor(color(LIGHT))
                canvas.roundRect(xx, y-h, w, h, 5, fill=1, stroke=0)
                canvas.setFillColor(color(tone))
                canvas.rect(xx, y-h, 3, h, fill=1, stroke=0)
                pl.drawOn(canvas, xx+9, y-9-lh)
                pv.drawOn(canvas, xx+9, y-14-lh-vh)
            y -= h+12
            y = draw(NOTAS[tipo], caption, margen, y, disponible)-12
        canvas.setStrokeColor(color("CFDAE5"))
        canvas.line(margen, 26, ancho-margen, 26)
        canvas.setFillColor(color(MUTED))
        canvas.setFont(font, 7.5)
        canvas.drawString(margen, 14, AVISO)
        canvas.drawRightString(ancho-margen, 14, f"FYAG  |  Página {pagina}")
        t = tabla([label.replace(" (texto)", "") for _, label in cols], True)
        _, h = t.wrap(disponible, alto)
        t.drawOn(canvas, margen, y-h)
        return y-h
    y = nueva_pagina(True)
    n = 0
    for row in filas:
        tiempo.comprobar()
        t = tabla([mostrar(k, row[k]) for k, _ in cols], zebra=n % 2 == 1)
        _, h = t.wrap(disponible, alto)
        if y-h < margen+8:
            y = nueva_pagina()
        if y-h < margen+8:
            raise ExportacionGrande()
        t.drawOn(canvas, margen, y-h)
        y -= h
        n += 1
    if n == 0:
        draw("No hay registros para el período y filtros seleccionados.", base, margen+5, y-12, disponible-10)
    tiempo.comprobar()
    canvas.save()
