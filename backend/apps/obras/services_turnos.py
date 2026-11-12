"""004B-2: Presupuesto -> Obra -> Usuario (inicio) -> membresía/turno.

Las operaciones con archivos controlan su commit exterior (durable) para poder
compensar un rollback SQL, también si falla el commit, sin archivos huérfanos.
No envolver cierre/subsanación en otro atomic de producción.
"""
from decimal import Decimal
from functools import wraps
import re

from django.db import models, transaction
from django.utils import timezone

from . import services as base
from .evidencias import guardar_foto, limpiar_archivos, validar_fotos
from .exceptions import DatosInvalidos, EstadoIncompatible, RecursoNoEncontrado, SinCambios
from .models import EvidenciaTurno, Obra, ObraParticipante, TurnoObra, TurnoObraEvento


def tarifa_decimal(valor):
    if not isinstance(valor, str) or not re.fullmatch(r"[0-9]{1,13}\.[0-9]{2}", valor):
        raise DatosInvalidos({"costo_hora_neto": ["Use un string decimal no negativo con dos decimales (máximo 13 enteros)."]})
    return Decimal(valor)


def _miembro(obra, actor):
    if not ObraParticipante.objects.select_for_update().filter(obra=obra, tecnico=actor, activo=True).exists():
        raise RecursoNoEncontrado()


def _turno(obra, referencia, actor):
    queryset = TurnoObra.objects.select_for_update().filter(obra=obra)
    if actor.rol == base.TECNICO:
        _miembro(obra, actor)
        queryset = queryset.filter(tecnico=actor)
    try:
        return queryset.get(pk=base._id(referencia, TurnoObra, "turno"))
    except TurnoObra.DoesNotExist as exc:
        raise RecursoNoEncontrado() from exc


def _editable(obra):
    if obra.estado not in {Obra.Estado.EN_PROCESO, Obra.Estado.SUSPENDIDA}:
        raise EstadoIncompatible()


def _snapshot(turno):
    return {
        "estado_revision": turno.estado_revision,
        "modo_cierre": turno.modo_cierre,
        "cerrado_por": turno.cerrado_por_id,
        "iniciado_en": turno.iniciado_en.isoformat(),
        "terminado_en": turno.terminado_en.isoformat() if turno.terminado_en else None,
        "duracion_segundos": str(turno.duracion_segundos) if turno.duracion_segundos is not None else None,
        "duracion_ajustada_segundos": turno.duracion_ajustada_segundos,
        "descripcion_trabajo": turno.descripcion_trabajo,
        "costo_hora_neto": str(turno.costo_hora_neto) if turno.costo_hora_neto is not None else None,
        "revisado_por": turno.revisado_por_id,
        "revisado_en": turno.revisado_en.isoformat() if turno.revisado_en else None,
        "observacion_revision": turno.observacion_revision,
        "fotos": list(turno.fotos.values_list("id", flat=True)),
    }


def _evento(turno, tipo, actor, motivo, antes):
    from .services_costos import invalidar
    control = invalidar(turno.obra, actor, motivo)
    nuevos = _snapshot(turno)
    nuevos["version_costos"] = control.version_actual
    TurnoObraEvento.objects.create(turno=turno, tipo=tipo, registrado_por=actor,
        motivo=motivo, datos_anteriores=antes, datos_nuevos=nuevos)
    from apps.alertas.services import notificar_despues_commit
    notificar_despues_commit("TURNO_PENDIENTE_REVISION", turno.pk)


@base._operacion
def iniciar_turno(referencia, datos, usuario):
    actor = base._actor_autorizado(usuario, base.TECNICO)
    obra = base._obra_bloqueada(referencia)
    actor = base._tecnico_elegible(actor, campo="tecnico")
    _miembro(obra, actor)
    base._campos_validos(datos, set())
    if obra.estado != Obra.Estado.EN_PROCESO:
        raise EstadoIncompatible()
    if TurnoObra.objects.filter(tecnico=actor, terminado_en=None).exists():
        raise EstadoIncompatible("El técnico ya tiene un turno abierto.")
    turno = TurnoObra(obra=obra, tecnico=actor, iniciado_en=timezone.now())
    # La unicidad concurrente la decide PostgreSQL, no full_clean (que daría 400).
    turno.full_clean(validate_constraints=False)
    models.Model.save(turno, force_insert=True)
    _evento(turno, "INICIO", actor, "Inicio de turno por el técnico", {})
    return turno


def _con_archivos(funcion):
    @wraps(funcion)
    def ejecutar(*args, **kwargs):
        creados = []
        try:
            with transaction.atomic(durable=True):
                return funcion(*args, **kwargs, archivos_creados=creados)
        except BaseException:
            limpiar_archivos(creados)
            raise
    return ejecutar


def _adjuntar(turno, actor, fotos, creados):
    if turno.fotos.count() + len(fotos) > 5:
        raise DatosInvalidos({"fotos[]": ["Máximo 5 fotografías acumuladas por turno."]})
    for contenido, extension, mime in validar_fotos(fotos):
        nombre, sha256 = guardar_foto(contenido, extension, creados)
        EvidenciaTurno.objects.create(turno=turno, obra=turno.obra, nombre_interno=nombre,
            tipo_mime=mime, tamano=len(contenido), sha256=sha256, registrado_por=actor)


def _pendiente(turno):
    turno.estado_revision = TurnoObra.Estado.PENDIENTE_REVISION
    turno.revisado_por = None
    turno.revisado_en = None
    turno.observacion_revision = ""


@_con_archivos
@base._operacion
def finalizar_turno(referencia, turno_id, datos, usuario, *, fotos=(), archivos_creados):
    actor = base._actor_autorizado(usuario, base.TECNICO)
    obra = base._obra_bloqueada(referencia)
    turno = _turno(obra, turno_id, actor)
    base._campos_validos(datos, {"descripcion_trabajo"}, {"descripcion_trabajo"})
    descripcion = base._texto(datos["descripcion_trabajo"], "descripcion_trabajo")
    _editable(obra)
    if turno.estado_revision != TurnoObra.Estado.ABIERTO:
        raise EstadoIncompatible("El turno ya está cerrado.")
    antes = _snapshot(turno)
    turno.terminado_en = timezone.now()
    delta = turno.terminado_en - turno.iniciado_en
    turno.duracion_segundos = Decimal(delta.days * 86400 + delta.seconds) + Decimal(delta.microseconds) / Decimal(1000000)
    if turno.duracion_segundos <= 0:
        raise EstadoIncompatible("La duración del turno debe ser positiva.")
    turno.descripcion_trabajo = descripcion
    turno.modo_cierre = TurnoObra.ModoCierre.TECNICO
    turno.cerrado_por = actor
    _pendiente(turno)
    turno.save()
    _adjuntar(turno, actor, fotos, archivos_creados)
    _evento(turno, "CIERRE", actor, "Cierre de turno por el técnico", antes)
    return turno


def _ajuste(turno, valor):
    if valor is not None and (type(valor) is not int or not 0 < valor <= 9223372036854775807):
        raise DatosInvalidos({"duracion_ajustada_segundos": ["Use un entero positivo o null."]})
    if turno.modo_cierre == TurnoObra.ModoCierre.SUPERVISOR and valor is not None and valor > turno.duracion_segundos:
        raise DatosInvalidos({"duracion_ajustada_segundos": ["No puede superar la duración transcurrida de servidor."]})
    return valor


@base._operacion
def cerrar_administrativamente(referencia, turno_id, datos, usuario):
    actor = base._actor_autorizado(usuario, base.SUPERVISOR)
    obra = base._obra_bloqueada(referencia)
    turno = _turno(obra, turno_id, actor)
    base._campos_validos(datos, {"motivo", "descripcion_trabajo", "duracion_ajustada_segundos"}, {"motivo", "descripcion_trabajo"})
    motivo = base._motivo(datos["motivo"], obligatorio=True)
    descripcion = base._texto(datos["descripcion_trabajo"], "descripcion_trabajo")
    if obra.estado != Obra.Estado.EN_PROCESO or turno.estado_revision != TurnoObra.Estado.ABIERTO:
        raise EstadoIncompatible()
    antes = _snapshot(turno)
    turno.terminado_en = timezone.now()
    delta = turno.terminado_en - turno.iniciado_en
    turno.duracion_segundos = Decimal(delta.days * 86400 + delta.seconds) + Decimal(delta.microseconds) / Decimal(1000000)
    if turno.duracion_segundos <= 0:
        raise EstadoIncompatible("La duración del turno debe ser positiva.")
    turno.modo_cierre = TurnoObra.ModoCierre.SUPERVISOR
    turno.cerrado_por = actor
    turno.descripcion_trabajo = descripcion
    turno.duracion_ajustada_segundos = _ajuste(turno, datos.get("duracion_ajustada_segundos"))
    _pendiente(turno)
    turno.save()
    _evento(turno, "CIERRE_ADMINISTRATIVO", actor, motivo, antes)
    return turno


@_con_archivos
@base._operacion
def subsanar_turno(referencia, turno_id, datos, usuario, *, fotos=(), archivos_creados):
    actor = base._actor_autorizado(usuario, base.TECNICO)
    obra = base._obra_bloqueada(referencia)
    turno = _turno(obra, turno_id, actor)
    base._campos_validos(datos, {"descripcion_trabajo"})
    _editable(obra)
    if turno.estado_revision != TurnoObra.Estado.OBSERVADO:
        raise EstadoIncompatible()
    antes = _snapshot(turno)
    if "descripcion_trabajo" in datos:
        aclaracion = base._texto(datos["descripcion_trabajo"], "descripcion_trabajo")
        turno.descripcion_trabajo = base._texto(turno.descripcion_trabajo + "\n" + aclaracion, "descripcion_trabajo")
    elif not fotos:
        raise DatosInvalidos({"descripcion_trabajo": ["Agregue una aclaración o fotografías."]})
    _adjuntar(turno, actor, fotos, archivos_creados)
    _pendiente(turno)
    turno.save()
    _evento(turno, "SUBSANACION", actor, "Subsanación aportada por el técnico", antes)
    return turno


@base._operacion
def revisar_turno(referencia, turno_id, datos, usuario):
    actor = base._actor_autorizado(usuario, base.SUPERVISOR)
    obra = base._obra_bloqueada(referencia)
    turno = _turno(obra, turno_id, actor)
    base._campos_validos(datos, {"decision", "motivo", "costo_hora_neto"}, {"decision", "motivo"})
    motivo = base._motivo(datos["motivo"], obligatorio=True)
    decision = datos["decision"]
    if decision not in ("VALIDAR", "OBSERVAR"):
        raise DatosInvalidos({"decision": ["Use VALIDAR u OBSERVAR."]})
    if decision == "VALIDAR" and "costo_hora_neto" not in datos:
        raise DatosInvalidos({"costo_hora_neto": ["Ingrese la tarifa manual para validar."]})
    tarifa = tarifa_decimal(datos["costo_hora_neto"]) if "costo_hora_neto" in datos else turno.costo_hora_neto
    _editable(obra)
    if turno.estado_revision != TurnoObra.Estado.PENDIENTE_REVISION:
        raise EstadoIncompatible()
    if decision == "VALIDAR" and turno.modo_cierre == TurnoObra.ModoCierre.SUPERVISOR and turno.duracion_ajustada_segundos is None:
        raise EstadoIncompatible("El cierre administrativo requiere una duración ajustada verificada.")
    antes = _snapshot(turno)
    turno.costo_hora_neto = tarifa
    turno.estado_revision = TurnoObra.Estado.VALIDADO if decision == "VALIDAR" else TurnoObra.Estado.OBSERVADO
    turno.revisado_por = actor
    turno.revisado_en = timezone.now()
    turno.observacion_revision = motivo
    turno.save()
    _evento(turno, "VALIDACION" if decision == "VALIDAR" else "OBSERVACION", actor, motivo, antes)
    return turno


@base._operacion
def corregir_turno(referencia, turno_id, datos, usuario):
    actor = base._actor_autorizado(usuario, base.SUPERVISOR)
    obra = base._obra_bloqueada(referencia)
    turno = _turno(obra, turno_id, actor)
    base._campos_validos(datos, {"duracion_ajustada_segundos", "costo_hora_neto", "motivo", "descripcion_trabajo"}, {"motivo"})
    motivo = base._motivo(datos["motivo"], obligatorio=True)
    _editable(obra)
    if turno.terminado_en is None:
        raise EstadoIncompatible()
    antes = _snapshot(turno)
    if "duracion_ajustada_segundos" in datos:
        turno.duracion_ajustada_segundos = _ajuste(turno, datos["duracion_ajustada_segundos"])
    if "descripcion_trabajo" in datos:
        if turno.modo_cierre != TurnoObra.ModoCierre.SUPERVISOR:
            raise DatosInvalidos({"descripcion_trabajo": ["Solo se rectifica la descripción de un cierre administrativo."]})
        descripcion = base._texto(datos["descripcion_trabajo"], "descripcion_trabajo")
        # Las subsanaciones son adiciones del técnico, no texto del Supervisor.
        for evento in turno.eventos.filter(tipo="SUBSANACION").order_by("id"):
            anterior = evento.datos_anteriores["descripcion_trabajo"]
            posterior = evento.datos_nuevos["descripcion_trabajo"]
            descripcion += posterior[len(anterior):]
        turno.descripcion_trabajo = base._texto(descripcion, "descripcion_trabajo")
    if "costo_hora_neto" in datos:
        turno.costo_hora_neto = tarifa_decimal(datos["costo_hora_neto"])
    if _snapshot(turno) == antes:
        raise SinCambios("No hay correcciones efectivas.")
    _pendiente(turno)
    turno.save()
    _evento(turno, "CORRECCION", actor, motivo, antes)
    return turno
