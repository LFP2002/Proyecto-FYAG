"""SPEC-024: autorización exclusiva de Presupuestos; nunca reutilizar en Clientes."""
from django.utils.crypto import constant_time_compare
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied

from apps.usuarios.acceso import sesion_operativa
from apps.usuarios.configuracion_c2 import relaciones_seguridad
from apps.usuarios.models import Usuario, SeguridadCredencial, EstadoAcceso
from .exceptions import RecursoNoEncontrado

AF = Usuario.Rol.ADMINISTRATIVO_FINANZAS
S = Usuario.Rol.SUPERVISOR_OBRAS
G = Usuario.Rol.GERENCIA


def revalidar_presupuestos(usuario, accion='lectura', presupuesto=None, *, bloquear=False):
    if not isinstance(usuario, Usuario) or not usuario.pk or usuario._state.adding:
        raise PermissionDenied('Operación presupuestaria no autorizada.')
    if bloquear:
        # Al final de la escritura: Presupuesto -> Cliente (si aplica) -> Usuario
        # -> credencial -> acceso. NO KEY UPDATE es compatible con FK KEY SHARE.
        Usuario.objects.select_for_update(no_key=True).filter(pk=usuario.pk).first()
        SeguridadCredencial.objects.select_for_update().filter(usuario_id=usuario.pk).first()
        EstadoAcceso.objects.select_for_update().filter(usuario_id=usuario.pk).first()
    actual = Usuario.objects.select_related(*relaciones_seguridad()).filter(pk=usuario.pk).first()
    if (actual is None or not actual.is_active or actual.sesion_version != usuario.sesion_version
        or not constant_time_compare(actual.password, usuario.password) or not sesion_operativa(actual)):
        raise AuthenticationFailed('Sesión no disponible.')
    roles = {
        'lectura': {AF, S, G}, 'selector': {AF, S},
        'elaborar': {AF, S}, 'enviar_revision': {AF, S},
        'crear_revision': {AF, S}, 'decision_finanzas': {AF},
    }
    if actual.rol not in roles.get(accion, set()):
        raise PermissionDenied('Operación presupuestaria no autorizada.')
    if presupuesto is not None and actual.rol == S and presupuesto.creado_por_id != actual.pk:
        raise RecursoNoEncontrado()
    return actual


def presupuestos_visibles(usuario, queryset):
    actual = revalidar_presupuestos(usuario)
    if actual.rol == S:
        return queryset.filter(creado_por_id=actual.pk)
    return queryset
