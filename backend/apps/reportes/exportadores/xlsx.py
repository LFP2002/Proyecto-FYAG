from contextlib import suppress
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import Alignment, Font
from openpyxl.writer.excel import ExcelWriter

from ..catalogo import COLUMNAS, MONETARIOS
from .comun import metadatos, texto


def celda(hoja, value, *, cabecera=False):
    if type(value) is bool:
        return WriteOnlyCell(hoja, value=value)
    cell = WriteOnlyCell(hoja, value=texto(value))
    # TODOS los importes como texto exacto; evita cualquier conversión a float.
    cell.data_type = "s"
    cell.number_format = "@"
    if cabecera:
        cell.font = Font(bold=True)
    return cell


def generar(tipo, filas, info, archivo, tiempo):
    libro = Workbook(write_only=True)
    resultados = libro.create_sheet("Resultados")
    resumen = libro.create_sheet("Resumen")
    resultados.freeze_panes = "A2"
    for indice, (key, titulo) in enumerate(COLUMNAS[tipo], 1):
        from openpyxl.utils import get_column_letter
        resultados.column_dimensions[get_column_letter(indice)].width = 48 if key in MONETARIOS or key.endswith("_nombre") else min(max(len(titulo) + 2, 22), 35)
    resumen.column_dimensions["A"].width = 32
    resumen.column_dimensions["B"].width = 75
    try:
        resultados.append([celda(resultados, titulo, cabecera=True) for _, titulo in COLUMNAS[tipo]])
        for fila in filas:
            tiempo.comprobar()
            resultados.append([celda(resultados, fila[key]) for key, _ in COLUMNAS[tipo]])
        for key, value in metadatos(tipo, info):
            dato = celda(resumen, value)
            dato.alignment = Alignment(wrap_text=True, vertical="top")
            resumen.append([celda(resumen, key), dato])
        resumen.append([celda(resumen, "Precisión"), celda(resumen, "Todos los importes e identificadores se conservan como texto exacto; no usar inferencia numérica ni fórmulas para reinterpretarlos.")])
        # Contexto explícito: openpyxl Workbook.save no cierra su ZipFile si
        # write_data falla. Así no quedan finalizadores escribiendo tras el error.
        with ZipFile(archivo, "w", ZIP_DEFLATED, allowZip64=True) as archive:
            ExcelWriter(libro, archive).write_data()
    finally:
        # openpyxl write_only usa XML privado temporal. La versión está fijada;
        # cerrar y limpiar incluso si falla la escritura ZIP o el generador.
        for hoja in libro.worksheets:
            with suppress(Exception):
                hoja.close()
            writer = hoja._writer
            if writer is not None and Path(writer.out).exists():
                writer.cleanup()
        libro.close()
