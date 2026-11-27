from django.views.decorators.debug import sensitive_variables
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from .serializers_usuarios import ContratoEstrictoSerializer, EmailEstricto, TextoEstricto
from .services_usuarios import aprovisionar_primera_ti, instalacion_pendiente
from .throttles import SecurityRateThrottle
from .views_verificacion import VerificacionPublica


class SetupEstadoRate(SecurityRateThrottle):
    operation = 'setup-estado'
    ip_limit = (60, 60)
    identity_field = None


class SetupRate(SecurityRateThrottle):
    operation = 'setup-alta'
    ip_limit = (10, 900)
    identity_limit = (5, 900)


class SetupEntrada(ContratoEstrictoSerializer):
    first_name = TextoEstricto(max_length=150)
    last_name = TextoEstricto(max_length=150)
    username = TextoEstricto(max_length=150)
    email = EmailEstricto(max_length=254)
    clave_instalacion = TextoEstricto(trim_whitespace=False, allow_blank=True, write_only=True)
    password = TextoEstricto(max_length=4096, trim_whitespace=False, write_only=True)
    password_confirm = TextoEstricto(max_length=4096, trim_whitespace=False, write_only=True)


class SetupEstadoView(VerificacionPublica):
    throttle_classes = [SetupEstadoRate]

    def get(self, request):
        return Response({'pendiente': instalacion_pendiente()})


class SetupView(VerificacionPublica):
    throttle_classes = [SetupRate]

    @sensitive_variables()
    def post(self, request):
        entrada = SetupEntrada(data=request.data)
        entrada.is_valid(raise_exception=True)
        datos = entrada.validated_data
        clave = datos.pop('clave_instalacion')
        if datos.pop('password_confirm') != datos['password']:
            raise ValidationError({'password_confirm': ['Las contraseñas no coinciden.']})
        aprovisionar_primera_ti(datos, clave_instalacion=clave)
        return Response({'detail': 'Cuenta TI creada. Ya puedes iniciar sesión.'}, status=201)
