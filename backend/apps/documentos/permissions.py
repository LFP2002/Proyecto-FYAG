from rest_framework.exceptions import AuthenticationFailed, PermissionDenied
from rest_framework.permissions import BasePermission

from apps.usuarios.models import Usuario
from apps.usuarios.authentication import validar_sesion


def revalidar(usuario, token=None):
    actual = Usuario.objects.filter(pk=usuario.pk).first()
    if actual is None or not actual.is_active or actual.sesion_version != usuario.sesion_version:
        raise AuthenticationFailed("Sesión no disponible.")
    if token is not None:
        validar_sesion(token, actual)
    if actual.rol not in ("GERENCIA", "SUPERVISOR_OBRAS"):
        raise PermissionDenied("Sin acceso a metadatos documentales.")
    return actual


class PuedeOperarDocumentos(BasePermission):
    def has_permission(self, request, view):
        request.user = revalidar(request.user, request.auth)
        return True
