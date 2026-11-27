"""Lecturas que requieren un presupuesto comercial ya completo."""
from rest_framework.exceptions import APIException


class PresupuestoIncompleto(APIException):
    status_code = 409
    default_code = 'presupuesto_inconsistente'

    def __init__(self):
        super().__init__({'code': self.default_code, 'detail': 'La Obra tiene precios comerciales pendientes.'})


def neto_aprobado(presupuesto):
    # Obras y Finanzas conservan un importe no nullable. Un pendiente en una
    # Obra solo puede provenir de datos escritos fuera del flujo autorizado.
    neto = presupuesto.monto_neto
    if neto is None:
        raise PresupuestoIncompleto()
    return neto
