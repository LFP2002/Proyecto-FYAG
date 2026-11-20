"""No volcar datos de autenticación en informes de errores Django.

Los logs de aplicación no registran cuerpos/respuestas. En las rutas sensibles,
el reporter omite todos los locales, incluso de frames DRF sin decorador propio.
No habilita DEBUG ni reemplaza controles operacionales de proxy/APM.
"""
import re
import logging

from django.views.debug import ExceptionReporter, SafeExceptionReporterFilter


def ruta_sensible(request):
    if request is None:
        return False
    path = request.path
    return (path.startswith("/api/auth/")
            or (request.method in {"POST", "PATCH"} and path.startswith("/api/usuarios/")))


class CredencialesExceptionFilter(SafeExceptionReporterFilter):
    hidden_settings = re.compile(
        r"API|AUTH|TOKEN|KEY|SECRET|PASS|SIGNATURE|HTTP_COOKIE|CLAVE|CREDENCIAL|DESAFIO|REFRESH",
        flags=re.I,
    )

    def get_traceback_frame_variables(self, request, tb_frame):
        if ruta_sensible(request):
            return [(name, self.cleansed_substitute) for name in tb_frame.f_locals]
        return super().get_traceback_frame_variables(request, tb_frame)

    def get_post_parameters(self, request):
        if ruta_sensible(request):
            return {name: self.cleansed_substitute for name in request.POST}
        return super().get_post_parameters(request)


class CredencialesExceptionReporter(ExceptionReporter):
    def get_traceback_data(self):
        data = super().get_traceback_data()
        if ruta_sensible(self.request):
            data["exception_value"] = "Error interno en operación sensible; detalles omitidos."
            data["exception_notes"] = []
            for frame in data.get("frames", []):
                if frame.get("exc_cause"):
                    frame["exc_cause"] = "Causa sensible omitida."
        return data


class CredencialesLogFilter(logging.Filter):
    def filter(self, record):
        if ruta_sensible(getattr(record, "request", None)) and record.exc_info:
            # Django logger puede imprimir exc_info sin pasar por ExceptionReporter.
            record.msg = "Error interno en operación sensible; detalles omitidos."
            record.args = ()
            record.exc_info = (Exception, Exception("Detalles sensibles omitidos."), record.exc_info[2])
            record.exc_text = None
        return True
