"""Runner explícito de QA: jamás usa Mongo de desarrollo para ejecutar tests."""
import os
from tempfile import TemporaryDirectory
from unittest import TextTestResult
from uuid import uuid4

from django.conf import settings
from django.test.runner import DiscoverRunner
from django.test.utils import override_settings

from . import mongo


class DocumentalTestRunner(DiscoverRunner):
    def get_resultclass(self):
        return super().get_resultclass() or SecurityTestResult

    def setup_test_environment(self, **kwargs):
        conf = {**settings.DOCUMENTOS_MONGO, "host": os.getenv("FYAG_MONGO_TEST_HOST", "mongodb_test"),
            "puerto": int(os.getenv("FYAG_MONGO_TEST_PORT", "27017")), "db": "fyag_documentos_test",
            "usuario": os.getenv("FYAG_MONGO_TEST_USER", ""), "password": os.getenv("FYAG_MONGO_TEST_PASSWORD", "")}
        if not conf["usuario"] or not conf["password"]:
            raise RuntimeError("QA requiere Mongo efímero autenticado y variables FYAG_MONGO_TEST_*; no se usará desarrollo.")
        self.adjuntos_temporal = TemporaryDirectory(prefix="fyag-adjuntos-qa-")
        from pathlib import Path
        self.documental_settings = override_settings(DOCUMENTOS_MONGO=conf,
            ADJUNTOS_ROOT=Path(self.adjuntos_temporal.name),
            ADJUNTOS_SCANNER={"host": os.getenv("FYAG_CLAMD_TEST_HOST", "clamav_test"),
                "puerto": os.getenv("FYAG_CLAMD_TEST_PORT", "3310"), "timeout": 15,
                "socket": os.getenv("FYAG_CLAMD_TEST_SOCKET", "")})
        self.documental_settings.enable()
        try:
            mongo.coleccion()
            super().setup_test_environment(**kwargs)
        except BaseException:
            self.documental_settings.disable()
            mongo.cerrar()
            self.adjuntos_temporal.cleanup()
            raise

    def teardown_test_environment(self, **kwargs):
        try:
            super().teardown_test_environment(**kwargs)
        finally:
            mongo.cerrar()
            self.documental_settings.disable()
            self.adjuntos_temporal.cleanup()


class SecurityTestResult(TextTestResult):
    def startTest(self, test):
        self.security_namespace = override_settings(FYAG_SECURITY_REDIS_PREFIX=f'fyag:qa:{uuid4().hex}')
        self.security_namespace.enable()
        super().startTest(test)

    def stopTest(self, test):
        try:
            super().stopTest(test)
        finally:
            self.security_namespace.disable()
