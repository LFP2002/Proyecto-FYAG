"""Errores de negocio del incremento 004A, independientes de DRF."""


class ErrorObras(Exception):
    codigo = "error_obras"
    mensaje = "No se pudo completar la operación de Obras."

    def __init__(self, mensaje=None):
        super().__init__(mensaje or self.mensaje)


class DatosInvalidos(ErrorObras):
    codigo = "datos_invalidos"
    mensaje = "Los datos enviados no son válidos."

    def __init__(self, errores=None):
        self.errores = errores or {"__all__": [self.mensaje]}
        super().__init__()


class PermisoDenegado(ErrorObras):
    codigo = "permiso_denegado"
    mensaje = "No tiene permiso para realizar esta operación."


class RecursoNoEncontrado(ErrorObras):
    codigo = "recurso_no_encontrado"
    mensaje = "No se encontró el recurso solicitado."


class EstadoIncompatible(ErrorObras):
    codigo = "estado_incompatible"
    mensaje = "La acción no es válida para el estado actual."


class PresupuestoUtilizado(ErrorObras):
    codigo = "presupuesto_utilizado"
    mensaje = "El presupuesto ya está asociado a una obra."


class SinCambios(ErrorObras):
    codigo = "sin_cambios"
    mensaje = "El técnico responsable ya tiene el valor solicitado."
