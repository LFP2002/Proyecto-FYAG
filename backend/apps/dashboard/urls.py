from django.urls import path

from .views import ResumenDashboardView, SerieObrasView, ObrasActivasView

urlpatterns = [
    path("resumen/", ResumenDashboardView.as_view(), name="dashboard-resumen"),
    path("serie-obras/", SerieObrasView.as_view(), name="dashboard-serie-obras"),
    path("obras-activas/", ObrasActivasView.as_view(), name="dashboard-obras-activas"),
]
