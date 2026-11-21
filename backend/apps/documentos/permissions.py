from rest_framework.exceptions import AuthenticationFailed, PermissionDenied
from rest_framework.permissions import BasePermission

from apps.usuarios.models import Usuario
from apps.usuarios.authentication import validar_sesion
from apps.usuarios.credenciales import es_personal


def revalidar(usuario, token=None):
    from apps.usuarios.configuracion_c2 import relaciones_seguridad
    from apps.usuarios.acceso import acceso_permitido
    actual = Usuario.objects.select_related(*relaciones_seguridad()).filter(pk=usuario.pk).first()
    if actual is None or not actual.is_active or actual.sesion_version != usuario.sesion_version:
        raise AuthenticationFailed("Sesión no disponible.")
    if not es_personal(actual) or not acceso_permitido(actual):
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
