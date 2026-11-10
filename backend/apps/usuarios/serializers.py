from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.exceptions import InvalidToken
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer, TokenObtainSerializer, TokenRefreshSerializer

from .authentication import identificador_sesion, validar_sesion
from .tokens import RefreshToken


class LoginSerializer(TokenObtainPairSerializer):
    token_class = RefreshToken

    def validate_email(self, value):
        return value.strip().lower()

    def validate(self, attrs):
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
            if not user.is_active or user.email != attrs["email"] or not user.check_password(attrs["password"]):
                raise AuthenticationFailed("Credenciales inválidas.")
            self.user = user
            refresh = self.get_token(user)
            return {
                "refresh": str(refresh), "access": str(refresh.access_token),
                "user": {"id": user.id, "username": user.username, "email": user.email, "role": user.rol},
            }


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
            validar_sesion(token, user)
            # Revalida blacklist tras adquirir lock: dos refresh concurrentes no rotan dos veces.
            return super().validate(attrs)
