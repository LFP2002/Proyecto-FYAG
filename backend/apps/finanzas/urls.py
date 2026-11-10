from django.urls import path
from rest_framework.routers import SimpleRouter

from .views_documentos import DocumentoViewSet, ObrasElegiblesView, RegistrarSinCobroView, EstadoFinancieroView

router = SimpleRouter()
router.register("documentos", DocumentoViewSet, basename="documento-financiero")
urlpatterns = [
    path("obras-elegibles/", ObrasElegiblesView.as_view(), name="obras-elegibles-finanzas"),
    path("obras/<str:obra_id>/registrar-sin-cobro/", RegistrarSinCobroView.as_view(), name="registrar-sin-cobro"),
    path("obras/<str:obra_id>/estado-financiero/", EstadoFinancieroView.as_view(), name="estado-financiero"),
] + router.urls
