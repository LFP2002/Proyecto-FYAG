from rest_framework.exceptions import APIException


class ConflictoChat(APIException):
    status_code = 409

    def __init__(self, code='estado_incompatible'):
        super().__init__({'code': code, 'detail': 'La operación de chat no es compatible con su estado actual.'})


class ArchivoGrande(APIException):
    status_code = 413
    default_detail = 'El archivo o cuerpo excede el límite permitido.'


class NoDisponible(APIException):
    status_code = 503
    default_detail = 'El servicio de archivos no está disponible. Intente nuevamente.'
