from datetime import timedelta
from uuid import uuid4
from unittest.mock import patch
from importlib import import_module

from django.db import connection, transaction, IntegrityError
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.exceptions import IrreversibleError
from django.test import TransactionTestCase, TestCase, override_settings
from django.utils import timezone

from apps.chat import services
from apps.chat.models import ConversacionChat, ParticipanteChat, MensajeChat, ArchivoChat, ActoChat
from apps.chat.purga import purgar
from apps.usuarios.models import Usuario
from .base import ChatBase


class IntegridadChatTests(ChatBase, TestCase):
    def setUp(self):
        self.preparar()

    def test_conversacion_sin_miembros_ni_recibo_falla_diferido(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            ConversacionChat.objects.create(tipo='GRUPAL', titulo='Grupo inválido', creador=self.actor)
            with connection.cursor() as cursor:
                cursor.execute('SET CONSTRAINTS ALL IMMEDIATE')

    def test_mensaje_sin_contenido_archivo_o_recibo_no_confirma(self):
        c = self.directa()
        for contenido in ['', 'Sin recibo']:
            with self.assertRaises(IntegrityError), transaction.atomic():
                MensajeChat.objects.create(conversacion=c, autor=self.actor, texto=contenido, vence_en=timezone.now()+timedelta(days=30), clave_idempotencia=uuid4(), huella='a'*64)
                with connection.cursor() as cursor:
                    cursor.execute('SET CONSTRAINTS ALL IMMEDIATE')

    def test_cursores_y_recibos_no_mutables_por_sql(self):
        c = self.directa(); m = self.enviar(c)
        for sql, args in [
            ("UPDATE chat_actochat SET huella=%s WHERE mensaje_id=%s", ['b'*64, m.pk]),
            ('DELETE FROM chat_actochat WHERE mensaje_id=%s', [m.pk]),
            ('UPDATE chat_conversacionchat SET titulo=%s WHERE id=%s', ['Cambio', c.pk]),
        ]:
            with self.assertRaises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
                cursor.execute(sql, args)

    def test_grupo_de_20_participantes_valido(self):
        users = [Usuario.objects.create_user(username=f'grupo20_{i}', email=f'grupo20_{i}@chat.test', rol='TECNICO') for i in range(19)]
        c, nuevo = services.crear_conversacion({'tipo': 'GRUPAL', 'titulo': 'Grupo de 20', 'participantes': [u.pk for u in users], 'clave_idempotencia': str(uuid4())}, self.actor)
        self.assertTrue(nuevo)
        self.assertEqual(c.participantes.count(), 20)

    def test_sql_no_agrega_archivo_retroactivamente_a_mensaje_confirmado(self):
        c = self.directa(); m = self.enviar(c)
        row = ArchivoChat.objects.create()
        with self.assertRaises(IntegrityError), transaction.atomic():
            row.estado = 'PUBLICADO'; row.mensaje = m; row.nombre = 'falso.png'; row.mime = 'image/png'; row.tamano_bytes = 10; row.sha256 = 'a'*64
            row.save()

    def test_retencion_configurada_y_watermark_persiste_tras_purga(self):
        c = self.directa()
        with override_settings(CHAT_RETENCION_DIAS=1), patch('apps.chat.services.timezone.now', return_value=timezone.now()-timedelta(days=2)):
            m = self.enviar(c)
        self.assertEqual(m.vence_en-m.creado_en, timedelta(days=1))
        nuevo = self.enviar(c)
        services.leer(c.pk, {'ultimo_mensaje_id': nuevo.pk}, self.actor)
        purgar()
        p = ParticipanteChat.objects.get(conversacion=c, usuario=self.actor)
        self.assertEqual(p.ultimo_leido_mensaje_id, nuevo.pk)
        self.assertFalse(MensajeChat.objects.filter(pk=m.pk).exists())
        self.assertGreater(nuevo.pk, m.pk)


class MigracionChatTests(ChatBase, TransactionTestCase):
    def test_upgrade_sin_backfill_ni_cambios_usuarios_y_reversion_bloqueada(self):
        self.preparar()
        executor = MigrationExecutor(connection)
        hojas = executor.loader.graph.leaf_nodes()
        previos = [x for x in hojas if x[0] != 'chat']+[('chat', None)]
        antes = list(Usuario.objects.order_by('pk').values())
        try:
            executor.migrate(previos)
            MigrationExecutor(connection).migrate(hojas)
            self.assertEqual(list(Usuario.objects.order_by('pk').values()), antes)
            self.assertFalse(ConversacionChat.objects.exists())
            self.assertFalse(MensajeChat.objects.exists())
            self.directa()
            state = MigrationExecutor(connection).loader.project_state(hojas).apps
            with self.assertRaises(IrreversibleError), connection.schema_editor() as editor:
                import_module('apps.chat.migrations.0002_integridad_chat').reversa(state, editor)
        finally:
            MigrationExecutor(connection).migrate(hojas)
