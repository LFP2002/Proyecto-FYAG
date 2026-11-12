"""Datos sintéticos solo en BD temporal. Preparación operativa reutilizada de 007."""
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

from django.utils import timezone

from apps.comercial.models import Presupuesto, PresupuestoItem
from apps.obras import services as obras
from apps.obras.models import Obra, CierreCostosObra
from apps.finanzas import services_documentos as documentos, services_pagos as pagos
from apps.finanzas.tests.base import FinanzasBase
from apps.finanzas.validaciones import hoy_santiago

BASE = "/api/dashboard/"
RESUMEN = BASE + "resumen/"
SERIE = BASE + "serie-obras/"
ACTIVAS = BASE + "obras-activas/"


class DashboardBase(FinanzasBase):
    def preparar_dashboard(self):
        self.setUpTestData()
        self.preparar_finanzas()
        self.autenticar(self.gerencia)

    def historica(self, *, estado="FINALIZADA", fecha=None, costo="10.00", lineas=(("1.000", "10.00"),), cierre=True):
        """Fixture histórica adicional, no simula una respuesta ni cierra por API."""
        p = Presupuesto.objects.create(cliente=self.cliente, creado_por=self.finanzas, descripcion="Histórico dashboard", estado="APROBADO_CLIENTE")
        for orden, (cantidad, precio) in enumerate(lineas, 1):
            PresupuestoItem.objects.create(presupuesto=p, descripcion=f"Línea {orden}", unidad="unidad", cantidad=Decimal(cantidad), precio_unitario=Decimal(precio), orden=orden)
        obra = obras.crear_obra(self.datos(presupuesto=p.pk, tecnico_responsable=self.tecnico.pk, motivo="Asignación"), self.supervisor)
        fecha = fecha or timezone.now()
        cambios = {"estado": estado, "creado_en": fecha - timedelta(days=2), "iniciado_en": None, "finalizado_en": None, "cancelado_en": None}
        if estado in ("EN_PROCESO", "SUSPENDIDA", "FINALIZADA"):
            cambios["iniciado_en"] = fecha - timedelta(days=1)
        if estado == "FINALIZADA":
            cambios["finalizado_en"] = fecha
            if cierre:
                CierreCostosObra.objects.create(obra=obra, materiales_total=Decimal("0.00"), otros_total=Decimal("0.00"), mano_obra_total=Decimal(costo), costo_total=Decimal(costo), version_validada=1, validado_por=self.supervisor, finalizado_por=self.supervisor)
        elif estado == "CANCELADA":
            cambios["cancelado_en"] = fecha
        Obra.objects.filter(pk=obra.pk).update(**cambios)
        obra.refresh_from_db()
        return obra

    def documento(self, *, obra=None, folio="1010", **cambios):
        return documentos.registrar_documento(self.payload(obra=(obra or self.obra).pk, folio_externo=folio, **cambios), self.finanzas)

    def pago(self, doc, monto="100.13"):
        return pagos.registrar_pago(doc.pk, {"monto": monto, "fecha_pago": hoy_santiago().isoformat(), "medio": "EFECTIVO", "referencia_respaldo": "Respaldo de prueba"}, self.finanzas, str(uuid4()))[0]

    def anular(self, doc, pago):
        return pagos.anular_pago(doc.pk, pago.pk, {"motivo": "Corrección", "referencia_reversion_externa": "Respaldo"}, self.finanzas)
