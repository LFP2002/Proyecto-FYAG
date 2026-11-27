from django.utils.crypto import constant_time_compare
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied
from rest_framework.permissions import BasePermission

from apps.usuarios.acceso import sesion_operativa
from apps.usuarios.authentication import validar_sesion
from apps.usuarios.configuracion_c2 import relaciones_seguridad
from apps.usuarios.models import Usuario


LECTORES = {"BODEGUERO", "GERENCIA", "SUPERVISOR_OBRAS", "ADMINISTRATIVO_FINANZAS"}


def revalidar(actor, *, escritura=False, token=None):
    if not isinstance(actor, Usuario) or not actor.pk:
        raise AuthenticationFailed("Sesión no disponible.")
    actual = Usuario.objects.select_related(*relaciones_seguridad()).filter(pk=actor.pk).first()
    if (actual is None or not actual.is_active or actual.sesion_version != actor.sesion_version
        or not constant_time_compare(actual.password, actor.password) or not sesion_operativa(actual)):
        raise AuthenticationFailed("Sesión no disponible.")
    if token is not None:
        validar_sesion(token, actual)
    if actual.rol != actor.rol or actual.rol not in ({"BODEGUERO"} if escritura else LECTORES):
        raise PermissionDenied("Sin permiso para esta operación de inventario.")
    return actual


class PuedeOperarInventario(BasePermission):
    def has_permission(self, request, view):
        request.user = revalidar(request.user, escritura=request.method not in {"GET", "HEAD", "OPTIONS"}, token=request.auth)
        return True
