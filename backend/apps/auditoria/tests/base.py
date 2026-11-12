from decimal import Decimal
from uuid import uuid4

from apps.comercial.models import PresupuestoEvento
from apps.finanzas import services_documentos as finanzas
from apps.finanzas.models import PagoDocumento, CierreSinCobro, FinanzasEvento
from apps.finanzas.tests.base import FinanzasBase
from apps.obras import services as obras
from apps.obras.models import GastoObra, CostoObraEvento, CortesiaObra
from apps.usuarios import services_usuarios as usuarios
from apps.usuarios.models import UsuarioEvento
from apps.usuarios.tests.test_administracion import PASSWORD
from apps.finanzas.validaciones import hoy_santiago

URL = "/api/auditoria/eventos/"


class AuditoriaBase(FinanzasBase):
    def preparar_auditoria(self):
        self.preparar_finanzas()  # Operaciones reales de finalización 004B.
        self.ti = usuarios.aprovisionar_primera_ti({"email": "ti@example.test", "username": "ti", "password": PASSWORD})
        PresupuestoEvento.objects.create(presupuesto=self.presupuesto, estado_anterior=None, estado_nuevo="BORRADOR", registrado_por=self.finanzas)
        PresupuestoEvento.objects.create(presupuesto=self.presupuesto, estado_anterior="ENVIADO_CLIENTE", estado_nuevo="APROBADO_CLIENTE", registrado_por=self.finanzas, motivo="Aceptación histórica")
        obras.crear_categoria("Categoría con historia", self.gerencia)
        # Fixtures históricas explícitas, exclusivamente en BD temporal de tests.
        self.gasto = GastoObra.objects.create(id=91, obra=self.obra, tipo="MATERIAL", descripcion="Material de prueba", unidad="unidad", cantidad=Decimal("1.000"), costo_unitario_neto=Decimal("12.34"), fecha_gasto=hoy_santiago(), registrado_por=self.supervisor)
        CostoObraEvento.objects.create(obra=self.obra, gasto=self.gasto, tipo="ALTA", registrado_por=self.supervisor, motivo="Registro histórico", datos_nuevos={"cantidad": "1.000", "costo_unitario_neto": "12.34", "vigente": True})
        self.doc = finanzas.registrar_documento(self.payload(), self.finanzas)
        self.pago = PagoDocumento.objects.create(id=79, documento=self.doc, monto=Decimal("1.00"), fecha_pago=hoy_santiago(), medio="EFECTIVO", referencia_respaldo="Comprobante de prueba", registrado_por=self.finanzas, clave_idempotencia=uuid4(), huella_solicitud="a" * 64)
        FinanzasEvento.objects.create(pago=self.pago, tipo="PAGO_REGISTRADO", actor=self.finanzas, datos_nuevos={"documento": self.doc.pk, "monto": "1.00", "activo": True})
        otra = self.otra_finalizada()
        cortesia = CortesiaObra.objects.create(obra=otra, autorizado_por=self.supervisor, justificacion="Garantía de prueba")
        CostoObraEvento.objects.create(obra=otra, cortesia=cortesia, tipo="CORTESIA", registrado_por=self.supervisor, motivo="Decisión histórica", datos_nuevos={"tipo": "SIN_COBRO"})
        cierre = CierreSinCobro.objects.create(obra=otra, cortesia=cortesia, registrado_por=self.finanzas, motivo_registro="Garantía de prueba")
        FinanzasEvento.objects.create(cierre_sin_cobro=cierre, tipo="SIN_COBRO_REGISTRADO", actor=self.finanzas, motivo="Garantía de prueba", datos_nuevos={"obra": otra.pk, "cortesia": cortesia.pk})
        UsuarioEvento.objects.create(usuario_objetivo=self.ti, actor=self.ti, tipo="ESTABLECER_CLAVE", motivo="Histórico sin secretos")
        self.autenticar(self.gerencia)
