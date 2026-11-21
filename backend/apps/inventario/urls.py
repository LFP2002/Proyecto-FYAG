from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import ArticuloViewSet, ExistenciaViewSet, MovimientoViewSet, IngresoView

router = SimpleRouter()
router.register("articulos", ArticuloViewSet, basename="articulo-inventario")
router.register("existencias", ExistenciaViewSet, basename="existencia-inventario")
router.register("movimientos", MovimientoViewSet, basename="movimiento-inventario")
urlpatterns = [path("ingresos/", IngresoView.as_view(), name="ingreso-inventario")] + router.urls
