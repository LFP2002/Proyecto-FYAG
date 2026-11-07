"""Rutas operativas 004A y participantes 004B-1, sin acciones terminales."""

from rest_framework.routers import SimpleRouter

from .views import CategoriaServicioViewSet, ObraViewSet


router = SimpleRouter()
router.register("obras", ObraViewSet, basename="obra")
router.register("categorias-servicio", CategoriaServicioViewSet, basename="categoria-servicio")

urlpatterns = router.urls
