from django.http import FileResponse
from django.shortcuts import get_object_or_404
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.response import Response

from apps.usuarios.models import Usuario
from . import services_turnos
from .evidencias import ruta_privada
from .models import TurnoObra
from .serializers_turnos import TurnoLecturaSerializer, TurnoSupervisorSerializer


class TurnosMixin:
    def _turnos_queryset(self, obra):
        queryset = TurnoObra.objects.filter(obra=obra).prefetch_related("fotos")
        if self.request.user.rol == Usuario.Rol.TECNICO:
            queryset = queryset.filter(tecnico=self.request.user)
        return queryset.order_by("iniciado_en", "id")

    def _turno_autorizado(self, obra, turno_id):
        if not 0 < int(turno_id) <= 9223372036854775807:
            raise NotFound()
        return get_object_or_404(self._turnos_queryset(obra), pk=turno_id)

    def _turno_serializer(self):
        return TurnoLecturaSerializer if self.request.user.rol == Usuario.Rol.TECNICO else TurnoSupervisorSerializer

    def _respuesta_turno(self, turno, status=200):
        return Response(self._turno_serializer()(turno).data, status=status)

    @action(detail=True, methods=["get"], url_path="turnos")
    def turnos(self, request, pk=None):
        obra = self.get_object()
        if set(request.query_params) - {"page"} or len(request.query_params.getlist("page")) > 1:
            raise ValidationError({"detail": "Solo se admite page una vez."})
        return self._paginado(self._turnos_queryset(obra), self._turno_serializer())

    @action(detail=True, methods=["post"], url_path="turnos/iniciar", parser_classes=[JSONParser])
    def iniciar_turno(self, request, pk=None):
        obra = self.get_object()
        turno = services_turnos.iniciar_turno(obra, self._datos(), request.user)
        return self._respuesta_turno(turno, 201)

    def _escribir_turno(self, turno_id, operacion, con_fotos=False):
        obra = self.get_object()
        turno = self._turno_autorizado(obra, turno_id)
        datos = self._datos()
        extras = {"fotos": datos.pop("fotos", [])} if con_fotos else {}
        actual = operacion(obra, turno.pk, datos, self.request.user, **extras)
        return self._respuesta_turno(actual)

    @action(detail=True, methods=["post"], url_path=r"turnos/(?P<turno_id>[0-9]+)/finalizar", parser_classes=[JSONParser, MultiPartParser])
    def finalizar_turno(self, request, pk=None, turno_id=None):
        return self._escribir_turno(turno_id, services_turnos.finalizar_turno, con_fotos=True)

    @action(detail=True, methods=["post"], url_path=r"turnos/(?P<turno_id>[0-9]+)/subsanar", parser_classes=[JSONParser, MultiPartParser])
    def subsanar_turno(self, request, pk=None, turno_id=None):
        return self._escribir_turno(turno_id, services_turnos.subsanar_turno, con_fotos=True)

    @action(detail=True, methods=["post"], url_path=r"turnos/(?P<turno_id>[0-9]+)/revisar", parser_classes=[JSONParser])
    def revisar_turno(self, request, pk=None, turno_id=None):
        return self._escribir_turno(turno_id, services_turnos.revisar_turno)

    @action(detail=True, methods=["post"], url_path=r"turnos/(?P<turno_id>[0-9]+)/corregir", parser_classes=[JSONParser])
    def corregir_turno(self, request, pk=None, turno_id=None):
        return self._escribir_turno(turno_id, services_turnos.corregir_turno)

    @action(detail=True, methods=["post"], url_path=r"turnos/(?P<turno_id>[0-9]+)/cerrar-administrativamente", parser_classes=[JSONParser])
    def cerrar_administrativamente(self, request, pk=None, turno_id=None):
        return self._escribir_turno(turno_id, services_turnos.cerrar_administrativamente)

    @action(detail=True, methods=["get"], url_path=r"turnos/(?P<turno_id>[0-9]+)/fotos/(?P<foto_id>[0-9]+)")
    def foto_turno(self, request, pk=None, turno_id=None, foto_id=None):
        obra = self.get_object()
        turno = self._turno_autorizado(obra, turno_id)
        if not 0 < int(foto_id) <= 9223372036854775807:
            raise NotFound()
        foto = get_object_or_404(turno.fotos, pk=foto_id, obra=obra)
        try:
            archivo = ruta_privada(foto.nombre_interno).open("rb")
        except (FileNotFoundError, ValueError) as exc:
            raise NotFound() from exc
        extension = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}[foto.tipo_mime]
        respuesta = FileResponse(archivo, content_type=foto.tipo_mime, as_attachment=True, filename=f"evidencia-{foto.pk}.{extension}")
        respuesta["Cache-Control"] = "private, no-store"
        respuesta["X-Content-Type-Options"] = "nosniff"
        return respuesta
