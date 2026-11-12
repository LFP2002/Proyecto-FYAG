"""Registro cerrado de ocho fuentes. No invoca servicios mutadores de dominio."""
from dataclasses import dataclass

from django.db.models import Q

from apps.comercial.models import PresupuestoEvento
from apps.obras.models import (
    ObraEvento, ObraParticipanteEvento, CategoriaServicioEvento,
    TurnoObraEvento, CostoObraEvento,
)
from apps.finanzas.models import FinanzasEvento
from apps.usuarios.models import UsuarioEvento


@dataclass(frozen=True)
class Fuente:
    nombre: str
    modelo: type
    modulo: str
    actor: str
    recursos: tuple  # (tipo público, columna FK real)

    @property
    def tipos(self):
        if self.modelo is PresupuestoEvento:
            return ("CREACION", "CAMBIO_ESTADO")
        return tuple(self.modelo.Tipo.values)

    def consulta(self, filtros, inicio, fin, corte):
        qs = self.modelo.objects.filter(creado_en__gte=inicio, creado_en__lt=fin, creado_en__lte=corte)
        if "actor" in filtros:
            qs = qs.filter(**{self.actor: filtros["actor"]})
        if "recurso_tipo" in filtros:
            columna = dict(self.recursos)[filtros["recurso_tipo"]]
            qs = qs.filter(**{f"{columna}__isnull": False})
            if "recurso_id" in filtros:
                qs = qs.filter(**{columna: filtros["recurso_id"]})
        if "tipo" in filtros:
            tipo = filtros["tipo"]
            if tipo not in self.tipos:
                return qs.none()
            if self.modelo is PresupuestoEvento:
                qs = qs.filter(estado_anterior__isnull=tipo == "CREACION")
            else:
                qs = qs.filter(tipo=tipo)
        return qs

    def despues(self, qs, ultima):
        """Keyset total: fecha DESC, fuente ASC, evento_id DESC."""
        fecha, fuente, pk = ultima
        if self.nombre < fuente:
            return qs.filter(creado_en__lt=fecha)
        if self.nombre > fuente:
            return qs.filter(creado_en__lte=fecha)
        return qs.filter(Q(creado_en__lt=fecha) | Q(creado_en=fecha, pk__lt=pk))

    def columnas(self, etiqueta=False):
        fields = ["id", "creado_en", "motivo", self.actor, *[col for _, col in self.recursos]]
        if self.modelo is PresupuestoEvento:
            fields += ["estado_anterior", "estado_nuevo"]
        else:
            fields += ["tipo", "datos_anteriores", "datos_nuevos"]
        if etiqueta:
            relation = self.actor.removesuffix("_id")
            fields += [f"{relation}__first_name", f"{relation}__last_name", f"{relation}__username"]
        return fields

    def tipo(self, row):
        if self.modelo is PresupuestoEvento:
            return "CREACION" if row["estado_anterior"] is None else "CAMBIO_ESTADO"
        return row["tipo"]

    def recurso(self, row):
        referencias = [(tipo, row[col]) for tipo, col in self.recursos if row[col] is not None]
        if len(referencias) != 1:
            raise ValueError("Referencia de evento inconsistente")
        return referencias[0]


FUENTES = {f.nombre: f for f in (
    Fuente("PRESUPUESTO_EVENTO", PresupuestoEvento, "COMERCIAL", "registrado_por_id", (("PRESUPUESTO", "presupuesto_id"),)),
    Fuente("OBRA_EVENTO", ObraEvento, "OBRAS", "registrado_por_id", (("OBRA", "obra_id"),)),
    Fuente("PARTICIPANTE_EVENTO", ObraParticipanteEvento, "OBRAS", "registrado_por_id", (("PARTICIPANTE", "participante_id"),)),
    Fuente("CATEGORIA_SERVICIO_EVENTO", CategoriaServicioEvento, "OBRAS", "registrado_por_id", (("CATEGORIA_SERVICIO", "categoria_id"),)),
    Fuente("TURNO_EVENTO", TurnoObraEvento, "OBRAS", "registrado_por_id", (("TURNO", "turno_id"),)),
    Fuente("COSTO_OBRA_EVENTO", CostoObraEvento, "OBRAS", "registrado_por_id", (("GASTO", "gasto_id"), ("CONTROL_COSTOS", "control_id"), ("CORTESIA", "cortesia_id"))),
    Fuente("FINANZAS_EVENTO", FinanzasEvento, "FINANZAS", "actor_id", (("DOCUMENTO", "documento_id"), ("CIERRE_SIN_COBRO", "cierre_sin_cobro_id"), ("PAGO", "pago_id"))),
    Fuente("USUARIO_EVENTO", UsuarioEvento, "USUARIOS", "actor_id", (("USUARIO", "usuario_objetivo_id"),)),
)}
