from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

from apps.finanzas.models import DocumentoCobro
from apps.finanzas.consultas_cobranzas import con_cobranza, resumen_documento
from .test_pagos import PagosBase


class MigracionPagosTests(PagosBase, TransactionTestCase):
    def test_upgrade_0001_0002_preserva_documentos_eventos_y_origen(self):
        self.setUpTestData()
        self.preparar_pagos()
        before = self.estado_persistido()
        original = DocumentoCobro.objects.values().get(pk=self.doc.pk)
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        previous = [(app, "0001_facturacion_documental" if app == "finanzas" else name) for app, name in latest]
        executor.migrate(previous)
        try:
            old = executor.loader.project_state(previous).apps
            self.assertEqual(old.get_model("finanzas", "DocumentoCobro").objects.values().get(pk=self.doc.pk), original)
            old_events = list(old.get_model("finanzas", "FinanzasEvento").objects.values())
            executor = MigrationExecutor(connection)
            executor.migrate(latest)
            apps = executor.loader.project_state(latest).apps
            self.assertEqual(apps.get_model("finanzas", "PagoDocumento").objects.count(), 0)
            self.assertEqual(apps.get_model("finanzas", "DocumentoCobro").objects.values().get(pk=self.doc.pk), original)
            current_events = list(apps.get_model("finanzas", "FinanzasEvento").objects.values())
            self.assertEqual([{key: value for key, value in event.items() if key != "pago_id"} for event in current_events], old_events)
            self.assertTrue(all(event["pago_id"] is None for event in current_events))
            self.assertEqual(resumen_documento(con_cobranza(DocumentoCobro.objects.filter(pk=self.doc.pk)).get())["saldo"], "2180.35")
            self.assertEqual(self.estado_persistido(), before)
        finally:
            MigrationExecutor(connection).migrate(latest)
