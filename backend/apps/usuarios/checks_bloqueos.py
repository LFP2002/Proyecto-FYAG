from django.core.checks import Error, register
from django.core.exceptions import ImproperlyConfigured

from .bloqueos import validar_configuracion


@register()
def comprobar_configuracion_bloqueos(app_configs, **kwargs):
    try:
        validar_configuracion()
        from .configuracion_c2 import habilitado
        habilitado()
    except ImproperlyConfigured as exc:
        return [Error(str(exc), id="usuarios.E018")]
    return []
