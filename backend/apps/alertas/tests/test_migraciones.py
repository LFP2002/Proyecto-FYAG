"""Solo BD temporal de tests: esquema anterior con datos reales de los dominios."""
from unittest.mock import patch

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase, override_settings

from apps.alertas.models import Alerta
from apps.alertas.services import reconciliar
from apps.obras.models import Obra
from apps.finanzas.tests.base import FinanzasBase
from apps.finanzas.models import DocumentoCobro
from apps.finanzas import services_documentos
from apps.comercial.models import Presupuesto


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class MigracionAlertasTests(FinanzasBase, TransactionTestCase):
    def setUp(self):
        self.setUpTestData()
        # El helper histórico simula cierre en el futuro; instalar solo el
        # esquema anterior, sin proyectar alertas antes de la migración probada.
        with patch("apps.alertas.services.notificar_despues_commit"):
            self.preparar_finanzas()
        services_documentos.registrar_documento(self.payload(), self.finanzas)

    def test_instalacion_incremental_preserva_negocio_y_reconcilia(self):
        modelos = (Presupuesto, Obra, DocumentoCobro)
        antes = {m.__name__: list(m.objects.order_by("pk").values()) for m in modelos}
        executor = MigrationExecutor(connection)
        hojas = executor.loader.graph.leaf_nodes()
        try:
            executor.migrate([n for n in hojas if n[0] != "alertas"] + [("alertas", None)])
            self.assertNotIn("alertas_alerta", connection.introspection.table_names())
            self.assertEqual({m.__name__: list(m.objects.order_by("pk").values()) for m in modelos}, antes)
            # Estado previo existente, sin alterar filas históricas de los propietarios.
            executor = MigrationExecutor(connection)
            executor.migrate(hojas)
        finally:
            MigrationExecutor(connection).migrate(hojas)
        self.assertEqual({m.__name__: list(m.objects.order_by("pk").values()) for m in modelos}, antes)
        self.assertEqual(Alerta.objects.count(), 0)
        reconciliar()
        self.assertEqual({m.__name__: list(m.objects.order_by("pk").values()) for m in modelos}, antes)
