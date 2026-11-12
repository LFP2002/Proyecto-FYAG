"""Lectura de propietarios, sin nuevos algoritmos de saldos/costos."""
from contextlib import closing
from decimal import Decimal, localcontext
from itertools import groupby, islice

from django.db.models import Count, F, Q, Sum
from rest_framework.exceptions import APIException
from apps.comercial.calculos import calcular_subtotal, sumar_monto_neto
from apps.comercial.models import PresupuestoItem
from apps.obras.models import Obra
from apps.finanzas.models import DocumentoCobro
from apps.finanzas.consultas_cobranzas import con_cobranza, campo_importe
from apps.finanzas.validaciones import LIMITE
from .filtros import limites, ZONA
from . import catalogo


class OrigenInconsistente(APIException):
    status_code = 409
    def __init__(self, code):
        super().__init__({"code": code, "detail": "Las fuentes del reporte requieren revisión de integridad."})


def queryset(tipo, filtros, corte):
    if tipo == "cobranzas":
        qs = con_cobranza(DocumentoCobro.objects.filter(estado="VIGENTE", registrado_en__lte=corte), hoy=corte.astimezone(ZONA).date())
        qs = qs.filter(fecha_emision__gte=filtros["desde"], fecha_emision__lte=filtros["hasta"])
        if "cliente" in filtros:
            qs = qs.filter(obra__presupuesto__cliente_id=filtros["cliente"])
        if "estado" in filtros:
            qs = qs.filter(estado_cobranza_calculado=filtros["estado"])
        return qs.order_by("-fecha_emision", "-pk")
    inicio, fin = limites(filtros)
    campo = "creado_en" if tipo == "obras" and filtros["fecha_base"] == "CREACION" else "finalizado_en"
    qs = Obra.objects.filter(creado_en__lte=corte).filter(Q(finalizado_en__isnull=True) | Q(finalizado_en__lte=corte)).filter(**{f"{campo}__gte": inicio, f"{campo}__lt": fin, f"{campo}__lte": corte})
    if campo == "finalizado_en":
        qs = qs.filter(estado="FINALIZADA")
    if "cliente" in filtros:
        qs = qs.filter(presupuesto__cliente_id=filtros["cliente"])
    if "estado" in filtros:
        qs = qs.filter(estado=filtros["estado"])
    return qs.order_by(f"-{campo}", "-pk")


def netos(ids, tiempo):
    items = PresupuestoItem.objects.filter(presupuesto_id__in=ids).order_by("presupuesto_id", "pk").values_list("presupuesto_id", "cantidad", "precio_unitario")
    out = dict.fromkeys(ids, Decimal("0.00"))
    with closing(items.iterator(chunk_size=catalogo.LOTE)) as iterator:
        for pk, lineas in groupby(iterator, key=lambda x: x[0]):
            def subtotales():
                for _, c, p in lineas:
                    tiempo.comprobar()
                    yield calcular_subtotal(c, p)
            out[pk] = sumar_monto_neto(subtotales())
    return out


def totales(tipo, qs, tiempo):
    if tipo == "cobranzas":
        datos = qs.aggregate(documentos=Count("pk"),
            invalidos=Count("pk", filter=Q(abonado_calculado__lt=0) | Q(abonado_calculado__gt=F("monto_total")) | Q(saldo_calculado__lt=0)),
            monto_documentado_bruto=Sum("monto_total", output_field=campo_importe()),
            abonado=Sum("abonado_calculado", output_field=campo_importe()), saldo=Sum("saldo_calculado", output_field=campo_importe()),
            saldo_vencido=Sum("saldo_calculado", filter=Q(estado_cobranza_calculado="VENCIDA"), output_field=campo_importe()))
        if datos.pop("invalidos"):
            raise OrigenInconsistente("saldo_inconsistente")
        for key in catalogo.MONETARIOS & datos.keys():
            datos[key] = datos[key] if datos[key] is not None else Decimal("0.00")
            if not datos[key].is_finite() or not 0 <= datos[key] <= LIMITE:
                raise OrigenInconsistente("importe_fuera_rango")
        with localcontext() as ctx:
            ctx.prec = 80
            if datos["monto_documentado_bruto"] != datos["abonado"] + datos["saldo"]:
                raise OrigenInconsistente("saldo_inconsistente")
        tiempo.comprobar()
        return dinero(datos)
    datos = {"obras": 0, "presupuesto_neto": Decimal("0.00")}
    campos = ["presupuesto_id"]
    if tipo == "rentabilidad":
        datos.update(costo_real_neto=Decimal("0.00"), margen_neto=Decimal("0.00"))
        campos.append("cierre_costos__costo_total")
    with localcontext() as ctx, closing(qs.values_list(*campos).iterator(chunk_size=catalogo.LOTE)) as iterator:
        ctx.prec = 80
        while lote := list(islice(iterator, catalogo.LOTE)):
            tiempo.comprobar()
            if tipo == "rentabilidad" and any(row[1] is None for row in lote):
                raise OrigenInconsistente("cierre_costos_inconsistente")
            datos["obras"] += len(lote)
            datos["presupuesto_neto"] += sum(netos([row[0] for row in lote], tiempo).values(), Decimal("0.00"))
            if tipo == "rentabilidad":
                datos["costo_real_neto"] += sum((row[1] for row in lote), Decimal("0.00"))
        if tipo == "rentabilidad":
            datos["margen_neto"] = datos["presupuesto_neto"] - datos["costo_real_neto"]
    return dinero(datos)


def dinero(data):
    return {k: format(v, ".2f") if isinstance(v, Decimal) else v for k, v in data.items()}


def filas(tipo, qs, tiempo):
    if tipo == "cobranzas":
        seleccion = qs.values("pk", "obra_id", "obra__presupuesto__cliente_id", "obra__presupuesto__cliente__nombre_legal", "tipo_documento", "folio_externo", "fecha_emision", "fecha_vencimiento", "monto_total", "abonado_calculado", "saldo_calculado", "estado_cobranza_calculado")
        with closing(seleccion.iterator(chunk_size=catalogo.LOTE)) as iterator:
            for row in iterator:
                tiempo.comprobar()
                yield dinero({"documento": row["pk"], "obra": row["obra_id"], "codigo_obra": f"OB-{row['obra_id']:06d}", "cliente": row["obra__presupuesto__cliente_id"], "cliente_nombre": row["obra__presupuesto__cliente__nombre_legal"], "tipo_documento": row["tipo_documento"], "folio_externo": row["folio_externo"], "fecha_emision": row["fecha_emision"], "fecha_vencimiento": row["fecha_vencimiento"], "moneda": "CLP", "monto_documentado_bruto": row["monto_total"], "abonado": row["abonado_calculado"], "saldo": row["saldo_calculado"], "estado_cobranza": row["estado_cobranza_calculado"]})
        return
    campos = ["pk", "presupuesto_id", "presupuesto__cliente_id", "presupuesto__cliente__nombre_legal", "finalizado_en"]
    if tipo == "obras":
        campos += ["categoria_servicio__nombre", "estado", "tecnico_responsable_id", "tecnico_responsable__first_name", "tecnico_responsable__last_name", "tecnico_responsable__username", "fecha_programada", "creado_en"]
    else:
        campos += ["cierre_costos__costo_total", "cortesia__tipo"]
    with closing(qs.values(*campos).iterator(chunk_size=catalogo.LOTE)) as iterator:
        while lote := list(islice(iterator, catalogo.LOTE)):
            tiempo.comprobar()
            montos = netos([row["presupuesto_id"] for row in lote], tiempo)
            for row in lote:
                neto = montos[row["presupuesto_id"]]
                data = {"obra": row["pk"], "codigo_obra": f"OB-{row['pk']:06d}", "cliente": row["presupuesto__cliente_id"], "cliente_nombre": row["presupuesto__cliente__nombre_legal"], "finalizado_en": row["finalizado_en"], "presupuesto_neto": neto}
                if tipo == "obras":
                    nombre = " ".join(filter(None, [row["tecnico_responsable__first_name"], row["tecnico_responsable__last_name"]])).strip() or row["tecnico_responsable__username"]
                    data.update(categoria_nombre=row["categoria_servicio__nombre"], estado=row["estado"], tecnico_responsable=row["tecnico_responsable_id"], tecnico_nombre=nombre, fecha_programada=row["fecha_programada"], creado_en=row["creado_en"])
                else:
                    if row["cierre_costos__costo_total"] is None:
                        raise OrigenInconsistente("cierre_costos_inconsistente")
                    with localcontext() as ctx:
                        ctx.prec = 80
                        margen = neto - row["cierre_costos__costo_total"]
                    data.update(moneda="CLP", costo_real_neto=row["cierre_costos__costo_total"], margen_neto=margen, tiene_cortesia_sin_cobro=row["cortesia__tipo"] == "SIN_COBRO")
                yield dinero(data)
