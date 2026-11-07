"""Rutas habilitadas únicamente para el incremento 004A."""

from rest_framework.routers import SimpleRouter

from .views import CategoriaServicioViewSet, ObraViewSet


router = SimpleRouter()
router.register("obras", ObraViewSet, basename="obra")
router.register("categorias-servicio", CategoriaServicioViewSet, basename="categoria-servicio")

urlpatterns = router.urls
