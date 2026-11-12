from rest_framework.exceptions import AuthenticationFailed, PermissionDenied
from rest_framework.permissions import BasePermission

from apps.usuarios.models import Usuario


def revalidar(actor):
    actual = Usuario.objects.only("id", "rol", "is_active", "sesion_version").filter(pk=actor.pk).first()
    if actual is None or not actual.is_active or actual.sesion_version != actor.sesion_version:
        raise AuthenticationFailed("Sesión no disponible.")
    if actual.rol != "GERENCIA":
        raise PermissionDenied("El dashboard es exclusivo de Gerencia.")
    return actual


class PuedeLeerDashboard(BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        request.user = revalidar(request.user)
        return True
