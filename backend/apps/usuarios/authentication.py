from django.utils.crypto import constant_time_compare
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed, InvalidToken
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.utils import get_md5_hash_password


def identificador_sesion(token):
    value = token.get(api_settings.USER_ID_CLAIM)
    text = str(value)
    if (type(value) not in (int, str) or len(text) > 19
        or not text.isascii() or not text.isdecimal()
        or not 0 < int(text) <= 9223372036854775807):
        raise InvalidToken("Sesión no disponible.")
    return int(text)


def validar_sesion(token, user):
    version = token.get("sesion_version")
    if not user.is_active or type(version) is not int or version != user.sesion_version:
        raise AuthenticationFailed("Sesión no disponible.", code="sesion_revocada")
    if api_settings.CHECK_REVOKE_TOKEN and not constant_time_compare(
        str(token.get(api_settings.REVOKE_TOKEN_CLAIM, "")), get_md5_hash_password(user.password),
    ):
        raise AuthenticationFailed("Sesión no disponible.", code="sesion_revocada")


class VersionedJWTAuthentication(JWTAuthentication):
    def get_user(self, validated_token):
        identificador_sesion(validated_token)
        user = super().get_user(validated_token)
        validar_sesion(validated_token, user)
        return user
