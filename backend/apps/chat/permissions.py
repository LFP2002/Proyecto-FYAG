from django.utils.crypto import constant_time_compare
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import BasePermission

from apps.usuarios.acceso import sesion_operativa
from apps.usuarios.configuracion_c2 import relaciones_seguridad
from apps.usuarios.models import Usuario


def revalidar(actor):
    if not isinstance(actor, Usuario) or not actor.pk or actor._state.adding:
        raise AuthenticationFailed('Sesión no disponible.')
    actual = Usuario.objects.select_related(*relaciones_seguridad()).filter(pk=actor.pk).first()
    if (actual is None or not actual.is_active or actual.rol not in Usuario.Rol.values
        or actual.rol != actor.rol or actual.sesion_version != actor.sesion_version
        or not constant_time_compare(actual.password, actor.password) or not sesion_operativa(actual)):
        raise AuthenticationFailed('Sesión no disponible.')
    return actual


class PermisoChat(BasePermission):
    def has_permission(self, request, view):
        revalidar(request.user)
        return True
