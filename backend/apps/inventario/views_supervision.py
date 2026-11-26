"""Indicadores de inventario para Gerencia, sin mutaciones del libro."""
from decimal import Decimal, localcontext
from datetime import date
import re

from django.db.models import F
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from .models import ArticuloInventario, Merma
from .permissions import PuedeOperarInventario
from .services_mermas import importe
from .views import InventarioPaginacion, query, articulo_filtro
from .views_materiales import CabecerasMateriales


class SupervisionInventarioView(CabecerasMateriales, APIView):
    permission_classes = [IsAuthenticated, PuedeOperarInventario]
    http_method_names = ["get", "head", "options"]

    def get(self, request):
        if request.user.rol != "GERENCIA":
            raise PermissionDenied("Sin permiso para consultar la supervisión de inventario.")
        params = request.query_params
        query(params, {"seccion", "filtro", "buscar", "estado", "desde", "hasta", "articulo"})
        seccion = params.get("seccion", "existencias")
        filtro = params.get("filtro", "")
        buscar = params.get("buscar", "").strip().casefold()
        if seccion not in {"existencias", "mermas"} or len(buscar) > 100:
            raise ValidationError({"query": ["Consulta inválida."]})
        if filtro not in ({"", "sin_stock", "pendiente"} if seccion == "existencias" else {"", "bodega", "obra"}):
            raise ValidationError({"filtro": ["Filtro inválido."]})
        hoy = timezone.localdate()
        desde = hoy.replace(day=1)
        estado = params.get("estado", "APROBADA")
        if estado not in {"APROBADA", "PENDIENTE", "RECHAZADA"}:
            raise ValidationError({"estado": ["Estado inválido."]})
        if (seccion == "existencias" and any(k in params for k in ("estado", "desde", "hasta"))) or (seccion == "mermas" and "articulo" in params):
            raise ValidationError({"query": ["Filtros incompatibles con la sección."]})
        articulo = articulo_filtro(params) if "articulo" in params else None
        inicio, fin = desde, hoy
        if ("desde" in params) != ("hasta" in params) or (estado == "PENDIENTE" and "desde" in params):
            raise ValidationError({"desde": ["Indique ambas fechas únicamente para mermas decididas."]})
        if "desde" in params:
            try:
                if not all(re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", params[k]) for k in ("desde", "hasta")):
                    raise ValueError()
                inicio, fin = date.fromisoformat(params["desde"]), date.fromisoformat(params["hasta"])
                if inicio > fin or fin > hoy or (fin-inicio).days >= 366:
                    raise ValueError()
            except ValueError:
                raise ValidationError({"desde": ["Período inválido, máximo 366 días hasta hoy."]}) from None
        principales = []
        positivos = 0
        total_valorado = Decimal("0.00")
        sin_stock = pendientes = 0
        filas_stock = []
        filas_mermas = []
        total_bodega = Decimal("0.00")
        total_obra = Decimal("0.00")
        no_valoradas = 0
        cantidad_bodega = cantidad_obra = 0
        with localcontext() as ctx:
            ctx.prec = 60
            # Un join por material: no solicitudes individuales ni inferencia del saldo físico.
            materiales = ArticuloInventario.objects.annotate(
                saldo=F("existencia__saldo"), valorado=F("estadovaloracion__saldo_valorado"),
                promedio=F("estadovaloracion__promedio")
            ).values("id", "codigo", "nombre", "unidad", "activo", "saldo", "valorado", "promedio").order_by("nombre", "id")
            for a in materiales.iterator(chunk_size=200):
                saldo, valorado, promedio = a["saldo"], a["valorado"], a["promedio"]
                pendiente = saldo is None or (saldo != (valorado if valorado is not None else Decimal(0))) or (valorado is not None and valorado > 0 and promedio is None)
                agotado = a["activo"] and saldo == 0
                valor = importe(valorado, promedio, estricto=False) if valorado is not None and promedio is not None else (Decimal("0.00") if valorado == 0 or saldo == 0 else None)
                if valor is not None:
                    total_valorado += valor
                    if valor > 0:
                        positivos += 1
                        principales.append((valor, a["id"], a["codigo"], a["nombre"]))
                        principales.sort(key=lambda x: (-x[0], x[1]))
                        del principales[6:]
                sin_stock += agotado
                pendientes += pendiente
                if seccion != "existencias":
                    continue
                if filtro == "sin_stock" and not agotado or filtro == "pendiente" and not pendiente:
                    continue
                if articulo is not None and a["id"] != articulo:
                    continue
                if buscar and buscar not in (a["codigo"]+" "+a["nombre"]).casefold():
                    continue
                filas_stock.append({
                    "id": a["id"], "codigo": a["codigo"], "nombre": a["nombre"], "unidad": a["unidad"],
                    "activo": a["activo"], "saldo": format(saldo, ".3f") if saldo is not None else None,
                    "valor_neto": format(valor, ".2f") if valor is not None else None, "pendiente_valoracion": pendiente,
                })
            # Las mermas de obra ya forman parte del costo de la entrega: no se suman a la baja de bodega.
            aprobadas = Merma.objects.filter(estado="APROBADA", decidido_en__date__gte=desde,
                decidido_en__date__lte=hoy).select_related("articulo", "obra", "operacion", "entrega").order_by("-decidido_en", "-pk")
            for m in aprobadas.iterator(chunk_size=200):
                op = m.operacion if m.ambito == "BODEGA" else m.entrega
                costo = op.costo_unitario_neto if op is not None else None
                valor = importe(m.cantidad, costo, estricto=False) if costo is not None else None
                if valor is None:
                    no_valoradas += 1
                if m.ambito == "BODEGA":
                    cantidad_bodega += 1
                    if valor is not None:
                        total_bodega += valor
                else:
                    cantidad_obra += 1
                    if valor is not None:
                        total_obra += valor
            if seccion == "mermas":
                listado = Merma.objects.filter(estado=estado)
                if estado != "PENDIENTE":
                    listado = listado.filter(decidido_en__date__range=(inicio, fin))
                if filtro:
                    listado = listado.filter(ambito=filtro.upper())
                listado = listado.select_related("articulo", "obra", "operacion", "entrega").order_by("-creado_en" if estado == "PENDIENTE" else "-decidido_en", "-pk")
                for m in listado.iterator(chunk_size=200):
                    if buscar and buscar not in (m.articulo.codigo+" "+m.articulo.nombre).casefold():
                        continue
                    op = m.operacion if m.ambito == "BODEGA" else m.entrega
                    costo = op.costo_unitario_neto if op is not None and estado == "APROBADA" else None
                    valor = importe(m.cantidad, costo, estricto=False) if costo is not None else None
                    filas_mermas.append({"id": m.pk, "nombre": m.articulo.nombre, "codigo": m.articulo.codigo,
                        "ambito": m.ambito, "obra": m.obra.codigo if m.obra_id else None, "cantidad": format(m.cantidad, ".3f"),
                        "unidad": m.unidad, "tipo": m.tipo, "estado": m.estado, "motivo": m.motivo,
                        "motivo_decision": m.motivo_decision, "fecha": (m.decidido_en or m.creado_en).isoformat(),
                        "valor_neto": format(valor, ".2f") if valor is not None else None})
            otros = total_valorado - sum((x[0] for x in principales), Decimal("0.00"))
            composicion = [{"id": pk, "codigo": codigo, "nombre": nombre, "valor_neto": format(valor, ".2f"), "materiales": 1}
                           for valor, pk, codigo, nombre in principales]
            if otros > 0:
                composicion.append({"id": None, "codigo": None, "nombre": "Otros materiales", "valor_neto": format(otros, ".2f"), "materiales": positivos-len(principales)})
        rows = filas_stock if seccion == "existencias" else filas_mermas
        if seccion == "existencias":
            rows.sort(key=lambda r: (not r["pendiente_valoracion"] and not (r["activo"] and r["saldo"] == "0.000"), r["nombre"].casefold(), r["id"]))
        resumen = {"valor_stock_valorado": format(total_valorado, ".2f"), "sin_stock": sin_stock, "pendientes_valoracion": pendientes,
                   "mermas_bodega_neto": format(total_bodega, ".2f"), "mermas_obra_informativo": format(total_obra, ".2f"),
                   "mermas_bodega": cantidad_bodega, "mermas_obra": cantidad_obra, "mermas_sin_valor": no_valoradas,
                   "mermas_pendientes": Merma.objects.filter(estado="PENDIENTE").count(),
                   "desde": desde.isoformat(), "hasta": hoy.isoformat(), "composicion": composicion}
        paginador = InventarioPaginacion()
        respuesta = paginador.get_paginated_response(paginador.paginate_queryset(rows, request, view=self))
        respuesta.data["resumen"] = resumen
        respuesta.data["periodo_mermas"] = {"desde": inicio.isoformat(), "hasta": fin.isoformat()} if seccion == "mermas" and estado != "PENDIENTE" else None
        return respuesta
