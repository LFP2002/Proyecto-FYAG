from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission, SAFE_METHODS

from .permissions import revalidar as validar_sesion

ESCRITORES = {
    'AUTORIZACION_ENTREGA': 'SUPERVISOR_OBRAS', 'AUTORIZACION_DEVOLUCION': 'SUPERVISOR_OBRAS',
    'ENTREGA': 'BODEGUERO', 'DEVOLUCION': 'BODEGUERO',
    'VALORIZACION': 'ADMINISTRATIVO_FINANZAS', 'REGULARIZACION': 'ADMINISTRATIVO_FINANZAS',
}


def revalidar(actor, tipo, *, escritura=False):
    actual = validar_sesion(actor)
    roles = {ESCRITORES[tipo]} if escritura else (
        {'ADMINISTRATIVO_FINANZAS', 'GERENCIA'} if tipo in {'VALORIZACION', 'REGULARIZACION'}
        else {'BODEGUERO', 'SUPERVISOR_OBRAS', 'GERENCIA'})
    if actual.rol not in roles:
        raise PermissionDenied('Sin permiso para esta operación de materiales.')
    return actual


class PermisoMateriales(BasePermission):
    def has_permission(self, request, view):
        request.user = revalidar(request.user, view.tipo, escritura=request.method not in SAFE_METHODS)
        return True
