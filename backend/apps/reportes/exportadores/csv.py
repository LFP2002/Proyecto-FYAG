import csv
from io import StringIO

from ..catalogo import COLUMNAS, MONETARIOS
from .comun import metadatos, texto, texto_csv


def generar(tipo, filas, info, archivo, tiempo):
    archivo.write(b"\xef\xbb\xbf")
    buffer = StringIO(newline="")
    writer = csv.writer(buffer, delimiter=";", lineterminator="\r\n", quoting=csv.QUOTE_MINIMAL)
    def escribir(row):
        buffer.seek(0)
        buffer.truncate()
        writer.writerow(row)
        archivo.write(buffer.getvalue().encode("utf-8"))
    for key, value in metadatos(tipo, info):
        escribir(["META", key, texto(value) if key.removeprefix("Total ") in MONETARIOS else texto_csv(value)])
    escribir(["META", "Importación CSV", "UTF-8 BOM; delimitador punto y coma. Para conservar ceros en Excel, importar Folio como texto o utilizar XLSX."])
    escribir([])
    escribir([titulo for _, titulo in COLUMNAS[tipo]])
    for fila in filas:
        tiempo.comprobar()
        escribir([texto(fila[key]) if key in MONETARIOS else texto_csv(fila[key]) for key, _ in COLUMNAS[tipo]])
