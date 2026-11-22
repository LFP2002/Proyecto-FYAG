from django.urls import path

from .views import UsuariosView, ConversacionesView, ConversacionView, MensajesView, ArchivosView, LeidoView, DescargarView
from .views import ConexionView

urlpatterns = [
    path('conexion/', ConexionView.as_view(), name='chat-conexion'),
    path('usuarios/', UsuariosView.as_view(), name='chat-usuarios'),
    path('conversaciones/', ConversacionesView.as_view(), name='chat-conversaciones'),
    path('conversaciones/<str:conversacion_id>/', ConversacionView.as_view(), name='chat-conversacion'),
    path('conversaciones/<str:conversacion_id>/mensajes/', MensajesView.as_view(), name='chat-mensajes'),
    path('conversaciones/<str:conversacion_id>/archivos/', ArchivosView.as_view(), name='chat-archivos'),
    path('conversaciones/<str:conversacion_id>/leido/', LeidoView.as_view(), name='chat-leido'),
    path('archivos/<str:archivo_id>/descargar/', DescargarView.as_view(), name='chat-descargar'),
]
