from django.conf import settings
from django.middleware.csrf import get_token, rotate_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect

from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from .serializers import LoginSerializer, VersionedRefreshSerializer
from .services import delete_refresh_cookie, set_refresh_cookie
from .throttles import (
    LoginEmailRateThrottle,
    LoginIPRateThrottle,
    RefreshIPRateThrottle,
)


class CsrfTokenView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        return Response({"csrfToken": get_token(request)})


@method_decorator(csrf_protect, name="dispatch")
class LoginView(TokenObtainPairView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [
        LoginIPRateThrottle,
        LoginEmailRateThrottle,
    ]
    serializer_class = LoginSerializer

    def post(self, request, *args, **kwargs):
        response = super().post(
            request,
            *args,
            **kwargs,
        )

        refresh_token = response.data.pop(
            "refresh",
            None,
        )

        if refresh_token:
            set_refresh_cookie(
                response,
                refresh_token,
            )

        # Evita reutilizar el CSRF previo al login.
        rotate_token(request)

        response.data["csrfToken"] = get_token(request)

        return response


@method_decorator(csrf_protect, name="dispatch")
class RefreshView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [
        RefreshIPRateThrottle,
    ]

    def post(self, request):
        refresh_token = request.COOKIES.get(settings.JWT_REFRESH_COOKIE_NAME)

        if not refresh_token:
            return Response(
                {"detail": "Sesión de renovación no disponible."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        serializer = VersionedRefreshSerializer(data={"refresh": refresh_token})

        try:
            serializer.is_valid(raise_exception=True)
        except (TokenError, AuthenticationFailed):
            return Response(
                {"detail": "Refresh token inválido o expirado."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        data = dict(serializer.validated_data)

        nuevo_refresh = data.pop(
            "refresh",
            None,
        )

        response = Response(
            data,
            status=status.HTTP_200_OK,
        )

        if nuevo_refresh:
            set_refresh_cookie(
                response,
                nuevo_refresh,
            )

        return response


@method_decorator(csrf_protect, name="dispatch")
class LogoutView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        refresh_token = request.COOKIES.get(settings.JWT_REFRESH_COOKIE_NAME)

        if refresh_token:
            try:
                token = RefreshToken(refresh_token)
                token.blacklist()
            except TokenError:
                pass

        response = Response(status=status.HTTP_204_NO_CONTENT)

        delete_refresh_cookie(response)

        return response


class PerfilActualView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(
            {
                "id": request.user.id,
                "username": request.user.username,
                "email": request.user.email,
                "role": request.user.rol,
            }
        )
