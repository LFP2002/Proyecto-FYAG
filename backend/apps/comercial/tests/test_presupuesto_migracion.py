from django.db import connection, IntegrityError, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

from apps.comercial.tests.test_presupuesto_model import DatosPresupuestoMixin


class AprobacionObligatoriaMigracionTests(DatosPresupuestoMixin, TransactionTestCase):
    def test_normaliza_datos_historicos_sin_perder_contenido(self):
        anterior = ('comercial', '0004_presupuesto_presupuestoevento_presupuestoitem_and_more')
        nueva = ('comercial', '0005_remove_presupuesto_presupuesto_gerencia_coherente_and_more')
        executor = MigrationExecutor(connection)
        executor.migrate([anterior])
        try:
            apps = executor.loader.project_state([anterior]).apps
            self.setUpTestData()
            Presupuesto = apps.get_model('comercial', 'Presupuesto')
            presupuesto = Presupuesto.objects.get(pk=self.presupuesto.pk)
            presupuesto.requiere_aprobacion_gerencia = False
            presupuesto.save()
            self.nuevo_item().save()
            self.nuevo_evento().save()
            cabecera = Presupuesto.objects.values().get(pk=presupuesto.pk)
            Item = apps.get_model('comercial', 'PresupuestoItem')
            Evento = apps.get_model('comercial', 'PresupuestoEvento')
            items = list(Item.objects.values())
            eventos = list(Evento.objects.values())
        finally:
            MigrationExecutor(connection).migrate([nueva])
        cabecera['requiere_aprobacion_gerencia'] = True
        self.assertEqual(Presupuesto.objects.values().get(pk=presupuesto.pk), cabecera)
        self.assertEqual(list(Item.objects.values()), items)
        self.assertEqual(list(Evento.objects.values()), eventos)
        with self.assertRaises(IntegrityError) as error:
            with transaction.atomic():
                Presupuesto.objects.filter(pk=presupuesto.pk).update(
                    requiere_aprobacion_gerencia=False
                )
        self.assertEqual(error.exception.__cause__.diag.constraint_name,
                         'presupuesto_aprobacion_gerencia_obligatoria')
