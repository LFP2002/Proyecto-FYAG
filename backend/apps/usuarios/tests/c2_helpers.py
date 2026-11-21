from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.usuarios.models import Usuario
from .test_administracion import PASSWORD


class BaseC2:
    def setUp(self):
        self.manager = Usuario.objects.create_user(username="qa_c2_ti1", email="qa_c2_ti1@example.test", password=PASSWORD, rol="ADMINISTRADOR_TI")
        self.other = Usuario.objects.create_user(username="qa_c2_ti2", email="qa_c2_ti2@example.test", password=PASSWORD, rol="ADMINISTRADOR_TI")
        self.target = Usuario.objects.create_user(username="qa_c2_target", email="qa_c2_target@example.test", password=PASSWORD, rol="TECNICO")
        self.activation = override_settings(
            BLOQUEOS_C2_HABILITADO=True, BLOQUEOS_C2_ENTORNO="QA_AISLADO_C2",
            BLOQUEOS_C2_TI_QA_IDS=(self.manager.pk, self.other.pk),
            BLOQUEOS_C2_RECUPERACION_QA_CONFIRMADA=True, BLOQUEOS_C2_RIESGO_DOS_QA_ACEPTADO=True,
            BLOQUEOS_C2_RESPUESTAS="401_GENERICO", BLOQUEOS_C2_SESIONES_TEMPORALES="REVOCAR_TODAS_QA")
        self.activation.enable()
        self.addCleanup(self.activation.disable)
        self.now = timezone.now() + timedelta(seconds=1)
        self.clock = patch("apps.usuarios.autenticacion_c2.timezone.now", side_effect=lambda: self.now)
        self.clock.start()
        self.addCleanup(self.clock.stop)
        self.client = APIClient(enforce_csrf_checks=True)
        self.csrf = self.client.get("/api/auth/csrf/").data["csrfToken"]
        cache.clear()

    def login(self, user=None, password=PASSWORD, *, clear_rate=True):
        if clear_rate:
            cache.clear()  # Aislar motor; throttles se prueban explícitamente aparte.
        result = self.client.post("/api/auth/login/", {"email": (user or self.target).email, "password": password},
                                  format="json", HTTP_X_CSRFTOKEN=self.csrf)
        if result.status_code == 200:
            self.csrf = result.data["csrfToken"]
        return result

    def fail(self, user=None, count=5):
        for _ in range(count):
            self.assertEqual(self.login(user, "incorrecta-sintetica-qa").status_code, 401)

    def four_cycles(self, user=None):
        for minutes in (15, 60, 240):
            self.fail(user)
            self.now += timedelta(minutes=minutes)
        self.fail(user)
