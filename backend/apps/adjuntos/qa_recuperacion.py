"""Escenario opt-in SOLO laboratorio compose.adjuntos-qa.yaml; nunca producción.

Se invoca desde manage.py shell para preparar/verificar un respaldo coordinado.
No elimina ni sustituye datos. En caso de segunda ejecución verifica los existentes.
"""
import hashlib
import json
from io import StringIO
from pathlib import Path
import tarfile

from django.conf import settings
from django.core.management import call_command
from django.db import connection
from rest_framework.test import APIClient

from apps.adjuntos import metadata
from apps.adjuntos.models import AdjuntoDocumento
from apps.adjuntos.tests.test_adjuntos import AdjuntosBase, pdf
from apps.documentos import mongo, services as documentos
from apps.obras.models import EvidenciaTurno
from apps.obras.tests.test_turnos import foto
from apps.usuarios.models import Usuario
from apps.usuarios.tokens import AccessToken


def ejecutar(preparar=False):
    if connection.settings_dict["NAME"] != "fyag_adjuntos_qa" or connection.settings_dict["HOST"] not in {"postgres_qa", "postgres_restore_qa"} or settings.DOCUMENTOS_MONGO["host"] not in {"mongo_qa", "mongo_restore_qa"}:
        raise RuntimeError("Solo laboratorio QA aislado; configuración rechazada")
    ruta = Path("/backup/manifest.json")
    if preparar:
        if ruta.exists() or Usuario.objects.exists():
            raise RuntimeError("Laboratorio no vacío; conservarlo y elegir proyecto nuevo")
        case = AdjuntosBase(methodName="runTest")
        case.setUpTestData(); case.preparar()
        case.autenticar(case.supervisor)
        # Usa volumen persistente del laboratorio, no el runner temporal de tests.
        r = case.client.post(f"/api/adjuntos/obras/{case.obra.pk}/", {"archivo": pdf()}, format="multipart", HTTP_IDEMPOTENCY_KEY="55bfed8d-e605-46e9-bef5-f79d3092e30d")
        if r.status_code != 201:
            raise AssertionError(r.data)
        adj = AdjuntoDocumento.objects.get(pk=r.data["id"])
        metadata.sincronizar(adj)
        metadata.editar(adj, case.supervisor, {"revision": 0, "descripcion": "Vista frontal"}, "qa-recuperacion")
        turno = case.cerrar(case.abrir(), fotos=[foto()])
        evidencia = EvidenciaTurno.objects.get(turno=turno)
        documentos.sincronizar(documentos.fuente(evidencia.pk))
        with tarfile.open("/backup/adjuntos.tar", "w") as tar:
            tar.add(settings.ADJUNTOS_ROOT, arcname="adjuntos")
        with tarfile.open("/backup/evidencias.tar", "w") as tar:
            tar.add(settings.EVIDENCIAS_ROOT, arcname="evidencias")
    else:
        mongo.cerrar()
    call_command("reconciliar_adjuntos_mongodb", stdout=StringIO())
    call_command("reconciliar_adjuntos_mongodb", stdout=StringIO())
    adj = AdjuntoDocumento.objects.get()
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(adj.registrado_por)}")
    response = client.get(f"/api/adjuntos/{adj.pk}/descargar/")
    if response.status_code != 200:
        raise AssertionError(getattr(response, "data", None))
    data = b"".join(response.streaming_content); response.close()
    anotacion = metadata.leer(adj)
    evidencia = EvidenciaTurno.objects.get()
    notas_012a = mongo.coleccion().find_one({"evidencia_id": evidencia.pk})
    if notas_012a is None:
        raise AssertionError("Proyección 012A ausente")
    from apps.obras.evidencias import ruta_privada
    hash_012a = hashlib.sha256(Path(ruta_privada(evidencia.nombre_interno)).read_bytes()).hexdigest()
    actual = {"adjunto_id": adj.pk, "sha256": hashlib.sha256(data).hexdigest(), "revision": anotacion["revision"],
        "descripcion": anotacion["descripcion"], "evidencia_012a_id": evidencia.pk, "sha256_012a": hash_012a,
        "documentos_012a": mongo.coleccion().count_documents({})}
    if preparar:
        ruta.write_text(json.dumps(actual, sort_keys=True), encoding="utf-8")
    elif actual != json.loads(ruta.read_text(encoding="utf-8")):
        raise AssertionError("Manifest no coincide")
    print(json.dumps({"resultado": "QA_integridad_notas_012a_correctas", **actual}, sort_keys=True))


def dependencia_caida(mongo_caido=False, scanner_caido=False):
    if connection.settings_dict["NAME"] != "fyag_adjuntos_qa" or connection.settings_dict["HOST"] != "postgres_qa" or settings.DOCUMENTOS_MONGO["host"] != "mongo_qa":
        raise RuntimeError("Solo laboratorio QA origen")
    adj = AdjuntoDocumento.objects.get()
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(adj.registrado_por)}")
    assert client.get(f"/api/adjuntos/obras/{adj.obra_id}/").status_code == 200
    response = client.get(f"/api/adjuntos/{adj.pk}/descargar/")
    assert response.status_code == 200
    assert hashlib.sha256(b"".join(response.streaming_content)).hexdigest() == adj.sha256
    response.close()
    assert client.get(f"/api/adjuntos/{adj.pk}/anotaciones/").status_code == (503 if mongo_caido else 200)
    if scanner_caido:
        response = client.post(f"/api/adjuntos/obras/{adj.obra_id}/", {"archivo": pdf()}, format="multipart",
            HTTP_IDEMPOTENCY_KEY="97aa9509-b223-4294-99c5-f131c13282f9")
        assert response.status_code == 503, response.data
        assert AdjuntoDocumento.objects.count() == 1
    print(json.dumps({"resultado": "QA_dependencia_caida_aislada", "mongo_caido": mongo_caido, "scanner_caido": scanner_caido}))


def rollback_rutas():
    """Rollback funcional no destructivo; nunca downgrade de tablas con datos."""
    from types import ModuleType
    from django.test import override_settings
    from config.urls import urlpatterns
    if connection.settings_dict["HOST"] != "postgres_qa" or settings.DOCUMENTOS_MONGO["host"] != "mongo_qa":
        raise RuntimeError("Solo laboratorio QA origen")
    adj = AdjuntoDocumento.objects.get()
    evidencia = EvidenciaTurno.objects.get()
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(adj.registrado_por)}")
    anterior = ModuleType("qa_urls_sin_adjuntos")
    anterior.urlpatterns = [route for route in urlpatterns if str(route.pattern) != "api/adjuntos/"]
    with override_settings(ROOT_URLCONF=anterior, DEBUG=False):
        assert client.get(f"/api/adjuntos/{adj.pk}/").status_code == 404
        assert client.get(f"/api/documentos-metadata/evidencias/{evidencia.pk}/").status_code == 200
    ejecutar()
    print('{"resultado":"QA_rollback_rutas_sin_perdida_correcto"}')
