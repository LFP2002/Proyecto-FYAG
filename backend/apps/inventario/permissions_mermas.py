from rest_framework.exceptions import AuthenticationFailed, PermissionDenied
from rest_framework.permissions import BasePermission, SAFE_METHODS

from apps.usuarios.acceso import sesion_operativa
from apps.usuarios.configuracion_c2 import relaciones_seguridad
from apps.usuarios.models import Usuario


LECTORES = {'BODEGA': {'BODEGUERO', 'ADMINISTRATIVO_FINANZAS', 'GERENCIA'},
            'OBRA': {'TECNICO', 'SUPERVISOR_OBRAS', 'GERENCIA'}}
ESCRITORES = {'BODEGA': {'crear': 'BODEGUERO', 'decidir': 'ADMINISTRATIVO_FINANZAS'},
              'OBRA': {'crear': 'TECNICO', 'decidir': 'SUPERVISOR_OBRAS'}}


def revalidar(actor, ambito, accion='leer'):
    if not isinstance(actor, Usuario) or not actor.pk or actor._state.adding:
        raise AuthenticationFailed('Sesión no disponible.')
    actual = Usuario.objects.select_related(*relaciones_seguridad()).filter(pk=actor.pk).first()
    if actual is None or not actual.is_active or actual.sesion_version != actor.sesion_version or not sesion_operativa(actual):
        raise AuthenticationFailed('Sesión no disponible.')
    roles = LECTORES[ambito] if accion == 'leer' else {ESCRITORES[ambito][accion]}
    if actual.rol not in roles:
        raise PermissionDenied('Sin permiso para esta operación de mermas.')
    return actual


class PermisoMermas(BasePermission):
    def has_permission(self, request, view):
        accion = 'leer' if request.method in SAFE_METHODS else view.accion_escritura
        request.user = revalidar(request.user, view.ambito, accion)
        return True
