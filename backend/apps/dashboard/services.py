from . import consultas
from .consistencia import lectura_estable
from .filtros import ZONA, entero, periodo, query_estricta
from .permissions import revalidar


def resumen(actor, params):
    with lectura_estable() as corte:
        revalidar(actor)
        desde, hasta = periodo(params, corte.astimezone(ZONA).date())
        cartera = consultas.cartera_actual()
        operacion = consultas.operacion_actual()
        cierres = consultas.rentabilidad(consultas.finalizadas(desde, hasta, corte))
        operacion["obras_finalizadas_periodo"] = cierres["obras_con_cierre"]
        return {"generado_en": corte, "zona_horaria": "America/Santiago", "moneda": "CLP",
                "periodo": {"desde": desde, "hasta": hasta}, "operacion": operacion,
                "rentabilidad_cerrada_periodo": cierres, "cobranza_actual": consultas.cobranza(cartera)}


def serie_obras(actor, params):
    query_estricta(params, {"meses"})
    meses = entero(params.get("meses", "6"), "meses", maximo=12)
    with lectura_estable() as corte:
        revalidar(actor)
        return consultas.serie(meses, corte)
