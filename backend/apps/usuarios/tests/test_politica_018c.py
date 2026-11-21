from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from django.test import SimpleTestCase

from apps.usuarios.politica_bloqueos import (
    EstadoPolitica, POLITICA_RATIFICADA, Senal, calcular_transicion, validar_politica,
)


class PoliticaC1Tests(SimpleTestCase):
    ahora = datetime(2026, 11, 20, 12, tzinfo=timezone.utc)

    def cinco(self, state, now):
        for _ in range(5):
            result = calcular_transicion(state, Senal.CLAVE_INCORRECTA, now)
            state = result.estado
        return result

    def test_uno_a_cuatro_y_quinto(self):
        state = EstadoPolitica()
        for count in range(1, 5):
            result = calcular_transicion(state, Senal.CLAVE_INCORRECTA, self.ahora)
            state = result.estado
            self.assertEqual(len(state.fallos), count)
            self.assertEqual(state.estado, "NORMAL")
            self.assertEqual(result.eventos, ())
        result = calcular_transicion(state, Senal.CLAVE_INCORRECTA, self.ahora)
        self.assertEqual(result.estado.estado, "BLOQUEO_TEMPORAL")
        self.assertEqual(result.estado.bloqueado_hasta, self.ahora + timedelta(minutes=15))
        self.assertEqual(result.eventos, (("BLOQUEO_TEMPORAL", 5),))

    def test_ventana_movil_no_fija_y_frontera_excluyente(self):
        state = EstadoPolitica(fallos=(self.ahora, self.ahora + timedelta(minutes=1),
                                     self.ahora + timedelta(minutes=2), self.ahora + timedelta(minutes=3)))
        result = calcular_transicion(state, Senal.CLAVE_INCORRECTA, self.ahora + timedelta(minutes=15))
        self.assertEqual(len(result.estado.fallos), 4)
        self.assertEqual(result.estado.fallos[0], self.ahora + timedelta(minutes=1))
        before = calcular_transicion(state, Senal.CLAVE_INCORRECTA,
                                     self.ahora + timedelta(minutes=15, microseconds=-1))
        self.assertEqual(before.estado.estado, "BLOQUEO_TEMPORAL")

    def test_ventana_expirada_reinicia_solo_fallos(self):
        state = EstadoPolitica(fallos=(self.ahora,) * 4, ciclos=(self.ahora - timedelta(hours=1),))
        result = calcular_transicion(state, Senal.CLAVE_INCORRECTA, self.ahora + timedelta(minutes=15))
        self.assertEqual(len(result.estado.fallos), 1)
        self.assertEqual(result.estado.ciclos, state.ciclos)

    def test_tres_duraciones_y_cuarto_ciclo_ti(self):
        state, now = EstadoPolitica(), self.ahora
        for minutes in (15, 60, 240):
            result = self.cinco(state, now)
            state = result.estado
            self.assertEqual(state.bloqueado_hasta, now + timedelta(minutes=minutes))
            now = state.bloqueado_hasta
        result = self.cinco(state, now)
        self.assertEqual(result.estado.estado, "REQUIERE_TI")
        self.assertEqual(len(result.estado.ciclos), 4)
        self.assertIsNone(result.estado.bloqueado_hasta)
        self.assertEqual(result.eventos[-1], ("BLOQUEO_TI", 5))

    def test_bloqueo_no_se_extiende_y_expira_exactamente(self):
        state = self.cinco(EstadoPolitica(), self.ahora).estado
        for signal in Senal:
            self.assertEqual(calcular_transicion(state, signal, state.bloqueado_hasta - timedelta(microseconds=1)).estado, state)
        result = calcular_transicion(state, Senal.REVISAR_VENCIMIENTO, state.bloqueado_hasta)
        self.assertEqual(result.estado.estado, "NORMAL")
        self.assertEqual(result.eventos, (("EXPIRACION", 0),))
        self.assertEqual(result.estado.ciclos, state.ciclos)

    def test_24h_frontera_y_reinicio_escalada(self):
        state = EstadoPolitica(ciclos=(self.ahora,), fallos=(self.ahora + timedelta(hours=23, minutes=59),) * 4)
        before = calcular_transicion(state, Senal.CLAVE_INCORRECTA, self.ahora + timedelta(hours=24, microseconds=-1))
        self.assertEqual(before.estado.bloqueado_hasta - before.estado.bloqueo_inicio, timedelta(minutes=60))
        exact = calcular_transicion(state, Senal.CLAVE_INCORRECTA, self.ahora + timedelta(hours=24))
        self.assertEqual(len(exact.estado.ciclos), 1)
        self.assertEqual(exact.estado.bloqueado_hasta - exact.estado.bloqueo_inicio, timedelta(minutes=15))

    def test_acierto_limpia_racha_no_historia(self):
        state = EstadoPolitica(fallos=(self.ahora,) * 3, ciclos=(self.ahora - timedelta(hours=1),))
        result = calcular_transicion(state, Senal.CLAVE_CORRECTA, self.ahora)
        self.assertEqual(result.estado.fallos, ())
        self.assertEqual(result.estado.ciclos, state.ciclos)
        self.assertEqual(result.eventos, (("REINICIO_RACHA", 3),))

    def test_ti_no_caduca_ni_acierto_desbloquea(self):
        state = EstadoPolitica("REQUIERE_TI", (), (self.ahora,) * 4, self.ahora)
        for signal in Senal:
            self.assertEqual(calcular_transicion(state, signal, self.ahora + timedelta(days=30)).estado, state)

    def test_sin_verificacion_no_muta_ni_expira(self):
        state = EstadoPolitica(fallos=(self.ahora,))
        self.assertEqual(calcular_transicion(state, Senal.SIN_VERIFICACION, self.ahora + timedelta(days=1)).estado, state)

    def test_reloj_aware_y_santiago_equivalente(self):
        a = self.cinco(EstadoPolitica(), self.ahora)
        b = self.cinco(EstadoPolitica(), self.ahora.astimezone(ZoneInfo("America/Santiago")))
        self.assertEqual(a, b)
        with self.assertRaises(ValueError):
            calcular_transicion(EstadoPolitica(), Senal.CLAVE_INCORRECTA, self.ahora.replace(tzinfo=None))

    def test_bloqueo_son_minutos_absolutos_cruzando_dst_chileno(self):
        # Fin DST: reloj local repite hora, pero la duración siempre son 900 s.
        utc = datetime(2026, 4, 5, 2, 55, tzinfo=timezone.utc)
        local = utc.astimezone(ZoneInfo("America/Santiago"))
        result = self.cinco(EstadoPolitica(), local).estado
        self.assertEqual(result.bloqueado_hasta, utc + timedelta(seconds=900))
        after = calcular_transicion(result, Senal.REVISAR_VENCIMIENTO,
                                    (utc + timedelta(seconds=900)).astimezone(ZoneInfo("America/Santiago")))
        self.assertEqual(after.estado.estado, "NORMAL")

    def test_estado_incoherente_y_senal_sin_tipo_rechazados(self):
        for state in (EstadoPolitica(estado="NO_DISPONIBLE"), EstadoPolitica(fallos=(self.ahora,) * 5),
                      EstadoPolitica(fallos=(self.ahora + timedelta(seconds=1),)),
                      EstadoPolitica("BLOQUEO_TEMPORAL")):
            with self.assertRaises(ValueError):
                calcular_transicion(state, Senal.CLAVE_INCORRECTA, self.ahora)
        with self.assertRaises(ValueError):
            calcular_transicion(EstadoPolitica(), "CLAVE_INCORRECTA", self.ahora)

    def test_configuracion_ratificada_estricta(self):
        validar_politica(dict(POLITICA_RATIFICADA))
        for config in (None, {}, {**POLITICA_RATIFICADA, "intentos": 4},
                       {**POLITICA_RATIFICADA, "ciclo_ti": True},
                       {**POLITICA_RATIFICADA, "duraciones_segundos": [900, 3600, 14400]}):
            with self.assertRaises(ValueError):
                validar_politica(config)
