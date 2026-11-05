from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer


class LoginSerializer(TokenObtainPairSerializer):

    def validate(self, attrs):
        try:
            data = super().validate(attrs)
        except AuthenticationFailed as exc:
            raise AuthenticationFailed("Credenciales inválidas.") from exc

        data["user"] = {
            "id": self.user.id,
            "username": self.user.username,
            "email": self.user.email,
            "role": self.user.rol,
        }

        return data
