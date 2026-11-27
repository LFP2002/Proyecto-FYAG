"""Administración 006: mutex transaccional -> cuentas por PK ascendente.

Nunca bloquear Obras/Presupuestos/Turnos después de un Usuario. Los EXISTS de
dependencias se ejecutan bajo lock del técnico, compartido con asignar/iniciar.
"""
from functools import wraps
from datetime import timedelta
from hashlib import sha256
from secrets import compare_digest, token_urlsafe
import re
from django.conf import settings
from django.utils import timezone
from django.views.decorators.debug import sensitive_variables

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import connection, IntegrityError, transaction
from django.db.models import Q
from rest_framework.exceptions import APIException, AuthenticationFailed, NotFound, PermissionDenied, ValidationError

from .models import EventoInstalacionFYAG, InstalacionFYAG, Usuario, UsuarioEvento

G = Usuario.Rol.GERENCIA
TI = Usuario.Rol.ADMINISTRADOR_TI
PROFILE = {"email", "username", "first_name", "last_name"}
SNAPSHOT = PROFILE | {"rol", "is_active"}
ADMIN_MUTEX = 6006006  # Namespace FYAG/SPEC-006, advisory xact (se libera al commit/rollback).


class ConflictoUsuario(APIException):
    status_code = 409

    def __init__(self, codigo, mensaje):
        super().__init__({"code": codigo, "detail": mensaje})


def operacion(func):
    @wraps(func)
    @sensitive_variables()
    def wrapped(*args, **kwargs):
        try:
            with transaction.atomic():
                return func(*args, **kwargs)
        except DjangoValidationError as exc:
            errors = exc.message_dict if hasattr(exc, "message_dict") else {"non_field_errors": exc.messages}
            raise ValidationError(errors) from None
        except IntegrityError as exc:
            name = getattr(getattr(exc.__cause__, "diag", None), "constraint_name", "")
            fields = {"usuarios_usuario_email_key": "email", "usuarios_usuario_email_0a82e5f9_uniq": "email", "usuarios_usuario_username_key": "username"}
            if name in fields:
                raise ValidationError({fields[name]: ["Ya existe una cuenta con este valor."]}) from None
            raise
    return wrapped


def _id(value):
    pk = value.pk if isinstance(value, Usuario) else value
    if type(pk) is not int or not 0 < pk <= 9223372036854775807:
        raise ValidationError({"id": ["Identificador entero positivo requerido."]})
    return pk


def _admin(actor, target=None):
    if not isinstance(actor, Usuario) or not actor.is_authenticated or actor.pk is None:
        raise PermissionDenied("Operación no autorizada.")
    target_id = _id(target) if target is not None else None
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [ADMIN_MUTEX])
    # El mismo mutex protege TI/Gerencia y el aprovisionamiento inicial.
    # Filas activas de ambos roles, actor y objetivo: siempre por PK ascendente.
    accounts = {user.pk: user for user in Usuario.objects.select_for_update().filter(
        Q(rol__in=[G, TI], is_active=True) | Q(pk__in=[actor.pk, target_id]),
    ).order_by("pk")}
    actual = accounts.get(actor.pk)
    if not actual or not actual.is_active or actual.rol != TI or actor.rol != TI:
        raise PermissionDenied("Operación no autorizada.")
    from django.utils.crypto import constant_time_compare
    if actual.sesion_version != actor.sesion_version or not constant_time_compare(actual.password, actor.password):
        raise AuthenticationFailed("Sesión no disponible.")
    from .credenciales import es_personal
    if not es_personal(actual):
        raise AuthenticationFailed("Sesión no disponible.")
    from .acceso import acceso_permitido
    if not acceso_permitido(actual):
        raise AuthenticationFailed("Sesión no disponible.")
    if target_id is not None and target_id not in accounts:
        raise NotFound("Cuenta no disponible.")
    return actual, accounts.get(target_id)


def _contract(data, allowed, required=()):
    if not isinstance(data, dict):
        raise ValidationError({"non_field_errors": ["Se requiere un objeto JSON."]})
    errors = {key: ["Campo no permitido."] for key in data if key not in allowed}
    errors.update({key: ["Campo obligatorio."] for key in required if key not in data})
    if errors:
        raise ValidationError(errors)


def _text(value, field, maximum=2000, required=True):
    if not isinstance(value, str):
        raise ValidationError({field: ["Debe ser texto."]})
    value = value.strip()
    if required and not value:
        raise ValidationError({field: ["Campo obligatorio."]})
    if len(value) > maximum:
        raise ValidationError({field: [f"Máximo {maximum} caracteres."]})
    return value


def _snapshot(user):
    return {key: getattr(user, key) for key in sorted(SNAPSHOT)}


def _event(user, actor, kind, reason="", before=None, after=None):
    return UsuarioEvento.objects.create(usuario_objetivo=user, actor=actor, tipo=kind,
        motivo=reason, datos_anteriores=before or {}, datos_nuevos=after or {})


def _version(user):
    if user.sesion_version >= 9223372036854775807:
        raise ConflictoUsuario("version_agotada", "No es posible actualizar la sesión de esta cuenta.")
    user.sesion_version += 1


def _profile(data):
    result = {}
    for key in PROFILE & data.keys():
        value = _text(data[key], key, maximum=254 if key == "email" else 150, required=key in {"email", "username"})
        result[key] = value.lower() if key == "email" else value
    return result


def _unique(user):
    for field in ("email", "username"):
        if Usuario.objects.exclude(pk=user.pk).filter(**{field: getattr(user, field)}).exists():
            raise ValidationError({field: ["Ya existe una cuenta con este valor."]})
    user.full_clean(validate_unique=False, validate_constraints=False)


def _role(value):
    if not isinstance(value, str) or value not in Usuario.Rol.values:
        raise ValidationError({"rol": ["Rol no permitido."]})
    return str(value)


@sensitive_variables()
def _password(value, user, field):
    if not isinstance(value, str) or not value or len(value) > 4096:
        raise ValidationError({field: ["Contraseña inválida."]})
    try:
        validate_password(value, user=user)
    except DjangoValidationError as exc:
        raise ValidationError({field: exc.messages}) from None


def _not_self(actor, user):
    if actor.pk == user.pk:
        raise ConflictoUsuario("autooperacion_protegida", "No puede realizar esta operación sobre su propia cuenta.")


def _last_manager(user):
    if user.is_active and user.rol == G and Usuario.objects.filter(rol=G, is_active=True).count() <= 1:
        raise ConflictoUsuario("ultima_gerencia", "Debe permanecer una Gerencia activa.")


def _last_ti(user):
    from .configuracion_c2 import habilitado
    if habilitado() and user.pk in settings.BLOQUEOS_C2_TI_QA_IDS:
        raise ConflictoUsuario("recuperacion_qa_protegida", "Recuperadora QA protegida mientras C2 esté habilitada.")
    if user.is_active and user.rol == TI and Usuario.objects.filter(rol=TI, is_active=True).count() <= 1:
        raise ConflictoUsuario("ultima_ti", "Debe permanecer una cuenta TI activa.")


def _dependencies(user):
    from apps.obras.models import Obra, ObraParticipante, TurnoObra
    # Consultas no bloqueantes. El lock de Usuario serializa los escritores que
    # crean estas obligaciones; nunca adquirir locks operativos desde aquí.
    terminales = [Obra.Estado.FINALIZADA, Obra.Estado.CANCELADA]
    if (Obra.objects.filter(tecnico_responsable=user).exclude(estado__in=terminales).exists()
        or ObraParticipante.objects.filter(tecnico=user, activo=True).exclude(obra__estado__in=terminales).exists()
        or TurnoObra.objects.filter(tecnico=user, terminado_en__isnull=True).exists()):
        raise ConflictoUsuario("asignaciones_pendientes", "La cuenta tiene asignaciones operativas o turnos abiertos pendientes de resolver.")


@sensitive_variables()
@operacion
def crear_usuario(data, actor):
    actor, _ = _admin(actor)
    _contract(data, PROFILE | {"rol"}, {"email", "username", "rol"})
    user = Usuario(**_profile(data), rol=_role(data["rol"]), is_active=False)
    user.set_unusable_password()  # Estado intermedio no visible fuera de esta transacción.
    _unique(user)
    user.save()
    _event(user, actor, UsuarioEvento.Tipo.CREACION, after=_snapshot(user))
    from .credenciales import emitir_temporal
    from .verificacion import emitir, TITULARIDAD
    issued = emitir_temporal(user, actor, inicial=True)
    emitir(user, TITULARIDAD)
    return issued


@operacion
def editar_usuario(target, data, actor):
    actor, user = _admin(actor, target)
    _contract(data, PROFILE)
    changes = {key: value for key, value in _profile(data).items() if value != getattr(user, key)}
    nuevo = changes.pop('email', None)
    if nuevo is not None:
        from django.core.validators import validate_email
        try:
            validate_email(nuevo)
        except DjangoValidationError:
            raise ValidationError({'email': ['Ingrese una dirección válida.']}) from None
        if Usuario.objects.exclude(pk=user.pk).filter(email=nuevo).exists():
            raise ValidationError({'email': ['Ya existe una cuenta con este valor.']})
    if changes:
        before = {key: getattr(user, key) for key in changes}
        for key, value in changes.items():
            setattr(user, key, value)
        _unique(user)
        user.save(update_fields=list(changes))
        _event(user, actor, UsuarioEvento.Tipo.EDICION, before=before, after=changes)
    if nuevo is not None:
        from .verificacion import proponer
        proponer(user, actor, nuevo)
    return user


@operacion
def actividad_usuario(target, data, actor, *, activo):
    actor, user = _admin(actor, target)
    _contract(data, {"motivo"}, {"motivo"})
    reason = _text(data["motivo"], "motivo")
    if not activo:
        _last_manager(user)
        _last_ti(user)
        _not_self(actor, user)
    if user.is_active == activo:
        return user
    if not activo:
        _dependencies(user)
    before = user.is_active
    user.is_active = activo
    _version(user)
    user.save(update_fields=["is_active", "sesion_version"])
    _event(user, actor, UsuarioEvento.Tipo.ACTIVACION if activo else UsuarioEvento.Tipo.DESACTIVACION,
        reason, {"is_active": before}, {"is_active": activo})
    return user


@operacion
def cambiar_rol(target, data, actor):
    actor, user = _admin(actor, target)
    _contract(data, {"rol", "motivo"}, {"rol", "motivo"})
    role, reason = _role(data["rol"]), _text(data["motivo"], "motivo")
    if role != G:
        _last_manager(user)
    if role != TI:
        _last_ti(user)
    _not_self(actor, user)
    if role == user.rol:
        raise ConflictoUsuario("sin_cambios", "La cuenta ya tiene ese rol.")
    if role != Usuario.Rol.TECNICO:
        _dependencies(user)
    before = user.rol
    user.rol = role
    _version(user)
    user.save(update_fields=["rol", "sesion_version"])
    _event(user, actor, UsuarioEvento.Tipo.CAMBIO_ROL, reason, {"rol": before}, {"rol": role})
    return user


@operacion
def establecer_clave(target, data, actor):
    actor, user = _admin(actor, target)
    _not_self(actor, user)
    raise ConflictoUsuario("operacion_retirada", "Utilice restablecer-clave con motivo; la clave debe ser elegida por su titular.")


@sensitive_variables()
@operacion
def cambiar_clave_propia(data, actor):
    _contract(data, {"clave_actual", "nueva_clave"}, {"clave_actual", "nueva_clave"})
    if not isinstance(actor, Usuario) or actor.pk is None:
        raise AuthenticationFailed("Sesión no disponible.")
    try:
        user = Usuario.objects.select_for_update().get(pk=actor.pk)
    except Usuario.DoesNotExist:
        raise AuthenticationFailed("Sesión no disponible.") from None
    from django.utils.crypto import constant_time_compare
    if (not user.is_active or user.rol != actor.rol or user.sesion_version != actor.sesion_version
            or not constant_time_compare(user.password, actor.password)):
        raise AuthenticationFailed("Sesión no disponible.")
    from .credenciales import es_personal
    if not es_personal(user):
        raise AuthenticationFailed("Sesión no disponible.")
    from .acceso import acceso_permitido
    if not acceso_permitido(user):
        raise AuthenticationFailed("Sesión no disponible.")
    if not isinstance(data["clave_actual"], str) or not user.check_password(data["clave_actual"]):
        raise ValidationError({"clave_actual": ["La contraseña actual no es correcta."]})
    _password(data["nueva_clave"], user, "nueva_clave")
    user.set_password(data["nueva_clave"])
    _version(user)
    user.save(update_fields=["password", "sesion_version"])
    _event(user, user, UsuarioEvento.Tipo.CAMBIO_CLAVE_PROPIA)
    return user


_AUTORIDAD_CLI = object()
_CLAVE_INSTALACION = re.compile(r'[A-Za-z0-9_-]{43}')


def _bloquear_instalacion(*, cli=False):
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [ADMIN_MUTEX])
    rows = InstalacionFYAG.objects.select_for_update()
    return rows.get_or_create(pk=1)[0] if cli else rows.filter(pk=1).first()


def _nueva(instalacion):
    return instalacion is not None and instalacion.inicializada_en is None and not Usuario.objects.exists()


def instalacion_pendiente():
    return _nueva(InstalacionFYAG.objects.filter(pk=1).only('inicializada_en').first())


@sensitive_variables()
@operacion
def emitir_clave_instalacion(operador, referencia):
    if not all(isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_.@-]{1,64}', value)
               for value in (operador, referencia)):
        raise ValidationError('Indique identificadores de operador y referencia válidos, no secretos.')
    instalacion = _bloquear_instalacion()
    if not _nueva(instalacion):
        raise ConflictoUsuario("ti_ya_aprovisionada", "La instalación ya fue inicializada; no se puede repetir el aprovisionamiento.")
    tipos = EventoInstalacionFYAG.Tipo
    tipo = tipos.RENOVACION if instalacion.clave_digest else tipos.EMISION
    clave = token_urlsafe(32)
    vence = timezone.now() + timedelta(minutes=30)
    instalacion.clave_digest, instalacion.clave_vence_en = sha256(clave.encode()).hexdigest(), vence
    instalacion.save(update_fields=['clave_digest', 'clave_vence_en'])
    EventoInstalacionFYAG.objects.create(tipo=tipo, operador=operador, referencia=referencia)
    return clave, vence


@sensitive_variables()
@operacion
def aprovisionar_primera_ti(data, *, clave_instalacion=_AUTORIDAD_CLI):
    """El único caller sin clave es la CLI interactiva de infraestructura."""
    cli = clave_instalacion is _AUTORIDAD_CLI
    instalacion = _bloquear_instalacion(cli=cli)
    nueva = _nueva(instalacion)
    if cli:
        if not nueva:
            raise ConflictoUsuario('ti_ya_aprovisionada', 'La instalación ya fue inicializada; no se puede repetir el aprovisionamiento.')
    elif (not nueva or not instalacion.clave_digest or instalacion.clave_vence_en <= timezone.now()
          or not isinstance(clave_instalacion, str) or not _CLAVE_INSTALACION.fullmatch(clave_instalacion)
          or not compare_digest(instalacion.clave_digest, sha256(clave_instalacion.encode()).hexdigest())):
        raise ConflictoUsuario('setup_no_autorizado', 'No se autorizó el aprovisionamiento inicial.')
    required = {'email', 'username', 'password'} if cli else PROFILE | {'password'}
    _contract(data, PROFILE | {'password'}, required)
    user = Usuario(**_profile(data), rol=TI.value, is_active=True, is_staff=False, is_superuser=False)
    if not cli and not (user.first_name and user.last_name):
        raise ValidationError('Nombre y apellidos son obligatorios.')
    _password(data['password'], user, 'password')
    user.set_password(data['password'])
    _unique(user)
    user.save()
    from .credenciales import es_personal
    if not es_personal(user):
        raise ConflictoUsuario("seguridad_no_disponible", "No se pudo confirmar el estado de seguridad inicial.")
    # El trigger 0012 marca la primera inserción; el de 0015 limpia la clave,
    # incluso cuando la inserción se realiza por otra vía. Ambos son transaccionales.
    tipos = EventoInstalacionFYAG.Tipo
    EventoInstalacionFYAG.objects.create(tipo=tipos.INICIALIZACION_CLI if cli else tipos.INICIALIZACION_WEB)
    _event(user, user, UsuarioEvento.Tipo.CREACION, 'Aprovisionamiento inicial por infraestructura (sin sesión autenticada).', after=_snapshot(user))
    from .verificacion import emitir, TITULARIDAD
    emitir(user, TITULARIDAD)
    return user
