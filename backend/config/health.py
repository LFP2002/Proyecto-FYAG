from django.db import DatabaseError, connections
from django.http import JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_safe


@never_cache
@require_safe
def live(request):
    return JsonResponse({"status": "ok"})


@never_cache
@require_safe
def ready(request):
    # SQL es común a las operaciones de negocio. No consultar servicios
    # auxiliares ni convertir una caída de estos en un reinicio del backend.
    try:
        with connections["default"].cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except DatabaseError:
        return JsonResponse({"status": "unavailable"}, status=503)
    return JsonResponse({"status": "ok"})
