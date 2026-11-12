from contextlib import contextmanager
from dataclasses import dataclass
from time import monotonic

from django.db import connection, transaction
from django.utils import timezone
from rest_framework.exceptions import APIException
from . import catalogo


class ExportacionGrande(APIException):
    status_code = 413
    def __init__(self):
        super().__init__({"code": "exportacion_demasiado_grande", "detail": "La exportación supera el límite permitido de filas o tamaño."})


class TiempoAgotado(APIException):
    status_code = 500
    def __init__(self):
        super().__init__({"code": "reporte_tiempo_excedido", "detail": "El reporte excedió el presupuesto de procesamiento; reduzca el periodo."})


@dataclass
class PresupuestoTiempo:
    inicio: float
    def comprobar(self):
        if monotonic() - self.inicio > catalogo.MAX_SEGUNDOS:
            raise TiempoAgotado()


@contextmanager
def snapshot():
    if connection.in_atomic_block:
        raise RuntimeError("Reportes requiere una transacción de lectura propia.")
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
            cursor.execute("SET LOCAL statement_timeout = '30000ms'")
            cursor.execute("SELECT pg_current_snapshot()")
            cursor.fetchone()
        yield timezone.now(), PresupuestoTiempo(monotonic())
