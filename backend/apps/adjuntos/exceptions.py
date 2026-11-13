from rest_framework.exceptions import APIException


class ContenidoRechazado(APIException):
    status_code = 422
    default_detail = "Contenido documental rechazado."
    default_code = "contenido_rechazado"


class ArchivoGrande(APIException):
    status_code = 413
    default_detail = "El archivo excede el límite permitido."


class ScannerNoDisponible(APIException):
    status_code = 503

    def __init__(self):
        super().__init__({"code": "scanner_no_disponible", "detail": "No se pueden aceptar archivos sin análisis de seguridad."})


class AlmacenNoDisponible(APIException):
    status_code = 503

    def __init__(self):
        super().__init__({"code": "almacen_no_disponible", "detail": "Almacenamiento documental no disponible."})


class ConflictoAdjunto(APIException):
    status_code = 409

    def __init__(self, code="estado_incompatible"):
        super().__init__({"code": code, "detail": "La operación no es compatible con el estado actual del recurso."})
