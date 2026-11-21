from django.contrib.auth import get_user_model
from django.db import transaction
from django.views.decorators.debug import sensitive_variables
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.exceptions import InvalidToken
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer, TokenObtainSerializer, TokenRefreshSerializer

from .authentication import identificador_sesion, validar_sesion
from .tokens import RefreshToken


class LoginSerializer(TokenObtainPairSerializer):
    token_class = RefreshToken

    def validate_email(self, value):
        return value.strip().lower()

    @sensitive_variables()
    def validate(self, attrs):
        from .configuracion_c2 import habilitado
        if habilitado():
            from .autenticacion_c2 import verificar_acceso
            def emitir(user):
                from .credenciales import iniciar_cambio
                if user.seguridad_credencial.estado != "PERSONAL":
                    return iniciar_cambio(user)
                refresh = self.get_token(user)
                return {"refresh": str(refresh), "access": str(refresh.access_token),
                        "user": {"id": user.id, "username": user.username, "email": user.email, "role": user.rol}}
            result = verificar_acceso(attrs.get("email"), attrs.get("password"), self.context.get("request"), emitir=emitir)
            if result is None:
                raise AuthenticationFailed("Credenciales inválidas.")
            return result
        try:
            TokenObtainSerializer.validate(self, attrs)
        except AuthenticationFailed as exc:
            raise AuthenticationFailed("Credenciales inválidas.") from exc

        # Serializa emisión con cambios administrativos/contraseña de esta cuenta.
        with transaction.atomic():
            try:
                user = get_user_model().objects.select_for_update().get(pk=self.user.pk)
            except get_user_model().DoesNotExist:
                raise AuthenticationFailed("Credenciales inválidas.") from None
            from .credenciales import ESTADO_NO_DISPONIBLE, estado_credencial, iniciar_cambio
            state = estado_credencial(user)
            if (not user.is_active or user.email != attrs["email"]
                or state == ESTADO_NO_DISPONIBLE
                or not user.check_password(attrs["password"])):
                raise AuthenticationFailed("Credenciales inválidas.")
            self.user = user
            if state != "PERSONAL":
                return iniciar_cambio(user)
            refresh = self.get_token(user)
            return {
                "refresh": str(refresh), "access": str(refresh.access_token),
                "user": {"id": user.id, "username": user.username, "email": user.email, "role": user.rol},
            }

    def to_internal_value(self, data):
        from .configuracion_c2 import habilitado
        if habilitado() and (not isinstance(data, dict) or not isinstance(data.get("email"), str)
                            or not isinstance(data.get("password"), str) or len(data["password"]) > 4096):
            from rest_framework.exceptions import ValidationError
            raise ValidationError({"non_field_errors": ["Se requiere email y password de texto válidos."]})
        return super().to_internal_value(data)


class VersionedRefreshSerializer(TokenRefreshSerializer):
    token_class = RefreshToken

    def validate(self, attrs):
        token = self.token_class(attrs["refresh"])
        identifier = identificador_sesion(token)
        with transaction.atomic():
            try:
                user = get_user_model().objects.select_for_update().get(pk=identifier)
            except (get_user_model().DoesNotExist, ValueError, OverflowError):
                raise InvalidToken("Sesión no disponible.") from None
            from .configuracion_c2 import habilitado
            if habilitado():
                from .models import EstadoAcceso, SeguridadCredencial, Usuario
                credential = SeguridadCredencial.objects.select_for_update().filter(usuario=user).first()
                access = EstadoAcceso.objects.select_for_update().filter(usuario=user).first()
                Usuario._meta.get_field("seguridad_credencial").set_cached_value(user, credential)
                Usuario._meta.get_field("estado_acceso").set_cached_value(user, access)
            validar_sesion(token, user)
            # Revalida blacklist tras adquirir lock: dos refresh concurrentes no rotan dos veces.
            return super().validate(attrs)
