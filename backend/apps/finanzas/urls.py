from django.urls import path
from rest_framework.routers import SimpleRouter

from .views_documentos import DocumentoViewSet, ObrasElegiblesView, RegistrarSinCobroView, EstadoFinancieroView
from .views_pagos import PagosListaView, PagoDetalleView, PagoAnularView, PagosHistorialView, CobranzasView, CobranzasResumenView

router = SimpleRouter()
router.register("documentos", DocumentoViewSet, basename="documento-financiero")
urlpatterns = [
    path("documentos/<str:documento_id>/pagos/", PagosListaView.as_view(), name="pagos-documento"),
    path("documentos/<str:documento_id>/pagos/historial/", PagosHistorialView.as_view(), name="historial-pagos-documento"),
    path("documentos/<str:documento_id>/pagos/<str:pago_id>/anular/", PagoAnularView.as_view(), name="anular-pago-documento"),
    path("documentos/<str:documento_id>/pagos/<str:pago_id>/", PagoDetalleView.as_view(), name="detalle-pago-documento"),
    path("cobranzas/resumen/", CobranzasResumenView.as_view(), name="resumen-cobranzas"),
    path("cobranzas/", CobranzasView.as_view(), name="cobranzas"),
    path("obras-elegibles/", ObrasElegiblesView.as_view(), name="obras-elegibles-finanzas"),
    path("obras/<str:obra_id>/registrar-sin-cobro/", RegistrarSinCobroView.as_view(), name="registrar-sin-cobro"),
    path("obras/<str:obra_id>/estado-financiero/", EstadoFinancieroView.as_view(), name="estado-financiero"),
] + router.urls
