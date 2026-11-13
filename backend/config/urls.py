from django.contrib import admin
from django.urls import include, path


urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("apps.usuarios.urls")),
    path("api/", include("apps.usuarios.urls_usuarios")),
    path("api/", include("apps.comercial.urls")),
    path("api/", include("apps.obras.urls")),
    path("api/finanzas/", include("apps.finanzas.urls")),
    path("api/auditoria/", include("apps.auditoria.urls")),
    path("api/alertas/", include("apps.alertas.urls")),
    path("api/dashboard/", include("apps.dashboard.urls")),
    path("api/reportes/", include("apps.reportes.urls")),
    path("api/documentos-metadata/", include("apps.documentos.urls")),
    path("api/adjuntos/", include("apps.adjuntos.urls")),
]
