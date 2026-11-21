from rest_framework.permissions import BasePermission
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied

from apps.usuarios.models import Usuario

ROLES = {"GERENCIA", "SUPERVISOR_OBRAS", "ADMINISTRATIVO_FINANZAS"}


def revalidar(actor, *, escritura=False):
    from apps.usuarios.acceso import sesion_operativa
    if not isinstance(actor, Usuario) or not actor.pk:
        raise PermissionDenied("Actor no autorizado.")
    actual = Usuario.objects.only("id", "rol", "is_active", "sesion_version").filter(pk=actor.pk).first()
    if actual is None or not actual.is_active or actual.sesion_version != actor.sesion_version or not sesion_operativa(actual):
        raise AuthenticationFailed("Sesión no disponible.")
    if actual.rol not in ROLES:
        raise PermissionDenied("No tiene acceso a alertas de negocio.")
    if escritura and actual.rol == "GERENCIA":
        raise PermissionDenied("Gerencia solo puede consultar alertas.")
    return actual


class PuedeLeerAlertas(BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        request.user = revalidar(request.user, escritura=request.method == "POST")
        return True
