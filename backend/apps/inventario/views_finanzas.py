"""Proyección operativa exclusiva de Finanzas. Los servicios de escritura conservan la autoridad."""
from decimal import Decimal, localcontext

from django.db.models import Exists, F, OuterRef, Q, Value
from django.db.models.functions import Coalesce
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from .models import ArticuloInventario, EstadoValoracion, MovimientoInventario, OperacionMaterial
from .permissions import PuedeOperarInventario
from .services_mermas import importe
from .views import InventarioPaginacion, query
from .views_materiales import CabecerasMateriales


def identidad(a):
    return {"nombre": a.nombre, "codigo": a.codigo, "unidad": a.unidad}


def material_search(qs, term, prefix=""):
    if term:
        return qs.filter(Q(**{prefix + "nombre__icontains": term}) | Q(**{prefix + "codigo__icontains": term}))
    return qs


def existencias(term, filtro):
    rows = []
    resumen = {"materiales": 0, "sin_stock": 0, "pendientes": 0, "valor_neto": "0.00"}
    total = Decimal("0.00")
    qs = ArticuloInventario.objects.select_related("existencia", "estadovaloracion").order_by("nombre", "id")
    with localcontext() as ctx:
        ctx.prec = 60
        for a in qs.iterator(chunk_size=200):
            stock = getattr(a, "existencia", None)
            v = getattr(a, "estadovaloracion", None)
            saldo = stock.saldo if stock else None
            pendiente = saldo is None or v is None or saldo != v.saldo_valorado or (v.saldo_valorado > 0 and v.promedio is None)
            agotado = a.activo and saldo == 0
            valor = importe(v.saldo_valorado, v.promedio, estricto=False) if v and v.promedio is not None else (Decimal("0.00") if saldo == 0 or (v and v.saldo_valorado == 0) else None)
            resumen["materiales"] += 1
            resumen["sin_stock"] += int(agotado)
            resumen["pendientes"] += int(pendiente)
            if valor is not None:
                total += valor
            if term and term.casefold() not in a.nombre.casefold() and term.casefold() not in a.codigo.casefold():
                continue
            if (filtro == "sin_stock" and not agotado) or (filtro == "pendiente" and not pendiente):
                continue
            rows.append({"id": a.pk, **identidad(a), "descripcion": a.descripcion, "activo": a.activo,
                         "saldo": format(saldo, ".3f") if saldo is not None else None,
                         "pendiente": pendiente, "valor_neto": format(valor, ".2f") if valor is not None else None})
    resumen["valor_neto"] = format(total, ".2f")
    return rows, resumen


def ingresos_elegibles():
    # Se ofrece exclusivamente el primer ingreso aún no valorizado por artículo.
    historial = Coalesce("articulo__estadovaloracion__ultimo_movimiento_historico", Value(0))
    anteriores = MovimientoInventario.objects.filter(articulo_id=OuterRef("articulo_id"), tipo="INGRESO",
        pk__gt=historial, pk__lt=OuterRef("pk"), valoracion__isnull=True)
    regularizado = OperacionMaterial.objects.filter(articulo_id=OuterRef("articulo_id"), tipo="REGULARIZACION")
    return (MovimientoInventario.objects.filter(tipo="INGRESO", valoracion__isnull=True,
             articulo__estadovaloracion__isnull=False, pk__gt=historial)
            .annotate(anteriores=Exists(anteriores), regularizado=Exists(regularizado))
            .filter(anteriores=False)
            .filter(Q(articulo__estadovaloracion__saldo_historico=0) | Q(regularizado=True))
            .select_related("articulo").order_by("pk"))


def historicos_elegibles():
    previos = OperacionMaterial.objects.filter(articulo_id=OuterRef("articulo_id"), tipo__in=["REGULARIZACION", "VALORIZACION"])
    return (EstadoValoracion.objects.filter(saldo_historico__gt=0).annotate(previos=Exists(previos))
            .filter(previos=False).select_related("articulo").order_by("articulo__nombre", "articulo_id"))


class FinanzasInventarioView(CabecerasMateriales, APIView):
    permission_classes = [IsAuthenticated, PuedeOperarInventario]
    http_method_names = ["get", "head", "options"]

    def get(self, request):
        if request.user.rol != "ADMINISTRATIVO_FINANZAS":
            raise PermissionDenied("Consulta exclusiva de Finanzas.")
        params = request.query_params
        section = params.get("seccion", "inventario")
        allowed = {"inventario": {"filtro"}, "movimientos": {"tipo", "desde", "hasta"},
                   "valoraciones": set(), "regularizaciones": set(), "ingresos": set(), "historicos": set()}
        if section not in allowed:
            raise ValidationError({"seccion": "Sección inválida."})
        query(params, {"seccion", "buscar"} | allowed[section])
        term = params.get("buscar", "").strip()
        if "buscar" in params and (not term or len(term) > 150 or any(ord(c) < 32 for c in term)):
            raise ValidationError({"buscar": "Búsqueda inválida."})
        resumen = None
        if section == "inventario":
            filtro = params.get("filtro", "")
            if filtro not in {"", "sin_stock", "pendiente"}:
                raise ValidationError({"filtro": "Filtro inválido."})
            rows, resumen = existencias(term, filtro)
            project = lambda r: r
        elif section in {"movimientos", "ingresos"}:
            if section == "movimientos":
                # Reutiliza la validación de fechas y tipos del libro físico.
                from datetime import date
                import re
                rows = MovimientoInventario.objects.all()
                if "tipo" in params:
                    if params["tipo"] not in MovimientoInventario.Tipo.values:
                        raise ValidationError({"tipo": "Tipo inválido."})
                    rows = rows.filter(tipo=params["tipo"])
                if ("desde" in params) != ("hasta" in params):
                    raise ValidationError({"desde": "Indique ambas fechas."})
                if "desde" in params:
                    try:
                        if not all(re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", params[k]) for k in ("desde", "hasta")):
                            raise ValueError()
                        desde, hasta = date.fromisoformat(params["desde"]), date.fromisoformat(params["hasta"])
                        if desde > hasta or (hasta-desde).days >= 366:
                            raise ValueError()
                    except ValueError:
                        raise ValidationError({"desde": "Período inválido."}) from None
                    rows = rows.filter(creado_en__date__range=(desde, hasta))
                rows = rows.select_related("articulo").order_by("-creado_en", "-pk")
            else:
                rows = ingresos_elegibles()
            rows = material_search(rows, term, "articulo__")
            def project(r):
                return {"id": r.pk, **identidad(r.articulo), "tipo": r.tipo, "cantidad": format(r.cantidad, ".3f"),
                        "saldo_anterior": format(r.saldo_anterior, ".3f"), "saldo_posterior": format(r.saldo_posterior, ".3f"),
                        "referencia": r.referencia, "motivo": r.motivo, "creado_en": r.creado_en.isoformat()}
        elif section == "historicos":
            rows = material_search(historicos_elegibles(), term, "articulo__")
            def project(r):
                return {"id": r.articulo_id, **identidad(r.articulo), "cantidad": format(r.saldo_historico, ".3f")}
        else:
            rows = material_search(OperacionMaterial.objects.filter(tipo="VALORIZACION" if section == "valoraciones" else "REGULARIZACION")
                                   .select_related("articulo", "ingreso").order_by("-pk"), term, "articulo__")
            def project(r):
                def fmt(v, places):
                    return format(v, places) if v is not None else None
                return {"id": r.pk, **identidad(r.articulo), "tipo": r.tipo, "cantidad": fmt(r.cantidad, ".3f"),
                        "costo_unitario_neto": fmt(r.costo_unitario_neto, ".2f"), "saldo_valorado_anterior": fmt(r.saldo_valorado_anterior, ".3f"),
                        "saldo_valorado_posterior": fmt(r.saldo_valorado_posterior, ".3f"), "promedio_anterior": fmt(r.promedio_anterior, ".2f"),
                        "promedio_posterior": fmt(r.promedio_posterior, ".2f"), "referencia": r.referencia, "motivo": r.motivo,
                        "creado_en": r.creado_en.isoformat(), "referencia_ingreso": r.ingreso.referencia if r.ingreso_id else None}
        paginator = InventarioPaginacion()
        response = paginator.get_paginated_response([project(r) for r in paginator.paginate_queryset(rows, request, view=self)])
        if resumen is not None:
            response.data["resumen"] = resumen
        return response
