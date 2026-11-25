"""Indicadores de inventario para Gerencia, sin mutaciones del libro."""
from decimal import Decimal, localcontext

from django.db.models import F
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from .models import ArticuloInventario, Merma
from .permissions import PuedeOperarInventario
from .services_mermas import importe
from .views import InventarioPaginacion, query
from .views_materiales import CabecerasMateriales


class SupervisionInventarioView(CabecerasMateriales, APIView):
    permission_classes = [IsAuthenticated, PuedeOperarInventario]
    http_method_names = ["get", "head", "options"]

    def get(self, request):
        if request.user.rol != "GERENCIA":
            raise PermissionDenied("Sin permiso para consultar la supervisión de inventario.")
        params = request.query_params
        query(params, {"seccion", "filtro", "buscar"})
        seccion = params.get("seccion", "existencias")
        filtro = params.get("filtro", "")
        buscar = params.get("buscar", "").strip().casefold()
        if seccion not in {"existencias", "mermas"} or len(buscar) > 100:
            raise ValidationError({"query": ["Consulta inválida."]})
        if filtro not in ({"", "sin_stock", "pendiente"} if seccion == "existencias" else {"", "bodega", "obra"}):
            raise ValidationError({"filtro": ["Filtro inválido."]})
        hoy = timezone.localdate()
        desde = hoy.replace(day=1)
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
                sin_stock += agotado
                pendientes += pendiente
                if seccion != "existencias":
                    continue
                if filtro == "sin_stock" and not agotado or filtro == "pendiente" and not pendiente:
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
                if seccion != "mermas" or filtro and m.ambito.lower() != filtro:
                    continue
                if buscar and buscar not in (m.articulo.codigo+" "+m.articulo.nombre).casefold():
                    continue
                filas_mermas.append({"id": m.pk, "nombre": m.articulo.nombre, "codigo": m.articulo.codigo,
                    "ambito": m.ambito, "obra": m.obra.codigo if m.obra_id else None, "cantidad": format(m.cantidad, ".3f"),
                    "unidad": m.unidad, "tipo": m.tipo, "fecha": m.decidido_en.isoformat(), "valor_neto": format(valor, ".2f") if valor is not None else None})
        rows = filas_stock if seccion == "existencias" else filas_mermas
        if seccion == "existencias":
            rows.sort(key=lambda r: (not r["pendiente_valoracion"] and not (r["activo"] and r["saldo"] == "0.000"), r["nombre"].casefold(), r["id"]))
        resumen = {"valor_stock_valorado": format(total_valorado, ".2f"), "sin_stock": sin_stock, "pendientes_valoracion": pendientes,
                   "mermas_bodega_neto": format(total_bodega, ".2f"), "mermas_obra_informativo": format(total_obra, ".2f"),
                   "mermas_bodega": cantidad_bodega, "mermas_obra": cantidad_obra, "mermas_sin_valor": no_valoradas,
                   "mermas_pendientes": Merma.objects.filter(estado="PENDIENTE").count(),
                   "desde": desde.isoformat(), "hasta": hoy.isoformat()}
        paginador = InventarioPaginacion()
        respuesta = paginador.get_paginated_response(paginador.paginate_queryset(rows, request, view=self))
        respuesta.data["resumen"] = resumen
        return respuesta
