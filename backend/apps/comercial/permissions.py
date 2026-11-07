from rest_framework.permissions import BasePermission

from apps.usuarios.models import Usuario


class PuedeGestionarClientes(BasePermission):
    message = "No tiene permiso para gestionar clientes."

    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.rol in (
            Usuario.Rol.GERENCIA,
            Usuario.Rol.ADMINISTRATIVO_FINANZAS,
        )


class PuedeOperarPresupuestos(BasePermission):
    message = "No tiene permiso para realizar esta operación de presupuestos."

    acciones_gerencia = frozenset({"aprobar_gerencia", "rechazar_gerencia"})
    acciones_comerciales = frozenset({
        "create", "partial_update", "items", "item_detalle",
        "enviar_gerencia", "enviar_cliente", "registrar_aprobacion_cliente",
        "registrar_rechazo_cliente", "anular", "crear_revision",
    })

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        rol = request.user.rol
        if rol not in (
            Usuario.Rol.GERENCIA, Usuario.Rol.ADMINISTRATIVO_FINANZAS,
        ):
            return False
        accion = getattr(view, "action", None)
        if accion in self.acciones_gerencia:
            return rol == Usuario.Rol.GERENCIA
        if accion in self.acciones_comerciales:
            return rol == Usuario.Rol.ADMINISTRATIVO_FINANZAS
        # Lectura, OPTIONS y métodos sin handler: estos últimos llegarán a 405.
        return accion in {None, "metadata", "list", "retrieve", "historial"}
