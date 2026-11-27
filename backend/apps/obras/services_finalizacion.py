"""004B-5: finalización bajo el mismo lock Presupuesto -> Obra de 004A/B.

Se reutilizan guard y cálculos de 004B-4 sin llamar a validar_costos ni modificar
su marca. Un rechazo revierte la transacción completa, sin efectos secundarios.
"""
import json

from django.db.models import F, OuterRef, Sum
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac

from apps.inventario.models import OperacionMaterial as Op

from . import services as base, services_costos as costos
from .exceptions import CierreMaterialesPendientes, CostosIncompletos, EstadoIncompatible
from .materials_plan import _suma, autorizaciones
from .models import CierreCostosObra, ControlCostosObra, Obra, ObraEvento


def devoluciones_recibibles(obra):
    from apps.inventario.consultas_materiales import con_recibible

    return con_recibible(Op.objects.filter(obra=obra, tipo='AUTORIZACION_DEVOLUCION')).filter(
        cantidad_recibible_efectiva__gt=0)


def _material(obra, codigo, nombre, unidad, cantidad, responsable):
    return {'obra': obra.codigo, 'codigo': codigo, 'nombre': nombre, 'unidad': unidad,
            'cantidad': format(cantidad, '.3f'), 'responsable': responsable}


def remanentes(obra, actor):
    qs = autorizaciones(obra).annotate(pendiente=F('cantidad') - _suma(
        'ENTREGA', 'autorizacion_id', autorizacion_id=OuterRef('pk'))).filter(pendiente__gt=0)
    filas = list(qs.order_by('pk').values_list('pk', 'pendiente'))
    if not filas:
        return None, qs.none()
    huella = json.dumps([obra.pk, actor.pk, obra.estado, [(pk, format(q, '.3f')) for pk, q in filas]], separators=(',', ':'))
    return salted_hmac('fyag.obras.019f.remanentes', huella, algorithm='sha256').hexdigest(), qs


def _validacion_pendientes(control):
    if control.costos_validados:
        return []
    return ['validacion_obsoleta_o_ausente'] + (['control_inexistente'] if not control.pk else [])


MENSAJES = {
    'responsable_no_elegible': ('tecnicos', 'Asigne un técnico responsable activo.'),
    'responsable_sin_membresia': ('tecnicos', 'Regularice la participación del responsable en la obra.'),
    'sin_turno_acreditado': ('turnos', 'Valide al menos un turno con duración, descripción y tarifa.'),
    'turnos_sin_acreditar': ('turnos', 'Resuelva los turnos no acreditados.'),
    'turnos_abiertos': ('turnos', 'Cierre los turnos abiertos.'),
    'turnos_pendientes_revision': ('turnos', 'Revise los turnos pendientes.'),
    'turnos_observados': ('turnos', 'Solicite al técnico subsanar los turnos observados.'),
    'turnos_sin_tarifa': ('turnos', 'Registre la tarifa en la revisión del turno.'),
    'turno_inconsistente': ('turnos', 'Revise los datos de los turnos inconsistentes.'),
    'ejecutor_inconsistente': ('turnos', 'Revise el ejecutor y la membresía de los turnos.'),
    'duracion_administrativa_sin_verificar': ('turnos', 'Verifique la duración de los cierres administrativos.'),
    'duracion_inconsistente': ('turnos', 'Revise los tiempos y la duración registrada.'),
    'evidencia_inconsistente': ('turnos', 'Revise las evidencias de los turnos; solicite soporte si están dañadas.'),
    'gasto_inconsistente': ('gastos', 'Revise fechas, cantidades y devoluciones de los gastos vigentes.'),
    'costo_total_no_positivo': ('costos', 'Revise los costos reales: el total acreditado debe ser positivo.'),
    'materiales_sin_declarar_o_incoherente': ('costos', 'Valide nuevamente los costos con los materiales vigentes.'),
    'otros_sin_declarar_o_incoherente': ('costos', 'Valide nuevamente los costos con los otros gastos vigentes.'),
    'control_inexistente': ('costos', 'Complete la validación económica general.'),
    'validacion_obsoleta_o_ausente': ('costos', 'Valide los costos actuales antes de finalizar.'),
    'estado_para_validar': ('resumen', 'La validación requiere una obra en ejecución o suspendida.'),
    'estado_para_finalizar': ('resumen', 'La finalización requiere una obra en ejecución; reanúdela si está suspendida.'),
    'cierre_existente': ('resumen', 'La obra ya tiene un cierre registrado.'),
}


def _detalles(codigos):
    return [{'codigo': c, 'destino': MENSAJES[c][0], 'mensaje': MENSAJES[c][1]} for c in sorted(set(codigos))]


@base._operacion
def requisitos_cierre(referencia, usuario):
    actor = base._actor_autorizado(usuario, base.SUPERVISOR)
    obra = base._obra_bloqueada(referencia)
    if obra.estado not in {Obra.Estado.EN_PROCESO, Obra.Estado.SUSPENDIDA}:
        return {'validacion': _detalles(['estado_para_validar']), 'finalizacion': _detalles(['estado_para_finalizar']),
                'devoluciones': [], 'despachos': [], 'confirmacion_remanente': None}
    responsable = costos._responsable_pendientes(obra)
    control = costos._consultar_control(obra)
    gastos, turnos = costos._recursos_revision(obra)
    evaluado = ControlCostosObra(obra=obra)
    costos._derivar_rubros(evaluado, gastos)
    validacion = responsable + costos._pendientes(obra, evaluado, gastos, turnos)
    finalizacion = validacion + _validacion_pendientes(control)
    # Los rubros persistidos solo son requisito del cierre de una validación vigente.
    if control.costos_validados:
        finalizacion += costos._pendientes_rubros(control, gastos)
    if obra.estado != Obra.Estado.EN_PROCESO:
        finalizacion.append('estado_para_finalizar')
    if CierreCostosObra.objects.filter(obra=obra).exists():
        finalizacion.append('cierre_existente')
    devoluciones = [_material(obra, codigo, nombre, unidad, cantidad, 'Bodega')
                    for codigo, nombre, unidad, cantidad in devoluciones_recibibles(obra).order_by('pk')
                    .values_list('articulo__codigo', 'articulo__nombre', 'unidad', 'cantidad_recibible_efectiva')]
    confirmacion, qs = remanentes(obra, actor)
    agrupado = qs.order_by().values('articulo__codigo', 'articulo__nombre', 'unidad').annotate(
        total=Sum('pendiente')).order_by('articulo__codigo', 'unidad')
    return {'validacion': _detalles(validacion), 'finalizacion': _detalles(finalizacion),
            'devoluciones': devoluciones, 'confirmacion_remanente': confirmacion,
            'despachos': [_material(obra, d['articulo__codigo'], d['articulo__nombre'], d['unidad'],
                                   d['total'], 'Supervisor') for d in agrupado]}


@base._operacion
def finalizar_obra(referencia, datos, usuario):
    actor = base._actor_autorizado(usuario, base.SUPERVISOR)
    obra = base._obra_bloqueada(referencia)
    base._campos_validos(datos, {"motivo", "confirmacion_remanente"}, {"motivo"})
    motivo = base._motivo(datos["motivo"], obligatorio=True)
    if obra.estado != Obra.Estado.EN_PROCESO:
        raise EstadoIncompatible()
    # El responsable se bloquea antes que los recursos/control. La Obra ya
    # bloqueada serializa todas las escrituras económicas y de participantes.
    pendientes = costos._responsable_pendientes(obra)
    control = costos._consultar_control(obra)
    pendientes.extend(_validacion_pendientes(control))
    if CierreCostosObra.objects.filter(obra=obra).exists():
        raise EstadoIncompatible("La Obra ya tiene una fotografía de cierre.")
    if devoluciones_recibibles(obra).exists():
        raise CierreMaterialesPendientes('devolucion_pendiente',
            'Bodega debe recibir las devoluciones pendientes. Actualice la lista de cierre para ver los materiales.')
    gastos, turnos = costos._recursos_revision(obra)
    pendientes.extend(costos._pendientes(obra, control, gastos, turnos))
    if pendientes:
        raise CostosIncompletos(sorted(set(pendientes)))
    esperada, _ = remanentes(obra, actor)
    recibida = datos.get('confirmacion_remanente')
    if (esperada or recibida) and (not isinstance(recibida, str) or not esperada
                                  or not constant_time_compare(esperada, recibida)):
        raise CierreMaterialesPendientes('confirmacion_remanente_requerida',
            'Actualice y confirme las cantidades pendientes que quedarán inhabilitadas al finalizar.')
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
        nuevos={"estado": obra.estado, "finalizado_en": obra.finalizado_en.isoformat(),
                **({'remanente_despacho_confirmado': True} if esperada else {})},
        motivo=motivo,
    )
    return obra
