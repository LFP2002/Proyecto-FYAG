"""Permisos por fuente, no herencia implícita de un permiso de módulo."""
from rest_framework.permissions import BasePermission
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied, ValidationError

from apps.usuarios.models import Usuario
from .adapters import FUENTES

OBRAS = {name for name, f in FUENTES.items() if f.modulo == "OBRAS"}
POR_ROL = {
    "GERENCIA": OBRAS | {"PRESUPUESTO_EVENTO", "FINANZAS_EVENTO"},
    # El historial de categorías está reservado a Gerencia en el origen.
    "SUPERVISOR_OBRAS": OBRAS - {"CATEGORIA_SERVICIO_EVENTO"},
    "ADMINISTRATIVO_FINANZAS": {"FINANZAS_EVENTO"},
    "ADMINISTRADOR_TI": {"USUARIO_EVENTO"},
}


class PuedeLeerAuditoria(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_active and request.user.rol in POR_ROL)


def revalidar(actor):
    actual = Usuario.objects.only("id", "rol", "is_active", "sesion_version").filter(pk=actor.pk).first()
    if actual is None or not actual.is_active or actual.sesion_version != actor.sesion_version:
        raise AuthenticationFailed("Sesión no disponible.")
    if actual.rol not in POR_ROL:
        raise PermissionDenied("No tiene acceso a auditoría global.")
    return actual


def seleccionar(actor, filtros):
    permitidas = POR_ROL[actor.rol]
    modulo = filtros.get("modulo")
    fuente = filtros.get("fuente")
    if modulo and modulo not in {FUENTES[n].modulo for n in permitidas}:
        raise PermissionDenied("Módulo no autorizado.")
    if fuente and fuente not in permitidas:
        raise PermissionDenied("Fuente no autorizada.")
    if fuente and modulo and FUENTES[fuente].modulo != modulo:
        raise ValidationError({"fuente": "La fuente no corresponde al módulo."})
    candidatas = [FUENTES[n] for n in sorted(permitidas) if (not modulo or FUENTES[n].modulo == modulo) and (not fuente or n == fuente)]
    tipos_autorizados = {t for f in candidatas for t in f.tipos}
    recurso = filtros.get("recurso_tipo")
    if recurso:
        compatibles = [f for f in candidatas if recurso in dict(f.recursos)]
        if (fuente or modulo) and not compatibles:
            raise ValidationError({"recurso_tipo": "Recurso incompatible con la fuente o módulo."})
        candidatas = compatibles
    tipo = filtros.get("tipo")
    if tipo and tipo not in ({t for f in candidatas for t in f.tipos} if candidatas else tipos_autorizados):
        raise ValidationError({"tipo": "Tipo de evento no permitido en las fuentes seleccionadas."})
    return candidatas
