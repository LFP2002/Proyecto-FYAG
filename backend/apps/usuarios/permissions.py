from rest_framework.permissions import BasePermission

from .models import Usuario


class EsGerenciaActiva(BasePermission):
    message = "No tiene permiso para administrar cuentas."

    def has_permission(self, request, view):
        user = request.user
        return bool(user and user.is_authenticated and Usuario.objects.filter(
            pk=user.pk, is_active=True, rol=Usuario.Rol.GERENCIA,
        ).exists())
