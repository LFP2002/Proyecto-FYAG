"""Regenera los artefactos estáticos OpenAPI/Postman de SPEC-012B (sin servicios)."""
import json
from pathlib import Path

ROOT = Path(__file__).parent


def ref(name):
    return {"$ref": "#/components/schemas/"+name}


def respuesta(schema, description="Operación realizada"):
    return {"description": description, "content": {"application/json": {"schema": schema}}}


error = {str(code): {"description": text} for code, text in {
    400: "Entrada inválida; campos/UUID/query/JSON/multipart estrictos",
    401: "JWT ausente, expirado, revocado o usuario inactivo",
    403: "Rol prohibido (TI nunca accede)", 404: "SQL inexistente o técnico sin participación activa",
    405: "Método no admitido", 409: "Estado, límite 10, idempotencia, integridad o revisión CAS incompatible; metadata pendiente",
    413: "PDF >8 MiB o imagen >5 MiB", 415: "Se requiere multipart/form-data",
    422: "Contenido/estructura/seguridad rechazados", 503: "Scanner, almacenamiento o Mongo no disponibles según operación",
}.items()}
headers = {name: {"schema": {"type": "string"}} for name in (
    "Cache-Control", "Vary", "X-Content-Type-Options", "X-Correlation-ID")}
schemas = {
    "Adjunto": {"type": "object", "additionalProperties": False, "required": ["id", "tipo", "destino", "nombre_visible", "mime", "tamano_bytes", "estado", "registrado_por", "registrado_en"],
        "properties": {"id": {"type": "integer", "format": "int64"}, "tipo": {"enum": ["RESPALDO_FACTURA", "INFORME_TECNICO"]},
            "destino": {"oneOf": [{"type": "object", "required": [key], "additionalProperties": False, "properties": {key: {"type": "integer", "format": "int64"}}} for key in ("obra", "documento_cobro")]},
            "nombre_visible": {"type": "string", "maxLength": 160}, "mime": {"enum": ["application/pdf", "image/jpeg", "image/png"]},
            "tamano_bytes": {"type": "integer", "minimum": 1, "maximum": 8388608}, "estado": {"enum": ["DISPONIBLE"]},
            "registrado_por": {"type": "integer", "format": "int64"}, "registrado_en": {"type": "string", "format": "date-time"}}},
    "Pagina": {"type": "object", "required": ["count", "next", "previous", "results"], "properties": {
        "count": {"type": "integer"}, "next": {"type": "string", "nullable": True}, "previous": {"type": "string", "nullable": True},
        "results": {"type": "array", "maxItems": 25, "items": ref("Adjunto")}}},
    "Carga": {"type": "object", "additionalProperties": False, "required": ["archivo"], "properties": {
        "archivo": {"type": "string", "format": "binary", "description": "Un único PDF <=8 MiB o JPEG/PNG <=5 MiB, <=12 millones píxeles. Se inspecciona contenido y escanea; imágenes sin EXIF/GPS."},
        "nombre_visible": {"type": "string", "maxLength": 160, "description": "Opcional; sin rutas/controles, letras, números, espacios, ._-(); extensión compatible"}}},
}
vocabularios = {
    "Factura": "estado_documental legibilidad orientacion caras requiere_revision tipo_copia integridad_visual soporte idioma calidad_imagen color observacion_tecnica",
    "Informe": "ubicacion_general vista componente condicion tipo_evidencia fase_trabajo iluminacion orientacion equipo_tipo zona_tecnica requiere_revision estado_visual",
}
for tipo, claves in vocabularios.items():
    schemas["Atributos"+tipo] = {"type": "object", "maxProperties": 12, "additionalProperties": False,
        "description": "Máximo 4 KiB JSON UTF-8 compacto. Solo contenido técnico; sin PII, enlaces, HTML, OCR o datos económicos.",
        "properties": {k: {"oneOf": [{"type": "string", "maxLength": 200}, {"type": "boolean"}]} for k in claves.split()}}
editables = {"descripcion": {"type": "string", "maxLength": 1000}, "etiquetas": {"type": "array", "uniqueItems": True, "maxItems": 12, "items": {"type": "string", "minLength": 1, "maxLength": 40}},
    "atributos": {"anyOf": [ref("AtributosFactura"), ref("AtributosInforme")], "description": "Usar exclusivamente el vocabulario correspondiente al tipo SQL del adjunto; vacío permitido."}, "revision": {"type": "integer", "format": "int64", "minimum": 0, "maximum": 9223372036854775806}}
schemas["PatchAnotaciones"] = {"type": "object", "additionalProperties": False, "required": ["revision"], "anyOf": [{"required": [k]} for k in ("descripcion", "etiquetas", "atributos")], "properties": editables}
schemas["Anotaciones"] = {"type": "object", "additionalProperties": False,
    "properties": {**editables, "adjunto_id": {"type": "integer", "format": "int64"}, "tipo": schemas["Adjunto"]["properties"]["tipo"],
        "destino_id": {"type": "integer", "format": "int64"}, "mime": schemas["Adjunto"]["properties"]["mime"],
        "tamano_bytes": {"type": "integer"}, "registrado_en": {"type": "string", "format": "date-time"}, "sincronizado_en": {"type": "string", "format": "date-time"}}}
schemas["Anotaciones"]["required"] = list(schemas["Anotaciones"]["properties"])
schemas["Anotaciones"]["properties"]["revision"] = {**editables["revision"], "maximum": 9223372036854775807}
paths = {}
ident = {"name": "id", "in": "path", "required": True, "schema": {"type": "integer", "format": "int64", "minimum": 1}}
for destino in ("documentos-cobro", "obras"):
    permiso = "AF escribe solo documento VIGENTE; AF/Gerencia leen" if destino == "documentos-cobro" else "Supervisor escribe EN_PROCESO/SUSPENDIDA/FINALIZADA; técnico miembro activo escribe solo EN_PROCESO. Gerencia/Supervisor/miembro activo leen"
    paths["/api/adjuntos/"+destino+"/{id}/"] = {"parameters": [ident],
        "get": {"summary": "Listado SQL (sin depender de Mongo/scanner)", "description": permiso+". Orden registrado_en DESC/id DESC. 25 por página; query desconocida/duplicada inválida.",
            "parameters": [{"name": "page", "in": "query", "schema": {"type": "integer", "minimum": 1, "default": 1}}], "responses": {"200": respuesta(ref("Pagina")), **error}},
        "post": {"summary": "Subir adjunto privado", "description": permiso+". Máximo 10 por destino. Replay idéntico con permisos actuales devuelve 200, incluso con scanner caído; bytes íntegros obligatorios.",
            "parameters": [{"name": "Idempotency-Key", "in": "header", "required": True, "schema": {"type": "string", "format": "uuid"}}],
            "requestBody": {"required": True, "content": {"multipart/form-data": {"schema": ref("Carga")}}},
            "responses": {"201": respuesta(ref("Adjunto"), "Creado tras escaneo y commit SQL"), "200": respuesta(ref("Adjunto"), "Replay idéntico"), **error}}}
paths["/api/adjuntos/{id}/"] = {"parameters": [ident], "get": {"summary": "Detalle SQL privado", "responses": {"200": respuesta(ref("Adjunto")), **error}}}
paths["/api/adjuntos/{id}/descargar/"] = {"parameters": [ident], "get": {"summary": "Descarga autenticada con tamaño/SHA-256 verificados antes de transmitir", "description": "Attachment; no URLs públicas. No necesita Mongo ni scanner. Técnico desasignado pierde acceso.",
    "responses": {"200": {"description": "PDF original o píxeles saneados JPEG/PNG", "headers": {**headers, "Content-Disposition": {"schema": {"type": "string"}}}, "content": {mime: {"schema": {"type": "string", "format": "binary"}} for mime in ("application/pdf", "image/jpeg", "image/png")}}, **error}}}
paths["/api/adjuntos/{id}/anotaciones/"] = {"parameters": [ident],
    "get": {"summary": "Leer notas Mongo tras comprobar SQL", "responses": {"200": respuesta(ref("Anotaciones")), **error}},
    "patch": {"summary": "Actualizar notas con revisión CAS", "description": "AF factura; Supervisor/miembro activo informe (sin requisito de estado de subida). Gerencia solo lectura. Reemplaza solo campos presentes; sin mutar archivo o SQL.",
        "requestBody": {"required": True, "content": {"application/json": {"schema": ref("PatchAnotaciones")}}}, "responses": {"200": respuesta(ref("Anotaciones")), **error}}}
for item in paths.values():
    for method, operation in item.items():
        if method in ("get", "post", "patch"):
            for response in operation["responses"].values():
                response.setdefault("headers", headers)
schema = {"openapi": "3.0.3", "info": {"title": "FYAG SPEC-012B — Adjuntos privados", "version": "1.0.0", "description": "Ocho operaciones. HEAD/OPTIONS autenticados respetan RBAC. Sin acceso TI ni rutas físicas. JWT versionado, actividad y pertenencia SQL en cada operación. Errores saneados y correlación; códigos cubren operaciones según corresponda."},
    "servers": [{"url": "http://localhost:8000"}], "security": [{"JWT": []}], "paths": paths,
    "components": {"securitySchemes": {"JWT": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT versionado"}}, "schemas": schemas}}
(ROOT/"openapi").mkdir(exist_ok=True)
(ROOT/"openapi/SPEC-012B-v1.json").write_text(json.dumps(schema, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
items = []
for ruta, item in paths.items():
    for method, operation in item.items():
        if method not in ("get", "post", "patch"):
            continue
        variable = "documento_id" if "documentos-cobro" in ruta else "obra_id" if "/obras/" in ruta else "adjunto_id"
        request = {"method": method.upper(), "header": [], "url": "{{base_url}}"+ruta.replace("{id}", "{{"+variable+"}}"), "description": operation["summary"]}
        if method == "post":
            request["header"] = [{"key": "Idempotency-Key", "value": "{{idempotency_key}}"}]
            request["body"] = {"mode": "formdata", "formdata": [{"key": "archivo", "type": "file", "src": []}]}
        elif method == "patch":
            request["header"] = [{"key": "Content-Type", "value": "application/json"}]
            request["body"] = {"mode": "raw", "raw": '{"revision":0,"descripcion":"Vista frontal"}'}
        items.append({"name": operation["summary"]+" — "+variable, "request": request})
postman = {"info": {"name": "FYAG SPEC-012B local", "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json", "description": "Seleccionar manualmente archivo real en Body form-data File. Importar no transfiere archivos ni rutas. Token/IDs de QA deben configurarse."},
    "auth": {"type": "bearer", "bearer": [{"key": "token", "value": "{{token}}", "type": "string"}]},
    "variable": [{"key": k, "value": v} for k, v in {"base_url": "http://localhost:8000", "token": "", "obra_id": "", "documento_id": "", "adjunto_id": "", "idempotency_key": ""}.items()], "item": items}
(ROOT/"postman").mkdir(exist_ok=True)
(ROOT/"postman/SPEC-012B.postman_collection.json").write_text(json.dumps(postman, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
