from django.urls import path
from .views import DestinoView, DetalleView, DescargarView, AnotacionesView

urlpatterns = [
    path("documentos-cobro/<str:id>/", DestinoView.as_view(), {"tipo": "RESPALDO_FACTURA"}, name="adjuntos-documento"),
    path("obras/<str:id>/", DestinoView.as_view(), {"tipo": "INFORME_TECNICO"}, name="adjuntos-obra"),
    path("<str:id>/", DetalleView.as_view(), name="adjunto-detalle"),
    path("<str:id>/descargar/", DescargarView.as_view(), name="adjunto-descargar"),
    path("<str:id>/anotaciones/", AnotacionesView.as_view(), name="adjunto-anotaciones"),
]
