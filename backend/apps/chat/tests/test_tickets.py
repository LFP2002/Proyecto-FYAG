from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import hashlib
from threading import Barrier

from django.db import close_old_connections, connection, transaction, IntegrityError
from django.test import TransactionTestCase, override_settings
from django.utils import timezone

from apps.chat import tickets
from apps.chat.models import TicketChat, CanalChat
from apps.finanzas.tests.test_concurrencia import CarrerasPostgreSQL
from apps.usuarios.models import Usuario
from .base import ChatBase, URL


class TicketsPostgreSQL(ChatBase, TransactionTestCase):
    def setUp(self):
        self.preparar()

    def test_endpoint_digest_y_contrato(self):
        response = self.client.post(URL+'conexion/', {}, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(set(response.data), {'ticket', 'vence_en'})
        row = TicketChat.objects.get()
        self.assertEqual(row.digest, hashlib.sha256(response.data['ticket'].encode()).hexdigest())
        self.assertLessEqual(row.vence_en-row.creado_en, timedelta(seconds=45))
        self.assertIsNone(row.usado_en)
        self.assertEqual(self.client.post(URL+'conexion/', {'grupo': 'otro'}, format='json').status_code, 400)
        self.client.credentials()
        self.assertEqual(self.client.post(URL+'conexion/', {}, format='json').status_code, 401)

    def test_uso_unico(self):
        ticket, _ = tickets.emitir(self.actor)
        canal = tickets.admitir('127.0.0.1')
        identidad = tickets.consumir(ticket, canal)
        self.assertTrue(tickets.verificar(identidad, canal, renovar=True))
        with self.assertRaises(tickets.Denegado):
            tickets.consumir(ticket, tickets.admitir('127.0.0.1'))
        self.assertEqual(CanalChat.objects.filter(usuario=self.actor).count(), 1)

    def test_renovacion_revocada_durante_espera_no_extiende_canal(self):
        ticket, _ = tickets.emitir(self.actor)
        canal_id = tickets.admitir('127.0.0.1')
        identidad = tickets.consumir(ticket, canal_id)
        anterior = CanalChat.objects.get(pk=canal_id).vence_en

        def renovar():
            with self.assertRaises(tickets.Denegado):
                tickets.verificar(identidad, canal_id, renovar=True)

        CarrerasPostgreSQL.race(self, lambda: CanalChat.objects.select_for_update().get(pk=canal_id), renovar,
            tras_espera=lambda: Usuario.objects.filter(pk=self.actor.pk).update(
                sesion_version=self.actor.sesion_version + 1))
        self.assertEqual(CanalChat.objects.get(pk=canal_id).vence_en, anterior)

    def test_expirado_y_password_cambiado(self):
        pasado = timezone.now()-timedelta(seconds=60)
        with override_settings(CHAT_WS_TICKET_TTL=1):
            from unittest.mock import patch
            with patch('apps.chat.tickets.timezone.now', return_value=pasado):
                expirado, _ = tickets.emitir(self.actor)
        with self.assertRaises(tickets.Denegado):
            tickets.consumir(expirado, tickets.admitir('127.0.0.1'))
        ticket, _ = tickets.emitir(self.actor)
        self.actor.set_password('Cambio-QA-no-secreto-023B')
        self.actor.save(update_fields=['password'])
        with self.assertRaises(tickets.Denegado):
            tickets.consumir(ticket, tickets.admitir('127.0.0.1'))

    def test_ticket_concurrente_dos_conexiones_pg(self):
        ticket, _ = tickets.emitir(self.actor)
        canales = [tickets.admitir('127.0.0.1') for _ in range(2)]
        barrera = Barrier(2)
        def competir(canal):
            close_old_connections()
            try:
                barrera.wait(timeout=5)
                try:
                    tickets.consumir(ticket, canal)
                    return 'ok'
                except tickets.Denegado:
                    return 'denegado'
            finally:
                connection.close()
        with ThreadPoolExecutor(max_workers=2) as pool:
            resultados = list(pool.map(competir, canales))
        self.assertCountEqual(resultados, ['ok', 'denegado'])

    def test_revocacion_sesion_inactivo_y_password(self):
        for campo in ('sesion_version', 'is_active', 'password'):
            with self.subTest(campo=campo):
                self.actor.refresh_from_db()
                self.actor.is_active = True
                self.actor.save(update_fields=['is_active'])
                ticket, _ = tickets.emitir(self.actor)
                canal = tickets.admitir('127.0.0.1')
                identidad = tickets.consumir(ticket, canal)
                value = {'sesion_version': self.actor.sesion_version+1, 'is_active': False, 'password': '!revocado'}[campo]
                Usuario.objects.filter(pk=self.actor.pk).update(**{campo: value})
                with self.assertRaises(tickets.Denegado):
                    tickets.verificar(identidad, canal)
                tickets.liberar(canal)

    def test_ticket_sql_inmutable(self):
        tickets.emitir(self.actor)
        with self.assertRaises(IntegrityError), transaction.atomic():
            TicketChat.objects.update(digest='a'*64)
        with self.assertRaises(IntegrityError), transaction.atomic():
            TicketChat.objects.all().delete()

    def test_cupo_usuario_y_pendientes_compartidos(self):
        limites = {'usuario': 1, 'ip': 8, 'total': 8, 'pendientes': 2, 'pendientes_ip': 2,
                   'handshakes_ip_minuto': 20, 'frames': 10, 'ventana_frames': 10}
        with override_settings(CHAT_WS_LIMITES=limites):
            ticket, _ = tickets.emitir(self.actor)
            tickets.consumir(ticket, tickets.admitir('127.0.0.1'))
            segundo, _ = tickets.emitir(self.actor)
            canal = tickets.admitir('127.0.0.1')
            with self.assertRaises(tickets.CupoAgotado):
                tickets.consumir(segundo, canal)
            tickets.admitir('127.0.0.1')
            with self.assertRaises(tickets.CupoAgotado):
                tickets.admitir('127.0.0.1')
