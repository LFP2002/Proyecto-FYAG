"""Matriz de acceso por rol/acción para Obras 004A. Sin bypass por is_superuser."""

from rest_framework.permissions import BasePermission

from apps.usuarios.models import Usuario


G = Usuario.Rol.GERENCIA
S = Usuario.Rol.SUPERVISOR_OBRAS
AF = Usuario.Rol.ADMINISTRATIVO_FINANZAS
T = Usuario.Rol.TECNICO


class PuedeOperarObras(BasePermission):
    message = "No tiene permiso para realizar esta operación de Obras."

    acciones_supervisor = frozenset({
        "create", "partial_update", "cambiar_tecnico", "iniciar", "suspender",
        "reanudar", "presupuestos_disponibles", "tecnicos_disponibles",
    })

    def has_permission(self, request, view):
        usuario = request.user
        if not usuario.is_authenticated or not usuario.is_active:
            return False
        accion = getattr(view, "action", None)
        # OPTIONS debe respetar también el ámbito de la subruta.
        if accion == "metadata":
            accion = view.action_map.get("get") or view.action_map.get("post")
        if accion == "mis_obras":
            return usuario.rol == T
        if accion in {"iniciar_turno", "finalizar_turno", "subsanar_turno"}:
            return usuario.rol == T
        if accion in {"revisar_turno", "corregir_turno", "cerrar_administrativamente"}:
            return usuario.rol == S
        if accion in {"turnos", "foto_turno"}:
            return usuario.rol in {G, S, T}
        if accion == "participantes":
            return usuario.rol == S if request.method == "POST" else usuario.rol in {G, S}
        if accion == "desasignar_participante":
            return usuario.rol == S
        if accion == "historial_participantes":
            return usuario.rol in {G, S}
        if accion in self.acciones_supervisor:
            return usuario.rol == S
        if accion == "historial":
            return usuario.rol in {G, S}
        if accion in {"list", "retrieve", "metadata", None}:
            return usuario.rol in {G, S, AF, T}
        return False


class PuedeOperarCategorias(BasePermission):
    message = "No tiene permiso para gestionar categorías de servicios."

    def has_permission(self, request, view):
        usuario = request.user
        if not usuario.is_authenticated or not usuario.is_active:
            return False
        accion = getattr(view, "action", None)
        if accion in {"create", "partial_update", "activar", "desactivar", "historial"}:
            return usuario.rol == G
        if accion in {"list", "retrieve", "metadata", None}:
            return usuario.rol in {G, S}
        return False
