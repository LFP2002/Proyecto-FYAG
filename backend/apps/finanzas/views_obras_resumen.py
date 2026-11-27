"""Proyección económica de obras para AF, sin ampliar serializers operativos."""
import re
from datetime import date

from django.db.models import Case, CharField, Exists, F, OuterRef, Q, Value, When
from django.db.models.functions import Concat
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.comercial.proyecciones import neto_aprobado
from apps.obras.models import CierreCostosObra, CortesiaObra, Obra
from apps.obras.serializers import ObraFinanzasSerializer
from .models import CierreSinCobro, DocumentoCobro
from .permissions import PermisoFinanciero
from .consultas_cobranzas import con_cobranza, resumen_documento
from .views_documentos import FinanzasPaginacion, pk_url, query_estricta

ESTADOS = ("NO_HABILITADA", "PENDIENTE_VALIDACION", "PENDIENTE_FACTURACION",
           "PENDIENTE_REGISTRO_SIN_COBRO", "DOCUMENTADO", "SIN_COBRO")


def consulta():
    return Obra.objects.select_related(
        "presupuesto__cliente", "categoria_servicio", "tecnico_responsable"
    ).prefetch_related("presupuesto__items").annotate(
        con_documento=Exists(DocumentoCobro.objects.filter(obra_id=OuterRef("pk"), estado="VIGENTE")),
        sin_cobro=Exists(CierreSinCobro.objects.filter(obra_id=OuterRef("pk"))),
        con_cortesia=Exists(CortesiaObra.objects.filter(obra_id=OuterRef("pk"), tipo="SIN_COBRO")),
        con_cierre=Exists(CierreCostosObra.objects.filter(obra_id=OuterRef("pk"))),
    ).annotate(situacion_financiera=Case(
        When(sin_cobro=True, then=Value("SIN_COBRO")),
        When(con_documento=True, then=Value("DOCUMENTADO")),
        When(~Q(estado="FINALIZADA"), then=Value("NO_HABILITADA")),
        When(Q(con_cierre=False) | ~Q(presupuesto__estado="APROBADO_CLIENTE"), then=Value("PENDIENTE_VALIDACION")),
        When(con_cortesia=True, then=Value("PENDIENTE_REGISTRO_SIN_COBRO")),
        default=Value("PENDIENTE_FACTURACION"), output_field=CharField(),
    )).order_by("-creado_en", "-id")


def proyeccion(obra):
    return {
        **ObraFinanzasSerializer(obra).data,
        "monto_neto_aprobado": format(neto_aprobado(obra.presupuesto), ".2f"),
        "situacion_financiera": obra.situacion_financiera,
    }


class ObrasResumenFinanzasView(APIView):
    permission_classes = [IsAuthenticated, PermisoFinanciero]
    solo_finanzas = True
    http_method_names = ["get", "head", "options"]

    def get(self, request, obra_id=None):
        if obra_id is not None:
            if request.query_params:
                raise ValidationError({"query": "No se admiten filtros en el detalle."})
            obra = consulta().filter(pk=pk_url(obra_id)).first()
            if obra is None:
                raise NotFound("Obra no encontrada.")
            documento = con_cobranza(DocumentoCobro.objects.filter(obra=obra, estado="VIGENTE")).first()
            # La situación y el saldo no representan costos ni ingresos estimados.
            data = proyeccion(obra)
            data["documento"] = {
                "folio": documento.folio_externo,
                "monto_total": format(documento.monto_total, ".2f"),
                "cobranza": resumen_documento(documento),
            } if documento else None
            return Response(data, headers={"Cache-Control": "private, no-store"})

        params = request.query_params
        query_estricta(params, {"buscar", "estado", "situacion_financiera", "cliente_nombre", "categoria_nombre", "responsable_nombre", "fecha_programada_desde", "fecha_programada_hasta", "ordering"})
        qs = consulta()
        for campo, estados in (("estado", Obra.Estado.values), ("situacion_financiera", ESTADOS)):
            if campo in params:
                if params[campo] not in estados:
                    raise ValidationError({campo: "Valor no permitido."})
                qs = qs.filter(**{campo: params[campo]})
        for campo, lookup in (
            ("cliente_nombre", "presupuesto__cliente__nombre_legal__icontains"),
            ("categoria_nombre", "categoria_servicio__nombre__icontains"),
            ("responsable_nombre", None),
            ("buscar", None),
        ):
            if campo not in params:
                continue
            term = params[campo].strip()
            if not term or len(term) > 150 or any(ord(c) < 32 for c in term):
                raise ValidationError({campo: "Búsqueda no válida."})
            if lookup:
                qs = qs.filter(**{lookup: term})
            elif campo == 'responsable_nombre':
                qs = qs.annotate(nombre_responsable=Concat('tecnico_responsable__first_name', Value(' '), 'tecnico_responsable__last_name')).filter(Q(nombre_responsable__icontains=term) | Q(tecnico_responsable__username__icontains=term))
            else:
                criteria = Q(presupuesto__cliente__nombre_legal__icontains=term) | Q(categoria_servicio__nombre__icontains=term)
                match = re.fullmatch(r"OB-([0-9]{1,19})", term.upper())
                if match and 0 < int(match[1]) <= 9223372036854775807:
                    criteria |= Q(pk=int(match[1]))
                qs = qs.filter(criteria)
        fechas = {}
        for campo, lookup in (("fecha_programada_desde", "fecha_programada__gte"), ("fecha_programada_hasta", "fecha_programada__lte")):
            if campo in params:
                try:
                    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", params[campo]):
                        raise ValueError()
                    fechas[campo] = date.fromisoformat(params[campo])
                except ValueError:
                    raise ValidationError({campo: "Fecha inválida. Use YYYY-MM-DD."}) from None
                qs = qs.filter(**{lookup: fechas[campo]})
        if len(fechas) == 2 and fechas["fecha_programada_desde"] > fechas["fecha_programada_hasta"]:
            raise ValidationError({"fecha_programada_hasta": "Rango de fechas invertido."})
        if "ordering" in params:
            orden = params["ordering"]
            if orden not in {"creado_en", "-creado_en", "fecha_programada", "-fecha_programada"}:
                raise ValidationError({"ordering": "Orden no permitido."})
            if orden.endswith("fecha_programada"):
                campo = F("fecha_programada").desc(nulls_last=True) if orden.startswith("-") else F("fecha_programada").asc(nulls_last=True)
                qs = qs.order_by(campo, "-id" if orden.startswith("-") else "id")
            else:
                qs = qs.order_by(orden, "-id" if orden.startswith("-") else "id")
        paginator = FinanzasPaginacion()
        page = paginator.paginate_queryset(qs, request, view=self)
        response = paginator.get_paginated_response([proyeccion(obra) for obra in page])
        response["Cache-Control"] = "private, no-store"
        return response
