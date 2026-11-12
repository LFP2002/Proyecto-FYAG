import unicodedata

from .. import catalogo
from ..consistencia import ExportacionGrande

AVISO = "Reporte de gestión — no es documento tributario ni DTE"


def texto(value):
    if value is None:
        return ""
    if type(value) is bool:
        return "true" if value else "false"
    # Controles/bidi/zero-width no pueden convertir texto en instrucciones.
    return "".join(" " if unicodedata.category(c) in ("Cc", "Zl", "Zp") else c
                   for c in str(value) if unicodedata.category(c) not in ("Cf", "Cs")
                   and ord(c) % 65536 not in (0xFFFE, 0xFFFF) and not 0xFDD0 <= ord(c) <= 0xFDEF)


def texto_csv(value):
    value = texto(value)
    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value


def metadatos(tipo, info):
    rows = [("Aviso", AVISO), ("Reporte", catalogo.TITULOS[tipo]), ("Tipo", tipo),
            ("Desde", info["periodo"]["desde"]), ("Hasta", info["periodo"]["hasta"]),
            ("Fecha de corte Santiago", info["fecha_corte"]), ("Zona horaria", "America/Santiago"),
            ("Moneda", "CLP"), ("Filas", info["count"])]
    rows += [("Filtro " + k, v) for k, v in info["filtros"].items()]
    rows += [("Total " + k, v) for k, v in info["totales"].items()]
    return rows


class ArchivoLimitado:
    """Proxy seekable para ZIP/PDF. El límite se aplica antes de cada write."""
    def __init__(self, archivo, tiempo):
        self.archivo, self.tiempo = archivo, tiempo

    def write(self, data):
        self.tiempo.comprobar()
        if self.archivo.tell() + len(data) > catalogo.MAX_BYTES:
            raise ExportacionGrande()
        return self.archivo.write(data)

    def __getattr__(self, name):
        return getattr(self.archivo, name)
