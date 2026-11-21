from django.utils import timezone

from .acceso import estado_acceso
from .models import EstadoAcceso, RecuperacionAcceso, Usuario
from .services_usuarios import ConflictoUsuario


def bloquear_estado_recuperacion(user):
    """Caller ya posee mutex/usuarios/credencial. Nunca reconstruye estado."""
    state = EstadoAcceso.objects.select_for_update().filter(usuario=user).first()
    Usuario._meta.get_field("estado_acceso").set_cached_value(user, state)
    if estado_acceso(user) == "NO_DISPONIBLE" or state.version >= 9223372036854775807:
        raise ConflictoUsuario("seguridad_no_disponible", "Estado de seguridad no disponible; requiere revisión autorizada.")
    return state


def confirmar_recuperacion(user, actor, state, event):
    previous, version = state.estado, state.version
    state.estado = "NORMAL"
    state.intentos = 0
    state.fallos_en = state.ciclos_en = []
    state.ventana_inicio = state.ventana_hasta = state.bloqueo_inicio = state.bloqueado_hasta = None
    state.version += 1
    state.actualizado_en = timezone.now()
    state.save()
    RecuperacionAcceso.objects.create(usuario=user, actor=actor, reemision=event,
        estado_anterior=previous, version_anterior=version, version_nueva=state.version, creado_en=state.actualizado_en)
