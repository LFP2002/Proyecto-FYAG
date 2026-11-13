from io import StringIO
import os
from tempfile import TemporaryDirectory
from uuid import uuid4

from django.conf import settings
from django.core.management import call_command
from django.test import TransactionTestCase, override_settings
from pymongo import MongoClient

from apps.obras.models import EvidenciaTurno
from apps.obras.tests.test_turnos import TurnosBase, foto
from apps.documentos import mongo, services

BASE = "/api/documentos-metadata/"


class DocumentosBase(TurnosBase, TransactionTestCase):
    def setUp(self):
        self.setUpTestData()
        self.preparar()
        self.temporal = TemporaryDirectory()
        self.addCleanup(self.temporal.cleanup)
        config = override_settings(EVIDENCIAS_ROOT=self.temporal.name)
        config.enable()
        self.addCleanup(config.disable)
        conf = settings.DOCUMENTOS_MONGO
        assert conf["db"] == "fyag_documentos_test"
        self.admin = MongoClient(conf["host"], conf["puerto"], username=os.environ["FYAG_MONGO_TEST_ROOT_USER"],
            password=os.environ["FYAG_MONGO_TEST_ROOT_PASSWORD"], authSource="admin", tz_aware=True, serverSelectionTimeoutMS=2000)
        self.addCleanup(self.admin.close)
        self.db = self.admin[conf["db"]]
        self.col = self.db[mongo.COL]
        self.col.delete_many({})
        self.addCleanup(lambda: self.col.delete_many({}))
        self.turno = self.cerrar(self.abrir(), fotos=[foto()])
        self.evidencia = EvidenciaTurno.objects.get()
        self.autenticar(self.gerencia)

    def reconciliar(self):
        out = StringIO()
        call_command("reconciliar_documentos_mongodb", stdout=out)
        return out.getvalue()

    def get(self, evidencia=None):
        return self.client.get(BASE + f"evidencias/{evidencia or self.evidencia.pk}/")

    def patch(self, data, evidencia=None):
        return self.client.patch(BASE + f"evidencias/{evidencia or self.evidencia.pk}/", data, format="json")

    def proyectar(self, evidencia=None):
        services.sincronizar(services.fuente((evidencia or self.evidencia).pk))

    def evidencia_extra(self):
        return EvidenciaTurno.objects.create(turno=self.turno, obra=self.obra, nombre_interno=uuid4().hex+".png",
            tipo_mime="image/png", tamano=70, sha256="a"*64, registrado_por=self.tecnico)
