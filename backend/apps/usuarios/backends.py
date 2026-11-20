"""Autenticación Django también fail-closed; no solo la emisión JWT de DRF."""
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.hashers import check_password
from django.views.decorators.debug import sensitive_variables

from .credenciales import ESTADO_NO_DISPONIBLE, estado_credencial, es_personal


class CredencialesModelBackend(ModelBackend):
    @sensitive_variables()
    def authenticate(self, request, username=None, password=None, **kwargs):
        User = get_user_model()
        identifier = username if username is not None else kwargs.get(User.USERNAME_FIELD)
        if identifier is None or password is None:
            return None
        try:
            user = User.objects.select_related("seguridad_credencial").get(**{User.USERNAME_FIELD: identifier})
        except User.DoesNotExist:
            User().set_password(password)  # Trabajo de hash para identidad inexistente.
            return None
        # Sin setter: una autenticación rechazada no reescribe un hash antiguo.
        valid_password = check_password(password, user.password)
        state = estado_credencial(user)
        if not valid_password or not user.is_active or state == ESTADO_NO_DISPONIBLE:
            return None
        if state != "PERSONAL" and request is not None and request.path != "/api/auth/login/":
            return None  # Ni admin Django ni otra ruta convierten temporal en sesión.
        return user

    def user_can_authenticate(self, user):
        return user.is_active and estado_credencial(user) != ESTADO_NO_DISPONIBLE

    def get_user(self, user_id):
        User = get_user_model()
        user = User.objects.select_related("seguridad_credencial").filter(pk=user_id).first()
        # Una sesión Django tampoco puede operar con temporal o estado ausente.
        return user if user is not None and user.is_active and es_personal(user) else None
