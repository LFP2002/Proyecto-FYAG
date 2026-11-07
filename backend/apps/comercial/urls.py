from rest_framework.routers import SimpleRouter

from .views import ClienteViewSet
from .views_presupuestos import PresupuestoViewSet


router = SimpleRouter()
router.register("clientes", ClienteViewSet, basename="cliente")
router.register("presupuestos", PresupuestoViewSet, basename="presupuesto")

urlpatterns = router.urls
