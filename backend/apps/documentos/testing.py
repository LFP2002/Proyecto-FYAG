"""Runner explícito de QA: jamás usa Mongo de desarrollo para ejecutar tests."""
import os

from django.conf import settings
from django.test.runner import DiscoverRunner
from django.test.utils import override_settings

from . import mongo


class DocumentalTestRunner(DiscoverRunner):
    def setup_test_environment(self, **kwargs):
        conf = {**settings.DOCUMENTOS_MONGO, "host": os.getenv("FYAG_MONGO_TEST_HOST", "mongodb_test"),
            "puerto": int(os.getenv("FYAG_MONGO_TEST_PORT", "27017")), "db": "fyag_documentos_test",
            "usuario": os.getenv("FYAG_MONGO_TEST_USER", ""), "password": os.getenv("FYAG_MONGO_TEST_PASSWORD", "")}
        if not conf["usuario"] or not conf["password"]:
            raise RuntimeError("QA requiere Mongo efímero autenticado y variables FYAG_MONGO_TEST_*; no se usará desarrollo.")
        self.documental_settings = override_settings(DOCUMENTOS_MONGO=conf)
        self.documental_settings.enable()
        try:
            mongo.coleccion()
            super().setup_test_environment(**kwargs)
        except BaseException:
            self.documental_settings.disable()
            mongo.cerrar()
            raise

    def teardown_test_environment(self, **kwargs):
        try:
            super().teardown_test_environment(**kwargs)
        finally:
            mongo.cerrar()
            self.documental_settings.disable()
