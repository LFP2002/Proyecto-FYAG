"""Adaptador SQL C1, únicamente simulación opt-in; NO integrado a autenticación."""
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.utils import timezone

from .credenciales import estado_coherente
from .models import EstadoAcceso, EventoAcceso, SeguridadCredencial, Usuario
from .politica_bloqueos import EstadoPolitica, Senal, VENTANA, calcular_transicion, validar_politica


class EstadoAccesoNoDisponible(Exception):
    """No hay reconstrucción implícita ni traducción HTTP en C1."""


def validar_configuracion():
    try:
        validar_politica(getattr(settings, "BLOQUEOS_C1_POLITICA", None))
    except ValueError as exc:
        raise ImproperlyConfigured(str(exc)) from None
    if type(getattr(settings, "BLOQUEOS_C1_SIMULACION_HABILITADA", None)) is not bool:
        raise ImproperlyConfigured("La habilitación C1 debe ser booleana y explícita.")


def registrar_verificacion(usuario_id, senal):
    """Solo señal de resultado, jamás contraseña/email/IP/request/token.

    C1 no verifica claves ni acredita esta señal: futura C2 deberá comprobarlas
    fuera del lock y revalidar hash/versión al adquirirlo. No llamar desde HTTP.
    Sin señal comprobada no se consulta ni modifica ninguna fila.
    """
    validar_configuracion()
    if not settings.BLOQUEOS_C1_SIMULACION_HABILITADA:
        raise ImproperlyConfigured("Motor C1 aislado: escrituras de simulación deshabilitadas.")
    if not isinstance(senal, Senal):
        raise ValueError("Se requiere señal interna tipada.")
    if senal == Senal.SIN_VERIFICACION:
        return None
    if type(usuario_id) is not int or not 0 < usuario_id <= 9223372036854775807:
        raise ValueError("Identificador interno inválido.")
    with transaction.atomic():
        user = Usuario.objects.select_for_update().filter(pk=usuario_id).first()
        if user is None:
            return None  # Inexistente no crea estado ni cuenta como fallo.
        credential = SeguridadCredencial.objects.select_for_update().filter(usuario_id=usuario_id).first()
        state = EstadoAcceso.objects.select_for_update().filter(usuario_id=usuario_id).first()
        if not estado_coherente(credential) or state is None:
            raise EstadoAccesoNoDisponible("Estado de seguridad no disponible; no se repara.")
        ahora = timezone.now()  # Tras esperar locks, nunca al inicio de la request.
        if ahora < state.actualizado_en:
            raise EstadoAccesoNoDisponible("Reloj servidor regresivo; requiere revisión.")
        if (state.intentos != len(state.fallos_en)
            or state.ventana_inicio != (state.fallos_en[0] if state.fallos_en else None)
            or state.ventana_hasta != (state.ventana_inicio + VENTANA if state.fallos_en else None)):
            raise EstadoAccesoNoDisponible("Contadores/ventana incoherentes; no se reparan.")
        before = EstadoPolitica(state.estado, tuple(state.fallos_en), tuple(state.ciclos_en), state.bloqueo_inicio, state.bloqueado_hasta)
        try:
            result = calcular_transicion(before, senal, ahora)
        except ValueError:
            raise EstadoAccesoNoDisponible("Estado de acceso incoherente; no se repara.") from None
        if before == result.estado:
            return result
        if state.version >= 9223372036854775807:
            raise EstadoAccesoNoDisponible("Versión de acceso agotada.")
        after = result.estado
        state.estado, state.fallos_en, state.ciclos_en = after.estado, list(after.fallos), list(after.ciclos)
        state.intentos = len(after.fallos)
        state.ventana_inicio = after.fallos[0] if after.fallos else None
        state.ventana_hasta = state.ventana_inicio + VENTANA if after.fallos else None
        state.bloqueo_inicio, state.bloqueado_hasta = after.bloqueo_inicio, after.bloqueado_hasta
        state.version += 1
        state.actualizado_en = ahora
        state.save()
        for tipo, cantidad in result.eventos:
            titular = tipo == "REINICIO_RACHA"
            EventoAcceso.objects.create(usuario=user, tipo=tipo, actor_tipo="TITULAR" if titular else "SISTEMA",
                                        actor=user if titular else None, version=state.version,
                                        cantidad_fallos=cantidad, creado_en=ahora)
        return result
