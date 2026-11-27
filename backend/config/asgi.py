"""
ASGI config for config project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/asgi/
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

django_application = get_asgi_application()

from apps.usuarios.preflight_bloqueos import validar_arranque_si_productivo

validar_arranque_si_productivo()

from channels.routing import ProtocolTypeRouter, URLRouter
from django.urls import path
from apps.chat.ws import ChatConsumer, OriginChat

application = ProtocolTypeRouter({
    'http': django_application,
    'websocket': OriginChat(URLRouter([path('ws/chat/', ChatConsumer.as_asgi())])),
})
