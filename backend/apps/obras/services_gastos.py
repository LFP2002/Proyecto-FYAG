"""004B-3: materiales y otros gastos directos.

Orden de bloqueos: Presupuesto -> Obra -> GastoObra -> evento. Toda escritura
revalida estado, vigencia y cantidades desde la base de datos bajo lock y
confirma junto a su evento en una sola transacción.
"""

import re
from datetime import date
from decimal import Decimal, ROUND_HALF_UP, localcontext

from django.core.validators import DecimalValidator
from django.utils import timezone

from apps.comercial.calculos import CANTIDAD_MAXIMA, CENTAVO, PRECIO_MAXIMO

from . import services as base
from .exceptions import (
    DatosInvalidos, EstadoIncompatible, RecursoNoEncontrado,
)
from .models import CostoObraEvento, GastoObra, Obra


CANTIDAD_MINIMA = Decimal("0.001")
COSTO_MINIMO = Decimal("0.00")
CAMPOS_CREAR = frozenset({
    "tipo", "descripcion", "unidad", "cantidad", "costo_unitario_neto",
    "fecha_gasto", "referencia_respaldo", "observacion",
})
OBLIGATORIOS = frozenset({
    "tipo", "descripcion", "unidad", "cantidad", "costo_unitario_neto",
    "fecha_gasto",
})
CAMPOS_EDITAR = CAMPOS_CREAR | {"motivo"}
TEXTO_DECIMAL = re.compile(r"[0-9]+(?:\.[0-9]+)?")
EDITABLES = {Obra.Estado.EN_PROCESO, Obra.Estado.SUSPENDIDA}


def _decimal(valor, campo, *, max_digits, decimal_places, minimo, maximo, escala):
    # En el borde HTTP la entrada debe ser un string decimal; el serializer ya
    # lo convierte a Decimal. Nada de floats, bool, NaN, exponentes ni comas.
    # La escala se rechaza, nunca se redondea.
    if isinstance(valor, str):
        texto = valor.strip()
        if not TEXTO_DECIMAL.fullmatch(texto):
            raise DatosInvalidos({campo: ["Formato decimal inválido."]})
        numero = Decimal(texto)
    elif type(valor) is Decimal:
        numero = valor
    else:
        raise DatosInvalidos({campo: ["Envíe un string decimal con punto."]})
    try:
        DecimalValidator(max_digits, decimal_places)(numero)
    except Exception:  # ValidationError de Django: exceso de dígitos o escala.
        raise DatosInvalidos({
            campo: [f"Use hasta {max_digits - decimal_places} enteros y "
                    f"{decimal_places} decimales como máximo."]
        }) from None
    if not numero.is_finite() or not minimo <= numero <= maximo:
        raise DatosInvalidos({campo: ["Valor fuera del rango permitido."]})
    with localcontext() as contexto:
        contexto.prec = 50
        return numero.quantize(escala)


def _cantidad(valor, campo="cantidad"):
    return _decimal(
        valor, campo, max_digits=12, decimal_places=3,
        minimo=CANTIDAD_MINIMA, maximo=CANTIDAD_MAXIMA,
        escala=Decimal("0.001"),
    )


def _costo(valor, campo="costo_unitario_neto"):
    return _decimal(
        valor, campo, max_digits=15, decimal_places=2,
        minimo=COSTO_MINIMO, maximo=PRECIO_MAXIMO, escala=CENTAVO,
    )


def _tipo(valor):
    if not isinstance(valor, str) or valor not in GastoObra.Tipo.values:
        raise DatosInvalidos({"tipo": ["Tipo de gasto desconocido."]})
    return valor


def _texto_opcional(datos, campo, maximo):
    if campo not in datos:
        return ""
    return base._texto(datos[campo], campo, obligatorio=False, maximo=maximo)


def _obra(referencia):
    return base._obra_bloqueada(referencia)


def _editable(obra):
    if obra.estado not in EDITABLES:
        raise EstadoIncompatible()


def _gasto(obra, referencia):
    try:
        return GastoObra.objects.select_for_update().get(
            pk=base._id(referencia, GastoObra, "gasto"), obra=obra,
        )
    except GastoObra.DoesNotExist as exc:
        raise RecursoNoEncontrado() from exc


def _snapshot(gasto, **extras):
    datos = {
        "tipo": gasto.tipo,
        "descripcion": gasto.descripcion,
        "unidad": gasto.unidad,
        "cantidad": str(gasto.cantidad),
        "cantidad_devuelta": str(gasto.cantidad_devuelta),
        "costo_unitario_neto": str(gasto.costo_unitario_neto),
        "fecha_gasto": gasto.fecha_gasto.isoformat(),
        "referencia_respaldo": gasto.referencia_respaldo,
        "observacion": gasto.observacion,
        "vigente": gasto.vigente,
        "subtotal": str(gasto.subtotal),
    }
    datos.update(extras)
    return datos


def _evento(gasto, tipo, actor, motivo, anteriores, **extras):
    from .services_costos import invalidar
    control = invalidar(gasto.obra, actor, motivo, gastos=True)
    extras["version_costos"] = control.version_actual
    return CostoObraEvento.objects.create(
        obra=gasto.obra, gasto=gasto, tipo=tipo, registrado_por=actor,
        motivo=motivo, datos_anteriores=anteriores,
        datos_nuevos=_snapshot(gasto, **extras),
    )


def _fecha_ordinaria(fecha, obra, campo="fecha_gasto"):
    if fecha > timezone.localdate():
        raise DatosInvalidos({campo: ["No puede ser una fecha futura."]})
    if obra.iniciado_en and fecha < timezone.localdate(obra.iniciado_en):
        raise DatosInvalidos({
            campo: ["No puede ser anterior al inicio de la Obra sin corrección motivada."],
        })


def _fecha_no_futura(fecha, campo):
    if fecha > timezone.localdate():
        raise DatosInvalidos({campo: ["No puede ser una fecha futura."]})


def _validar_fechas_de_devolucion(gasto):
    """El gasto no puede fecharse después de una devolución ya registrada."""
    eventos = CostoObraEvento.objects.filter(
        gasto=gasto, tipo=CostoObraEvento.Tipo.DEVOLUCION,
    ).values_list("datos_nuevos", flat=True)
    for datos in eventos:
        detalle = datos.get("devolucion") if isinstance(datos, dict) else None
        fecha_texto = detalle.get("fecha") if isinstance(detalle, dict) else None
        if not isinstance(fecha_texto, str):
            raise EstadoIncompatible(
                "No fue posible verificar las devoluciones registradas."
            )
        try:
            fecha = date.fromisoformat(fecha_texto)
        except ValueError:
            raise EstadoIncompatible(
                "No fue posible verificar las devoluciones registradas."
            ) from None
        if gasto.fecha_gasto > fecha:
            raise DatosInvalidos({
                "fecha_gasto": [
                    "No puede ser posterior a las devoluciones registradas."
                ],
            })


@base._operacion
def crear_gasto(obra, datos, usuario):
    actor = base._actor_autorizado(usuario, base.SUPERVISOR)
    obra = _obra(obra)
    base._campos_validos(datos, CAMPOS_CREAR, OBLIGATORIOS)
    _editable(obra)
    tipo = _tipo(datos["tipo"])
    descripcion = base._texto(datos["descripcion"], "descripcion", maximo=500)
    unidad = base._texto(datos["unidad"], "unidad", maximo=30)
    cantidad = _cantidad(datos["cantidad"])
    costo = _costo(datos["costo_unitario_neto"])
    fecha = base._fecha(datos["fecha_gasto"], campo="fecha_gasto")
    referencia = _texto_opcional(datos, "referencia_respaldo", 500)
    observacion = _texto_opcional(datos, "observacion", 2000)
    _fecha_ordinaria(fecha, obra)
    gasto = GastoObra(
        obra=obra, tipo=tipo, descripcion=descripcion, unidad=unidad,
        cantidad=cantidad, cantidad_devuelta=Decimal("0.000"),
        costo_unitario_neto=costo, fecha_gasto=fecha,
        referencia_respaldo=referencia, observacion=observacion,
        vigente=True, registrado_por=actor,
    )
    gasto.full_clean()
    gasto.save()
    _evento(gasto, "ALTA", actor, "Alta de gasto registrada por el Supervisor", {})
    return gasto


@base._operacion
def editar_gasto(obra, referencia, datos, usuario):
    actor = base._actor_autorizado(usuario, base.SUPERVISOR)
    obra = _obra(obra)
    gasto = _gasto(obra, referencia)
    base._campos_validos(datos, CAMPOS_EDITAR)
    _editable(obra)
    if not gasto.vigente:
        raise EstadoIncompatible("El gasto está anulado y no admite modificaciones.")
    anteriores = _snapshot(gasto)
    cambios = False
    if "tipo" in datos:
        tipo = _tipo(datos["tipo"])
        if tipo != gasto.tipo:
            if tipo != GastoObra.Tipo.MATERIAL and gasto.cantidad_devuelta:
                raise DatosInvalidos({
                    "tipo": ["Un gasto con devoluciones solo puede ser MATERIAL."],
                })
            gasto.tipo = tipo
            cambios = True
    for campo, normalizar in (
        ("descripcion", lambda v: base._texto(v, "descripcion", maximo=500)),
        ("unidad", lambda v: base._texto(v, "unidad", maximo=30)),
        ("cantidad", _cantidad),
        ("costo_unitario_neto", _costo),
        ("fecha_gasto", lambda v: base._fecha(v, campo="fecha_gasto")),
        ("referencia_respaldo", lambda v: base._texto(
            v, "referencia_respaldo", obligatorio=False, maximo=500)),
        ("observacion", lambda v: base._texto(
            v, "observacion", obligatorio=False, maximo=2000)),
    ):
        if campo not in datos:
            continue
        valor = normalizar(datos[campo])
        if valor != getattr(gasto, campo):
            setattr(gasto, campo, valor)
            cambios = True
    if "fecha_gasto" in datos:
        # Una corrección fechada antes del inicio es admisible solo aquí,
        # porque exige motivo y genera auditoría; nunca en el alta ordinaria.
        _fecha_no_futura(gasto.fecha_gasto, "fecha_gasto")
    if not cambios:
        if "motivo" in datos:
            base._motivo(datos["motivo"], obligatorio=False)
        return gasto
    motivo = base._motivo(datos.get("motivo", ""), obligatorio=True)
    if gasto.cantidad_devuelta > gasto.cantidad:
        raise DatosInvalidos({
            "cantidad": ["No puede ser menor a la cantidad ya devuelta."],
        })
    if "fecha_gasto" in datos and gasto.tipo == GastoObra.Tipo.MATERIAL:
        # La fecha real de cada devolución vive en su evento, no en el gasto.
        _validar_fechas_de_devolucion(gasto)
    gasto.full_clean()
    gasto.save(update_fields=[
        "tipo", "descripcion", "unidad", "cantidad", "costo_unitario_neto",
        "fecha_gasto", "referencia_respaldo", "observacion", "actualizado_en",
    ])
    _evento(gasto, "CORRECCION", actor, motivo, anteriores)
    return gasto


@base._operacion
def devolver_gasto(obra, referencia, datos, usuario):
    actor = base._actor_autorizado(usuario, base.SUPERVISOR)
    obra = _obra(obra)
    gasto = _gasto(obra, referencia)
    base._campos_validos(
        datos, {"cantidad", "fecha_devolucion", "motivo"},
        {"cantidad", "fecha_devolucion", "motivo"},
    )
    _editable(obra)
    if not gasto.vigente:
        raise EstadoIncompatible("El gasto está anulado y no admite devoluciones.")
    if gasto.tipo != GastoObra.Tipo.MATERIAL:
        raise DatosInvalidos({
            "cantidad": ["Solo los materiales admiten devoluciones."],
        })
    motivo = base._motivo(datos["motivo"], obligatorio=True)
    cantidad = _cantidad(datos["cantidad"], campo="cantidad")
    fecha = base._fecha(datos["fecha_devolucion"], campo="fecha_devolucion")
    _fecha_no_futura(fecha, "fecha_devolucion")
    if fecha < gasto.fecha_gasto:
        raise DatosInvalidos({
            "fecha_devolucion": ["No puede ser anterior a la fecha del gasto."],
        })
    acumulada = gasto.cantidad_devuelta + cantidad
    if acumulada > gasto.cantidad:
        raise DatosInvalidos({
            "cantidad": ["La devolución supera la cantidad registrada."],
        })
    anteriores = _snapshot(gasto)
    gasto.cantidad_devuelta = acumulada
    gasto.full_clean()
    gasto.save(update_fields=["cantidad_devuelta", "actualizado_en"])
    _evento(
        gasto, "DEVOLUCION", actor, motivo, anteriores,
        devolucion={"cantidad": str(cantidad), "fecha": fecha.isoformat()},
    )
    return gasto


@base._operacion
def anular_gasto(obra, referencia, datos, usuario):
    actor = base._actor_autorizado(usuario, base.SUPERVISOR)
    obra = _obra(obra)
    gasto = _gasto(obra, referencia)
    base._campos_validos(datos, {"motivo"}, {"motivo"})
    _editable(obra)
    if not gasto.vigente:
        raise EstadoIncompatible("El gasto ya está anulado.")
    motivo = base._motivo(datos["motivo"], obligatorio=True)
    anteriores = _snapshot(gasto)
    gasto.vigente = False
    gasto.anulado_por = actor
    gasto.anulado_en = timezone.now()
    gasto.motivo_anulacion = motivo
    gasto.full_clean()
    gasto.save(update_fields=[
        "vigente", "anulado_por", "anulado_en", "motivo_anulacion",
        "actualizado_en",
    ])
    _evento(
        gasto, "ANULACION", actor, motivo, anteriores,
        anulacion={
            "anulado_por": actor.pk,
            "anulado_en": gasto.anulado_en.isoformat(),
            "motivo": motivo,
        },
    )
    return gasto
