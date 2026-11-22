import hashlib
import hmac
from time import time

from django.conf import settings
from django.db import transaction, connection
from rest_framework.exceptions import Throttled

from .models import CupoChat


def limitar(request, accion):
    limites = settings.CHAT_LIMITES[accion]
    identidades = [f'u:{request.user.pk}', 'ip:'+request.META.get('REMOTE_ADDR', '')]
    keys = [hmac.new(settings.SECRET_KEY.encode(), (accion+':'+i).encode(), hashlib.sha256).hexdigest() for i in identidades]
    ventana = int(time())//60
    with transaction.atomic():
        # Mutex breve solo del contador, liberado antes de cualquier recurso.
        # Evita inversiones por colisiones hash entre dos claves usuario/IP.
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_advisory_xact_lock(2302,0)')
        for key, limite in sorted(zip(keys, limites)):
            cupo, nuevo = CupoChat.objects.get_or_create(clave=key, ventana=ventana)
            if not nuevo and cupo.cantidad >= limite:
                raise Throttled(wait=60-int(time())%60)
            if not nuevo:
                cupo.cantidad += 1
                cupo.save(update_fields=['cantidad'])
