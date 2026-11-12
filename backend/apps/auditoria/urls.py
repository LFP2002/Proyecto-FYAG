from django.urls import path

from .views import EventosAuditoriaView

urlpatterns = [path("eventos/", EventosAuditoriaView.as_view(), name="auditoria-eventos")]
