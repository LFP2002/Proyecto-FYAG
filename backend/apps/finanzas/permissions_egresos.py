"""021: autorización persistida, también para callers de dominio sin HTTP."""
from django.utils.crypto import constant_time_compare
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied
from rest_framework.permissions import BasePermission, SAFE_METHODS

from apps.usuarios.acceso import sesion_operativa
from apps.usuarios.configuracion_c2 import relaciones_seguridad
from apps.usuarios.models import Usuario


def revalidar(actor, *, escritura=False):
    if not isinstance(actor, Usuario) or actor.pk is None or actor._state.adding:
        raise PermissionDenied("Operación financiera no autorizada.")
    actual = Usuario.objects.select_related(*relaciones_seguridad()).filter(pk=actor.pk).first()
    if (actual is None or not actual.is_active or actual.sesion_version != actor.sesion_version
        or not constant_time_compare(actual.password, actor.password) or not sesion_operativa(actual)):
        raise AuthenticationFailed("Sesión no disponible.")
    roles = {Usuario.Rol.ADMINISTRATIVO_FINANZAS}
    if not escritura:
        roles.add(Usuario.Rol.GERENCIA)
    if actual.rol not in roles or actual.rol != actor.rol:
        raise PermissionDenied("Operación financiera no autorizada.")
    return actual


class PermisoEgresos(BasePermission):
    def has_permission(self, request, view):
        request.user = revalidar(request.user, escritura=request.method not in SAFE_METHODS)
        return True
