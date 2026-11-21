from rest_framework.exceptions import AuthenticationFailed, PermissionDenied
from rest_framework.permissions import BasePermission, SAFE_METHODS

from apps.usuarios.acceso import sesion_operativa
from apps.usuarios.configuracion_c2 import relaciones_seguridad
from apps.usuarios.models import Usuario


def revalidar(actor, accion='leer'):
    if not isinstance(actor, Usuario) or not actor.pk or actor._state.adding:
        raise AuthenticationFailed('Sesión no disponible.')
    actual = Usuario.objects.select_related(*relaciones_seguridad()).filter(pk=actor.pk).first()
    if actual is None or not actual.is_active or actual.sesion_version != actor.sesion_version or not sesion_operativa(actual):
        raise AuthenticationFailed('Sesión no disponible.')
    roles = {'crear': {'TECNICO'}, 'decidir': {'SUPERVISOR_OBRAS'}, 'leer': {'TECNICO', 'SUPERVISOR_OBRAS', 'GERENCIA'}}
    if actual.rol not in roles[accion]:
        raise PermissionDenied('Sin permiso para esta operación de solicitudes.')
    return actual


class PermisoSolicitudes(BasePermission):
    def has_permission(self, request, view):
        accion = 'leer' if request.method in SAFE_METHODS else view.accion_escritura
        request.user = revalidar(request.user, accion)
        return True
