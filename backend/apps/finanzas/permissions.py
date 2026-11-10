from rest_framework.permissions import BasePermission

from apps.usuarios.models import Usuario


class PermisoFinanciero(BasePermission):
    def has_permission(self, request, view):
        roles = [Usuario.Rol.ADMINISTRATIVO_FINANZAS]
        if request.method in {"GET", "HEAD", "OPTIONS"} and not getattr(view, "solo_finanzas", False):
            roles.append(Usuario.Rol.GERENCIA)
        return bool(request.user and request.user.is_authenticated and Usuario.objects.filter(
            pk=request.user.pk, is_active=True, rol__in=roles,
        ).exists())
