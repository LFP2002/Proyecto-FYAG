from rest_framework.permissions import BasePermission

from apps.usuarios.models import Usuario


class PuedeGestionarClientes(BasePermission):
    message = "No tiene permiso para gestionar clientes."

    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.rol in (
            Usuario.Rol.GERENCIA,
            Usuario.Rol.ADMINISTRATIVO_FINANZAS,
        )
