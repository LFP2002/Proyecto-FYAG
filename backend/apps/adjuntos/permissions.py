from rest_framework.exceptions import AuthenticationFailed, NotFound, PermissionDenied
from rest_framework.permissions import BasePermission
from rest_framework_simplejwt.exceptions import TokenError

from apps.usuarios.authentication import validar_sesion
from apps.usuarios.models import Usuario
from apps.obras.models import ObraParticipante
from apps.documentos.validaciones import entero_ascii


def actor_actual(actor, token=None):
    actual = Usuario.objects.filter(pk=actor.pk).first()
    if actual is None or not actual.is_active or actual.sesion_version != actor.sesion_version:
        raise AuthenticationFailed("Sesión no disponible.")
    if token is not None:
        try:
            token.check_exp()
        except TokenError:
            raise AuthenticationFailed("Sesión no disponible.") from None
        validar_sesion(token, actual)
    if actual.rol not in {"GERENCIA", "SUPERVISOR_OBRAS", "ADMINISTRATIVO_FINANZAS", "TECNICO"}:
        raise PermissionDenied("Sin acceso a adjuntos de negocio.")
    return actual


def autorizar_tipo(actor, tipo, escribir=False):
    roles = ({"ADMINISTRATIVO_FINANZAS"} if escribir else {"GERENCIA", "ADMINISTRATIVO_FINANZAS"}) if tipo == "RESPALDO_FACTURA" else ({"SUPERVISOR_OBRAS", "TECNICO"} if escribir else {"GERENCIA", "SUPERVISOR_OBRAS", "TECNICO"})
    if actor.rol not in roles:
        raise PermissionDenied("Sin acceso a este tipo documental.")


def miembro(actor, obra_id):
    if actor.rol == "TECNICO" and not ObraParticipante.objects.filter(obra_id=obra_id, tecnico=actor, activo=True).exists():
        raise NotFound("Recurso no disponible.")


class PuedeOperarAdjuntos(BasePermission):
    def has_permission(self, request, view):
        request.user = actor_actual(request.user, request.auth)
        tipo = view.kwargs.get("tipo")
        if tipo:
            autorizar_tipo(request.user, tipo, request.method == "POST")
            if request.method in {"HEAD", "OPTIONS"}:
                from .services import parent
                parent(tipo, entero_ascii(view.kwargs["id"], "id"), request.user)
        elif request.method == "PATCH" and request.user.rol == "GERENCIA":
            raise PermissionDenied("Gerencia tiene acceso de lectura.")
        elif "id" in view.kwargs:
            from .services import autorizado
            autorizado(request.user, entero_ascii(view.kwargs["id"], "id"), request.auth,
                editar=request.method == "PATCH")
        return True
