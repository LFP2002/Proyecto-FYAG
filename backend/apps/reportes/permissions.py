from rest_framework.exceptions import AuthenticationFailed, NotFound, PermissionDenied
from rest_framework.permissions import BasePermission

from apps.usuarios.models import Usuario
from .catalogo import TIPOS

POR_ROL = {"GERENCIA": TIPOS, "ADMINISTRATIVO_FINANZAS": ("cobranzas",)}


def revalidar(actor, tipo=None):
    actual = Usuario.objects.only("id", "rol", "is_active", "sesion_version").filter(pk=actor.pk).first()
    if actual is None or not actual.is_active or actual.sesion_version != actor.sesion_version:
        raise AuthenticationFailed("Sesión no disponible.")
    if actual.rol not in POR_ROL:
        raise PermissionDenied("No tiene acceso a Reportes.")
    if tipo is not None:
        if tipo not in TIPOS:
            raise NotFound("Tipo de reporte no encontrado.")
        if tipo not in POR_ROL[actual.rol]:
            raise PermissionDenied("No tiene acceso a este reporte.")
    return actual


class PuedeLeerReportes(BasePermission):
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        request.user = revalidar(request.user, view.kwargs.get("tipo"))
        return True
