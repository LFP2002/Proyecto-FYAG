from django.urls import path
from rest_framework.routers import SimpleRouter

from .views import ArticuloViewSet, ExistenciaViewSet, MovimientoViewSet, IngresoView
from .views_materiales import OperacionesViewSet, EstadosValoracionViewSet

router = SimpleRouter()
router.register("articulos", ArticuloViewSet, basename="articulo-inventario")
router.register("existencias", ExistenciaViewSet, basename="existencia-inventario")
router.register("movimientos", MovimientoViewSet, basename="movimiento-inventario")
router.register('estados-valorizacion', EstadosValoracionViewSet, basename='estado-valorizacion')
urlpatterns = [path("ingresos/", IngresoView.as_view(), name="ingreso-inventario")] + router.urls
for ruta, tipo in [
    ('autorizaciones-entrega', 'AUTORIZACION_ENTREGA'), ('entregas', 'ENTREGA'),
    ('autorizaciones-devolucion', 'AUTORIZACION_DEVOLUCION'), ('devoluciones', 'DEVOLUCION'),
    ('valorizaciones', 'VALORIZACION'), ('regularizaciones-iniciales', 'REGULARIZACION'),
]:
    urlpatterns.append(path(ruta+'/', OperacionesViewSet.as_view({'get': 'list', 'post': 'create'}, tipo=tipo), name=ruta))
