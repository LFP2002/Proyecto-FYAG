from rest_framework.routers import SimpleRouter

from .views_usuarios import UsuarioViewSet

router = SimpleRouter()
router.register("usuarios", UsuarioViewSet, basename="usuario")
urlpatterns = router.urls
