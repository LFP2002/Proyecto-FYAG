from django.views.decorators.debug import sensitive_variables
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from .recuperacion_correo import confirmar, solicitar
from .serializers_usuarios import TextoEstricto
from .views_verificacion import Confirmacion, ConfirmacionRate, Reenvio, ReenvioRate, VerificacionPublica


class SolicitudRate(ReenvioRate):
    operation = 'recuperacion-solicitud'


class ConsumoRate(ConfirmacionRate):
    operation = 'recuperacion-confirmacion'


class Restablecimiento(Confirmacion):
    nueva_clave = TextoEstricto(max_length=4096, trim_whitespace=False, write_only=True)
    confirmacion = TextoEstricto(max_length=4096, trim_whitespace=False, write_only=True)


class SolicitarRecuperacionView(VerificacionPublica):
    throttle_classes = [SolicitudRate]

    def post(self, request):
        entrada = Reenvio(data=request.data)
        entrada.is_valid(raise_exception=True)
        solicitar(entrada.validated_data['email'])
        return Response({'detail': 'Si el correo electrónico corresponde a una cuenta habilitada para recuperación, recibirás las instrucciones para restablecer tu contraseña.'}, status=202)


class ConfirmarRecuperacionView(VerificacionPublica):
    throttle_classes = [ConsumoRate]

    @sensitive_variables()
    def post(self, request):
        entrada = Restablecimiento(data=request.data)
        entrada.is_valid(raise_exception=True)
        datos = entrada.validated_data
        if datos['nueva_clave'] != datos['confirmacion']:
            raise ValidationError({'confirmacion': ['Las contraseñas no coinciden.']})
        confirmar(datos['token'], datos['nueva_clave'])
        return Response(status=204)
