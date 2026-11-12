from decimal import Decimal

from apps.comercial.models import Presupuesto, PresupuestoItem
from apps.obras import services as obras
from apps.obras.tests.test_turnos import TurnosBase
from apps.usuarios.models import Usuario
from rest_framework.test import APIClient

from apps.alertas.services import reconciliar
from apps.alertas.models import Alerta

URL = "/api/alertas/"


class AlertasBase(TurnosBase):
    def preparar_alertas(self):
        self.preparar()
        self.client = APIClient()
        self.autenticar(self.gerencia)

    def pendiente(self):
        p = Presupuesto.objects.create(cliente=self.cliente, creado_por=self.finanzas, descripcion="Presupuesto real de prueba")
        PresupuestoItem.objects.create(presupuesto=p, descripcion="Servicio", unidad="unidad", cantidad=Decimal("1.000"), precio_unitario=Decimal("10.00"), orden=1)
        return p

    def suspender(self):
        obras.suspender_obra(self.obra, self.supervisor, "Pausa operativa")
        reconciliar()
        return Alerta.objects.get(tipo="OBRA_SUSPENDIDA", rol_destinatario="GERENCIA", estado="PENDIENTE")

    def ti(self):
        return Usuario.objects.create_user(username="ti009", email="ti009@example.test", rol="ADMINISTRADOR_TI")
