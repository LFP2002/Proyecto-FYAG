from contextlib import suppress
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.drawing.image import Image
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.writer.excel import ExcelWriter

from ..catalogo import COLUMNAS, MONETARIOS, TITULOS
from .comun import AVISO, metadatos, texto
from .presentacion import LOGO, NAVY, BLUE, CYAN, MUTED, LIGHT, NOTAS, IDS, fecha, mostrar, indicadores, filtros_visibles, columnas_detalle


def celda(hoja, value, *, cabecera=False, zebra=False, dinero=False, title=False, tone=NAVY, muted=False):
    cell = WriteOnlyCell(hoja, value=value if type(value) is bool else texto(value))
    if type(value) is not bool:
        # Incluso un texto que comienza por '=' queda explícitamente tipado como texto.
        cell.data_type = "s"
        cell.number_format = "@"
    cell.font = Font(name="Calibri", size=17 if title else 11, bold=cabecera or title or dinero, color="FFFFFF" if cabecera else MUTED if muted else tone)
    if cabecera or zebra:
        cell.fill = PatternFill("solid", fgColor=NAVY if cabecera else LIGHT)
    cell.alignment = Alignment(horizontal="right" if dinero else "left", vertical="center", wrap_text=True)
    return cell


def configurar(hoja, columnas, count, detalle=False):
    hoja.sheet_view.showGridLines = False
    hoja.freeze_panes = "A2"
    hoja.sheet_properties.pageSetUpPr.fitToPage = True
    hoja.page_setup.orientation = "landscape"
    hoja.page_setup.fitToWidth = 1
    hoja.page_setup.fitToHeight = 0
    hoja.print_title_rows = "1:1"
    hoja.auto_filter.ref = f"A1:{get_column_letter(len(columnas))}{count+1}"
    hoja.row_dimensions[1].height = 32
    for i, (key, label) in enumerate(columnas, 1):
        hoja.column_dimensions[get_column_letter(i)].width = (
            36 if key == "cliente_nombre" else 30 if key in MONETARIOS else
            27 if key.endswith("_nombre") else 14 if key in IDS else
            22 if key.endswith("_en") and detalle else 35 if key.endswith("_en") else
            max(16, min(26, len(label)+3)))
    hoja.append([celda(hoja, label, cabecera=True) for _, label in columnas])


def generar(tipo, filas, info, archivo, tiempo):
    libro = Workbook(write_only=True)
    resumen = libro.create_sheet("Resumen")
    detalle = libro.create_sheet("Detalle")
    resultados = libro.create_sheet("Resultados")
    try:
        resumen.sheet_view.showGridLines = False
        resumen.column_dimensions["A"].width = 34
        resumen.column_dimensions["B"].width = 72
        resumen.column_dimensions["D"].width = 25
        logo = Image(str(LOGO))
        logo.width, logo.height = 156, 106
        resumen.add_image(logo, "D1")
        resumen.row_dimensions[1].height = 32
        resumen.append([celda(resumen, "FYAG · Informe interno", cabecera=True), celda(resumen, TITULOS[tipo], cabecera=True)])
        resumen.append([celda(resumen, "Período", muted=True), celda(resumen, fecha(info["periodo"]["desde"])+" al "+fecha(info["periodo"]["hasta"]))])
        resumen.append([celda(resumen, "Corte Santiago", muted=True), celda(resumen, fecha(info["fecha_corte"]))])
        resumen.append([celda(resumen, "Filtros", muted=True), celda(resumen, filtros_visibles(info))])
        resumen.append([celda(resumen, "Moneda / Emisor", muted=True), celda(resumen, "CLP" + (" · " + info["emisor"] if info.get("emisor") else ""))])
        resumen.append([celda(resumen, "Resumen ejecutivo", cabecera=True), celda(resumen, "Total del período filtrado", cabecera=True)])
        for index, (label, value, tone) in enumerate(indicadores(info), 7):
            resumen.row_dimensions[index].height = 32
            resumen.append([celda(resumen, label, zebra=True), celda(resumen, value, title=True, tone=tone, zebra=True, dinero=True)])
        for n in range(7+len(info["totales"]), 12+len(info["totales"])):
            resumen.row_dimensions[n].height = 30
        resumen.append([celda(resumen, "Interpretación", muted=True), celda(resumen, NOTAS[tipo])])
        resumen.append([celda(resumen, "Aviso de uso", muted=True), celda(resumen, AVISO)])
        resumen.append([celda(resumen, "Detalle"), celda(resumen, "Vista legible con filtros y formatos chilenos.")])
        resumen.append([celda(resumen, "Resultados"), celda(resumen, "Datos originales completos; importes e identificadores como texto exacto.")])
        resumen.append([celda(resumen, "Metadatos de origen", cabecera=True), celda(resumen, "Valores exactos", cabecera=True)])
        for key, value in metadatos(tipo, info):
            tiempo.comprobar()
            resumen.append([celda(resumen, key), celda(resumen, value)])
        cols = columnas_detalle(tipo)
        configurar(detalle, cols, info["count"], True)
        configurar(resultados, COLUMNAS[tipo], info["count"])
        for n, fila in enumerate(filas, 2):
            tiempo.comprobar()
            # Ajuste conservador para nombres largos y montos de máxima precisión.
            height = min(200, max(32, 14 * (1 + max(len(texto(fila[k])) // 25 for k, _ in COLUMNAS[tipo]))))
            detalle.row_dimensions[n].height = height
            resultados.row_dimensions[n].height = height
            detalle.append([celda(detalle, mostrar(k, fila[k]), zebra=n%2==0, dinero=k in MONETARIOS) for k, _ in cols])
            resultados.append([celda(resultados, fila[k], zebra=n%2==0, dinero=k in MONETARIOS) for k, _ in COLUMNAS[tipo]])
        with ZipFile(archivo, "w", ZIP_DEFLATED, allowZip64=True) as archive:
            ExcelWriter(libro, archive).write_data()
    finally:
        for hoja in libro.worksheets:
            with suppress(Exception):
                hoja.close()
            writer = hoja._writer
            if writer is not None and Path(writer.out).exists():
                writer.cleanup()
        libro.close()
