"""Lectura compartida de estado operativo; no muta contadores en JWT/permisos."""
from django.utils import timezone

from .configuracion_c2 import habilitado
from .models import EstadoAcceso, Usuario
from .politica_bloqueos import EstadoPolitica, VENTANA, validar_estado


def estado_acceso(user, *, ahora=None):
    relation = Usuario._meta.get_field("estado_acceso")
    state = relation.get_cached_value(user) if relation.is_cached(user) else EstadoAcceso.objects.filter(usuario_id=user.pk).first()
    now = ahora or timezone.now()
    try:
        if (state is None or state.usuario_id != user.pk or state.version < 1
            or now < state.actualizado_en or state.actualizado_en < state.creado_en
            or state.intentos != len(state.fallos_en)
            or state.ventana_inicio != (state.fallos_en[0] if state.fallos_en else None)
            or state.ventana_hasta != (state.ventana_inicio + VENTANA if state.fallos_en else None)):
            return "NO_DISPONIBLE"
        validar_estado(EstadoPolitica(state.estado, tuple(state.fallos_en), tuple(state.ciclos_en), state.bloqueo_inicio, state.bloqueado_hasta), now)
    except (TypeError, ValueError, AttributeError):
        return "NO_DISPONIBLE"
    if state.estado == "BLOQUEO_TEMPORAL" and now >= state.bloqueado_hasta:
        return "NORMAL"  # Caducidad efectiva; no escribe desde GET/JWT.
    return state.estado


def acceso_permitido(user):
    return not habilitado() or estado_acceso(user) == "NORMAL"


def sesion_operativa(user):
    from .credenciales import es_personal
    return es_personal(user) and acceso_permitido(user)
