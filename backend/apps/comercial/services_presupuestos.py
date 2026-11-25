"""Escrituras de dominio comercial bajo bloqueo del presupuesto persistido.

La autorización se revalida en dominio antes y después de adquirir locks.
"""

from collections.abc import Mapping
from functools import wraps
from inspect import signature

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.inventario.models import ArticuloInventario

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
from .permissions_presupuestos import revalidar_presupuestos, presupuestos_visibles, S


Estado = Presupuesto.Estado
CAMPOS_CABECERA = frozenset({
    "cliente", "descripcion",
})
CAMPOS_ITEM = frozenset({
    "descripcion", "cantidad", "unidad", "precio_unitario", "orden",
})
CAMPOS_ITEM_EDITABLES = CAMPOS_ITEM | {"articulo"}


def _datos_item(datos, *, completos=False):
    _datos_permitidos(datos, CAMPOS_ITEM_EDITABLES)
    if completos:
        _datos_permitidos(
            {campo: valor for campo, valor in datos.items() if campo in CAMPOS_ITEM},
            CAMPOS_ITEM, completos=True,
        )


def _aplicar_item(item, cambios):
    """Conservar la instantánea salvo selección explícita de otro material."""
    cambios = dict(cambios)
    articulo_id = cambios.pop("articulo", item.articulo_id)
    if articulo_id is not None and (
        type(articulo_id) is not int or not 0 < articulo_id <= 9223372036854775807
    ):
        raise DatosInvalidos({"articulo": ["Indique un identificador válido."]})
    if articulo_id != item.articulo_id and articulo_id is not None:
        articulo = ArticuloInventario.objects.select_for_update(no_key=True).filter(
            pk=articulo_id, activo=True
        ).first()
        if articulo is None:
            raise DatosInvalidos({"articulo": ["Material no disponible."]})
        # El precio de venta no proviene del catálogo. Solo identidad y unidad.
        for campo, esperado in (("descripcion", articulo.nombre.strip()), ("unidad", articulo.unidad)):
            if campo in cambios and (
                not isinstance(cambios[campo], str) or cambios[campo].strip() != esperado
            ):
                raise DatosInvalidos({campo: ["El material cambió; seleccione nuevamente el catálogo."]})
            cambios[campo] = esperado
        item.articulo_id = articulo.pk
        item.codigo_articulo = articulo.codigo
    elif articulo_id is None:
        item.articulo_id = None
        item.codigo_articulo = ""
    else:
        for campo in ("descripcion", "unidad"):
            if campo in cambios and (
                not isinstance(cambios[campo], str) or cambios[campo].strip() != getattr(item, campo)
            ):
                raise DatosInvalidos({campo: ["Seleccione otro material o desvincule la línea."]})
    for campo, valor in cambios.items():
        setattr(item, campo, valor)



def _operacion(funcion):
    """Traduce errores conocidos después del rollback del bloque atómico."""
    @wraps(funcion)
    def ejecutar(*args, **kwargs):
        try:
            with transaction.atomic():
                parametros = signature(funcion).bind(*args, **kwargs).arguments
                usuario = parametros.get('usuario')
                # recalcular_monto_neto es un cálculo interno, sin escrituras.
                inicial = revalidar_presupuestos(usuario) if 'usuario' in signature(funcion).parameters else None
                resultado = funcion(*args, **kwargs)
                if inicial is not None:
                    final = revalidar_presupuestos(usuario, bloquear=True)
                    if final.rol != inicial.rol:
                        from rest_framework.exceptions import PermissionDenied
                        raise PermissionDenied('Operación presupuestaria no autorizada.')
                return resultado
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


def _presupuesto_bloqueado(referencia, usuario=None):
    try:
        queryset = Presupuesto.objects.all()
        if usuario is not None:
            queryset = presupuestos_visibles(usuario, queryset)
        return queryset.select_for_update().get(
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


def _usuario_interno(usuario, accion='elaborar', presupuesto=None):
    return revalidar_presupuestos(usuario, accion, presupuesto)


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
        registrado_por=_usuario_interno(usuario, presupuesto=presupuesto), motivo=motivo,
    )


@_operacion
def crear_presupuesto(*, cliente, descripcion, usuario):
    _usuario_interno(usuario)
    cliente = _cliente_activo_bloqueado(cliente)
    presupuesto = Presupuesto.objects.create(
        cliente=cliente, descripcion=descripcion,
        requiere_aprobacion_gerencia=False,
        creado_por=_usuario_interno(usuario),
    )
    _evento(presupuesto, None, usuario)
    return presupuesto


@_operacion
def modificar_presupuesto(presupuesto, cambios, usuario=None):
    _usuario_interno(usuario)
    actual = _presupuesto_bloqueado(presupuesto, usuario)
    _usuario_interno(usuario, presupuesto=actual)
    _exigir_borrador(actual)
    _datos_permitidos(cambios, CAMPOS_CABECERA)
    for campo, valor in cambios.items():
        if campo == "cliente":
            valor = _cliente_activo_bloqueado(valor)
        setattr(actual, campo, valor)
    _usuario_interno(usuario)
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
def crear_item(presupuesto, datos, usuario=None):
    _usuario_interno(usuario)
    actual = _presupuesto_bloqueado(presupuesto, usuario)
    _usuario_interno(usuario, presupuesto=actual)
    _exigir_borrador(actual)
    _datos_item(datos, completos=True)
    item = PresupuestoItem(presupuesto=actual)
    _aplicar_item(item, datos)
    _guardar_item(item)
    _actualizar_fecha(actual)
    return item


@_operacion
def modificar_item(presupuesto, item, cambios, usuario=None):
    _usuario_interno(usuario)
    actual = _presupuesto_bloqueado(presupuesto, usuario)
    _usuario_interno(usuario, presupuesto=actual)
    _exigir_borrador(actual)
    _datos_item(cambios)
    item = _item_del_presupuesto(actual, item)
    _aplicar_item(item, cambios)
    _guardar_item(item)
    _actualizar_fecha(actual)
    return item


@_operacion
def eliminar_item(presupuesto, item, usuario=None):
    _usuario_interno(usuario)
    actual = _presupuesto_bloqueado(presupuesto, usuario)
    _usuario_interno(usuario, presupuesto=actual)
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
    motivo_obligatorio=False, autorizacion='decision_finanzas',
):
    _usuario_interno(usuario, autorizacion)
    actual = _presupuesto_bloqueado(presupuesto, usuario)
    _usuario_interno(usuario, autorizacion, actual)
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
    _usuario_interno(usuario, autorizacion, actual)
    actual.estado = destino
    actual.save(update_fields=["estado", "actualizado_en"])
    _evento(actual, anterior, usuario, motivo)
    from apps.alertas.services import notificar_despues_commit
    notificar_despues_commit("PRESUPUESTO_PENDIENTE_GERENCIA", actual.pk)
    notificar_despues_commit("PRESUPUESTO_PENDIENTE_FINANZAS", actual.pk)
    return actual


def enviar_finanzas(presupuesto, usuario, motivo=""):
    return _transicionar(
        presupuesto, usuario, motivo, origenes={Estado.BORRADOR},
        destino=Estado.PENDIENTE_FINANZAS,
        autorizacion='enviar_revision',
    )


def aprobar_finanzas(presupuesto, usuario, motivo=""):
    return _transicionar(
        presupuesto, usuario, motivo,
        origenes={Estado.PENDIENTE_GERENCIA, Estado.PENDIENTE_FINANZAS},
        destino=Estado.APROBADO_FINANZAS,
    )


def rechazar_finanzas(presupuesto, usuario, motivo):
    return _transicionar(
        presupuesto, usuario, motivo,
        origenes={Estado.PENDIENTE_GERENCIA, Estado.PENDIENTE_FINANZAS},
        destino=Estado.RECHAZADO_FINANZAS,
        motivo_obligatorio=True,
    )


def enviar_cliente(presupuesto, usuario, motivo=""):
    return _transicionar(
        presupuesto, usuario, motivo,
        origenes={Estado.APROBADO_GERENCIA, Estado.APROBADO_FINANZAS},
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
            Estado.PENDIENTE_FINANZAS, Estado.APROBADO_FINANZAS,
            Estado.APROBADO_GERENCIA,
            Estado.ENVIADO_CLIENTE, Estado.APROBADO_CLIENTE,
        }, destino=Estado.ANULADO, motivo_obligatorio=True,
    )


@_operacion
def crear_revision(presupuesto, usuario):
    _usuario_interno(usuario, 'crear_revision')
    origen = _presupuesto_bloqueado(presupuesto, usuario)
    actor = _usuario_interno(usuario, 'crear_revision', origen)
    if actor.rol == S and origen.estado != Estado.RECHAZADO_FINANZAS:
        raise EstadoIncompatible()
    if origen.estado not in {
        Estado.RECHAZADO_FINANZAS, Estado.RECHAZADO_GERENCIA,
        Estado.RECHAZADO_CLIENTE, Estado.ANULADO,
    }:
        raise EstadoIncompatible()
    cliente = _cliente_activo_bloqueado(origen.cliente_id)
    revision = Presupuesto.objects.create(
        cliente=cliente, descripcion=origen.descripcion,
        requiere_aprobacion_gerencia=False,
        presupuesto_origen=origen, creado_por=_usuario_interno(usuario),
    )
    for linea in PresupuestoItem.objects.filter(presupuesto=origen):
        copia = PresupuestoItem(
            presupuesto=revision,
            articulo_id=linea.articulo_id, codigo_articulo=linea.codigo_articulo,
            **{campo: getattr(linea, campo) for campo in CAMPOS_ITEM},
        )
        _guardar_item(copia)
    _evento(revision, None, usuario)
    return revision


def enviar_gerencia(*args, **kwargs):
    from rest_framework.exceptions import PermissionDenied
    raise PermissionDenied("Acción gerencial retirada.")


aprobar_gerencia = enviar_gerencia
rechazar_gerencia = enviar_gerencia
