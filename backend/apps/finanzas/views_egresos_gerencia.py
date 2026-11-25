"""SPEC-021: supervisión de egresos, sin modificar el libro de pagos."""
import re
from decimal import Decimal, localcontext

from django.db.models import Count, Max, Q, Sum
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response

from . import consultas_egresos as consultas
from .models import Egreso, PagoDocumento
from .permissions_egresos import revalidar
from .serializers_egresos import EgresoLecturaSerializer
from .views_egresos import EgresosAPIView
from .views_documentos import FinanzasPaginacion


class SupervisionEgresosView(EgresosAPIView):
    def get(self, request):
        actor = revalidar(request.user)
        if actor.rol != "GERENCIA":
            raise PermissionDenied("Consulta exclusiva de Gerencia.")
        params = request.query_params
        consultas.validar_query(params, {"vista", "buscar", "categoria", "medio", "desde", "hasta", "page"})
        inicio, fin = consultas.periodo(params, obligatorio=True)
        vista = params.get("vista", "activos")
        buscar = params.get("buscar", "").strip()
        if vista not in {"activos", "anulados", "todos"} or len(buscar) > 100:
            raise ValidationError({"query": "Consulta inválida."})
        qs = Egreso.objects.filter(fecha_pago__range=(inicio, fin))
        # Una única consulta agregada para todos los indicadores; nombre de
        # beneficiario registrado, no identidad de proveedor ni RUT inferido.
        grupos = qs.filter(activo=True).order_by().values("categoria", "beneficiario").annotate(
            total=Sum("monto"), pagos=Count("pk"), mayor=Max("monto"))
        categorias = {c: Decimal("0.00") for c in Egreso.Categoria.values}
        beneficiarios = {}
        total = mayor = Decimal("0.00")
        pagos = 0
        with localcontext() as ctx:
            ctx.prec = 80
            for g in grupos:
                importe = g["total"]
                total += importe
                categorias[g["categoria"]] += importe
                pagos += g["pagos"]
                mayor = max(mayor, g["mayor"])
                nombre = g["beneficiario"]
                valor, cantidad = beneficiarios.get(nombre, (Decimal("0.00"), 0))
                beneficiarios[nombre] = (valor + importe, cantidad + g["pagos"])
            ranking = sorted(beneficiarios.items(), key=lambda e: (-e[1][0], e[0]))[:3]
            resumen = {"moneda": "CLP", "desde": inicio.isoformat(), "hasta": fin.isoformat(),
                       "total": format(total, ".2f"), "pagos": pagos, "beneficiarios": len(beneficiarios),
                       "mayor": format(mayor, ".2f"),
                       "categorias": [{"categoria": c, "monto": format(v, ".2f")} for c, v in categorias.items()],
                       "ranking": [{"beneficiario": n, "monto": format(v, ".2f"), "pagos": p} for n, (v, p) in ranking]}
        if vista != "todos":
            qs = qs.filter(activo=vista == "activos")
        for campo, opciones in (("categoria", Egreso.Categoria.values), ("medio", PagoDocumento.Medio.values)):
            if campo in params:
                if params[campo] not in opciones:
                    raise ValidationError({campo: "Valor no permitido."})
                qs = qs.filter(**{campo: params[campo]})
        if buscar:
            filtro = Q(concepto__icontains=buscar) | Q(beneficiario__icontains=buscar)
            match = re.fullmatch(r"OB-([0-9]{1,19})", buscar, re.IGNORECASE)
            if match and 0 < int(match[1]) <= 9223372036854775807:
                filtro |= Q(obra_id=int(match[1]))
            qs = qs.filter(filtro)
        paginator = FinanzasPaginacion()
        rows = paginator.paginate_queryset(qs.order_by("-fecha_pago", "-id"), request, view=self)
        response = paginator.get_paginated_response(EgresoLecturaSerializer(rows, many=True).data)
        response.data["resumen"] = resumen
        return response
