from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import LoginView, PerfilActualView


urlpatterns = [
    path("login/", LoginView.as_view(), name="login"),
    path("refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("me/", PerfilActualView.as_view(), name="perfil_actual"),
]