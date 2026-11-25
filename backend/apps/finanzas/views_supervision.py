"""Cartera gerencial: un único corte civil y una lectura de las filas financieras."""
from decimal import Decimal, localcontext

from rest_framework.exceptions import ValidationError
from rest_framework.permissions import BasePermission, IsAuthenticated
from rest_framework.views import APIView

from apps.usuarios.models import Usuario
from .consultas_cobranzas import con_cobranza
from .models import DocumentoCobro
from .services_documentos import ConflictoFinanciero
from .validaciones import LIMITE, hoy_santiago
from .views_documentos import FinanzasPaginacion, query_estricta
from .views_pagos import filtrar_fechas


class SoloGerencia(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and Usuario.objects.filter(
            pk=request.user.pk, is_active=True, rol=Usuario.Rol.GERENCIA).exists())


class SupervisionCobranzasView(APIView):
    permission_classes = [IsAuthenticated, SoloGerencia]
    http_method_names = ["get", "head", "options"]

    def get(self, request):
        params = request.query_params
        query_estricta(params, {"vista", "buscar", "desde", "hasta"})
        vista = params.get("vista", "atencion")
        buscar = params.get("buscar", "").strip().casefold()
        if vista not in {"atencion", "vigentes", "documentos"} or len(buscar) > 100:
            raise ValidationError({"query": "Consulta inválida."})
        if ("desde" in params) != ("hasta" in params):
            raise ValidationError({"desde": "Completa ambas fechas de emisión."})
        hoy = hoy_santiago()
        qs = DocumentoCobro.objects.all()
        if "desde" in params:
            qs = filtrar_fechas(qs, {"fecha_emision_desde": params["desde"], "fecha_emision_hasta": params["hasta"]}, "fecha_emision")
        qs = con_cobranza(qs, hoy=hoy).order_by("fecha_vencimiento", "id").values(
            "id", "folio_externo", "obra__presupuesto__cliente_id", "obra__codigo", "obra__presupuesto__cliente__nombre_legal",
            "fecha_emision", "fecha_vencimiento", "estado", "monto_total", "abonado_calculado",
            "saldo_calculado", "estado_cobranza_calculado")
        total = cobrado = saldo = vencido = Decimal("0.00")
        documentos = 0
        clientes_vencidos = set()
        rows = []
        with localcontext() as ctx:
            ctx.prec = 60
            for d in qs.iterator(chunk_size=200):
                vigente = d["estado"] == "VIGENTE"
                estado = d["estado_cobranza_calculado"] if vigente else "REVERTIDO"
                abono, restante = d["abonado_calculado"], d["saldo_calculado"]
                if vigente:
                    if not 0 <= abono <= d["monto_total"] or not 0 <= restante <= LIMITE:
                        raise ConflictoFinanciero("saldo_inconsistente", "El documento requiere revisión de integridad financiera.")
                    documentos += 1
                    total += d["monto_total"]
                    cobrado += abono
                    saldo += restante
                    if estado == "VENCIDA":
                        vencido += restante
                        clientes_vencidos.add(d["obra__presupuesto__cliente_id"])
                if vista == "atencion" and estado != "VENCIDA" or vista == "vigentes" and not vigente:
                    continue
                cliente, obra = d["obra__presupuesto__cliente__nombre_legal"], d["obra__codigo"]
                if buscar and buscar not in " ".join((cliente, obra, d["folio_externo"])).casefold():
                    continue
                rows.append({"id": d["id"], "folio": d["folio_externo"], "cliente": cliente, "obra": obra,
                    "emision": d["fecha_emision"].isoformat(), "vencimiento": d["fecha_vencimiento"].isoformat(),
                    "total": format(d["monto_total"], ".2f"), "cobrado": format(abono, ".2f") if vigente else None,
                    "saldo": format(restante, ".2f") if vigente else None, "estado": estado,
                    "dias_atraso": (hoy - d["fecha_vencimiento"]).days if estado == "VENCIDA" else 0})
            if any(not value.is_finite() or not 0 <= value <= LIMITE for value in (total, cobrado, saldo, vencido)):
                raise ConflictoFinanciero("importe_fuera_rango", "El agregado financiero requiere revisión.")
            resumen = {"moneda": "CLP", "documentos": documentos, "clientes_vencidos": len(clientes_vencidos),
                "total": format(total, ".2f"), "cobrado": format(cobrado, ".2f"), "saldo": format(saldo, ".2f"),
                "vencido": format(vencido, ".2f"), "no_vencido": format(saldo-vencido, ".2f"), "fecha_corte": hoy.isoformat()}
        rows.sort(key=lambda r: {"VENCIDA": 0, "PARCIAL": 1, "PENDIENTE": 1, "PAGADA": 2, "REVERTIDO": 3}[r["estado"]])
        paginator = FinanzasPaginacion()
        response = paginator.get_paginated_response(paginator.paginate_queryset(rows, request, view=self))
        response.data["resumen"] = resumen
        response["Cache-Control"] = "private, no-store"
        return response
