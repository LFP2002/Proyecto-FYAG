from datetime import timedelta
import os
import subprocess
import sys
from unittest.mock import patch

from django.db import connection
from django.test import TransactionTestCase, override_settings
from django.utils import timezone

from apps.usuarios import bloqueos
from apps.usuarios.models import EstadoAcceso, EventoAcceso, Usuario
from apps.usuarios.politica_bloqueos import Senal
from . import test_concurrencia_006 as concurrencia


@override_settings(BLOQUEOS_C1_SIMULACION_HABILITADA=True)
class ConcurrenciaC1Tests(TransactionTestCase):
    race = concurrencia.ConcurrenciaTests.race

    def setUp(self):
        self.user = Usuario.objects.create_user(username="qa_c1_race", email="qa_c1_race@example.test", rol="TECNICO")
        self.now = timezone.now() + timedelta(seconds=1)

    def fallo(self):
        return bloqueos.registrar_verificacion(self.user.pk, Senal.CLAVE_INCORRECTA)

    def test_quinto_concurrente_un_solo_ciclo_y_evento(self):
        with patch("apps.usuarios.bloqueos.timezone.now", return_value=self.now):
            for _ in range(4):
                self.fallo()
            one, two = self.race(self.fallo, self.fallo)
        self.assertEqual(one.estado, two.estado)
        state = EstadoAcceso.objects.get()
        self.assertEqual((state.version, state.intentos, len(state.ciclos_en)), (6, 0, 1))
        self.assertEqual(EventoAcceso.objects.filter(tipo="BLOQUEO_TEMPORAL").count(), 1)

    def test_incrementos_concurrentes_no_se_pierden(self):
        with patch("apps.usuarios.bloqueos.timezone.now", return_value=self.now):
            self.race(self.fallo, self.fallo)
        self.assertEqual(EstadoAcceso.objects.get().intentos, 2)

    def test_cuarto_ciclo_concurrente_no_duplica_ti(self):
        now = self.now
        for minutes in (15, 60, 240):
            with patch("apps.usuarios.bloqueos.timezone.now", return_value=now):
                for _ in range(5):
                    self.fallo()
            now += timedelta(minutes=minutes)
        with patch("apps.usuarios.bloqueos.timezone.now", return_value=now):
            for _ in range(4):
                self.fallo()
            self.race(self.fallo, self.fallo)
        self.assertEqual(EstadoAcceso.objects.get().estado, "REQUIERE_TI")
        self.assertEqual(EventoAcceso.objects.filter(tipo="BLOQUEO_TI").count(), 1)

    def test_reconexion_conserva_contador_y_bloqueo(self):
        with patch("apps.usuarios.bloqueos.timezone.now", return_value=self.now):
            for _ in range(4):
                self.fallo()
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_backend_pid()")
                before = cursor.fetchone()[0]
            connection.close()
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_backend_pid()")
                self.assertNotEqual(cursor.fetchone()[0], before)
            self.assertEqual(EstadoAcceso.objects.get().intentos, 4)
            self.fallo()
            connection.close()
            self.assertEqual(EstadoAcceso.objects.get().estado, "BLOQUEO_TEMPORAL")

    def test_workers_python_nuevos_releen_estado_confirmado(self):
        # Dos intérpretes nuevos, exclusivamente contra la BD efímera de test.
        database = connection.settings_dict["NAME"]
        self.assertTrue(database.startswith("test_"))
        env = {**os.environ, "POSTGRES_DB": database}
        code = (
            "from django.test import override_settings; "
            "from apps.usuarios.bloqueos import registrar_verificacion; "
            "from apps.usuarios.politica_bloqueos import Senal; "
            "override_settings(BLOQUEOS_C1_SIMULACION_HABILITADA=True).enable(); "
            f"registrar_verificacion({self.user.pk}, Senal.CLAVE_INCORRECTA)"
        )
        for _ in range(2):
            result = subprocess.run([sys.executable, "manage.py", "shell", "-c", code],
                                    env=env, capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, "Worker QA falló; no imprimir contexto sensible.")
        self.assertEqual(EstadoAcceso.objects.get().intentos, 2)
