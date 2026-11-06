from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.http import Http404

from .models import Cliente


ERRORES_UNICIDAD = {
    "cliente_rut_unico": "Ya existe un cliente con este RUT.",
    "cliente_documento_unico": (
        "Ya existe un cliente con esta identificación extranjera."
    ),
}


def validar_cliente(cliente):
    """Valida el estado completo sin exponer constraints internos."""
    cliente.full_clean(validate_unique=False, validate_constraints=False)
    candidatos = Cliente.objects.exclude(pk=cliente.pk)
    tipo = cliente.tipo_identificacion
    if tipo == Cliente.TipoIdentificacion.RUT:
        constraint = "cliente_rut_unico"
        candidatos = candidatos.filter(
            tipo_identificacion=tipo,
            numero_identificacion=cliente.numero_identificacion,
        )
    elif tipo == Cliente.TipoIdentificacion.DOCUMENTO_EXTRANJERO:
        constraint = "cliente_documento_unico"
        candidatos = candidatos.filter(
            tipo_identificacion=tipo,
            pais_identificacion=cliente.pais_identificacion,
            tipo_documento_extranjero=cliente.tipo_documento_extranjero,
            numero_identificacion=cliente.numero_identificacion,
        )
    else:
        return
    if candidatos.exists():
        raise ValidationError({
            "numero_identificacion": ERRORES_UNICIDAD[constraint],
        })


def _cliente_bloqueado(pk):
    try:
        return Cliente.objects.select_for_update().get(pk=pk)
    except Cliente.DoesNotExist as exc:
        raise Http404("Cliente no encontrado.") from exc


def guardar_cliente(datos, instancia=None):
    """Revalida PATCH contra la fila actual y protege carreras de unicidad."""
    try:
        with transaction.atomic():
            cliente = (
                _cliente_bloqueado(instancia.pk) if instancia else Cliente()
            )
            for campo, valor in datos.items():
                setattr(cliente, campo, valor)
            validar_cliente(cliente)
            cliente.save()
            return cliente
    except IntegrityError as exc:
        diagnostico = getattr(exc.__cause__, "diag", None)
        nombre = getattr(diagnostico, "constraint_name", None)
        if nombre not in ERRORES_UNICIDAD:
            raise
        raise ValidationError({
            "numero_identificacion": ERRORES_UNICIDAD[nombre],
        }) from exc


def _cambiar_estado(cliente, activo):
    with transaction.atomic():
        actual = _cliente_bloqueado(cliente.pk)
        if actual.activo != activo:
            actual.activo = activo
            actual.save(update_fields=["activo", "actualizado_en"])
        return actual


def activar_cliente(cliente):
    return _cambiar_estado(cliente, True)


def desactivar_cliente(cliente):
    return _cambiar_estado(cliente, False)
