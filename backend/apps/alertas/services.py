"""Proyección eventual. Locks propios por recurso; nunca locks de los propietarios.

Orden: advisory(tipo, recurso) -> filas Alerta en orden de rol. Las lecturas de
origen son MVCC tras el lock, no SELECT FOR UPDATE. Ningún callback se ejecuta
antes de liberar la transacción del dominio. No hay ciclo de locks con Finanzas.
"""
import hashlib
import logging
from time import monotonic
from uuid import uuid4

from django.db import connection, models, transaction
from django.db.models import Max
from rest_framework.exceptions import APIException, NotFound, ValidationError

from .catalogo import CATALOGO, MAX_PK
from .consultas import condicion, vigentes
from .models import Alerta, AlertaEvento, EstadoReconciliacion
from .permissions import revalidar
from .reloj import ahora as hora_servidor

logger = logging.getLogger(__name__)


class ConflictoAlerta(APIException):
    status_code = 409

    def __init__(self, code, detail):
        super().__init__({"code": code, "detail": detail})


def bloquear(tipo, pk):
    clave = int.from_bytes(hashlib.blake2b(f"fyag.alertas.v1:{tipo}:{pk}".encode(), digest_size=8).digest(), "big", signed=True)
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [clave])


def _evento(alerta, tipo, anterior, *, actor=None, motivo="", ahora):
    AlertaEvento.objects.create(alerta=alerta, tipo=tipo, estado_anterior=anterior,
        estado_nuevo=alerta.estado, actor=actor, motivo=motivo, registrado_en=ahora)


@transaction.atomic
def reconciliar_recurso(tipo, pk):
    if tipo not in CATALOGO or type(pk) is not int or not 0 < pk <= MAX_PK:
        raise ValueError("Clave de alerta inválida")
    bloquear(tipo, pk)
    activa = condicion(tipo, pk)  # releer DESPUÉS de esperar al otro proyector
    ahora = hora_servidor()
    regla = CATALOGO[tipo]
    cambios = 0
    for rol in sorted(regla.roles):
        qs = Alerta.objects.filter(tipo=tipo, recurso_tipo=regla.recurso, recurso_id=pk, rol_destinatario=rol)
        abierta = qs.select_for_update().filter(estado__in=["PENDIENTE", "ATENDIDA"]).first()
        if activa and abierta is None:
            generacion = (qs.aggregate(n=Max("generacion"))["n"] or 0) + 1
            alerta = Alerta.objects.create(tipo=tipo, recurso_tipo=regla.recurso, recurso_id=pk, rol_destinatario=rol,
                generacion=generacion, creado_en=ahora, ultima_comprobacion_en=ahora)
            _evento(alerta, "CREACION", None, ahora=ahora)
            cambios += 1
        elif abierta is not None:
            if not activa:
                anterior = abierta.estado
                abierta.estado, abierta.resuelta_en, abierta.ultima_comprobacion_en = "RESUELTA", ahora, ahora
                models.Model.save(abierta, update_fields=["estado", "resuelta_en", "ultima_comprobacion_en"])
                _evento(abierta, "RESOLUCION", anterior, ahora=ahora)
                cambios += 1
            elif (ahora - abierta.ultima_comprobacion_en).total_seconds() >= 60:
                abierta.ultima_comprobacion_en = ahora
                models.Model.save(abierta, update_fields=["ultima_comprobacion_en"])
    return cambios


def notificar_despues_commit(tipo, pk):
    """La callback recuperable no propaga excepciones ni imprime datos de dominio."""
    def ejecutar():
        try:
            reconciliar_recurso(tipo, pk)
        except Exception as exc:
            logger.error("alertas_callback_error correlacion=%s clase=%s", uuid4(), type(exc).__name__)
    transaction.on_commit(ejecutar)


def _lotes(qs, campo="pk", tamano=500):
    limite = qs.aggregate(n=Max(campo))["n"] or 0
    ultimo = 0
    while ultimo < limite:
        ids = list(qs.filter(**{f"{campo}__gt": ultimo, f"{campo}__lte": limite}).order_by(campo).values_list(campo, flat=True)[:tamano])
        if not ids:
            break
        yield ids
        ultimo = ids[-1]


def reconciliar():
    """Transacción corta por recurso. Un ciclo parcial NO actualiza la salud."""
    inicio = monotonic()
    examinados = cambios = 0
    for tipo in CATALOGO:
        for ids in _lotes(vigentes(tipo)):
            for pk in ids:
                cambios += reconciliar_recurso(tipo, pk)
                examinados += 1
        # Incluye orígenes ya desaparecidos y causas que dejaron de estar activas.
        abiertas = Alerta.objects.filter(tipo=tipo, estado__in=["PENDIENTE", "ATENDIDA"])
        for ids in _lotes(abiertas):
            for pk in Alerta.objects.filter(pk__in=ids).order_by().values_list("recurso_id", flat=True).distinct():
                cambios += reconciliar_recurso(tipo, pk)
                examinados += 1
    with transaction.atomic():
        estado, _ = EstadoReconciliacion.objects.select_for_update().get_or_create(pk=1)
        estado.ultima_correcta_en = hora_servidor()
        estado.save(update_fields=["ultima_correcta_en"])
    return {"examinados": examinados, "transiciones": cambios, "segundos": round(monotonic() - inicio, 6)}


def obtener(actor, pk):
    if type(pk) is not int or not 0 < pk <= MAX_PK:
        raise NotFound("Alerta no encontrada.")
    alerta = Alerta.objects.filter(pk=pk, rol_destinatario=actor.rol).first()
    if alerta is None:
        raise NotFound("Alerta no encontrada.")
    return alerta


@transaction.atomic
def atender(actor, pk, motivo):
    actor = revalidar(actor)
    if type(motivo) is not str or not 1 <= len(motivo.strip()) <= 2000:
        raise ValidationError({"motivo": "Indique un texto de 1 a 2000 caracteres."})
    alerta = obtener(actor, pk)
    bloquear(alerta.tipo, alerta.recurso_id)
    # El rol/sesión puede cambiar mientras esperamos al reconciliador.
    actor = revalidar(actor)
    alerta = Alerta.objects.select_for_update().filter(pk=pk, rol_destinatario=actor.rol).first()
    if alerta is None:
        raise NotFound("Alerta no encontrada.")
    if alerta.estado == "ATENDIDA":
        raise ConflictoAlerta("alerta_ya_atendida", "La alerta ya fue atendida.")
    if alerta.estado == "RESUELTA":
        raise ConflictoAlerta("alerta_resuelta", "La alerta está resuelta.")
    if not condicion(alerta.tipo, alerta.recurso_id):
        raise ConflictoAlerta("alerta_desactualizada", "La condición de origen ya no está vigente.")
    ahora = hora_servidor()
    alerta.estado, alerta.atendida_por, alerta.atendida_en, alerta.motivo_atencion = "ATENDIDA", actor, ahora, motivo.strip()
    models.Model.save(alerta, update_fields=["estado", "atendida_por", "atendida_en", "motivo_atencion"])
    _evento(alerta, "ATENCION", "PENDIENTE", actor=actor, motivo=alerta.motivo_atencion, ahora=ahora)
    return alerta
