"""007A: Presupuesto -> Obra -> documento/cierre -> evento. Sin locks de Usuario."""
from functools import wraps

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, models, transaction
from django.utils import timezone
from rest_framework.exceptions import APIException, AuthenticationFailed, NotFound, PermissionDenied, ValidationError

from apps.comercial.models import Presupuesto
from apps.obras.models import Obra, CierreCostosObra, CortesiaObra
from apps.usuarios.models import Usuario
from .models import DocumentoCobro, CierreSinCobro, FinanzasEvento, PagoDocumento
from .serializers_documentos import DocumentoCrearSerializer, DocumentoRevertirSerializer, SinCobroCrearSerializer


class ConflictoFinanciero(APIException):
    status_code = 409

    def __init__(self, code, detail):
        super().__init__({"code": code, "detail": detail})


def operacion(func):
    @wraps(func)
    def ejecutar(*args, **kwargs):
        try:
            with transaction.atomic():
                return func(*args, **kwargs)
        except DjangoValidationError as exc:
            raise ValidationError(exc.message_dict if hasattr(exc, "message_dict") else {"non_field_errors": exc.messages}) from None
        except IntegrityError as exc:
            name = getattr(getattr(exc.__cause__, "diag", None), "constraint_name", "")
            if name in {"fin_documento_folio_unico", "fin_documento_vigente_unico"}:
                raise ConflictoFinanciero("documento_duplicado", "Ya existe un registro documental para esa Obra o folio/tipo.") from None
            # OneToOne sin nombre explícito: se serializa normalmente por Obra.
            if name == "finanzas_cierresincobro_obra_id_key":
                raise ConflictoFinanciero("sin_cobro_ya_registrado", "La Obra ya tiene cierre administrativo sin cobro.") from None
            raise
    return ejecutar


def actor_financiero(actor):
    if not isinstance(actor, Usuario) or actor.pk is None:
        raise PermissionDenied("Operación no autorizada.")
    actual = Usuario.objects.filter(pk=actor.pk, is_active=True, rol=Usuario.Rol.ADMINISTRATIVO_FINANZAS).first()
    if actual is None:
        raise PermissionDenied("Operación no autorizada.")
    if actual.sesion_version != actor.sesion_version:
        raise AuthenticationFailed("Sesión no disponible.")
    return actual


def identificador(value):
    if type(value) is not int or not 0 < value <= 9223372036854775807:
        raise ValidationError({"id": "Se requiere entero positivo dentro de rango."})
    return value


def obra_bloqueada(pk):
    pk = identificador(pk)
    root = Obra.objects.filter(pk=pk).values_list("presupuesto_id", flat=True).first()
    if root is None:
        raise NotFound("Obra no encontrada.")
    presupuesto = Presupuesto.objects.select_for_update().get(pk=root)
    obra = Obra.objects.select_for_update().get(pk=pk)
    if obra.presupuesto_id != root:
        raise ConflictoFinanciero("origen_inconsistente", "La referencia de origen cambió.")
    obra.presupuesto = presupuesto
    return obra


def elegibilidad(obra):
    if obra.estado != Obra.Estado.FINALIZADA:
        raise ConflictoFinanciero("obra_no_finalizada", "Se requiere una Obra finalizada.")
    if obra.presupuesto.estado != Presupuesto.Estado.APROBADO_CLIENTE:
        raise ConflictoFinanciero("presupuesto_no_aprobado", "Se requiere origen aprobado por el cliente.")
    if not CierreCostosObra.objects.filter(obra=obra).exists():
        raise ConflictoFinanciero("cierre_costos_requerido", "Se requiere cierre histórico de costos.")


def datos(serializer_class, payload):
    serializer = serializer_class(data=payload)
    serializer.is_valid(raise_exception=True)
    return dict(serializer.validated_data)


def evento(**kwargs):
    registro = FinanzasEvento.objects.create(**kwargs)
    documento_id = registro.documento_id
    if registro.pago_id:
        documento_id = kwargs["pago"].documento_id
    if documento_id:
        from apps.alertas.services import notificar_despues_commit
        notificar_despues_commit("COBRANZA_VENCIDA", documento_id)
    return registro


@operacion
def registrar_documento(payload, actor):
    actor = actor_financiero(actor)
    data = datos(DocumentoCrearSerializer, payload)
    obra = obra_bloqueada(data.pop("obra"))
    actor = actor_financiero(actor)  # Releer después de cualquier espera por raíz.
    elegibilidad(obra)
    if CierreSinCobro.objects.filter(obra=obra).exists():
        raise ConflictoFinanciero("sin_cobro_ya_registrado", "La Obra tiene cierre administrativo sin cobro.")
    if CortesiaObra.objects.filter(obra=obra, tipo="SIN_COBRO").exists():
        raise ConflictoFinanciero("cortesia_sin_cobro", "La Obra está autorizada sin cobro.")
    if (DocumentoCobro.objects.filter(obra=obra, estado="VIGENTE").exists()
        or DocumentoCobro.objects.filter(tipo_documento=data["tipo_documento"], folio_externo=data["folio_externo"]).exists()):
        raise ConflictoFinanciero("documento_duplicado", "Ya existe un registro documental para esa Obra o folio/tipo.")
    if data["monto_neto"] != obra.presupuesto.monto_neto:
        raise ConflictoFinanciero("monto_no_coincide", "El neto documental no coincide con el presupuesto aprobado.")
    documento = DocumentoCobro.objects.create(obra=obra, registrado_por=actor, **data)
    snapshot = {key: (format(value, ".2f") if key.startswith("monto_") else value.isoformat() if key.startswith("fecha_") else value) for key, value in data.items()}
    snapshot.update(obra=obra.pk, estado="VIGENTE")
    evento(documento=documento, tipo="DOCUMENTO_REGISTRADO", actor=actor, datos_nuevos=snapshot)
    return documento


@operacion
def revertir_documento(pk, payload, actor):
    actor = actor_financiero(actor)
    data = datos(DocumentoRevertirSerializer, payload)
    obra_id = DocumentoCobro.objects.filter(pk=identificador(pk)).values_list("obra_id", flat=True).first()
    if obra_id is None:
        raise NotFound("Documento no encontrado.")
    obra = obra_bloqueada(obra_id)
    actor = actor_financiero(actor)
    documento = DocumentoCobro.objects.select_for_update().get(pk=pk)
    if documento.obra_id != obra.pk:
        raise ConflictoFinanciero("origen_inconsistente", "La referencia de origen cambió.")
    if documento.estado != "VIGENTE":
        raise ConflictoFinanciero("documento_ya_revertido", "El registro ya fue revertido administrativamente.")
    if PagoDocumento.objects.filter(documento=documento, activo=True).exists():
        raise ConflictoFinanciero("pagos_pendientes_de_resolver", "Resuelva administrativamente los pagos activos antes de revertir el documento.")
    documento.estado = "REVERTIDO"
    documento.revertido_por = actor
    documento.revertido_en = timezone.now()
    documento.motivo_reversion = data["motivo"]
    documento.referencia_rectificacion_externa = data["referencia_rectificacion_externa"]
    documento.full_clean(validate_unique=False, validate_constraints=False)
    # Única actualización autorizada; save()/queryset públicos son inmutables.
    models.Model.save(documento, update_fields=["estado", "revertido_por", "revertido_en", "motivo_reversion", "referencia_rectificacion_externa"])
    evento(documento=documento, tipo="DOCUMENTO_REVERTIDO", actor=actor, motivo=data["motivo"], datos_anteriores={"estado": "VIGENTE"}, datos_nuevos={"estado": "REVERTIDO", "motivo_reversion": data["motivo"], "referencia_rectificacion_externa": data["referencia_rectificacion_externa"]})
    return documento


@operacion
def registrar_sin_cobro(obra_id, payload, actor):
    actor = actor_financiero(actor)
    data = datos(SinCobroCrearSerializer, payload)
    obra = obra_bloqueada(obra_id)
    actor = actor_financiero(actor)
    elegibilidad(obra)
    if CierreSinCobro.objects.filter(obra=obra).exists():
        raise ConflictoFinanciero("sin_cobro_ya_registrado", "La Obra ya tiene cierre administrativo sin cobro.")
    cortesia = CortesiaObra.objects.filter(obra=obra, tipo="SIN_COBRO").first()
    if cortesia is None:
        raise ConflictoFinanciero("cortesia_requerida", "Se requiere autorización histórica sin cobro de Obras.")
    if DocumentoCobro.objects.filter(obra=obra).exists():
        raise ConflictoFinanciero("documento_duplicado", "La Obra ya tiene historial documental.")
    cierre = CierreSinCobro.objects.create(obra=obra, cortesia=cortesia, registrado_por=actor, **data)
    evento(cierre_sin_cobro=cierre, tipo="SIN_COBRO_REGISTRADO", actor=actor, motivo=data["motivo_registro"], datos_nuevos={"obra": obra.pk, "cortesia": cortesia.pk, "motivo_registro": data["motivo_registro"]})
    return cierre
