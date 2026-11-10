from decimal import Decimal

from django.utils import timezone
from apps.comercial.models import Presupuesto, PresupuestoItem
from apps.obras import services as obras, services_costos as costos
from apps.obras.models import Obra, CierreCostosObra
from apps.obras.tests.test_finalizacion import FinalizacionBase
from apps.finanzas.validaciones import hoy_santiago


class FinanzasBase(FinalizacionBase):
    def preparar_finanzas(self):
        self.preparar()
        self.items(self.presupuesto)
        self.completa()
        if getattr(self, "con_cortesia", False):
            costos.registrar_cortesia(self.obra, {"justificacion": "Garantía autorizada", "motivo": "Decisión del Supervisor"}, self.supervisor)
            self.validar()
        self.finalizar()
        self.obra.refresh_from_db()
        self.autenticar(self.finanzas)
        self.documentos_url = "/api/finanzas/documentos/"

    def items(self, presupuesto):
        for orden, cantidad, precio in [(1, "1.125", "1234.56"), (2, "2.000", "345.67")]:
            PresupuestoItem.objects.create(presupuesto=presupuesto, descripcion=f"Línea {orden}", unidad="servicio", cantidad=Decimal(cantidad), precio_unitario=Decimal(precio), orden=orden)
        # 1388.88 + 691.34 = 2080.22, distinto al costo interno 8000.00.

    def payload(self, **changes):
        return {"obra": self.obra.pk, "tipo_documento": "FACTURA_AFECTA", "folio_externo": "10001",
                "fecha_emision": hoy_santiago().isoformat(), "fecha_vencimiento": hoy_santiago().isoformat(),
                "monto_neto": "2080.22", "monto_impuesto": "100.13", "monto_total": "2180.35",
                "referencia_respaldo": " Archivo interno del documento externo ", **changes}

    def registrar(self, **changes):
        return self.client.post(self.documentos_url, self.payload(**changes), format="json")

    def otra_finalizada(self):
        """Fixture histórica adicional, no pretende ejecutar un segundo cierre operativo."""
        presupuesto = Presupuesto.objects.create(cliente=self.cliente, creado_por=self.finanzas, descripcion="Histórico adicional", estado="APROBADO_CLIENTE")
        self.items(presupuesto)
        obra = obras.crear_obra(self.datos(presupuesto=presupuesto.pk, tecnico_responsable=self.tecnico.pk, motivo="Principal"), self.supervisor)
        obras.iniciar_obra(obra, self.supervisor, "Inicio")
        CierreCostosObra.objects.create(obra=obra, materiales_total=Decimal("0.00"), otros_total=Decimal("0.00"), mano_obra_total=Decimal("8000.00"), costo_total=Decimal("8000.00"), version_validada=1, validado_por=self.supervisor, finalizado_por=self.supervisor)
        Obra.objects.filter(pk=obra.pk).update(estado="FINALIZADA", finalizado_en=timezone.now())
        obra.refresh_from_db()
        return obra
