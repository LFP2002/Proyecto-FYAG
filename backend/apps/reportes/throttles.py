from rest_framework.throttling import UserRateThrottle


class ExportacionThrottle(UserRateThrottle):
    scope = "exportaciones_reportes"
    rate = "5/min"
