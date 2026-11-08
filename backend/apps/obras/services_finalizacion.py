"""004B-5: finalización bajo el mismo lock Presupuesto -> Obra de 004A/B.

Se reutilizan guard y cálculos de 004B-4 sin llamar a validar_costos ni modificar
su marca. Un rechazo revierte la transacción completa, sin efectos secundarios.
"""
from django.utils import timezone

from . import services as base, services_costos as costos
from .exceptions import CostosIncompletos, EstadoIncompatible
from .models import CierreCostosObra, GastoObra, Obra, ObraEvento, TurnoObra


@base._operacion
def finalizar_obra(referencia, datos, usuario):
    actor = base._actor_autorizado(usuario, base.SUPERVISOR)
    obra = base._obra_bloqueada(referencia)
    base._campos_validos(datos, {"motivo"}, {"motivo"})
    motivo = base._motivo(datos["motivo"], obligatorio=True)
    if obra.estado != Obra.Estado.EN_PROCESO:
        raise EstadoIncompatible()
    # El responsable se bloquea antes que los recursos/control. La Obra ya
    # bloqueada serializa todas las escrituras económicas y de participantes.
    pendientes = costos._responsable_pendientes(obra)
    control = costos._consultar_control(obra)
    if control.pk is None:
        pendientes.append("control_inexistente")
    if (control.version_validada is None
            or control.version_validada != control.version_actual
            or control.validado_por_id is None or control.validado_en is None):
        pendientes.append("validacion_obsoleta_o_ausente")
    if CierreCostosObra.objects.filter(obra=obra).exists():
        raise EstadoIncompatible("La Obra ya tiene una fotografía de cierre.")
    gastos = list(GastoObra.objects.filter(obra=obra, vigente=True).prefetch_related("eventos"))
    turnos = list(TurnoObra.objects.filter(obra=obra).prefetch_related("fotos"))
    pendientes.extend(costos._pendientes(obra, control, gastos, turnos))
    if pendientes:
        raise CostosIncompletos(sorted(set(pendientes)))
    totales = costos._totales(gastos, turnos)
    CierreCostosObra.objects.create(
        obra=obra, **totales, version_validada=control.version_validada,
        validado_por_id=control.validado_por_id, finalizado_por=actor,
    )
    obra.estado = Obra.Estado.FINALIZADA
    obra.finalizado_en = timezone.now()
    obra.save(update_fields=["estado", "finalizado_en", "actualizado_en"])
    base._evento_obra(
        obra, ObraEvento.Tipo.CAMBIO_ESTADO, actor, Obra.Estado.EN_PROCESO,
        previos={"estado": Obra.Estado.EN_PROCESO, "finalizado_en": None},
        nuevos={"estado": obra.estado, "finalizado_en": obra.finalizado_en.isoformat()},
        motivo=motivo,
    )
    return obra
