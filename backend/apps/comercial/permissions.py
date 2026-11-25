from rest_framework.permissions import BasePermission
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied

from apps.usuarios.models import Usuario


def revalidar_escritura(usuario):
    """020A: actor persistido AF, con sesión 018 vigente; no privilegios Django."""
    from apps.usuarios.configuracion_c2 import relaciones_seguridad
    from apps.usuarios.acceso import sesion_operativa
    if not isinstance(usuario, Usuario) or not usuario.pk or usuario._state.adding:
        raise PermissionDenied("Operación comercial no autorizada.")
    actual = Usuario.objects.select_related(*relaciones_seguridad()).filter(
        pk=usuario.pk,
    ).first()
    if (
        actual is None or not actual.is_active
        or actual.sesion_version != usuario.sesion_version
        or not sesion_operativa(actual)
    ):
        raise AuthenticationFailed("Sesión no disponible.")
    if actual.rol != Usuario.Rol.ADMINISTRATIVO_FINANZAS:
        raise PermissionDenied("Operación comercial exclusiva de Finanzas.")
    return actual


class PuedeGestionarClientes(BasePermission):
    message = "No tiene permiso para gestionar clientes."

    def has_permission(self, request, view):
        return request.user.is_authenticated and (
            request.user.rol == Usuario.Rol.ADMINISTRATIVO_FINANZAS
            or (
                request.method in {"GET", "HEAD", "OPTIONS"}
                and request.user.rol == Usuario.Rol.GERENCIA
            )
        )


class PuedeOperarPresupuestos(BasePermission):
    message = "No tiene permiso para realizar esta operación de presupuestos."

    acciones_comerciales = frozenset({
        "create", "partial_update", "items", "item_detalle",
        "enviar_finanzas", "aprobar_finanzas", "rechazar_finanzas",
        "enviar_cliente", "registrar_aprobacion_cliente",
        "registrar_rechazo_cliente", "anular", "crear_revision",
    })
    acciones_supervisor = frozenset({
        'create', 'partial_update', 'items', 'item_detalle',
        'enviar_finanzas', 'crear_revision',
    })

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        accion = getattr(view, "action", None)
        acciones_ruta = set(getattr(view, 'action_map', {}).values())
        if acciones_ruta & {"enviar_gerencia", "aprobar_gerencia", "rechazar_gerencia"}:
            return False  # Rutas retiradas: 403 uniforme antes de recurso/body.
        from .permissions_presupuestos import revalidar_presupuestos
        actual = revalidar_presupuestos(request.user)
        rol = actual.rol
        if acciones_ruta & {'clientes_elegibles', 'materiales_elegibles'}:
            return rol in {Usuario.Rol.ADMINISTRATIVO_FINANZAS, Usuario.Rol.SUPERVISOR_OBRAS}
        if accion in self.acciones_comerciales:
            return (rol == Usuario.Rol.ADMINISTRATIVO_FINANZAS or
                    rol == Usuario.Rol.SUPERVISOR_OBRAS and accion in self.acciones_supervisor)
        # Lectura, OPTIONS y métodos sin handler: estos últimos llegarán a 405.
        return accion in {None, "metadata", "list", "retrieve", "historial"}
