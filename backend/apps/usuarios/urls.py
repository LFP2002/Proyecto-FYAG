from django.urls import path

from .views import (
    CsrfTokenView,
    LoginView,
    LogoutView,
    PerfilActualView,
    RefreshView,
)
from .views_usuarios import CambiarClavePropiaView


urlpatterns = [
    path("cambiar-clave/", CambiarClavePropiaView.as_view(), name="cambiar_clave_propia"),
    path(
        "csrf/",
        CsrfTokenView.as_view(),
        name="csrf",
    ),
    path(
        "login/",
        LoginView.as_view(),
        name="login",
    ),
    path(
        "refresh/",
        RefreshView.as_view(),
        name="token_refresh",
    ),
    path(
        "logout/",
        LogoutView.as_view(),
        name="logout",
    ),
    path(
        "me/",
        PerfilActualView.as_view(),
        name="perfil_actual",
    ),
]
