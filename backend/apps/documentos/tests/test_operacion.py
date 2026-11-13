from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from io import StringIO
import json
import os
import secrets
from threading import Barrier, Event
from time import perf_counter
import tracemalloc
from unittest.mock import patch
from uuid import uuid4

from bson import Int64
from django.conf import settings
from django.core.management import call_command, CommandError
from django.db import close_old_connections, connection, transaction
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from pymongo import MongoClient
from pymongo.errors import OperationFailure, WriteError
from rest_framework.test import APIClient

from apps.documentos import mongo, services
from apps.documentos.exceptions import MongoNoDisponible
from apps.obras.models import EvidenciaTurno
from apps.obras.tests.test_turnos import foto
from apps.usuarios.tokens import AccessToken
from .base import DocumentosBase, BASE


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class OperacionDocumentalTests(DocumentosBase):
    def test_autenticacion_real_y_minimo_privilegio(self):
        conf = settings.DOCUMENTOS_MONGO
        app = mongo.cliente()
        self.assertEqual(app.admin.command("ping")["ok"], 1)
        for command in ({"usersInfo": 1}, {"listDatabases": 1}):
            if "listDatabases" in command:
                # Mongo filtra DBs autorizadas; forzar autorización global.
                command["authorizedDatabases"] = False
            with self.assertRaises(OperationFailure):
                app.admin.command(command)
        with self.assertRaises(OperationFailure):
            app[conf["db"]][mongo.COL].delete_many({})
        with self.assertRaises(OperationFailure):
            app[conf["db"]]["auditoria_eventos"].insert_one({"x": 1})
        with MongoClient(conf["host"], conf["puerto"], serverSelectionTimeoutMS=2000) as anon:
            with self.assertRaises(OperationFailure):
                anon[conf["db"]][mongo.COL].find_one()
        with override_settings(DOCUMENTOS_MONGO={**conf, "password": secrets.token_urlsafe(30)}):
            self.assertEqual(self.get().status_code, 503)

    def test_cliente_reutilizado_cierre_y_diagnostico(self):
        primero = mongo.cliente()
        self.assertIs(primero, mongo.cliente())
        output=StringIO()
        call_command("verificar_mongodb", stdout=output)
        self.assertIn("correctos", output.getvalue())
        self.assertIsNot(primero, mongo.cliente())

    def test_configuracion_documental_invalida_no_afecta_sql(self):
        conf=settings.DOCUMENTOS_MONGO
        for cambios in ({"puerto":"invalido"},{"host":"mongodb://cloud.invalid"},{"password":""},{"db":"otra_base"}):
            with override_settings(DOCUMENTOS_MONGO={**conf,**cambios}):
                self.assertEqual(self.get().status_code,503)
                self.assertEqual(self.client.get("/api/reportes/catalogo/").status_code,200)
            self.assertIsNotNone(mongo.coleccion())

    def test_lectura_no_ejecuta_sql_lazy_despues_de_responder(self):
        self.proyectar()
        r=self.client.get(BASE,{"obra":self.obra.pk})
        self.assertEqual(r.status_code,200,r.data)
        with CaptureQueriesContext(connection) as queries:
            r.render()
            json.loads(r.content)
        self.assertEqual(len(queries),0)

    def test_schema_indices_reales_y_rechazo_bson_servidor(self):
        self.proyectar()
        self.assertEqual(self.db.command({"listCollections":1,"filter":{"name":mongo.COL}})["cursor"]["firstBatch"][0]["options"]["validator"], mongo.esquema())
        self.assertEqual(list(self.col.index_information()[mongo.INDICE]["key"]), mongo.ORDEN)
        for changes in ({"extra":True},{"obra_id":1},{"descripcion":"<script>"},{"etiquetas":["a"]*13},{"atributos":{"$set":"x"}},{"atributos":{"vista":{"$gt":0}}},{"descripcion":"x"*17000}):
            with self.assertRaises(WriteError):
                self.col.update_one({}, {"$set":changes})
        self.assertEqual(self.col.find_one()["revision"],0)

    def test_indice_faltante_y_validador_alterado_503_no_200_vacio(self):
        self.proyectar()
        self.col.drop_index(mongo.INDICE)
        try:
            self.assertEqual(self.get().status_code,503)
            self.assertEqual(self.client.get(BASE,{"obra":self.obra.pk}).status_code,503)
        finally:
            self.col.create_index(mongo.ORDEN,name=mongo.INDICE)
        self.db.command({"collMod":mongo.COL,"validationLevel":"off"})
        try:
            self.assertEqual(self.get().status_code,503)
        finally:
            self.db.command({"collMod":mongo.COL,"validationLevel":"strict"})

    def test_bson_corrupto_y_huerfano_no_exponen_datos(self):
        self.proyectar()
        for changes in ({"sha256":"HASH_PRIVADO"},{"nombre_interno":"SECRETO_PRIVADO"},{"obra_id":Int64(9223372036854775807)},{"descripcion":"persona@example.test"}):
            original=self.col.find_one()
            self.col.update_one({}, {"$set":changes},bypass_document_validation=True)
            r=self.get()
            self.assertEqual(r.status_code,503)
            for value in ("HASH_PRIVADO","SECRETO_PRIVADO","persona@example.test"):
                self.assertNotIn(value,r.content.decode())
            self.col.replace_one({"_id":original["_id"]},original,bypass_document_validation=True)
        original=self.col.find_one()
        falso={**original,"_id":"evidencia_turno:9223372036854775807","evidencia_id":Int64(9223372036854775807)}
        self.col.insert_one(falso)
        self.assertEqual(self.client.get(BASE,{"obra":self.obra.pk}).status_code,503)

    def test_reconciliacion_repetida_conserva_anotaciones_y_tecnicos(self):
        self.assertIn('"cantidad": 1', self.reconciliar())
        r=self.patch({"revision":0,"descripcion":"Vista inicial","etiquetas":["antes"],"atributos":{"vista":"frontal"}})
        self.assertEqual(r.status_code,200,r.data)
        antes=self.col.find_one()
        for _ in range(3):
            self.reconciliar()
        despues=self.col.find_one()
        for key in services.EDITABLES:
            self.assertEqual(antes[key],despues[key])
        self.assertEqual(self.col.count_documents({}),1)

    def test_rechazo_mongo_dentro_atomic_y_rollback_no_proyectado(self):
        with transaction.atomic():
            with self.assertRaises(MongoNoDisponible):
                self.proyectar()
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                self.evidencia_extra()
                raise RuntimeError()
        self.reconciliar()
        self.assertEqual(self.col.count_documents({}),1)

    def test_dos_patch_concurrentes_solo_un_cas_exitoso(self):
        self.proyectar()
        token=str(AccessToken.for_user(self.gerencia))
        barrera=Barrier(2)
        original=services.validar_documento
        def leer(doc,row):
            result=original(doc,row)
            if doc["revision"]==0:
                barrera.wait(timeout=10)
            return result
        def editar(texto):
            close_old_connections()
            try:
                client=APIClient();client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
                return client.patch(BASE+f'evidencias/{self.evidencia.pk}/',{"revision":0,"descripcion":texto},format="json")
            finally:
                connection.close()
        with patch("apps.documentos.services.validar_documento",side_effect=leer),ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(editar,texto) for texto in ("Vista frontal","Vista posterior")]
            results=[f.result(timeout=15) for f in futures]
        self.assertEqual(sorted(r.status_code for r in results),[200,409])
        self.assertEqual(self.col.find_one()["revision"],1)

    def test_sincronizadores_concurrentes_preservan_cas(self):
        self.proyectar()
        self.assertEqual(self.patch({"revision":0,"descripcion":"Conservar"}).status_code,200)
        row=services.fuente(self.evidencia.pk)
        def sincronizar():
            close_old_connections()
            try:
                for _ in range(10):
                    services.sincronizar(row)
            finally:
                connection.close()
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures=[pool.submit(sincronizar) for _ in range(3)]
            for f in futures: f.result(timeout=15)
        doc=self.col.find_one()
        self.assertEqual(doc["descripcion"],"Conservar")
        self.assertEqual(doc["revision"],1)

    def test_commits_fuera_orden_se_recuperan_en_siguiente_ciclo(self):
        listo,continuar=Event(),Event()
        def tardio():
            close_old_connections()
            try:
                with transaction.atomic():
                    e=self.evidencia_extra()
                    listo.set()
                    if not continuar.wait(10): raise AssertionError("No liberar commit")
                return e.pk
            finally:
                connection.close()
        with ThreadPoolExecutor(max_workers=1) as pool:
            future=pool.submit(tardio)
            try:
                self.assertTrue(listo.wait(10))
                alto=self.evidencia_extra()
                self.reconciliar()
                self.assertEqual(self.col.count_documents({}),2)
            finally:
                continuar.set()
            bajo=future.result(timeout=15)
        self.assertLess(bajo,alto.pk)
        self.reconciliar()
        self.assertEqual(self.col.count_documents({}),3)
        self.assertIsNotNone(self.col.find_one({"_id":f"evidencia_turno:{bajo}"}))

    def test_fallo_real_conexion_no_impide_finalizar_subsanar_y_recuperar(self):
        conf=settings.DOCUMENTOS_MONGO
        with override_settings(DOCUMENTOS_MONGO={**conf,"host":"127.0.0.1","puerto":1,"timeout_ms":100}):
            # Backend SQL no tiene callbacks ni dependencia de éxito Mongo.
            self.turno = self.abrir()
            self.autenticar(self.tecnico)
            r=self.client.post(self.url+f'{self.turno.pk}/finalizar/',{"descripcion_trabajo":"Trabajo","fotos[]":[foto()]},format="multipart")
            self.assertEqual(r.status_code,200,r.data)
            from apps.obras import services_turnos
            services_turnos.revisar_turno(self.obra,self.turno.pk,{"decision":"OBSERVAR","motivo":"Aclarar"},self.supervisor)
            r=self.client.post(self.url+f'{self.turno.pk}/subsanar/',{"descripcion_trabajo":"Aclaración","fotos[]":[foto()]},format="multipart")
            self.assertEqual(r.status_code,200,r.data)
            self.autenticar(self.gerencia)
            self.assertEqual(self.get().status_code,503)
            self.assertEqual(self.client.get(BASE,{"obra":self.obra.pk}).status_code,503)
            with self.assertRaises(CommandError):
                call_command("reconciliar_documentos_mongodb",stdout=StringIO(),stderr=StringIO())
        self.reconciliar()
        self.assertEqual(self.col.count_documents({}),3)

    def test_modulos_sql_y_login_operan_con_mongo_no_disponible(self):
        password=secrets.token_urlsafe(30)
        self.gerencia.set_password(password); self.gerencia.save()
        self.autenticar(self.gerencia)
        conf=settings.DOCUMENTOS_MONGO
        with override_settings(DOCUMENTOS_MONGO={**conf,"host":"127.0.0.1","puerto":1,"timeout_ms":100}):
            routes=("/api/obras/","/api/presupuestos/","/api/finanzas/documentos/","/api/finanzas/cobranzas/","/api/auditoria/eventos/","/api/alertas/","/api/dashboard/resumen/","/api/reportes/obras/")
            for route in routes:
                r=self.client.get(route)
                self.assertEqual(r.status_code,200,(route,getattr(r,"data",None)))
            client=APIClient()
            r=client.post("/api/auth/login/",{"email":self.gerencia.email,"password":password},format="json")
            self.assertEqual(r.status_code,200,r.data)

    def test_perfil_mil_documentos_indices_memoria_y_queries(self):
        EvidenciaTurno.objects.bulk_create([EvidenciaTurno(turno=self.turno,obra=self.obra,nombre_interno=uuid4().hex+".png",tipo_mime="image/png",tamano=70,sha256="b"*64,registrado_por=self.tecnico) for _ in range(999)],batch_size=200)
        start=perf_counter();self.reconciliar();sync_time=perf_counter()-start
        tracemalloc.start()
        try:
            start=perf_counter()
            with CaptureQueriesContext(connection) as queries:
                r=self.client.get(BASE,{"obra":self.obra.pk})
            elapsed=perf_counter()-start
            _,peak=tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        self.assertEqual(r.status_code,200,r.data)
        self.assertEqual(r.data["count"],1000)
        self.assertEqual(len(r.data["results"]),25)
        self.assertLessEqual(len(queries),10)
        self.assertLess(peak,20*1024*1024)
        explain=self.db.command("explain",{"find":mongo.COL,"filter":{"obra_id":Int64(self.obra.pk),"origen":"EVIDENCIA_TURNO"},"sort":{"creado_en":-1,"evidencia_id":-1}},verbosity="executionStats")
        plan=json.dumps(explain["queryPlanner"]["winningPlan"])
        self.assertIn(mongo.INDICE,plan)
        self.assertNotIn('"SORT"',plan)
        stats=explain["executionStats"]
        print("PERFIL_DOCUMENTOS="+json.dumps({"filas":1000,"pagina":25,"sql":len(queries),"segundos_listado":round(elapsed,4),"segundos_reconciliacion":round(sync_time,4),"pico_python_bytes":peak,"mongo_docs_examined":stats["totalDocsExamined"],"mongo_keys_examined":stats["totalKeysExamined"],"mongo_execution_ms":stats["executionTimeMillis"]}))
