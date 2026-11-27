"""Verificación única y transaccional de la política ratificada SPEC-018C."""
from django.conf import settings
from django.contrib.auth.hashers import check_password, identify_hasher, make_password
from django.core.exceptions import ImproperlyConfigured
from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from django.views.decorators.debug import sensitive_variables

from .acceso import acceso_permitido, estado_acceso
from .bloqueos import EstadoAccesoNoDisponible, aplicar_verificacion_bloqueada
from .configuracion_c2 import habilitado, perfil_bloqueos, relaciones_seguridad
from .credenciales import estado_coherente, limpiar_desafio
from .models import DesafioCorreo, DesafioRecuperacionCorreo, EstadoAcceso, SeguridadCredencial, Usuario
from .politica_bloqueos import EstadoPolitica, Senal, calcular_transicion
from .services_usuarios import ADMIN_MUTEX, ConflictoUsuario, _version


@sensitive_variables()
def hash_utilizable(user):
    if not user.has_usable_password():
        return False
    try:
        # Inspección de formato, sin verificar secreto ni ejecutar hash costoso.
        identify_hasher(user.password).safe_summary(user.password)
    except (ValueError, TypeError, IndexError, KeyError, AssertionError, NotImplementedError):
        return False
    return True


@sensitive_variables()
def recuperadoras_qa(*, exigir_dos=False):
    """Precondición dinámica: no confundir IDs configurados con permisos reales."""
    users = list(Usuario.objects.select_related(*relaciones_seguridad()).filter(pk__in=settings.BLOQUEOS_C2_TI_QA_IDS))
    if (len(users) != 2 or any(u.rol != "ADMINISTRADOR_TI" or not u.is_active
                             or not estado_coherente(getattr(u, "seguridad_credencial", None))
                             or not hash_utilizable(u) or estado_acceso(u) == "NO_DISPONIBLE" for u in users)):
        raise ImproperlyConfigured("C2 denegada: recuperadoras QA ausentes, inactivas o incoherentes.")
    available = [u for u in users if u.seguridad_credencial.estado == "PERSONAL" and acceso_permitido(u)]
    if len(available) < (2 if exigir_dos else 1):
        raise ImproperlyConfigured("C2 denegada: no hay recuperación TI QA disponible.")
    return available


def preflight_qa():
    if not habilitado():
        raise ImproperlyConfigured("C2 está deshabilitada.")
    recuperadoras_qa(exigir_dos=True)


def exigir_respaldo_para_temporal_qa(user):
    """Caller ya validó habilitado() y mantiene ADMIN_MUTEX hasta el commit."""
    disponibles = recuperadoras_qa()
    if user.pk in settings.BLOQUEOS_C2_TI_QA_IDS and not any(ti.pk != user.pk for ti in disponibles):
        raise ConflictoUsuario("recuperacion_qa_protegida", "Debe permanecer otra recuperadora QA personal disponible.")


def _snapshot_vigente(snapshot, user, credential):
    previous = getattr(snapshot, "seguridad_credencial", None)
    return (constant_time_compare(user.password, snapshot.password)
            and all(getattr(user, f) == getattr(snapshot, f) for f in ("email", "sesion_version", "rol", "is_active"))
            and estado_coherente(credential) and estado_coherente(previous)
            and all(getattr(credential, f) == getattr(previous, f) for f in ("estado", "emitida_en", "vence_en")))


@sensitive_variables()
def verificar_acceso(identifier, password, request, *, emitir=None):
    perfil = perfil_bloqueos()
    if perfil == 'deshabilitado':
        raise ImproperlyConfigured("Verificador invocado con bloqueos deshabilitados.")
    qa = perfil == 'qa_c2'
    if not isinstance(identifier, str) or not isinstance(password, str) or not password or len(password) > 4096:
        return None
    if qa:
        recuperadoras_qa()
    snapshot = Usuario.objects.select_related(*relaciones_seguridad()).filter(email=identifier).first()
    if snapshot is None:
        make_password(password)  # Trabajo dummy; nunca se persiste ni cuenta.
        return None
    try:
        valid = check_password(password, snapshot.password)  # Sin setter ni lock SQL.
    except (ValueError, TypeError, OverflowError):
        return None  # Formato persistido inválido no acredita fallo del titular.
    try:
        identify_hasher(snapshot.password)
    except ValueError:
        return None  # Hash inutilizable/ausente no acredita una clave incorrecta.
    try:
        with transaction.atomic():
            if qa and snapshot.rol == "ADMINISTRADOR_TI":
                with connection.cursor() as cursor:
                    cursor.execute("SELECT pg_advisory_xact_lock(%s)", [ADMIN_MUTEX])
                accounts = {u.pk: u for u in Usuario.objects.select_for_update().filter(
                    Q(pk__in=settings.BLOQUEOS_C2_TI_QA_IDS) | Q(pk=snapshot.pk)).order_by("pk")}
                user = accounts.get(snapshot.pk)
            else:
                user = Usuario.objects.select_for_update().filter(pk=snapshot.pk).first()
            credential = SeguridadCredencial.objects.select_for_update().filter(usuario_id=snapshot.pk).first()
            state = EstadoAcceso.objects.select_for_update().filter(usuario_id=snapshot.pk).first()
            now = timezone.now()
            if (user is None or not _snapshot_vigente(snapshot, user, credential) or not user.is_active
                or (credential.estado != "PERSONAL" and credential.vence_en <= now)):
                return None
            # Precarga exacta de las filas bloqueadas; sin lecturas laterales viejas.
            Usuario._meta.get_field("estado_acceso").set_cached_value(user, state)
            Usuario._meta.get_field("seguridad_credencial").set_cached_value(user, credential)
            if estado_acceso(user, ahora=now) == "NO_DISPONIBLE":
                return None
            planned = calcular_transicion(EstadoPolitica(state.estado, tuple(state.fallos_en), tuple(state.ciclos_en),
                state.bloqueo_inicio, state.bloqueado_hasta), Senal.CLAVE_CORRECTA if valid else Senal.CLAVE_INCORRECTA, now)
            if qa and not valid and user.rol == "ADMINISTRADOR_TI" and any(t.startswith("BLOQUEO") for t, _ in planned.eventos):
                # Bajo mutex; no se bloquea la última recuperadora utilizable.
                if not any(u.pk != user.pk for u in recuperadoras_qa()):
                    return None
            if valid and credential.estado != "PERSONAL":
                from .backends import contexto_login_restringido
                if not contexto_login_restringido(request):
                    return None
            result = aplicar_verificacion_bloqueada(user, credential, state,
                Senal.CLAVE_CORRECTA if valid else Senal.CLAVE_INCORRECTA, now)
            if any(tipo in {"BLOQUEO_TEMPORAL", "BLOQUEO_TI"} for tipo, _ in result.eventos):
                _version(user)
                user.save(update_fields=["sesion_version"])
                limpiar_desafio(credential)
                credential.save(update_fields=["desafio_digest", "desafio_vence_en", "desafio_version"])
                if not qa:
                    DesafioCorreo.objects.filter(usuario=user, proposito='CAMBIO').delete()
                    DesafioRecuperacionCorreo.objects.filter(usuario=user).delete()
            if not valid or result.estado.estado != "NORMAL":
                return None  # Commit de fallos antes del 401 del serializer.
            return emitir(user) if emitir else user
    except (EstadoAccesoNoDisponible, ConflictoUsuario):
        return None  # La atomic ya revirtió; no reparar ni filtrar causas internas.
