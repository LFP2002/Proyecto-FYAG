"""Upgrade 023A→B preserva filas históricas; downgrade rechaza tickets vivos."""
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.exceptions import IrreversibleError
from django.test import TransactionTestCase

from apps.chat import tickets
from .base import ChatBase


class Upgrade023B(ChatBase, TransactionTestCase):
    def test_upgrade_preserva_023a(self):
        self.preparar()
        # La suite acaba de crear la DB test limpia aplicando todas las migraciones.
        # Revertir solo la ampliación B vacía; no tocar migraciones históricas.
        executor = MigrationExecutor(connection)
        executor.migrate([('chat', '0002_integridad_chat')])
        try:
            conv = self.directa()
            self.enviar(conv)
            tablas = ('chat_conversacionchat', 'chat_participantechat', 'chat_mensajechat', 'chat_actochat')
            def snapshot():
                result = {}
                with connection.cursor() as cursor:
                    for tabla in tablas:
                        cursor.execute(f'SELECT row_to_json(t)::text FROM {tabla} t ORDER BY id')
                        result[tabla] = cursor.fetchall()
                return result
            antes = snapshot()
            MigrationExecutor(connection).migrate([('chat', '0003_tickets_canales')])
            self.assertEqual(snapshot(), antes)
            ticket, _ = tickets.emitir(self.actor)
            self.assertTrue(ticket)
            with self.assertRaises(IrreversibleError):
                MigrationExecutor(connection).migrate([('chat', '0002_integridad_chat')])
        finally:
            MigrationExecutor(connection).migrate([('chat', '0003_tickets_canales')])
