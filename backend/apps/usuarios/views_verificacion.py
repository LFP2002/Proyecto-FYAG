from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.debug import sensitive_post_parameters, sensitive_variables
from rest_framework import serializers
from rest_framework.parsers import JSONParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers_usuarios import ContratoEstrictoSerializer, EmailEstricto
from .throttles import SecurityRateThrottle
from .verificacion import confirmar, encolar_reenvio


class ReenvioRate(SecurityRateThrottle):
    operation = 'correo-reenvio'
    ip_limit = (30, 3600)
    identity_limit = (3, 3600)


class ConfirmacionRate(SecurityRateThrottle):
    operation = 'correo-confirmacion'
    identity_field = 'token'
    ip_limit = (30, 60)


class Reenvio(ContratoEstrictoSerializer):
    email = EmailEstricto(max_length=254)


class Confirmacion(ContratoEstrictoSerializer):
    token = serializers.RegexField(r'\A[A-Za-z0-9_-]{43}\Z', trim_whitespace=False, write_only=True)


@method_decorator(never_cache, name='dispatch')
@method_decorator(csrf_protect, name='dispatch')
@method_decorator(sensitive_post_parameters(), name='dispatch')
class VerificacionPublica(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    parser_classes = [JSONParser]

    def finalize_response(self, *args, **kwargs):
        response = super().finalize_response(*args, **kwargs)
        response['Referrer-Policy'] = 'no-referrer'
        return response


class ReenviarCorreoView(VerificacionPublica):
    throttle_classes = [ReenvioRate]

    def post(self, request):
        entrada = Reenvio(data=request.data)
        entrada.is_valid(raise_exception=True)
        encolar_reenvio(entrada.validated_data['email'])
        return Response({'detail': 'Si corresponde verificar esa dirección, recibirás las instrucciones por correo.'}, status=202)


class VerificarCorreoView(VerificacionPublica):
    throttle_classes = [ConfirmacionRate]

    @sensitive_variables()
    def post(self, request):
        entrada = Confirmacion(data=request.data)
        entrada.is_valid(raise_exception=True)
        confirmar(entrada.validated_data['token'])
        return Response(status=204)
