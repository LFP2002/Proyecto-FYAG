"""Escrituras de dominio comercial bajo bloqueo del presupuesto persistido.

La autorización por rol corresponde a la futura capa de entrada. Los actores
se reciben como usuarios internos, nunca como strings o roles del consumidor.
"""

from collections.abc import Mapping
from functools import wraps

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from .calculos import sumar_monto_neto
from .exceptions import (
    ClienteInactivo,
    DatosInvalidos,
    EstadoIncompatible,
    MotivoObligatorio,
    OrdenDuplicado,
    RecursoNoEncontrado,
    PresupuestoUtilizado,
)
from .models import Cliente, Presupuesto, PresupuestoEvento, PresupuestoItem


Estado = Presupuesto.Estado
CAMPOS_CABECERA = frozenset({
    "cliente", "descripcion",
})
CAMPOS_ITEM = frozenset({
    "descripcion", "cantidad", "unidad", "precio_unitario", "orden",
})


def _operacion(funcion):
    """Traduce errores conocidos después del rollback del bloque atómico."""
    @wraps(funcion)
    def ejecutar(*args, **kwargs):
        try:
            with transaction.atomic():
                return funcion(*args, **kwargs)
        except IntegrityError as exc:
            diagnostico = getattr(exc.__cause__, "diag", None)
            if getattr(diagnostico, "constraint_name", None) == (
                "presupuesto_item_orden_unico"
            ):
                raise OrdenDuplicado() from exc
            raise
        except ValidationError as exc:
            errores = (
                exc.message_dict if hasattr(exc, "message_dict") else {}
            )
            # Los errores de constraints de full_clean son internos.
            if "__all__" in errores:
                errores["__all__"] = ["La combinación de datos no es válida."]
            raise DatosInvalidos(errores) from exc
    return ejecutar


def _pk(referencia, modelo):
    pk = referencia.pk if isinstance(referencia, modelo) else referencia
    if type(pk) is not int or pk <= 0:
        raise DatosInvalidos({"id": ["Indique un identificador válido."]})
    return pk


def _presupuesto_bloqueado(referencia):
    try:
        return Presupuesto.objects.select_for_update().get(
            pk=_pk(referencia, Presupuesto)
        )
    except Presupuesto.DoesNotExist as exc:
        raise RecursoNoEncontrado() from exc


def _cliente_activo_bloqueado(referencia):
    try:
        cliente = Cliente.objects.select_for_update().get(
            pk=_pk(referencia, Cliente)
        )
    except Cliente.DoesNotExist as exc:
        raise DatosInvalidos({"cliente": ["El cliente no existe."]}) from exc
    if not cliente.activo:
        raise ClienteInactivo()
    return cliente


def _usuario_interno(usuario):
    if (
        not isinstance(usuario, get_user_model())
        or not usuario.is_authenticated
        or usuario.pk is None
        or usuario._state.adding
    ):
        raise DatosInvalidos({"usuario": ["Se requiere un usuario interno."]})
    return usuario


def _datos_permitidos(datos, campos, *, completos=False):
    if not isinstance(datos, Mapping):
        raise DatosInvalidos()
    errores = {
        campo: ["No es un campo editable."] for campo in datos
        if campo not in campos
    }
    if completos:
        errores.update({
            campo: ["Este campo es obligatorio."] for campo in campos
            if campo not in datos
        })
    if errores:
        raise DatosInvalidos(errores)


def _exigir_borrador(presupuesto):
    if presupuesto.estado != Estado.BORRADOR:
        raise EstadoIncompatible()


def _evento(presupuesto, anterior, usuario, motivo=""):
    return PresupuestoEvento.objects.create(
        presupuesto=presupuesto, estado_anterior=anterior,
        estado_nuevo=presupuesto.estado,
        registrado_por=_usuario_interno(usuario), motivo=motivo,
    )


@_operacion
def crear_presupuesto(*, cliente, descripcion, usuario):
    cliente = _cliente_activo_bloqueado(cliente)
    presupuesto = Presupuesto.objects.create(
        cliente=cliente, descripcion=descripcion,
        requiere_aprobacion_gerencia=True,
        creado_por=_usuario_interno(usuario),
    )
    _evento(presupuesto, None, usuario)
    return presupuesto


@_operacion
def modificar_presupuesto(presupuesto, cambios):
    actual = _presupuesto_bloqueado(presupuesto)
    _exigir_borrador(actual)
    _datos_permitidos(cambios, CAMPOS_CABECERA)
    for campo, valor in cambios.items():
        if campo == "cliente":
            valor = _cliente_activo_bloqueado(valor)
        setattr(actual, campo, valor)
    actual.save()
    return actual


def _item_del_presupuesto(presupuesto, referencia):
    try:
        return PresupuestoItem.objects.get(
            presupuesto=presupuesto, pk=_pk(referencia, PresupuestoItem)
        )
    except PresupuestoItem.DoesNotExist as exc:
        raise RecursoNoEncontrado() from exc


def _guardar_item(item):
    item.full_clean(validate_constraints=False)
    if PresupuestoItem.objects.filter(
        presupuesto_id=item.presupuesto_id, orden=item.orden
    ).exclude(pk=item.pk).exists():
        raise OrdenDuplicado()
    item.save()


def _actualizar_fecha(presupuesto):
    presupuesto.save(update_fields=["actualizado_en"])


@_operacion
def crear_item(presupuesto, datos):
    actual = _presupuesto_bloqueado(presupuesto)
    _exigir_borrador(actual)
    _datos_permitidos(datos, CAMPOS_ITEM, completos=True)
    item = PresupuestoItem(presupuesto=actual, **datos)
    _guardar_item(item)
    _actualizar_fecha(actual)
    return item


@_operacion
def modificar_item(presupuesto, item, cambios):
    actual = _presupuesto_bloqueado(presupuesto)
    _exigir_borrador(actual)
    _datos_permitidos(cambios, CAMPOS_ITEM)
    item = _item_del_presupuesto(actual, item)
    for campo, valor in cambios.items():
        setattr(item, campo, valor)
    _guardar_item(item)
    _actualizar_fecha(actual)
    return item


@_operacion
def eliminar_item(presupuesto, item):
    actual = _presupuesto_bloqueado(presupuesto)
    _exigir_borrador(actual)
    _item_del_presupuesto(actual, item).delete()
    _actualizar_fecha(actual)


def _lineas_y_total(presupuesto):
    # Consulta nueva, sin reutilizar un prefetch o total recibido del caller.
    lineas = list(PresupuestoItem.objects.filter(presupuesto=presupuesto))
    for linea in lineas:
        linea.full_clean(validate_constraints=False)
    return lineas, sumar_monto_neto(linea.subtotal for linea in lineas)


@_operacion
def recalcular_monto_neto(presupuesto):
    actual = _presupuesto_bloqueado(presupuesto)
    return _lineas_y_total(actual)[1]


def _validar_salida(presupuesto):
    _cliente_activo_bloqueado(presupuesto.cliente_id)
    presupuesto.full_clean()
    lineas, neto = _lineas_y_total(presupuesto)
    if not lineas:
        raise DatosInvalidos({"items": ["Debe existir al menos un ítem."]})
    if neto <= 0:
        raise DatosInvalidos({
            "monto_neto": ["El monto neto debe ser positivo."],
        })


def _motivo_normalizado(motivo, obligatorio):
    if not isinstance(motivo, str):
        raise DatosInvalidos({"motivo": ["El motivo debe ser un string."]})
    motivo = motivo.strip()
    if obligatorio and not motivo:
        raise MotivoObligatorio()
    if len(motivo) > 2000:
        raise DatosInvalidos({"motivo": ["Máximo 2000 caracteres."]})
    return motivo


@_operacion
def _transicionar(
    presupuesto, usuario, motivo, *, origenes, destino,
    motivo_obligatorio=False,
):
    actual = _presupuesto_bloqueado(presupuesto)
    anterior = actual.estado
    if anterior not in origenes:
        raise EstadoIncompatible()
    if destino == Estado.ANULADO:
        # Ambos flujos bloquean primero el mismo presupuesto persistido.
        # Importación local para evitar acoplar la carga inicial de Comercial.
        from apps.obras.models import Obra
        if Obra.objects.filter(presupuesto_id=actual.pk).exists():
            raise PresupuestoUtilizado()
    motivo = _motivo_normalizado(motivo, motivo_obligatorio)
    if anterior == Estado.BORRADOR and destino != Estado.ANULADO:
        _validar_salida(actual)
    actual.estado = destino
    actual.save(update_fields=["estado", "actualizado_en"])
    _evento(actual, anterior, usuario, motivo)
    return actual


def enviar_gerencia(presupuesto, usuario, motivo=""):
    return _transicionar(
        presupuesto, usuario, motivo, origenes={Estado.BORRADOR},
        destino=Estado.PENDIENTE_GERENCIA,
    )


def aprobar_gerencia(presupuesto, usuario, motivo=""):
    return _transicionar(
        presupuesto, usuario, motivo, origenes={Estado.PENDIENTE_GERENCIA},
        destino=Estado.APROBADO_GERENCIA,
    )


def rechazar_gerencia(presupuesto, usuario, motivo):
    return _transicionar(
        presupuesto, usuario, motivo, origenes={Estado.PENDIENTE_GERENCIA},
        destino=Estado.RECHAZADO_GERENCIA,
        motivo_obligatorio=True,
    )


def enviar_cliente(presupuesto, usuario, motivo=""):
    return _transicionar(
        presupuesto, usuario, motivo,
        origenes={Estado.APROBADO_GERENCIA},
        destino=Estado.ENVIADO_CLIENTE,
    )


def registrar_aprobacion_cliente(presupuesto, usuario, motivo=""):
    return _transicionar(
        presupuesto, usuario, motivo, origenes={Estado.ENVIADO_CLIENTE},
        destino=Estado.APROBADO_CLIENTE,
    )


def registrar_rechazo_cliente(presupuesto, usuario, motivo):
    return _transicionar(
        presupuesto, usuario, motivo, origenes={Estado.ENVIADO_CLIENTE},
        destino=Estado.RECHAZADO_CLIENTE, motivo_obligatorio=True,
    )


def anular_presupuesto(presupuesto, usuario, motivo):
    return _transicionar(
        presupuesto, usuario, motivo, origenes={
            Estado.BORRADOR, Estado.PENDIENTE_GERENCIA,
            Estado.APROBADO_GERENCIA,
            Estado.ENVIADO_CLIENTE, Estado.APROBADO_CLIENTE,
        }, destino=Estado.ANULADO, motivo_obligatorio=True,
    )


@_operacion
def crear_revision(presupuesto, usuario):
    origen = _presupuesto_bloqueado(presupuesto)
    if origen.estado not in {
        Estado.RECHAZADO_GERENCIA, Estado.RECHAZADO_CLIENTE, Estado.ANULADO,
    }:
        raise EstadoIncompatible()
    cliente = _cliente_activo_bloqueado(origen.cliente_id)
    revision = Presupuesto.objects.create(
        cliente=cliente, descripcion=origen.descripcion,
        requiere_aprobacion_gerencia=True,
        presupuesto_origen=origen, creado_por=_usuario_interno(usuario),
    )
    for linea in PresupuestoItem.objects.filter(presupuesto=origen):
        copia = PresupuestoItem(
            presupuesto=revision,
            **{campo: getattr(linea, campo) for campo in CAMPOS_ITEM},
        )
        _guardar_item(copia)
    _evento(revision, None, usuario)
    return revision
