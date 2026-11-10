"""Administración 006: mutex transaccional -> cuentas por PK ascendente.

Nunca bloquear Obras/Presupuestos/Turnos después de un Usuario. Los EXISTS de
dependencias se ejecutan bajo lock del técnico, compartido con asignar/iniciar.
"""
from functools import wraps

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import connection, IntegrityError, transaction
from django.db.models import Q
from rest_framework.exceptions import APIException, AuthenticationFailed, NotFound, PermissionDenied, ValidationError

from .models import Usuario, UsuarioEvento

G = Usuario.Rol.GERENCIA
PROFILE = {"email", "username", "first_name", "last_name"}
SNAPSHOT = PROFILE | {"rol", "is_active"}
ADMIN_MUTEX = 6006006  # Namespace FYAG/SPEC-006, advisory xact (se libera al commit/rollback).


class ConflictoUsuario(APIException):
    status_code = 409

    def __init__(self, codigo, mensaje):
        super().__init__({"code": codigo, "detail": mensaje})


def operacion(func):
    @wraps(func)
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
    # El mutex evita phantoms de Gerencia entre operaciones 006. También se
    # bloquean sus filas (y actor/objetivo) siempre en el mismo orden de PK.
    accounts = {user.pk: user for user in Usuario.objects.select_for_update().filter(
        Q(rol=G, is_active=True) | Q(pk__in=[actor.pk, target_id]),
    ).order_by("pk")}
    actual = accounts.get(actor.pk)
    if not actual or not actual.is_active or actual.rol != G:
        raise PermissionDenied("Operación no autorizada.")
    if actual.sesion_version != actor.sesion_version:
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
    return value


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


def _dependencies(user):
    from apps.obras.models import Obra, ObraParticipante, TurnoObra
    # Consultas no bloqueantes. El lock de Usuario serializa los escritores que
    # crean estas obligaciones; nunca adquirir locks operativos desde aquí.
    terminales = [Obra.Estado.FINALIZADA, Obra.Estado.CANCELADA]
    if (Obra.objects.filter(tecnico_responsable=user).exclude(estado__in=terminales).exists()
        or ObraParticipante.objects.filter(tecnico=user, activo=True).exclude(obra__estado__in=terminales).exists()
        or TurnoObra.objects.filter(tecnico=user, terminado_en__isnull=True).exists()):
        raise ConflictoUsuario("asignaciones_pendientes", "La cuenta tiene asignaciones operativas o turnos abiertos pendientes de resolver.")


@operacion
def crear_usuario(data, actor):
    actor, _ = _admin(actor)
    _contract(data, PROFILE | {"rol", "password"}, {"email", "username", "rol", "password"})
    user = Usuario(**_profile(data), rol=_role(data["rol"]), is_active=False)
    _password(data["password"], user, "password")
    user.set_password(data["password"])
    _unique(user)
    user.save()
    _event(user, actor, UsuarioEvento.Tipo.CREACION, after=_snapshot(user))
    return user


@operacion
def editar_usuario(target, data, actor):
    actor, user = _admin(actor, target)
    _contract(data, PROFILE)
    changes = {key: value for key, value in _profile(data).items() if value != getattr(user, key)}
    if not changes:
        return user
    before = {key: getattr(user, key) for key in changes}
    for key, value in changes.items():
        setattr(user, key, value)
    _unique(user)
    fields = list(changes)
    if "email" in changes:
        _version(user)
        fields.append("sesion_version")
    user.save(update_fields=fields)
    _event(user, actor, UsuarioEvento.Tipo.EDICION, before=before, after=changes)
    return user


@operacion
def actividad_usuario(target, data, actor, *, activo):
    actor, user = _admin(actor, target)
    _contract(data, {"motivo"}, {"motivo"})
    reason = _text(data["motivo"], "motivo")
    if not activo:
        _last_manager(user)
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
    _contract(data, {"nueva_clave", "motivo"}, {"nueva_clave", "motivo"})
    _not_self(actor, user)
    reason = _text(data["motivo"], "motivo")
    _password(data["nueva_clave"], user, "nueva_clave")
    user.set_password(data["nueva_clave"])
    _version(user)
    user.save(update_fields=["password", "sesion_version"])
    _event(user, actor, UsuarioEvento.Tipo.ESTABLECER_CLAVE, reason)
    return user


@operacion
def cambiar_clave_propia(data, actor):
    _contract(data, {"clave_actual", "nueva_clave"}, {"clave_actual", "nueva_clave"})
    if not isinstance(actor, Usuario) or actor.pk is None:
        raise AuthenticationFailed("Sesión no disponible.")
    try:
        user = Usuario.objects.select_for_update().get(pk=actor.pk)
    except Usuario.DoesNotExist:
        raise AuthenticationFailed("Sesión no disponible.") from None
    if not user.is_active or user.sesion_version != actor.sesion_version:
        raise AuthenticationFailed("Sesión no disponible.")
    if not isinstance(data["clave_actual"], str) or not user.check_password(data["clave_actual"]):
        raise ValidationError({"clave_actual": ["La contraseña actual no es correcta."]})
    _password(data["nueva_clave"], user, "nueva_clave")
    user.set_password(data["nueva_clave"])
    _version(user)
    user.save(update_fields=["password", "sesion_version"])
    _event(user, user, UsuarioEvento.Tipo.CAMBIO_CLAVE_PROPIA)
    return user
