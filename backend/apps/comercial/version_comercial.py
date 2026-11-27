"""Huella del contenido comercial que el usuario ha revisado (sin costo de inventario)."""
import hashlib
import json


def version_comercial(presupuesto, lineas):
    contenido = [
        presupuesto.pk, presupuesto.estado, presupuesto.cliente_id, presupuesto.descripcion,
        [
            [i.pk, i.articulo_id, i.codigo_articulo, i.descripcion,
             format(i.cantidad, ".3f"), i.unidad,
             None if i.precio_unitario is None else format(i.precio_unitario, ".2f"), i.orden]
            for i in sorted(lineas, key=lambda i: (i.orden, i.pk))
        ],
    ]
    return hashlib.sha256(json.dumps(contenido, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()
