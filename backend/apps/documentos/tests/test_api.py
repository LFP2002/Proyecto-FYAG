import json
from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.test import override_settings
from django.utils import timezone
from bson import Int64

from apps.documentos import mongo, services
from apps.documentos.validaciones import CLAVES_ATRIBUTOS
from apps.usuarios.models import Usuario
from apps.usuarios.tokens import AccessToken
from apps.obras.models import EvidenciaTurno, TurnoObra
from .base import DocumentosBase, BASE


@override_settings(PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class DocumentosAPITests(DocumentosBase):
    def test_openapi_referencias_proyeccion_y_claves_canonicas(self):
        from pathlib import Path
        schema=json.loads((Path(settings.BASE_DIR)/"docs/openapi/SPEC-012-v1.json").read_text(encoding="utf-8"))
        self.assertEqual(set(schema["components"]["schemas"]["Documento"]["required"]),set(services.PUBLICOS))
        self.assertEqual(set(schema["components"]["schemas"]["Atributos"]["properties"]),CLAVES_ATRIBUTOS)
        self.assertEqual(set(mongo.esquema()["$jsonSchema"]["properties"]["atributos"]["properties"]),CLAVES_ATRIBUTOS)
        def walk(value):
            if isinstance(value,dict):
                if "$ref" in value:
                    target=schema
                    for key in value["$ref"].removeprefix("#/").split("/"): target=target[key]
                for child in value.values(): walk(child)
            elif isinstance(value,list):
                for child in value: walk(child)
        walk(schema)

    def test_proyeccion_real_origen_tipos_y_contrato_sin_archivos(self):
        self.proyectar()
        doc = self.col.find_one()
        self.assertEqual(doc["_id"], f"evidencia_turno:{self.evidencia.pk}")
        for key in ("evidencia_id", "obra_id", "turno_id", "tamano_bytes"):
            self.assertIsInstance(doc[key], Int64)
        response = self.get()
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(set(response.data), set(services.PUBLICOS))
        self.assertEqual(response.data["descripcion"], "")
        for key in ("sha256", "_id", "nombre_interno", "anotado_por_id", "anotado_en"):
            self.assertNotIn(key, response.data)
        self.assertNotIn(self.evidencia.nombre_interno, response.content.decode())
        self.assertEqual(response["Cache-Control"], "private, no-store")
        self.assertIn("Authorization", response["Vary"])
        self.assertEqual(response["X-Content-Type-Options"], "nosniff")

    def test_patch_documental_reemplaza_presentes_y_conserva_ausentes(self):
        self.proyectar()
        r = self.patch({"revision": 0, "descripcion": "  Estado   inicial  ", "etiquetas": [" Exterior ", "ANTES"], "atributos": {"vista": "Frontal", "requiere_revision": True}})
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["descripcion"], "Estado inicial")
        self.assertEqual(r.data["etiquetas"], ["antes", "exterior"])
        self.assertEqual(r.data["revision"], 1)
        r = self.patch({"revision": 1, "atributos": {}})
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["etiquetas"], ["antes", "exterior"])
        self.assertEqual(r.data["atributos"], {})
        doc = self.col.find_one()
        self.assertEqual(doc["anotado_por_id"], self.gerencia.pk)
        self.assertIsNotNone(doc["anotado_en"].tzinfo)
        self.assertEqual(self.get().data, r.data)

    def test_revision_obsoleta_no_sobrescribe_y_sin_lag_ambiguo(self):
        self.assertEqual(self.get().status_code, 409)
        self.assertEqual(self.get().data["code"], "metadata_pendiente_sincronizacion")
        self.assertEqual(self.patch({"revision": 0, "descripcion": "Vista"}).status_code, 409)
        self.proyectar()
        self.assertEqual(self.patch({"revision": 0, "descripcion": "Antes"}).status_code, 200)
        r = self.patch({"revision": 0, "descripcion": "Después"})
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data["code"], "revision_obsoleta")
        self.assertEqual(self.get().data["descripcion"], "Antes")

    def test_listado_paginado_orden_y_solo_proyecciones_existentes(self):
        for _ in range(27):
            self.evidencia_extra()
        EvidenciaTurno.objects.update(creado_en=timezone.now())
        self.reconciliar()
        r = self.client.get(BASE, {"obra": self.obra.pk})
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(set(r.data), {"count", "next", "previous", "results", "proyeccion", "fuente_autoritativa"})
        self.assertEqual(r.data["count"], 28)
        self.assertEqual(len(r.data["results"]), 25)
        r2 = self.client.get(r.data["next"])
        self.assertEqual(len(r2.data["results"]), 3)
        ids = [d["evidencia_id"] for d in r.data["results"]+r2.data["results"]]
        self.assertEqual(ids, sorted(ids, reverse=True))
        self.col.delete_many({})
        self.assertEqual(self.client.get(BASE, {"obra": self.obra.pk}).data["count"], 0)

    def test_filtros_estrictos_listado_detalle(self):
        for query in ("", "page=1", "obra=", "obra=01", "obra=+1", "obra=-1", "obra=1e2", "obra=9223372036854775808", "obra=1&obra=1", "obra=1&x=1", "obra=1&format=json", "obra=1&page=", "obra=1&page=0", "obra=1&page=01", "obra=1&page=1&page=1"):
            self.assertEqual(self.client.get(BASE+'?'+query).status_code, 400, query)
        for query in ("page=1", "revision=0", "obra=1", "format=json"):
            self.assertEqual(self.client.get(BASE+f'evidencias/{self.evidencia.pk}/?'+query).status_code, 400)
        self.assertEqual(self.client.get(BASE, {"obra": self.obra.pk, "page": 2}).status_code, 400)

    def test_roles_cinco_head_options_flags_claims(self):
        ti=Usuario.objects.create_user(username="ti012", email="ti012@example.test", rol="ADMINISTRADOR_TI")
        self.proyectar()
        for actor in (self.gerencia,self.supervisor,self.tecnico,self.finanzas,ti):
            actor.is_staff=actor.is_superuser=True
            actor.save()
            token=AccessToken.for_user(actor); token["rol"]="GERENCIA"
            self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
            expected=200 if actor.rol in ("GERENCIA","SUPERVISOR_OBRAS") else 403
            for method in ("get","head","options"):
                r=getattr(self.client,method)(BASE+f'evidencias/{self.evidencia.pk}/')
                self.assertEqual(r.status_code,expected,(actor.rol,method,getattr(r,"data",None)))
            revision=self.col.find_one()["revision"]
            self.assertEqual(self.patch({"revision":revision,"descripcion":"Vista frontal"}).status_code,expected)
            self.assertEqual(self.client.get(BASE,{"obra":self.obra.pk}).status_code,expected)

    def test_sesion_ausente_revocada_expirada_inactiva_y_cambio_rol(self):
        self.client.credentials()
        self.assertEqual(self.get().status_code,401)
        token=AccessToken.for_user(self.gerencia)
        token.set_exp(from_time=timezone.now()-timedelta(days=1),lifetime=timedelta(seconds=1))
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual(self.get().status_code,401)
        self.autenticar(self.gerencia)
        Usuario.objects.filter(pk=self.gerencia.pk).update(sesion_version=self.gerencia.sesion_version+1)
        self.assertEqual(self.get().status_code,401)
        self.gerencia.refresh_from_db();self.autenticar(self.gerencia)
        Usuario.objects.filter(pk=self.gerencia.pk).update(is_active=False)
        self.assertEqual(self.get().status_code,401)
        Usuario.objects.filter(pk=self.gerencia.pk).update(is_active=True,rol="TECNICO")
        self.assertEqual(self.get().status_code,403)

    def test_no_existe_sql_404_antes_mongo_y_pertenencia(self):
        with patch("apps.documentos.mongo.coleccion",side_effect=AssertionError("No tocar Mongo")):
            self.assertEqual(self.get(9223372036854775807).status_code,404)
            self.assertEqual(self.client.get(BASE,{"obra":9223372036854775807}).status_code,404)
        otra=self.otra_obra()
        self.assertEqual(self.client.get(BASE,{"obra":otra.pk}).data["count"],0)
        EvidenciaTurno.objects.filter(pk=self.evidencia.pk).update(obra=otra)
        self.assertEqual(self.get().status_code,404)

    def test_rechazo_campos_tecnicos_revision_y_null(self):
        self.proyectar()
        for data in ([],{}, {"revision":0}, {"descripcion":"Vista"}, {"revision":True,"descripcion":"Vista"}, {"revision":-1,"descripcion":"Vista"}, {"revision":0.0,"descripcion":"Vista"}, {"revision":9223372036854775807,"descripcion":"Vista"}, {"revision":0,"descripcion":None}, {"revision":0,"etiquetas":None}, {"revision":0,"atributos":None}):
            self.assertEqual(self.patch(data).status_code,400,data)
        for key in services.TECNICOS | {"anotado_en","anotado_por_id","$set"}:
            self.assertEqual(self.patch({"revision":0,"descripcion":"Vista",key:"x"}).status_code,400,key)
        self.assertEqual(self.col.find_one()["revision"],0)

    def test_json_duplicado_malicioso_y_content_type(self):
        self.proyectar()
        route=BASE+f'evidencias/{self.evidencia.pk}/'
        for raw in ('{"revision":0,"revision":0,"descripcion":"Vista"}', '{"revision":0,"atributos":{"vista":"a","vista":"b"}}','{"revision":NaN,"descripcion":"Vista"}','{"revision":0,"descripcion":"'+('x'*33000)+'"}'):
            self.assertEqual(self.client.patch(route,raw,content_type="application/json").status_code,400)
        self.assertEqual(self.client.patch(route,'x=1',content_type="text/plain").status_code,400)
        self.assertEqual(self.col.find_one()["revision"],0)

    def test_etiquetas_longitudes_unicode_y_normalizacion(self):
        self.proyectar()
        for values in (["antes"," ANTES "],[""],["x"*41],["a"]*13,[None],[True],["<script>"],["\u200bantes"],["a.b"],["$set"]):
            self.assertEqual(self.patch({"revision":0,"etiquetas":values}).status_code,400,values)
        self.assertEqual(self.patch({"revision":0,"descripcion":"x"*1001}).status_code,400)
        r=self.patch({"revision":0,"descripcion":"Refrigeracio\u0301n", "etiquetas":["Después","ANTES"]})
        self.assertEqual(r.status_code,200,r.data)
        self.assertEqual(r.data["etiquetas"],["antes","después"])

    def test_atributos_planos_claves_y_maximo_json(self):
        self.proyectar()
        for values in ({"$set":"a"},{"a.b":"a"},{"sha256":"a"},{"email":"a"},{"vista":[]},{"vista":{}},{"vista":None},{"vista":12},{"vista":"x"*201},{"cliente":"x"}):
            self.assertEqual(self.patch({"revision":0,"atributos":values}).status_code,400,values)
        grandes={k:"ñ"*200 for k in CLAVES_ATRIBUTOS}
        self.assertEqual(self.patch({"revision":0,"atributos":grandes}).status_code,400)
        validos={k:True for k in CLAVES_ATRIBUTOS}
        self.assertEqual(self.patch({"revision":0,"atributos":validos}).status_code,200)

    def test_rechazo_datos_sensibles_html_paths_archivos(self):
        self.proyectar()
        for text in ("<script>alert(1)</script>","persona@example.test","12.345.678-5","https://example.test", "data:image/png;base64,AAA", "/var/lib/fyag/evidencias/a.png", "C:\\Users\\privado", "Bearer abc", "monto 2000", "x"*100):
            self.assertEqual(self.patch({"revision":0,"descripcion":text}).status_code,400,text)

    def test_metodos_no_admitidos_y_no_cambia_turno_sql(self):
        self.proyectar()
        antes=TurnoObra.objects.values().get(pk=self.turno.pk)
        for method in ("post","put","delete"):
            self.assertEqual(getattr(self.client,method)(BASE+f'evidencias/{self.evidencia.pk}/',{},format="json").status_code,405)
        self.assertEqual(self.client.patch(BASE,{},format="json").status_code,405)
        self.assertEqual(self.patch({"revision":0,"descripcion":"Vista frontal"}).status_code,200)
        self.assertEqual(antes,TurnoObra.objects.values().get(pk=self.turno.pk))

    def test_logs_estructurados_sin_anotaciones_hash_o_ruta(self):
        self.proyectar()
        with self.assertLogs("apps.documentos.services",level="INFO") as logs:
            r=self.patch({"revision":0,"descripcion":"Unidad exterior revisión","etiquetas":["despues"],"atributos":{"vista":"posterior"}})
        self.assertEqual(r.status_code,200,r.data)
        event=json.loads(logs.records[0].getMessage())
        self.assertEqual(event["revision"],1)
        self.assertEqual(event["actor_id"],self.gerencia.pk)
        for value in ("Unidad exterior", "despues", "posterior",self.evidencia.sha256,self.evidencia.nombre_interno,"Bearer"):
            self.assertNotIn(value,str(logs.output))
