from rest_framework.exceptions import APIException


class MongoNoDisponible(APIException):
    status_code = 503

    def __init__(self):
        super().__init__({"code": "documentos_no_disponibles", "detail": "Servicio documental temporalmente no disponible."})


class MetadataPendiente(APIException):
    status_code = 409

    def __init__(self):
        super().__init__({"code": "metadata_pendiente_sincronizacion", "detail": "Metadatos pendientes de sincronización; reintente después de reconciliar."})


class RevisionObsoleta(APIException):
    status_code = 409

    def __init__(self):
        super().__init__({"code": "revision_obsoleta", "detail": "La revisión ya cambió; consulte el documento antes de editar."})
