import logging
from uuid import uuid4

from django.db import IntegrityError
from django.conf import settings
from django.http import FileResponse
from django.utils.cache import patch_vary_headers
from rest_framework.exceptions import APIException, UnsupportedMediaType
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import consultas, services
from .limites import limitar
from .models import ParticipanteChat
from .parsers import JSONEstricto, MultipartChat
from .permissions import PermisoChat
from .serializers import ConversacionSerializer, MensajeSerializer, usuario_minimo
from .validaciones import id_url

logger = logging.getLogger(__name__)


class Paginacion(PageNumberPagination):
    page_size = 25


class ChatAPIView(APIView):
    permission_classes = [IsAuthenticated, PermisoChat]
    parser_classes = [JSONEstricto]
    http_method_names = ['get', 'post', 'head', 'options']

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        response['Cache-Control'] = 'private, no-store'
        response['X-Content-Type-Options'] = 'nosniff'
        patch_vary_headers(response, ['Authorization'])
        return response

    def handle_exception(self, exc):
        if isinstance(exc, UnsupportedMediaType):
            return Response({'detail': 'Content-Type no permitido para esta operación.'}, status=400)
        if isinstance(exc, APIException):
            return super().handle_exception(exc)
        if isinstance(exc, IntegrityError) and getattr(getattr(exc.__cause__, 'diag', None), 'constraint_name', '') == 'chat_integridad':
            return Response({'code': 'estado_incompatible', 'detail': 'Estado de chat incompatible.'}, status=409)
        correlacion = uuid4().hex
        logger.warning('chat_no_disponible correlacion=%s', correlacion)
        return Response({'detail': 'Chat no disponible temporalmente.', 'correlacion': correlacion}, status=503)

    def paginar(self, qs, serializar):
        paginador = Paginacion()
        pagina = paginador.paginate_queryset(qs, self.request, view=self)
        return paginador.get_paginated_response([serializar(x) for x in pagina])


class UsuariosView(ChatAPIView):
    http_method_names = ['get', 'head', 'options']

    def get(self, request):
        return self.paginar(consultas.directorio(request.user, request.query_params), usuario_minimo)


class ConversacionesView(ChatAPIView):
    def get(self, request):
        consultas.query(request.query_params, {'page'})
        return self.paginar(consultas.con_contadores(consultas.conversaciones(request.user), request.user), lambda x: ConversacionSerializer(x).data)

    def post(self, request):
        consultas.query(request.query_params, set())
        limitar(request, 'conversacion')
        conv, nuevo = services.crear_conversacion(request.data, request.user)
        conv = consultas.con_contadores(consultas.conversaciones(request.user).filter(pk=conv.pk), request.user).get()
        return Response(ConversacionSerializer(conv).data, status=201 if nuevo else 200,
            headers={'Idempotency-Replayed': 'false' if nuevo else 'true'})


class ConversacionView(ChatAPIView):
    http_method_names = ['get', 'head', 'options']

    def get(self, request, conversacion_id):
        consultas.query(request.query_params, set())
        conv = consultas.obtener(request.user, id_url(conversacion_id))
        conv = consultas.con_contadores(consultas.conversaciones(request.user).filter(pk=conv.pk), request.user).get()
        data = ConversacionSerializer(conv).data
        miembros = ParticipanteChat.objects.filter(conversacion=conv).select_related('usuario').order_by('usuario_id')
        data['participantes'] = [usuario_minimo(p.usuario) for p in miembros]
        propio = next(p for p in miembros if p.usuario_id == request.user.pk)
        data['ultimo_leido_mensaje_id'] = propio.ultimo_leido_mensaje_id
        return Response(data)


class MensajesView(ChatAPIView):
    def get(self, request, conversacion_id):
        qs = consultas.mensajes(request.user, id_url(conversacion_id), request.query_params)
        pagina = list(qs[:26])
        visible = pagina[:25]
        return Response({'results': MensajeSerializer(visible, many=True).data,
            'siguiente_antes_id': visible[-1].pk if len(pagina) > 25 else None})

    def post(self, request, conversacion_id):
        consultas.query(request.query_params, set())
        pk = id_url(conversacion_id)
        consultas.obtener(request.user, pk)
        limitar(request, 'mensaje')
        mensaje, nuevo = services.publicar_texto(pk, request.data, request.user)
        return Response(MensajeSerializer(mensaje).data, status=201 if nuevo else 200,
            headers={'Idempotency-Replayed': 'false' if nuevo else 'true'})


class ArchivosView(ChatAPIView):
    http_method_names = ['post', 'options']
    parser_classes = [MultipartChat]

    def post(self, request, conversacion_id):
        consultas.query(request.query_params, set())
        pk = id_url(conversacion_id)
        consultas.obtener(request.user, pk)
        limitar(request, 'archivo')
        mensaje, nuevo = services.publicar_archivo(pk, request.data, request.headers.get('Idempotency-Key'), request.user)
        return Response(MensajeSerializer(mensaje).data, status=201 if nuevo else 200,
            headers={'Idempotency-Replayed': 'false' if nuevo else 'true'})


class LeidoView(ChatAPIView):
    http_method_names = ['post', 'options']

    def post(self, request, conversacion_id):
        consultas.query(request.query_params, set())
        p = services.leer(id_url(conversacion_id), request.data, request.user)
        return Response({'ultimo_leido_mensaje_id': p.ultimo_leido_mensaje_id})


class DescargarView(ChatAPIView):
    http_method_names = ['get', 'head', 'options']

    def get(self, request, archivo_id):
        consultas.query(request.query_params, set())
        archivo, copia = services.descargar(id_url(archivo_id), request.user)
        return FileResponse(copia, as_attachment=True, filename=archivo.nombre, content_type=archivo.mime)


class ConexionView(ChatAPIView):
    http_method_names = ['post', 'options']

    def post(self, request):
        from .tickets import emitir
        from .validaciones import contrato
        from .serializers import FechaUTC
        consultas.query(request.query_params, set())
        contrato(request.data, set(), set())
        limitar(request, 'ticket', limites=settings.CHAT_WS_TICKET_RATE)
        ticket, vence = emitir(request.user, request.auth)
        return Response({'ticket': ticket, 'vence_en': FechaUTC().to_representation(vence)}, status=201)
