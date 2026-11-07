"""Servicios transaccionales 004A (sin endpoints públicos de Obras).

Orden de locks: Presupuesto -> Obra -> CategoriaServicio -> Usuario técnico.
La creación se entrega junto con el guard de anulación comercial. FINALIZADA
Y CANCELADA NO están disponibles en este incremento.
"""

from collections.abc import Mapping
from datetime import date, datetime
from functools import wraps

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.comercial.models import Presupuesto
from apps.usuarios.models import Usuario

from .exceptions import (
    DatosInvalidos, EstadoIncompatible, PermisoDenegado, PresupuestoUtilizado,
    RecursoNoEncontrado, SinCambios,
)
from .models import (
    CategoriaServicio, CategoriaServicioEvento, Obra, ObraEvento,
    ObraParticipante, ObraParticipanteEvento,
)


SUPERVISOR = Usuario.Rol.SUPERVISOR_OBRAS
GERENCIA = Usuario.Rol.GERENCIA
TECNICO = Usuario.Rol.TECNICO

CAMPOS_CREAR = frozenset({
    "presupuesto", "categoria_servicio", "descripcion", "tecnico_responsable",
    "fecha_programada", "motivo",
})
CAMPOS_EDITAR = frozenset({
    "categoria_servicio", "descripcion", "fecha_programada", "motivo",
})


def _operacion(funcion):
    @wraps(funcion)
    def ejecutar(*args, **kwargs):
        try:
            with transaction.atomic():
                return funcion(*args, **kwargs)
        except ValidationError as exc:
            errores = (exc.message_dict if hasattr(exc, "message_dict")
                       else {"__all__": exc.messages})
            if "__all__" in errores:
                errores["__all__"] = ["Los datos no cumplen las reglas de integridad."]
            raise DatosInvalidos(errores) from exc
        except IntegrityError as exc:
            # Capturar solo la unicidad conocida. Otros errores son inesperados.
            diagnostico = getattr(exc.__cause__, "diag", None)
            nombre = getattr(diagnostico, "constraint_name", "") or ""
            if "obras_obra_presupuesto_id" in nombre and (
                "key" in nombre or "uniq" in nombre
            ):
                raise PresupuestoUtilizado() from exc
            if nombre == "obra_categoria_nombre_unico":
                raise DatosInvalidos({"nombre": ["La categoría ya existe."]}) from exc
            raise
    return ejecutar


def _id(referencia, modelo, campo):
    pk = referencia.pk if isinstance(referencia, modelo) else referencia
    if type(pk) is not int or pk < 1 or pk > 9223372036854775807:
        raise DatosInvalidos({campo: ["Indique un identificador entero positivo."]})
    return pk


def _actor_autorizado(usuario, rol):
    Modelo = get_user_model()
    if (
        not isinstance(usuario, Modelo)
        or not usuario.is_authenticated
        or usuario.pk is None
    ):
        raise PermisoDenegado()
    try:
        # Releer el rol persistido; no confiar en un objeto del caller anticuado.
        actual = Modelo.objects.get(pk=usuario.pk)
    except Modelo.DoesNotExist as exc:
        raise PermisoDenegado() from exc
    if not actual.is_active or actual.rol != rol:
        raise PermisoDenegado()
    return actual


def _campos_validos(datos, permitidos, obligatorios=()):
    if not isinstance(datos, Mapping):
        raise DatosInvalidos()
    errores = {
        campo: ["Campo no permitido."] for campo in datos
        if campo not in permitidos
    }
    errores.update({
        campo: ["Campo obligatorio."] for campo in obligatorios
        if campo not in datos
    })
    if errores:
        raise DatosInvalidos(errores)


def _texto(valor, campo, *, obligatorio=True, maximo=2000):
    if not isinstance(valor, str):
        raise DatosInvalidos({campo: ["Debe ser texto."]})
    texto = valor.strip()
    if obligatorio and not texto:
        raise DatosInvalidos({campo: ["No puede estar vacío."]})
    if len(texto) > maximo:
        raise DatosInvalidos({campo: [f"Máximo {maximo} caracteres."]})
    return texto


def _motivo(valor, *, obligatorio):
    return _texto(valor, "motivo", obligatorio=obligatorio)


def _fecha(valor):
    if valor is not None and (type(valor) is not date):
        # Un DateFieldSerializer entrega objetos date; no aceptar datetime ni bool.
        raise DatosInvalidos({"fecha_programada": ["Ingrese una fecha válida."]})
    return valor


def _presupuesto_bloqueado(referencia):
    try:
        return Presupuesto.objects.select_for_update().get(
            pk=_id(referencia, Presupuesto, "presupuesto")
        )
    except Presupuesto.DoesNotExist as exc:
        raise DatosInvalidos({"presupuesto": ["No existe el presupuesto."]}) from exc


def _obra_bloqueada(referencia):
    pk = _id(referencia, Obra, "obra")
    try:
        presupuesto_id = Obra.objects.values_list(
            "presupuesto_id", flat=True
        ).get(pk=pk)
    except Obra.DoesNotExist as exc:
        raise RecursoNoEncontrado() from exc
    # El presupuesto SIEMPRE se bloquea primero (también en las transiciones).
    Presupuesto.objects.select_for_update().get(pk=presupuesto_id)
    try:
        obra = Obra.objects.select_for_update().get(pk=pk)
    except Obra.DoesNotExist as exc:
        raise RecursoNoEncontrado() from exc
    if obra.presupuesto_id != presupuesto_id:
        # Una edición externa de la FK viola el contrato: nunca seguir a ciegas.
        raise EstadoIncompatible()
    return obra


def _categoria_bloqueada(referencia):
    try:
        return CategoriaServicio.objects.select_for_update().get(
            pk=_id(referencia, CategoriaServicio, "categoria_servicio")
        )
    except CategoriaServicio.DoesNotExist as exc:
        raise DatosInvalidos({
            "categoria_servicio": ["No existe la categoría."]
        }) from exc


def _categoria_elegible(referencia):
    categoria = _categoria_bloqueada(referencia)
    if not categoria.activo:
        raise DatosInvalidos({
            "categoria_servicio": ["La categoría está inactiva."]
        })
    return categoria


def _tecnico_elegible(referencia, campo="tecnico_responsable"):
    Modelo = get_user_model()
    pk = _id(referencia, Modelo, campo)
    try:
        tecnico = Modelo.objects.select_for_update().get(pk=pk)
    except Modelo.DoesNotExist as exc:
        raise DatosInvalidos({
            campo: ["No existe el técnico."]
        }) from exc
    if not tecnico.is_active or tecnico.rol != TECNICO:
        raise DatosInvalidos({
            campo: ["Se requiere un técnico activo."]
        })
    return tecnico


def _snapshot(obra):
    return {
        "presupuesto": obra.presupuesto_id,
        "categoria_servicio": obra.categoria_servicio_id,
        "descripcion": obra.descripcion,
        "tecnico_responsable": obra.tecnico_responsable_id,
        "fecha_programada": (
            obra.fecha_programada.isoformat() if obra.fecha_programada else None
        ),
        "estado": obra.estado,
        "iniciado_en": (
            obra.iniciado_en.isoformat() if obra.iniciado_en else None
        ),
    }


def _evento_obra(obra, tipo, usuario, anterior, *,
                 previos=None, nuevos=None, motivo=""):
    return ObraEvento.objects.create(
        obra=obra, tipo=tipo, estado_anterior=anterior,
        estado_nuevo=obra.estado, datos_anteriores=previos or {},
        datos_nuevos=nuevos or {}, registrado_por=usuario, motivo=motivo,
    )


def _categoria_evento(categoria, tipo, usuario, *, previos=None,
                      nuevos=None, motivo=""):
    return CategoriaServicioEvento.objects.create(
        categoria=categoria, tipo=tipo, registrado_por=usuario,
        datos_anteriores=previos or {}, datos_nuevos=nuevos or {},
        motivo=motivo,
    )


@_operacion
def crear_obra(datos, usuario):
    actor = _actor_autorizado(usuario, SUPERVISOR)
    _campos_validos(datos, CAMPOS_CREAR, (
        "presupuesto", "categoria_servicio", "descripcion",
    ))
    descripcion = _texto(datos["descripcion"], "descripcion")
    fecha = _fecha(datos.get("fecha_programada"))
    presupuesto = _presupuesto_bloqueado(datos["presupuesto"])
    if presupuesto.estado != Presupuesto.Estado.APROBADO_CLIENTE:
        raise EstadoIncompatible()
    if Obra.objects.filter(presupuesto_id=presupuesto.pk).exists():
        raise PresupuestoUtilizado()
    categoria = _categoria_elegible(datos["categoria_servicio"])
    tecnico = None
    if datos.get("tecnico_responsable") is not None:
        tecnico = _tecnico_elegible(datos["tecnico_responsable"])
    motivo = _motivo(datos.get("motivo", ""), obligatorio=tecnico is not None)
    obra = Obra.objects.create(
        presupuesto=presupuesto, categoria_servicio=categoria,
        descripcion=descripcion, tecnico_responsable=tecnico,
        fecha_programada=fecha, creado_por=actor,
    )
    if tecnico is not None:
        _activar_participante(obra, tecnico, actor, motivo)
    _evento_obra(
        obra, ObraEvento.Tipo.CREACION, actor, None,
        nuevos=_snapshot(obra), motivo=motivo,
    )
    return obra


@_operacion
def editar_obra(referencia, cambios, usuario):
    actor = _actor_autorizado(usuario, SUPERVISOR)
    _campos_validos(cambios, CAMPOS_EDITAR)
    obra = _obra_bloqueada(referencia)
    if obra.estado not in {
        Obra.Estado.PLANIFICADA, Obra.Estado.EN_PROCESO,
        Obra.Estado.SUSPENDIDA,
    }:
        raise EstadoIncompatible()
    previos, nuevos, campos = {}, {}, []
    if "descripcion" in cambios:
        desc = _texto(cambios["descripcion"], "descripcion")
        if desc != obra.descripcion:
            previos["descripcion"], nuevos["descripcion"] = obra.descripcion, desc
            obra.descripcion = desc
            campos.append("descripcion")
    if "categoria_servicio" in cambios:
        categoria = _categoria_elegible(cambios["categoria_servicio"])
        if categoria.pk != obra.categoria_servicio_id:
            previos["categoria_servicio"] = obra.categoria_servicio_id
            nuevos["categoria_servicio"] = categoria.pk
            obra.categoria_servicio = categoria
            campos.append("categoria_servicio")
    if "fecha_programada" in cambios:
        fecha = _fecha(cambios["fecha_programada"])
        if fecha != obra.fecha_programada:
            previos["fecha_programada"] = (
                obra.fecha_programada.isoformat()
                if obra.fecha_programada else None
            )
            nuevos["fecha_programada"] = fecha.isoformat() if fecha else None
            obra.fecha_programada = fecha
            campos.append("fecha_programada")
    if not campos:
        if "motivo" in cambios:
            _motivo(cambios["motivo"], obligatorio=False)
        return obra  # No-op: sin cambiar actualizado_en ni crear evento.
    motivo = _motivo(cambios.get("motivo", ""), obligatorio=True)
    obra.save(update_fields=[*campos, "actualizado_en"])
    _evento_obra(
        obra, ObraEvento.Tipo.EDICION, actor, obra.estado,
        previos=previos, nuevos=nuevos, motivo=motivo,
    )
    return obra


@_operacion
def cambiar_tecnico(referencia, tecnico_responsable, usuario, motivo):
    actor = _actor_autorizado(usuario, SUPERVISOR)
    obra = _obra_bloqueada(referencia)
    if obra.estado not in {
        Obra.Estado.PLANIFICADA, Obra.Estado.EN_PROCESO,
        Obra.Estado.SUSPENDIDA,
    }:
        raise EstadoIncompatible()
    nuevo_id = None if tecnico_responsable is None else _id(
        tecnico_responsable, get_user_model(), "tecnico_responsable"
    )
    if nuevo_id == obra.tecnico_responsable_id:
        raise SinCambios()
    if nuevo_id is None and obra.estado != Obra.Estado.PLANIFICADA:
        raise DatosInvalidos({
            "tecnico_responsable": ["Solo puede desasignar una obra planificada."]
        })
    nuevo = _tecnico_elegible(nuevo_id) if nuevo_id is not None else None
    motivo = _motivo(motivo, obligatorio=True)
    anterior = obra.tecnico_responsable_id
    obra.tecnico_responsable = nuevo
    obra.save(update_fields=["tecnico_responsable", "actualizado_en"])
    if anterior is not None:
        previo = ObraParticipante.objects.select_for_update().get(
            obra=obra, tecnico_id=anterior,
        )
        if previo.activo:
            _desactivar_participante(previo, actor, motivo)
    if nuevo is not None:
        _activar_participante(obra, nuevo, actor, motivo, permitir_activo=True)
    _evento_obra(
        obra, ObraEvento.Tipo.CAMBIO_TECNICO, actor, obra.estado,
        previos={"tecnico_responsable": anterior},
        nuevos={"tecnico_responsable": nuevo_id}, motivo=motivo,
    )
    return obra


@_operacion
def iniciar_obra(referencia, usuario, motivo):
    actor = _actor_autorizado(usuario, SUPERVISOR)
    obra = _obra_bloqueada(referencia)
    if obra.estado != Obra.Estado.PLANIFICADA:
        raise EstadoIncompatible()
    motivo = _motivo(motivo, obligatorio=True)
    if obra.tecnico_responsable_id is None:
        raise DatosInvalidos({
            "tecnico_responsable": ["Asigne un técnico antes de iniciar."]
        })
    _tecnico_elegible(obra.tecnico_responsable_id)
    anterior = obra.estado
    obra.estado = Obra.Estado.EN_PROCESO
    obra.iniciado_en = timezone.now()
    obra.save(update_fields=["estado", "iniciado_en", "actualizado_en"])
    _evento_obra(
        obra, ObraEvento.Tipo.CAMBIO_ESTADO, actor, anterior,
        previos={"estado": anterior, "iniciado_en": None},
        nuevos={"estado": obra.estado, "iniciado_en": obra.iniciado_en.isoformat()},
        motivo=motivo,
    )
    return obra


def _snapshot_participante(participante):
    return {
        "tecnico": participante.tecnico_id,
        "activo": participante.activo,
        "asignado_por": participante.asignado_por_id,
        "asignado_en": participante.asignado_en.isoformat() if participante.asignado_en else None,
        "motivo_asignacion": participante.motivo_asignacion,
        "desasignado_por": participante.desasignado_por_id,
        "desasignado_en": participante.desasignado_en.isoformat() if participante.desasignado_en else None,
        "motivo_desasignacion": participante.motivo_desasignacion,
        "origen_registro": participante.origen_registro,
    }


def _evento_participante(participante, tipo, actor, motivo, anteriores):
    ObraParticipanteEvento.objects.create(
        participante=participante, tipo=tipo, registrado_por=actor, motivo=motivo,
        datos_anteriores=anteriores, datos_nuevos=_snapshot_participante(participante),
    )


def _activar_participante(obra, tecnico, actor, motivo, *, permitir_activo=False):
    # Caller ya bloqueó Presupuesto -> Obra -> técnico. La Obra serializa altas.
    participante = ObraParticipante.objects.select_for_update().filter(
        obra=obra, tecnico=tecnico,
    ).first()
    creado = participante is None
    if participante and participante.activo:
        if permitir_activo:
            return participante, False
        raise SinCambios("El participante ya está activo.")
    anteriores = _snapshot_participante(participante) if participante else {}
    if creado:
        participante = ObraParticipante(obra=obra, tecnico=tecnico)
    participante.activo = True
    participante.asignado_por = actor
    participante.asignado_en = timezone.now()
    participante.motivo_asignacion = motivo
    participante.desasignado_por = None
    participante.desasignado_en = None
    participante.motivo_desasignacion = ""
    participante.save()
    _evento_participante(
        participante, "ASIGNACION" if creado else "REACTIVACION", actor, motivo, anteriores,
    )
    return participante, creado


def _desactivar_participante(participante, actor, motivo):
    anteriores = _snapshot_participante(participante)
    participante.activo = False
    participante.desasignado_por = actor
    participante.desasignado_en = timezone.now()
    participante.motivo_desasignacion = motivo
    participante.save()
    _evento_participante(participante, "DESASIGNACION", actor, motivo, anteriores)
    return participante


def _participantes_editables(obra):
    if obra.estado not in {Obra.Estado.PLANIFICADA, Obra.Estado.EN_PROCESO, Obra.Estado.SUSPENDIDA}:
        raise EstadoIncompatible()


@_operacion
def asignar_participante(referencia, datos, usuario):
    actor = _actor_autorizado(usuario, SUPERVISOR)
    obra = _obra_bloqueada(referencia)
    _campos_validos(datos, {"tecnico", "motivo"}, {"tecnico", "motivo"})
    _participantes_editables(obra)
    motivo = _motivo(datos["motivo"], obligatorio=True)
    tecnico = _tecnico_elegible(datos["tecnico"], campo="tecnico")
    return _activar_participante(obra, tecnico, actor, motivo)


@_operacion
def desasignar_participante(referencia, participante_id, usuario, motivo):
    actor = _actor_autorizado(usuario, SUPERVISOR)
    obra = _obra_bloqueada(referencia)
    try:
        participante = ObraParticipante.objects.select_for_update().get(
            pk=_id(participante_id, ObraParticipante, "participante"), obra=obra,
        )
    except ObraParticipante.DoesNotExist as exc:
        raise RecursoNoEncontrado() from exc
    motivo = _motivo(motivo, obligatorio=True)
    _participantes_editables(obra)
    if participante.tecnico_id == obra.tecnico_responsable_id:
        raise EstadoIncompatible("Cambie al responsable principal mediante cambiar-tecnico.")
    if not participante.activo:
        raise SinCambios("El participante ya está inactivo.")
    return _desactivar_participante(participante, actor, motivo)


@_operacion
def suspender_obra(referencia, usuario, motivo):
    actor = _actor_autorizado(usuario, SUPERVISOR)
    obra = _obra_bloqueada(referencia)
    if obra.estado != Obra.Estado.EN_PROCESO:
        raise EstadoIncompatible()
    motivo = _motivo(motivo, obligatorio=True)
    anterior = obra.estado
    obra.estado = Obra.Estado.SUSPENDIDA
    obra.save(update_fields=["estado", "actualizado_en"])
    _evento_obra(
        obra, ObraEvento.Tipo.CAMBIO_ESTADO, actor, anterior,
        previos={"estado": anterior}, nuevos={"estado": obra.estado},
        motivo=motivo,
    )
    return obra


@_operacion
def reanudar_obra(referencia, usuario, motivo):
    actor = _actor_autorizado(usuario, SUPERVISOR)
    obra = _obra_bloqueada(referencia)
    if obra.estado != Obra.Estado.SUSPENDIDA:
        raise EstadoIncompatible()
    motivo = _motivo(motivo, obligatorio=True)
    if obra.tecnico_responsable_id is None:
        raise DatosInvalidos({
            "tecnico_responsable": ["Asigne un técnico para reanudar."]
        })
    _tecnico_elegible(obra.tecnico_responsable_id)
    anterior = obra.estado
    obra.estado = Obra.Estado.EN_PROCESO
    obra.save(update_fields=["estado", "actualizado_en"])
    _evento_obra(
        obra, ObraEvento.Tipo.CAMBIO_ESTADO, actor, anterior,
        previos={"estado": anterior}, nuevos={"estado": obra.estado},
        motivo=motivo,
    )
    return obra


@_operacion
def crear_categoria(nombre, usuario):
    actor = _actor_autorizado(usuario, GERENCIA)
    nombre = _texto(nombre, "nombre", maximo=100)
    categoria = CategoriaServicio.objects.create(nombre=nombre, creado_por=actor)
    _categoria_evento(
        categoria, CategoriaServicioEvento.Tipo.CREACION, actor,
        nuevos={"nombre": categoria.nombre, "activo": categoria.activo},
    )
    return categoria


@_operacion
def renombrar_categoria(referencia, nombre, usuario, motivo=""):
    actor = _actor_autorizado(usuario, GERENCIA)
    categoria = _categoria_bloqueada(referencia)
    nuevo = _texto(nombre, "nombre", maximo=100)
    if nuevo == categoria.nombre:
        _motivo(motivo, obligatorio=False)
        return categoria
    motivo = _motivo(motivo, obligatorio=True)
    anterior = categoria.nombre
    categoria.nombre = nuevo
    categoria.save(update_fields=["nombre", "actualizado_en"])
    _categoria_evento(
        categoria, CategoriaServicioEvento.Tipo.EDICION, actor,
        previos={"nombre": anterior}, nuevos={"nombre": nuevo}, motivo=motivo,
    )
    return categoria


def _cambiar_actividad_categoria(referencia, usuario, motivo, activo):
    actor = _actor_autorizado(usuario, GERENCIA)
    categoria = _categoria_bloqueada(referencia)
    if categoria.activo is activo:
        _motivo(motivo, obligatorio=False)
        return categoria
    motivo = _motivo(motivo, obligatorio=True)
    anterior = categoria.activo
    categoria.activo = activo
    categoria.save(update_fields=["activo", "actualizado_en"])
    _categoria_evento(
        categoria,
        (CategoriaServicioEvento.Tipo.ACTIVACION if activo
         else CategoriaServicioEvento.Tipo.DESACTIVACION),
        actor, previos={"activo": anterior}, nuevos={"activo": activo},
        motivo=motivo,
    )
    return categoria


@_operacion
def activar_categoria(referencia, usuario, motivo=""):
    return _cambiar_actividad_categoria(referencia, usuario, motivo, True)


@_operacion
def desactivar_categoria(referencia, usuario, motivo=""):
    return _cambiar_actividad_categoria(referencia, usuario, motivo, False)
