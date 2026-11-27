from django.urls import path

from .views import (
    CsrfTokenView,
    LoginView,
    LogoutView,
    PerfilActualView,
    RefreshView,
    PrimerCambioView,
)
from .views_usuarios import CambiarClavePropiaView
from .views_verificacion import ReenviarCorreoView, VerificarCorreoView
from .views_setup import SetupEstadoView, SetupView


urlpatterns = [
    path('setup/estado/', SetupEstadoView.as_view(), name='setup_estado'),
    path('setup/', SetupView.as_view(), name='setup_primera_ti'),
    path('correo/reenviar/', ReenviarCorreoView.as_view(), name='correo_reenviar'),
    path('correo/verificar/', VerificarCorreoView.as_view(), name='correo_verificar'),
    path("primer-cambio-clave/", PrimerCambioView.as_view(), name="primer_cambio_clave"),
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
