import re

from django.db.models import Exists, OuterRef
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.obras.models import Obra, CortesiaObra, CierreCostosObra
from . import services_documentos as services
from .models import DocumentoCobro, CierreSinCobro
from .permissions import PermisoFinanciero
from .serializers_documentos import DocumentoLecturaSerializer, FinanzasEventoSerializer, OrigenFinancieroSerializer, FechaISO


def pk_url(value):
    if not re.fullmatch(r"[0-9]{1,19}", str(value)):
        raise ValidationError({"id": "Identificador entero positivo requerido."})
    return services.identificador(int(value))


def query_estricta(params, allowed=()):
    errors = {key: "Parámetro no permitido." for key in params if key not in set(allowed) | {"page"}}
    errors.update({key: "Parámetro repetido." for key in params if len(params.getlist(key)) != 1})
    if "page" in params and not re.fullmatch(r"[1-9][0-9]{0,18}", params["page"]):
        errors["page"] = "Página entera positiva requerida."
    if errors:
        raise ValidationError(errors)


class FinanzasPaginacion(PageNumberPagination):
    page_size = 25


def obras_lectura():
    return Obra.objects.select_related("presupuesto__cliente", "cortesia", "cierre_sin_cobro").prefetch_related("presupuesto__items")


def documentos_lectura():
    return DocumentoCobro.objects.select_related("obra__presupuesto__cliente", "obra__cortesia").prefetch_related("obra__presupuesto__items")


class DocumentoViewSet(mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated, PermisoFinanciero]
    parser_classes = [JSONParser]
    serializer_class = DocumentoLecturaSerializer
    pagination_class = FinanzasPaginacion
    http_method_names = ["get", "post", "head", "options"]

    def get_queryset(self):
        return documentos_lectura().order_by("-registrado_en", "-id")

    def get_object(self):
        pk_url(self.kwargs["pk"])
        return super().get_object()

    def retrieve(self, request, *args, **kwargs):
        query_estricta(request.query_params)
        return super().retrieve(request, *args, **kwargs)

    def list(self, request):
        params = request.query_params
        query_estricta(params, {"estado", "tipo_documento", "obra", "cliente", "fecha_emision_desde", "fecha_emision_hasta"})
        qs = self.get_queryset()
        for field, choices in [("estado", DocumentoCobro.Estado.values), ("tipo_documento", DocumentoCobro.Tipo.values)]:
            if field in params:
                if params[field] not in choices:
                    raise ValidationError({field: "Valor no permitido."})
                qs = qs.filter(**{field: params[field]})
        for field, lookup in [("obra", "obra_id"), ("cliente", "obra__presupuesto__cliente_id")]:
            if field in params:
                qs = qs.filter(**{lookup: pk_url(params[field])})
        dates = {}
        for field, lookup in [("fecha_emision_desde", "fecha_emision__gte"), ("fecha_emision_hasta", "fecha_emision__lte")]:
            if field in params:
                try:
                    dates[field] = FechaISO().run_validation(params[field])
                except ValidationError as exc:
                    raise ValidationError({field: exc.detail}) from None
                qs = qs.filter(**{lookup: dates[field]})
        if len(dates) == 2 and dates["fecha_emision_desde"] > dates["fecha_emision_hasta"]:
            raise ValidationError({"fecha_emision_hasta": "Rango de fechas invertido."})
        page = self.paginate_queryset(qs)
        return self.get_paginated_response(self.get_serializer(page, many=True).data)

    def create(self, request):
        obj = services.registrar_documento(request.data, request.user)
        return Response(self.get_serializer(obj).data, status=201)

    @action(detail=True, methods=["post"])
    def revertir(self, request, pk=None):
        obj = services.revertir_documento(pk_url(pk), request.data, request.user)
        return Response(self.get_serializer(obj).data)

    @action(detail=True, methods=["get"])
    def historial(self, request, pk=None):
        query_estricta(request.query_params)
        obj = self.get_object()
        page = self.paginate_queryset(obj.eventos.order_by("creado_en", "id"))
        return self.get_paginated_response(FinanzasEventoSerializer(page, many=True).data)


class ObrasElegiblesView(APIView):
    permission_classes = [IsAuthenticated, PermisoFinanciero]
    solo_finanzas = True

    def get(self, request):
        query_estricta(request.query_params)
        qs = obras_lectura().filter(estado="FINALIZADA", presupuesto__estado="APROBADO_CLIENTE").annotate(
            tiene_cierre=Exists(CierreCostosObra.objects.filter(obra_id=OuterRef("pk"))),
            tiene_documento=Exists(DocumentoCobro.objects.filter(obra_id=OuterRef("pk"), estado="VIGENTE")),
            tiene_sin_cobro=Exists(CierreSinCobro.objects.filter(obra_id=OuterRef("pk"))),
            tiene_cortesia=Exists(CortesiaObra.objects.filter(obra_id=OuterRef("pk"), tipo="SIN_COBRO")),
        ).filter(tiene_cierre=True, tiene_documento=False, tiene_sin_cobro=False, tiene_cortesia=False).order_by("-finalizado_en", "-id")
        paginator = FinanzasPaginacion()
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response(OrigenFinancieroSerializer(page, many=True).data)


class RegistrarSinCobroView(APIView):
    permission_classes = [IsAuthenticated, PermisoFinanciero]
    parser_classes = [JSONParser]

    def post(self, request, obra_id):
        obj = services.registrar_sin_cobro(pk_url(obra_id), request.data, request.user)
        return Response({"id": obj.pk, "obra": obj.obra_id, "cortesia": obj.cortesia_id, "motivo_registro": obj.motivo_registro, "registrado_por": obj.registrado_por_id, "registrado_en": obj.registrado_en, "estado_financiero": "SIN_COBRO"}, status=201)


class EstadoFinancieroView(APIView):
    permission_classes = [IsAuthenticated, PermisoFinanciero]

    def get(self, request, obra_id):
        query_estricta(request.query_params)
        obra = obras_lectura().filter(pk=pk_url(obra_id)).first()
        if obra is None:
            raise NotFound("Obra no encontrada.")
        cierre = getattr(obra, "cierre_sin_cobro", None)
        documento = documentos_lectura().filter(obra=obra, estado="VIGENTE").first()
        cortesia = getattr(obra, "cortesia", None)
        state = "SIN_COBRO" if cierre else "DOCUMENTADO" if documento else "PENDIENTE_REGISTRO_SIN_COBRO" if cortesia else "PENDIENTE_FACTURACION"
        return Response({"origen": OrigenFinancieroSerializer(obra).data, "estado_financiero": state,
                         "documento_vigente": DocumentoLecturaSerializer(documento).data if documento else None,
                         "cierre_sin_cobro": {"id": cierre.pk, "cortesia": cierre.cortesia_id, "motivo_registro": cierre.motivo_registro, "registrado_por": cierre.registrado_por_id, "registrado_en": cierre.registrado_en,
                                              "eventos": FinanzasEventoSerializer(cierre.eventos.order_by("creado_en", "id"), many=True).data} if cierre else None})
