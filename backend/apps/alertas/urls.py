from django.urls import path

from .views import (ListadoAlertasView, ResumenAlertasView, DetalleAlertaView,
                    HistorialAlertaView, AtenderAlertaView)

urlpatterns = [
    path("", ListadoAlertasView.as_view(), name="alertas-listado"),
    path("resumen/", ResumenAlertasView.as_view(), name="alertas-resumen"),
    path("<int:pk>/", DetalleAlertaView.as_view(), name="alertas-detalle"),
    path("<int:pk>/historial/", HistorialAlertaView.as_view(), name="alertas-historial"),
    path("<int:pk>/atender/", AtenderAlertaView.as_view(), name="alertas-atender"),
]
