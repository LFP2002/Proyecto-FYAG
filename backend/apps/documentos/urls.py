from django.urls import path

from .views import ListadoView, DetalleView

urlpatterns = [
    path("", ListadoView.as_view(), name="documentos-metadata-listado"),
    path("evidencias/<str:evidencia>/", DetalleView.as_view(), name="documentos-metadata-detalle"),
]
