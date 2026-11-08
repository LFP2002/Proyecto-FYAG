"""004B-4. El caller de invalidar ya posee Presupuesto -> Obra.

Sin señales ni transacciones durables: se participa en la transacción original,
incluida la compensación de fotografías de services_turnos.
"""
from datetime import date
from decimal import Decimal, InvalidOperation, localcontext
import hashlib

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.usuarios.models import Usuario
from . import services as base
from .exceptions import CostosIncompletos, DatosInvalidos, EstadoIncompatible, PermisoDenegado, SinCambios
from .evidencias import MAX_BYTES, ruta_privada
from .models import ControlCostosObra, CortesiaObra, CostoObraEvento, GastoObra, Obra, ObraParticipante, TurnoObra


RUBROS = ("materiales", "otros")
CAMPOS_CONTROL = {f"{r}_{c}" for r in RUBROS for c in ("estado", "justificacion")} | {"motivo"}


def _consultar_control(obra):
    """Consultar bajo el lock de Obra; el valor inicial no se persiste."""
    control = ControlCostosObra.objects.select_for_update().filter(obra=obra).first()
    return control if control is not None else ControlCostosObra(obra=obra)


def _crear_control(obra):
    # Incluso sin fila previa, el lock de Obra serializa la creación OneToOne.
    if not transaction.get_connection().in_atomic_block:
        raise RuntimeError("El control requiere la transacción y el lock de Obra.")
    control, _ = ControlCostosObra.objects.select_for_update().get_or_create(obra=obra)
    return control


def snapshot(control):
    return {
        "id": control.pk, "obra": control.obra_id,
        **{f"{r}_{c}": getattr(control, f"{r}_{c}") for r in RUBROS for c in ("estado", "justificacion")},
        "version_actual": control.version_actual,
        "version_validada": control.version_validada,
        "validado_por": control.validado_por_id,
        "validado_en": control.validado_en.isoformat() if control.validado_en else None,
        "costos_validados": control.costos_validados,
        "creado_en": control.creado_en.isoformat() if control.creado_en else None,
        "actualizado_en": control.actualizado_en.isoformat() if control.actualizado_en else None,
    }


def _evento(control, tipo, actor, motivo, antes, *, cortesia=None, nuevos=None):
    return CostoObraEvento.objects.create(
        obra_id=control.obra_id, tipo=tipo, registrado_por=actor, motivo=motivo,
        control=control if cortesia is None else None, cortesia=cortesia,
        datos_anteriores=antes, datos_nuevos=snapshot(control) if nuevos is None else nuevos,
    )


def _registros(obra):
    gastos = GastoObra.objects.filter(obra=obra, vigente=True)
    return {"materiales": gastos.filter(tipo="MATERIAL").exists(),
            "otros": gastos.exclude(tipo="MATERIAL").exists()}


def _incrementar(control):
    control.version_actual += 1
    control.version_validada = None
    control.validado_por = None
    control.validado_en = None


def invalidar(obra, actor, motivo, *, gastos=False):
    """Una llamada por operación efectiva; nunca desde helpers anidados."""
    control = _crear_control(obra)
    antes = snapshot(control)
    _incrementar(control)
    restablecidos = []
    if gastos:
        registros = _registros(obra)
        for rubro in RUBROS:
            estado = getattr(control, f"{rubro}_estado")
            if ((estado == "NO_APLICA" and registros[rubro])
                    or (estado == "CON_REGISTROS" and not registros[rubro])):
                setattr(control, f"{rubro}_estado", "PENDIENTE")
                setattr(control, f"{rubro}_justificacion", "")
                restablecidos.append(rubro)
    control.save()
    if restablecidos:
        _evento(control, "DECLARACION", actor, motivo, antes)
    return control


def _editable(obra):
    if obra.estado not in {Obra.Estado.EN_PROCESO, Obra.Estado.SUSPENDIDA}:
        raise EstadoIncompatible()


def _lector(usuario, *, finanzas=False):
    roles = {base.GERENCIA, base.SUPERVISOR}
    if finanzas:
        roles.add(Usuario.Rol.ADMINISTRATIVO_FINANZAS)
    if not isinstance(usuario, Usuario) or usuario.pk is None:
        raise PermisoDenegado()
    try:
        actual = Usuario.objects.get(pk=usuario.pk)
    except Usuario.DoesNotExist as exc:
        raise PermisoDenegado() from exc
    if not actual.is_active or actual.rol not in roles:
        raise PermisoDenegado()
    return actual


@base._operacion
def consultar_control(referencia, usuario):
    _lector(usuario)
    return snapshot(_consultar_control(base._obra_bloqueada(referencia)))


@base._operacion
def declarar_rubros(referencia, datos, usuario):
    actor = base._actor_autorizado(usuario, base.SUPERVISOR)
    obra = base._obra_bloqueada(referencia)
    base._campos_validos(datos, CAMPOS_CONTROL)
    _editable(obra)
    control = _consultar_control(obra)
    antes = snapshot(control)
    registros = _registros(obra)
    for rubro in RUBROS:
        campo, justificacion = f"{rubro}_estado", f"{rubro}_justificacion"
        if campo not in datos and justificacion not in datos:
            continue
        estado = datos.get(campo, getattr(control, campo))
        texto = base._texto(datos.get(justificacion, getattr(control, justificacion)), justificacion, obligatorio=estado == "NO_APLICA")
        if campo not in datos and estado == "PENDIENTE" and texto == getattr(control, justificacion):
            continue  # Justificación vacía normalizada: también es un no-op.
        if estado not in {"CON_REGISTROS", "NO_APLICA"}:
            raise DatosInvalidos({campo: ["Declare CON_REGISTROS o NO_APLICA."]})
        if (estado == "CON_REGISTROS") != registros[rubro]:
            raise DatosInvalidos({campo: ["La declaración no corresponde a los registros vigentes."]})
        setattr(control, campo, estado)
        setattr(control, justificacion, texto if estado == "NO_APLICA" else "")
    motivo = base._motivo(datos.get("motivo", ""), obligatorio=False)
    if snapshot(control) == antes:
        return antes
    motivo = base._motivo(motivo, obligatorio=True)
    _incrementar(control)
    control.save()
    _evento(control, "DECLARACION", actor, motivo, antes)
    return snapshot(control)


def _turno_acreditado(turno):
    if (turno.estado_revision != "VALIDADO" or turno.terminado_en is None
            or turno.costo_hora_neto is None or turno.duracion_segundos is None
            or not turno.duracion_segundos.is_finite() or turno.duracion_segundos <= 0
            or not turno.costo_hora_neto.is_finite()
            or turno.costo_hora_neto < 0
            or turno.revisado_por_id is None or turno.revisado_en is None
            or not turno.descripcion_trabajo.strip()):
        return False
    if turno.modo_cierre == "SUPERVISOR":
        if (turno.duracion_ajustada_segundos is None
                or not 0 < turno.duracion_ajustada_segundos <= turno.duracion_segundos):
            return False
    return turno.costo_mano_obra is not None


def _totales(gastos, turnos):
    with localcontext() as ctx:
        ctx.prec = 50
        materiales = sum((g.subtotal for g in gastos if g.tipo == "MATERIAL"), Decimal("0.00"))
        otros = sum((g.subtotal for g in gastos if g.tipo != "MATERIAL"), Decimal("0.00"))
        laboral = sum((t.costo_mano_obra for t in turnos if _turno_acreditado(t)), Decimal("0.00"))
        return dict(zip(("materiales_total", "otros_total", "mano_obra_total", "costo_total"),
                        (materiales, otros, laboral, materiales + otros + laboral)))


def _responsable_pendientes(obra):
    pendientes = []
    if not obra.iniciado_en or not obra.tecnico_responsable_id:
        pendientes.append("responsable_no_elegible")
    else:
        try:
            base._tecnico_elegible(obra.tecnico_responsable_id)
        except DatosInvalidos:
            pendientes.append("responsable_no_elegible")
        if not ObraParticipante.objects.filter(obra=obra, tecnico_id=obra.tecnico_responsable_id, activo=True).exists():
            pendientes.append("responsable_sin_membresia")
    return pendientes


def _gasto_coherente(obra, gasto):
    """Comprobar movimientos reales, no solo el acumulado de la fila."""
    gasto.full_clean()
    if gasto.fecha_gasto > timezone.localdate():
        return False
    devuelta = Decimal("0.000")
    correccion_temporal = False
    for evento in gasto.eventos.all():
        if evento.obra_id != obra.pk:
            return False
        if not isinstance(evento.datos_nuevos, dict) or not isinstance(evento.datos_anteriores, dict):
            return False
        if evento.tipo == "CORRECCION":
            if (evento.datos_nuevos.get("fecha_gasto") == gasto.fecha_gasto.isoformat()
                    and evento.datos_anteriores.get("fecha_gasto") != gasto.fecha_gasto.isoformat()
                    and evento.motivo.strip()):
                correccion_temporal = True
        if evento.tipo != "DEVOLUCION":
            continue
        detalle = evento.datos_nuevos["devolucion"]
        fecha = date.fromisoformat(detalle["fecha"])
        if not isinstance(detalle["cantidad"], str):
            return False
        cantidad = Decimal(detalle["cantidad"])
        if (not cantidad.is_finite() or cantidad <= 0
                or not gasto.fecha_gasto <= fecha <= timezone.localdate()):
            return False
        devuelta += cantidad
    if obra.iniciado_en and gasto.fecha_gasto < timezone.localdate(obra.iniciado_en) and not correccion_temporal:
        return False
    return devuelta == gasto.cantidad_devuelta


def _pendientes(obra, control, gastos, turnos):
    pendientes = []
    miembros = set(ObraParticipante.objects.filter(obra=obra).values_list("tecnico_id", flat=True))
    if not any(_turno_acreditado(turno) for turno in turnos):
        pendientes.append("sin_turno_acreditado")
    for turno in turnos:
        try:
            turno.full_clean()
        except ValidationError:
            pendientes.append("turno_inconsistente")
        if not _turno_acreditado(turno):
            pendientes.append("turnos_sin_acreditar")
            motivo_estado = {
                "ABIERTO": "turnos_abiertos",
                "PENDIENTE_REVISION": "turnos_pendientes_revision",
                "OBSERVADO": "turnos_observados",
            }.get(turno.estado_revision)
            if motivo_estado:
                pendientes.append(motivo_estado)
            if turno.costo_hora_neto is None:
                pendientes.append("turnos_sin_tarifa")
            if turno.modo_cierre == "SUPERVISOR" and turno.duracion_ajustada_segundos is None:
                pendientes.append("duracion_administrativa_sin_verificar")
        elif turno.modo_cierre == "TECNICO" and turno.cerrado_por_id != turno.tecnico_id:
            pendientes.append("ejecutor_inconsistente")
        if (turno.tecnico_id not in miembros
                or (obra.iniciado_en and turno.iniciado_en < obra.iniciado_en)):
            pendientes.append("ejecutor_inconsistente")
        if turno.terminado_en:
            delta = turno.terminado_en - turno.iniciado_en
            segundos = Decimal(delta.days * 86400 + delta.seconds) + Decimal(delta.microseconds) / Decimal(1000000)
            if turno.duracion_segundos != segundos:
                pendientes.append("duracion_inconsistente")
        for evidencia in turno.fotos.all():
            try:
                evidencia.full_clean()
                with ruta_privada(evidencia.nombre_interno).open("rb") as archivo:
                    contenido = archivo.read(MAX_BYTES + 1)
                if evidencia.obra_id != obra.pk or len(contenido) != evidencia.tamano or hashlib.sha256(contenido).hexdigest() != evidencia.sha256:
                    pendientes.append("evidencia_inconsistente")
            except (ValidationError, OSError, ValueError):
                pendientes.append("evidencia_inconsistente")
    for gasto in gastos:
        try:
            if not _gasto_coherente(obra, gasto):
                pendientes.append("gasto_inconsistente")
        except (ValidationError, KeyError, TypeError, ValueError, InvalidOperation):
            pendientes.append("gasto_inconsistente")
    for rubro in RUBROS:
        tiene = any((g.tipo == "MATERIAL") == (rubro == "materiales") for g in gastos)
        estado = getattr(control, f"{rubro}_estado")
        if (estado == "PENDIENTE" or (estado == "CON_REGISTROS") != tiene
                or (estado == "NO_APLICA" and not getattr(control, f"{rubro}_justificacion").strip())):
            pendientes.append(f"{rubro}_sin_declarar_o_incoherente")
    if _totales(gastos, turnos)["costo_total"] <= 0:
        pendientes.append("costo_total_no_positivo")
    return sorted(set(pendientes))


def validar_costos(referencia, datos, usuario):
    resultado = _validar_costos(referencia, datos, usuario)
    if isinstance(resultado, CostosIncompletos):
        # Confirmar la retirada de una marca obsoleta antes de responder 409.
        # No crear un evento VALIDACION ni incrementar la versión al rechazar.
        raise resultado
    return resultado


@base._operacion
def _validar_costos(referencia, datos, usuario):
    actor = base._actor_autorizado(usuario, base.SUPERVISOR)
    obra = base._obra_bloqueada(referencia)
    base._campos_validos(datos, {"motivo"}, {"motivo"})
    motivo = base._motivo(datos["motivo"], obligatorio=True)
    _editable(obra)
    # Usuario antes de recursos/control, igual que iniciar/reasignar.
    responsable_pendientes = _responsable_pendientes(obra)
    control = _consultar_control(obra)
    gastos = list(GastoObra.objects.filter(obra=obra, vigente=True).prefetch_related("eventos"))
    turnos = list(TurnoObra.objects.filter(obra=obra).prefetch_related("fotos"))
    pendientes = sorted(set(responsable_pendientes + _pendientes(obra, control, gastos, turnos)))
    if pendientes:
        if control.version_validada is not None:
            control.version_validada = None
            control.validado_por = None
            control.validado_en = None
            control.save()
        return CostosIncompletos(pendientes)
    if control.costos_validados:
        raise SinCambios("La versión actual ya está validada.")
    antes = snapshot(control)
    control.version_validada = control.version_actual
    control.validado_por = actor
    control.validado_en = timezone.now()
    control.save()
    _evento(control, "VALIDACION", actor, motivo, antes)
    return snapshot(control)


def _snapshot_cortesia(cortesia):
    return {"id": cortesia.pk, "obra": cortesia.obra_id, "tipo": cortesia.tipo,
            "justificacion": cortesia.justificacion, "autorizado_por": cortesia.autorizado_por_id,
            "autorizado_en": cortesia.autorizado_en.isoformat()}


@base._operacion
def registrar_cortesia(referencia, datos, usuario):
    actor = base._actor_autorizado(usuario, base.SUPERVISOR)
    obra = base._obra_bloqueada(referencia)
    base._campos_validos(datos, {"justificacion", "motivo"}, {"justificacion"})
    justificacion = base._texto(datos["justificacion"], "justificacion")
    _editable(obra)
    cortesia = CortesiaObra.objects.select_for_update().filter(obra=obra).first()
    antes = _snapshot_cortesia(cortesia) if cortesia else {}
    motivo = base._motivo(datos.get("motivo", ""), obligatorio=False)
    if cortesia and justificacion == cortesia.justificacion:
        raise SinCambios("La cortesía ya tiene esa justificación.")
    if cortesia:
        motivo = base._motivo(motivo, obligatorio=True)
    if cortesia and motivo == justificacion:
        raise DatosInvalidos({"motivo": ["Explique la rectificación con un motivo distinto de la justificación."]})
    if cortesia is None:
        cortesia = CortesiaObra(obra=obra)
    cortesia.justificacion = justificacion
    cortesia.autorizado_por = actor
    cortesia.autorizado_en = timezone.now()
    cortesia.save()
    control = invalidar(obra, actor, motivo or "Autorización excepcional sin cobro")
    _evento(control, "CORTESIA", actor, motivo or "Autorización excepcional sin cobro", antes,
            cortesia=cortesia, nuevos=_snapshot_cortesia(cortesia))
    return _snapshot_cortesia(cortesia)


@base._operacion
def resumen_costos(referencia, usuario):
    actor = _lector(usuario, finanzas=True)
    obra = base._obra_bloqueada(referencia)
    control = _consultar_control(obra)
    gastos = list(GastoObra.objects.filter(obra=obra, vigente=True))
    turnos = list(TurnoObra.objects.filter(obra=obra))
    cortesia = CortesiaObra.objects.filter(obra=obra).first()
    datos = {"obra": obra.pk, **{k: format(v, ".2f") for k, v in _totales(gastos, turnos).items()},
             "costos_validados": control.costos_validados, "cortesia_sin_cobro": cortesia is not None}
    if actor.rol != Usuario.Rol.ADMINISTRATIVO_FINANZAS:
        datos.update({k: v for k, v in snapshot(control).items() if k not in {"id", "creado_en", "actualizado_en"}})
        datos["cortesia_justificacion"] = cortesia.justificacion if cortesia else None
        datos["provisional"] = not control.costos_validados or obra.estado == Obra.Estado.SUSPENDIDA
    return datos
