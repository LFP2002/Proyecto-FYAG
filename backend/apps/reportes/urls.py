from django.urls import path

from .views import CatalogoView, ReporteListadoView, ExportarView

urlpatterns = [
    path("catalogo/", CatalogoView.as_view(), name="reportes-catalogo"),
    path("obras/", ReporteListadoView.as_view(), {"tipo": "obras"}, name="reportes-obras"),
    path("rentabilidad/", ReporteListadoView.as_view(), {"tipo": "rentabilidad"}, name="reportes-rentabilidad"),
    path("cobranzas/", ReporteListadoView.as_view(), {"tipo": "cobranzas"}, name="reportes-cobranzas"),
    path("<str:tipo>/exportar/", ExportarView.as_view(), name="reportes-exportar"),
]
