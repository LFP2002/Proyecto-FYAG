"""Errores públicos de dominio, independientes de DRF y del transporte HTTP."""


class ErrorPresupuesto(Exception):
    codigo = "error_presupuesto"
    mensaje = "No se pudo completar la operación del presupuesto."

    def __init__(self, mensaje=None):
        super().__init__(mensaje or self.mensaje)


class EstadoIncompatible(ErrorPresupuesto):
    codigo = "estado_incompatible"
    mensaje = "La operación no es válida en el estado actual del presupuesto."


class TransicionNoPermitida(EstadoIncompatible):
    codigo = "transicion_no_permitida"
    mensaje = "La acción no corresponde a la aprobación configurada."


class DatosInvalidos(ErrorPresupuesto):
    codigo = "datos_invalidos"
    mensaje = "Los datos del presupuesto no son válidos."

    def __init__(self, errores=None):
        self.errores = errores or {"__all__": [self.mensaje]}
        super().__init__()


class ClienteInactivo(DatosInvalidos):
    codigo = "cliente_inactivo"
    mensaje = "El cliente debe estar activo para esta operación."


class MotivoObligatorio(DatosInvalidos):
    codigo = "motivo_obligatorio"
    mensaje = "Debe indicar un motivo no vacío."


class OrdenDuplicado(DatosInvalidos):
    codigo = "orden_duplicado"
    mensaje = "Ya existe un ítem con este orden en el presupuesto."


class RecursoNoEncontrado(ErrorPresupuesto):
    codigo = "recurso_no_encontrado"
    mensaje = "No se encontró el recurso solicitado."
