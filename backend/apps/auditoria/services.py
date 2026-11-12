from django.db.models import Max
from django.utils import timezone
from rest_framework.exceptions import APIException

from .cursors import CursorInvalido, abrir, crear
from .permissions import revalidar, seleccionar
from .serializers import filtros_query, rango, normalizar_evento


def consultar(actor, params):
    actor = revalidar(actor)
    ultima = None
    if "cursor" in params:
        if set(params) != {"cursor"} or (hasattr(params, "getlist") and len(params.getlist("cursor")) != 1):
            raise CursorInvalido()
        filtros, corte, marcas, ultima = abrir(params["cursor"], actor)
    else:
        filtros, corte, marcas = filtros_query(params), timezone.now(), None
    try:
        fuentes = seleccionar(actor, filtros)
    except APIException:
        if ultima is not None:
            raise CursorInvalido() from None
        raise
    nombres = {f.nombre for f in fuentes}
    if marcas is not None and set(marcas) != nombres:
        raise CursorInvalido()
    inicio, fin = rango(filtros)
    if ultima and not inicio <= ultima[0] < fin:
        raise CursorInvalido()
    queries = {f.nombre: f.consulta(filtros, inicio, fin, corte) for f in fuentes}
    if marcas is None:
        marcas = {name: qs.aggregate(pk=Max("pk"))["pk"] or 0 for name, qs in queries.items()}
    candidatos = []
    limite = filtros["limit"]
    for f in fuentes:
        if not marcas[f.nombre]:
            continue
        qs = queries[f.nombre].filter(pk__lte=marcas[f.nombre])
        if ultima:
            qs = f.despues(qs, ultima)
        # A lo sumo limit+1 por fuente. Nunca iterar el histórico completo.
        for row in qs.order_by("-creado_en", "-pk").values(*f.columnas(etiqueta=actor.rol == "ADMINISTRADOR_TI"))[:limite + 1]:
            candidatos.append((f, row))
    # Ordenaciones estables: sin epoch float y sin depender de collation SQL.
    candidatos.sort(key=lambda item: item[1]["id"], reverse=True)
    candidatos.sort(key=lambda item: item[0].nombre)
    candidatos.sort(key=lambda item: item[1]["creado_en"], reverse=True)
    hay_mas = len(candidatos) > limite
    publicados = candidatos[:limite]
    resultados = [normalizar_evento(f, row, actor.rol) for f, row in publicados]
    siguiente = None
    if hay_mas:
        fuente, row = publicados[-1]
        siguiente = crear(actor, filtros, corte, marcas, (row["creado_en"], fuente.nombre, row["id"]))
    return {"results": resultados, "next_cursor": siguiente, "has_more": hay_mas, "fecha_corte": corte, "zona_horaria": "America/Santiago"}
