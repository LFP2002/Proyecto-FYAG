"""Emisión única de tokens FYAG; los tokens sin versión son credenciales antiguas."""
from rest_framework_simplejwt.tokens import AccessToken as SimpleAccessToken, RefreshToken as SimpleRefreshToken
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken


class VersionMixin:
    @classmethod
    def for_user(cls, user):
        token = super().for_user(user)
        token["sesion_version"] = user.sesion_version
        return token


class AccessToken(VersionMixin, SimpleAccessToken):
    pass


class RefreshToken(VersionMixin, SimpleRefreshToken):
    access_token_class = AccessToken

    @classmethod
    def for_user(cls, user):
        token = super().for_user(user)
        # BlacklistMixin crea el outstanding antes de añadir la claim del mixin.
        OutstandingToken.objects.filter(jti=token["jti"]).update(token=str(token))
        return token
