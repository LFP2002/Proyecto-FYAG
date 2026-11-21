"""Motor puro C1, sin Django ORM, contraseñas, HTTP ni autorización TI."""
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from enum import Enum
from types import MappingProxyType


POLITICA_RATIFICADA = MappingProxyType({
    "intentos": 5, "ventana_segundos": 900, "duraciones_segundos": (900, 3600, 14400),
    "reincidencia_segundos": 86400, "ciclo_ti": 4,
})
VENTANA = timedelta(seconds=POLITICA_RATIFICADA["ventana_segundos"])
REINCIDENCIA = timedelta(seconds=POLITICA_RATIFICADA["reincidencia_segundos"])
DURACIONES = tuple(timedelta(seconds=s) for s in POLITICA_RATIFICADA["duraciones_segundos"])


def validar_politica(config):
    # Los constraints SQL de 0008 reflejan esta versión ratificada de la política.
    # Cambiar umbrales exige revisión y migración, no una variable de entorno.
    if (type(config) is not dict or config != POLITICA_RATIFICADA
        or any(type(config.get(k)) is not int for k in ("intentos", "ventana_segundos", "reincidencia_segundos", "ciclo_ti"))
        or type(config.get("duraciones_segundos")) is not tuple
        or any(type(v) is not int for v in config.get("duraciones_segundos", ()))):
        raise ValueError("Configuración C1 ausente o distinta de la política ratificada.")


class Senal(Enum):
    CLAVE_INCORRECTA = "CLAVE_INCORRECTA"
    CLAVE_CORRECTA = "CLAVE_CORRECTA"
    REVISAR_VENCIMIENTO = "REVISAR_VENCIMIENTO"
    SIN_VERIFICACION = "SIN_VERIFICACION"


@dataclass(frozen=True)
class EstadoPolitica:
    estado: str = "NORMAL"
    fallos: tuple = ()
    ciclos: tuple = ()
    bloqueo_inicio: datetime | None = None
    bloqueado_hasta: datetime | None = None


@dataclass(frozen=True)
class Transicion:
    estado: EstadoPolitica
    # (tipo, cantidad_fallos); la persistencia fija actor/versión/reloj.
    eventos: tuple = ()


def consciente(value):
    return isinstance(value, datetime) and value.utcoffset() is not None


def validar_estado(state, ahora):
    if not isinstance(state, EstadoPolitica) or not consciente(ahora):
        raise ValueError("Estado/reloj C1 inválido.")
    for values, maximum in ((state.fallos, 4), (state.ciclos, 4)):
        if (type(values) is not tuple or len(values) > maximum
            or any(not consciente(t) or t > ahora for t in values)
            or tuple(sorted(values)) != values):
            raise ValueError("Secuencia temporal C1 inválida.")
    if state.fallos and state.fallos[-1] >= state.fallos[0] + VENTANA:
        raise ValueError("Ventana C1 incoherente.")
    if state.estado == "NORMAL":
        valid = state.bloqueo_inicio is None and state.bloqueado_hasta is None and len(state.ciclos) <= 3
    elif state.estado in ("BLOQUEO_TEMPORAL", "REQUIERE_TI"):
        valid = (not state.fallos and bool(state.ciclos) and state.bloqueo_inicio == state.ciclos[-1])
        if state.estado == "REQUIERE_TI":
            valid = valid and len(state.ciclos) == 4 and state.bloqueado_hasta is None
        else:
            valid = (valid and 1 <= len(state.ciclos) <= 3 and consciente(state.bloqueado_hasta)
                     and state.bloqueado_hasta == state.bloqueo_inicio + DURACIONES[len(state.ciclos) - 1])
    else:
        valid = False
    if not valid:
        raise ValueError("Estado de acceso C1 incoherente.")


def calcular_transicion(state, senal, ahora):
    """Ventanas móviles abiertas a la izquierda; ningún reloj viene del cliente."""
    # Aritmética absoluta también cuando un test/caller usa ZoneInfo con DST.
    # No sumar minutos de reloj de pared al cruzar el cambio de hora chileno.
    if consciente(ahora) and isinstance(state, EstadoPolitica):
        if (type(state.fallos) is tuple and type(state.ciclos) is tuple
            and all(consciente(t) for t in state.fallos + state.ciclos)):
            state = replace(state, fallos=tuple(t.astimezone(timezone.utc) for t in state.fallos),
                            ciclos=tuple(t.astimezone(timezone.utc) for t in state.ciclos),
                            bloqueo_inicio=state.bloqueo_inicio.astimezone(timezone.utc) if consciente(state.bloqueo_inicio) else state.bloqueo_inicio,
                            bloqueado_hasta=state.bloqueado_hasta.astimezone(timezone.utc) if consciente(state.bloqueado_hasta) else state.bloqueado_hasta)
        ahora = ahora.astimezone(timezone.utc)
    validar_estado(state, ahora)
    if not isinstance(senal, Senal):
        raise ValueError("Se requiere una señal interna de verificación tipada.")
    if senal == Senal.SIN_VERIFICACION or state.estado == "REQUIERE_TI":
        return Transicion(state)
    eventos = ()
    if state.estado == "BLOQUEO_TEMPORAL":
        if ahora < state.bloqueado_hasta:
            return Transicion(state)  # Ni aciertos ni fallos extienden el bloqueo.
        state = replace(state, estado="NORMAL", bloqueo_inicio=None, bloqueado_hasta=None)
        eventos = (("EXPIRACION", 0),)
    state = replace(state, fallos=tuple(t for t in state.fallos if t > ahora - VENTANA),
                    ciclos=tuple(t for t in state.ciclos if t > ahora - REINCIDENCIA))
    if senal == Senal.CLAVE_CORRECTA:
        if state.fallos:
            eventos += (("REINICIO_RACHA", len(state.fallos)),)
        return Transicion(replace(state, fallos=()), eventos)
    if senal == Senal.REVISAR_VENCIMIENTO:
        return Transicion(state, eventos)
    fallos = state.fallos + (ahora,)
    if len(fallos) < POLITICA_RATIFICADA["intentos"]:
        return Transicion(replace(state, fallos=fallos), eventos)
    ciclos = state.ciclos + (ahora,)
    requiere_ti = len(ciclos) == POLITICA_RATIFICADA["ciclo_ti"]
    return Transicion(EstadoPolitica(
        estado="REQUIERE_TI" if requiere_ti else "BLOQUEO_TEMPORAL", ciclos=ciclos,
        bloqueo_inicio=ahora,
        bloqueado_hasta=None if requiere_ti else ahora + DURACIONES[len(ciclos) - 1],
    ), eventos + (("BLOQUEO_TI" if requiere_ti else "BLOQUEO_TEMPORAL", 5),))
