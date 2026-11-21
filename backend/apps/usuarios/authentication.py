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
    from .acceso import sesion_operativa
    version = token.get("sesion_version")
    if not user.is_active or type(version) is not int or version != user.sesion_version:
        raise AuthenticationFailed("Sesión no disponible.", code="sesion_revocada")
    if not sesion_operativa(user):
        raise AuthenticationFailed("Sesión no disponible.", code="sesion_revocada")
    if api_settings.CHECK_REVOKE_TOKEN and not constant_time_compare(
        str(token.get(api_settings.REVOKE_TOKEN_CLAIM, "")), get_md5_hash_password(user.password),
    ):
        raise AuthenticationFailed("Sesión no disponible.", code="sesion_revocada")


class VersionedJWTAuthentication(JWTAuthentication):
    def get_user(self, validated_token):
        identifier = identificador_sesion(validated_token)
        try:
            # Una sola consulta, sin N+1; validar_sesion conserva y refuerza las
            # comprobaciones de actividad/hash de SimpleJWT y añade versión/estado.
            from .configuracion_c2 import relaciones_seguridad
            user = self.user_model.objects.select_related(*relaciones_seguridad()).get(
                **{api_settings.USER_ID_FIELD: identifier},
            )
        except self.user_model.DoesNotExist:
            raise AuthenticationFailed("Sesión no disponible.") from None
        validar_sesion(validated_token, user)
        return user
