# SPEC-012B — Implementación local de adjuntos privados

## Estado y alcance

Implementación en `feature/backend-012b-adjuntos`, basada en `30213ec` (PR #42).
Sin commits, push, PR ni merge autorizados. El encabezado pendiente de la SPEC
no reemplaza la aprobación del contrato. No incluye frontend, OCR, DTE/SII,
adjuntos de pagos ni cambios económicos. Los resultados ejecutados se registran
al final de este documento; no confundir contrato/CI configurado con evidencia.

## Arquitectura e inventario

`backend/apps/adjuntos/` contiene exclusivamente el nuevo dominio:

| Archivo | Responsabilidad |
|---|---|
| `models.py`, `migrations/0001_initial.py` | Registro inmutable `AdjuntoDocumento`, FK PROTECT, parent exclusivo, CHECKs MIME/tamaño/digest/estado/nombre, UUIDs únicos e índices por destino/fecha/id |
| `permissions.py`, `services.py` | JWT/usuario SQL, RBAC, estados, límite 10, locks, idempotencia y compensación |
| `parsers.py`, `validaciones.py` | Multipart estricto acotado, filename original, nombre seguro, UUID |
| `contenido.py`, `pdf_guard.py` | Pillow, estructura PNG/JPEG/PDF y límites |
| `almacen.py`, `scanner.py` | POSIX privado y protocolo clamd INSTREAM |
| `metadata.py`, `esquema.json` | Proyección técnica BSON, vocabularios independientes y CAS |
| `views.py`, `urls.py` | Ocho operaciones REST, errores saneados y cabeceras privadas |
| `management/commands/` | Reconciliación repetible y diagnóstico sin borrado |
| `tests/` | Integración PostgreSQL/Mongo/clamd y fallos inducidos de QA |

Integración: `config/settings.py`, `config/urls.py`, requisitos runtime (`pypdf==7.0.1`),
`compose.yaml`, `.env.example`, `.github/workflows/backend-ci.yml`,
`database/adjuntos_mongodb.js` y ampliación del bootstrap de usuarios Mongo.
Laboratorio recuperable: `compose.adjuntos-qa.yaml`,
`apps/adjuntos/qa_recuperacion.py` y `database/qa_respaldo_adjuntos.js`.
El runner documental conserva aislamiento QA y añade almacén temporal/scanner QA.
No se modifican modelos/migraciones ni servicios económicos o evidencias existentes.
La migración nueva depende de `finanzas.0001_facturacion_documental` (tabla padre),
no de pagos: conserva el recorrido histórico de migración 0001→0002.

PostgreSQL es autoridad de relaciones/identidad/permisos y características finales;
el volumen privado contiene bytes; Mongo solo anotaciones y espejo técnico mínimo.
No GridFS, bytes en DB, URLs públicas, paths o claves físicas en JSON.

## API y permisos

Contrato importable: [`openapi/SPEC-012B-v1.json`](openapi/SPEC-012B-v1.json).

| Ruta bajo `/api/adjuntos/` | Operaciones |
|---|---|
| `documentos-cobro/{id}/` | POST respaldo / GET listado |
| `obras/{id}/` | POST informe / GET listado |
| `{id}/` | GET detalle SQL |
| `{id}/descargar/` | GET bytes privados |
| `{id}/anotaciones/` | GET / PATCH notas CAS |

POST multipart con exactamente un `archivo`, `nombre_visible` opcional y
`Idempotency-Key` UUID obligatorio. No JSON/base64/rutas remotas, campos extra,
duplicados o archivos múltiples. Tipo/destino vienen exclusivamente de URL.
201 inicial, 200 replay idéntico; misma key/payload distinto 409. La huella incluye
actor, tipo, destino, nombre y hashes original/final; una key no divulga otro actor.
Replay exige permisos actuales e integridad, pero no scanner disponible.
Listados SQL: 25 fijos, `registrado_en DESC,id DESC`, `count/next/previous/results`.
Query desconocida/duplicada inválida; IDs positivos ASCII sin ceros iniciales.

| Rol | Respaldo factura | Informe técnico |
|---|---|---|
| AF | Lee/edita notas; sube solo VIGENTE | Sin acceso |
| Gerencia | Solo lectura | Solo lectura |
| Supervisor | Sin acceso | Lee/edita; sube EN_PROCESO/SUSPENDIDA/FINALIZADA |
| Técnico | Sin acceso | Lee/edita siendo miembro activo; sube solo EN_PROCESO |
| TI, incluso staff/superuser | Sin acceso | Sin acceso |

El técnico desasignado pierde acceso aunque sea autor. Las notas no exigen el
estado de nueva subida; sí rol/actividad/pertenencia. Facturas revertidas conservan
lectura histórica. HEAD/OPTIONS no evitan permisos. JWT se valida por versión y
actividad, y el rol se consulta en SQL, nunca se confía en claims de rol.

Errores: 400 entrada, 401 sesión, 403 rol, 404 recurso/pertenencia, 405 método,
409 estado/límite/idempotencia/CAS/integridad/metadata pendiente, 413 tamaño,
415 medio no admitido, 422 contenido y 503 dependencia no disponible.
Los fallos inesperados no exponen mensajes internos. Logs operativos: actor/ID,
evento, resultado y correlación; no son auditoría inmutable ni confirman que el
cliente guardó la descarga.

## Seguridad de contenido y persistencia

Ver [operación, escaneo y recuperación](SPEC-012B-OPERACION.md).
Imágenes PNG/JPEG <=5 MiB y <=12 millones de píxeles: estructura/CRC/framing,
decodificación Pillow y copia a raster nuevo, sin EXIF/GPS. Hash de bytes finales.
PDF <=8 MiB: pypdf mantenido, estricto, sin reescritura de bytes (incluidas firmas).
Proceso inspector: 256 MiB, CPU 5 s, pared 8 s, 100 páginas, 2.000 referencias,
20.000 nodos, profundidad 64 y 16 MiB de streams decodificados. Rechaza cifrado,
JavaScript, acciones y archivos embebidos; límites provocan rechazo, no aceptación.
No certifica validez criptográfica de firmas. Rechaza ZIP compuesto y bytes fuera
del framing aceptado. No hay promesa de detectar todo formato políglota imaginable.

ClamAV real privado recibe bytes finales por INSTREAM, sin paths ni montaje de
adjuntos; solo respuesta exacta `stream: OK` acepta. Malware: 422; desconexión,
timeout (total 15 s), ERROR o respuesta desconocida: 503. Límites heurísticos
configurados para alertar en vez de saltar contenido. Nunca se ejecuta scanner
ni escritura Mongo dentro de locks SQL. Login/módulos originales/descargas no
dependen del scanner.

`adjuntos_data` separado de `evidencias_data`. Raíz POSIX absoluta fuera de web;
apertura componente a componente con dirfd/O_NOFOLLOW, staging privado exclusivo,
claves UUID aleatorias, archivos 0600 y directorios nuevos 0700. No soporte degradado
en Windows nativo: usar el contenedor Linux. Publicación hardlink no-clobber y
fsync; fila disponible solo tras análisis y publicación. Idempotencia advisory lock
por key y orden Presupuesto → Obra → Documento serializan destino/estado/límite.
La pertenencia se vuelve a consultar bajo lock de Obra, compatible con servicios
vigentes que bloquean esa Obra al asignar/desasignar.

Sin transacción distribuida: SQL rollback retira únicamente publicación propia
si SQL confirma que no está referenciada. Commit ambiguo conserva bytes para
diagnóstico; caída abrupta puede dejar staging/huérfanos, nunca se borran por lote.
Descarga copia a temporal mientras verifica tamaño y SHA-256 antes de FileResponse;
archivo faltante/corrupto/symlink => 409, sin transmitir bytes no verificados.
Cabeceras: attachment, MIME permitido, private/no-store, nosniff, Vary Authorization,
CSP sandbox y X-Correlation-ID.

## MongoDB

Colección independiente `fyag_documentos.adjuntos_metadata`, `_id=adjunto:{id}`,
BSON estricto y máximo 16 KiB. Técnicos desde SQL: adjunto/tipo/destino/MIME/tamaño/
fechas; no nombre visible, hash, contenido, folio, monto ni datos personales.
Descripción 1.000 caracteres; 12 etiquetas de 40; 12 atributos simples por tipo,
4 KiB JSON compacto. Vocabularios en OpenAPI y `metadata.CLAVES`; filtros de texto
conservadores, no un detector perfecto de PII.

CAS obligatorio `revision`; colisión 409. PATCH reemplaza campos presentes y
conserva ausentes. Reconciliador por lotes 200 reinicia PK desde cero en cada pasada,
`$set` técnico y `$setOnInsert` notas. Metadata pendiente 409, Mongo caído 503 solo
notas; POST/listado/descarga continúan. Lecturas no escriben incidentalmente.
Bootstrap autenticado idempotente, preserva notas y credenciales existentes; rol
runtime solo find/insert/update/listIndexes sobre ambas colecciones y listCollections,
sin delete/drop/collMod. No se altera validador/contenido de `documentos_metadata`.

## Frontend y Postman

Ver [guía frontend/Postman](SPEC-012B-FRONTEND-POSTMAN.md). No se implementó frontend.
Los JSON OpenAPI/Postman se regeneran con `python docs/generar_contrato_012b.py`.

## Evidencia de validación local

Ejecutado el **13-11-2026**, Docker Linux, PostgreSQL 18, MongoDB 8 autenticado,
ClamAV **1.5.4** (firmas QA 28178 del 09-11-2026), Python 3.13.18, Django 5.2.19,
Pillow 12.3.0 y pypdf 7.0.1. No se usó scanner simulado para casos positivos/EICAR.

| Comprobación ejecutada | Resultado real |
|---|---|
| `python manage.py check` | Sin problemas |
| `python manage.py makemigrations --check --dry-run` | No changes detected |
| `python manage.py test apps.adjuntos --noinput` | **31 pruebas OK, 12,853 s** |
| Adjuntos + migración histórica de pagos (pasada anterior) | 31 pruebas OK, 14,833 s (30 adjuntos + 1 histórica) |
| Regresión completa anterior al último test de commit ambiguo | **868 pruebas OK, 226,940 s** |
| Regresión completa definitiva `python manage.py test --noinput` | **869 pruebas OK, 227,071 s** (838 anteriores + 31 nuevas) |
| Bootstrap 012B Mongo local repetido | Correcto; colección 012A y credenciales conservadas |
| Build runtime/QA y migración local `adjuntos.0001_initial` | Correctos |
| OpenAPI/Postman | JSON válidos, 8 operaciones/8 requests; referencias/vocabularios comprobados por test |
| `git diff --check` | Sin errores de whitespace (avisos locales LF/CRLF) |
| Transporte privado usado por CI | Prueba local con ClamAV sin red y socket Unix: inocuo OK, EICAR rechazado; sin puertos host |

Cobertura 012B: PDF original e imagen saneada PNG/JPEG, EXIF, 12 millones de
píxeles, límites de bytes, truncados/MIME/nombres/multipart maliciosos, PDF activo/
cifrado/ZIP compuesto; cinco roles, HEAD/OPTIONS, JWT expirado/revocado/inactivo,
IDOR y desasignación; revalidación de estado/pertenencia tras scanner sin locks;
EICAR real directo y dentro de PDF; scanner inaccesible y timeout real de socket;
replay/colisión/concurrencia de misma key y último cupo; CHECKs SQL; fallo de disco,
rollback, commit rechazado y confirmación ambigua conservando bytes/replay;
archivo ausente/corrupto/symlink, no-clobber y diagnóstico sin borrar; BSON estricto,
privilegios mínimos, notas CAS concurrentes, vocabularios, datos sensibles, Mongo
inaccesible/recuperado, commits fuera de orden y aislamiento del validador 012A.

La primera regresión detectó una dependencia innecesaria a pagos en la migración
nueva; se corrigió únicamente esa dependencia y pasó la regresión posterior. Las
primeras pruebas detectaron normalización CR/LF por `BytesParser.parse(file)` y
permisos incompletos de OPTIONS; ambos corregidos y cubiertos antes de entrega.
Fixtures corregidas respetan restricciones existentes; no se relajaron CHECKs.

### Respaldo/restauración/reinicio realmente ejecutados

Laboratorio separado **`fyag012bqa`** con PostgreSQL/Mongo/adjuntos/evidencias propios,
sin puertos host ni acceso a datos locales existentes:

- Preparación: PDF aceptado por scanner, notas revisión 1 y evidencia/proyección 012A.
- `pg_dump -Fc`, `mongodump` autenticado y tar de ambos volúmenes con manifest.
- Restauración a motores y volúmenes **nuevos** del perfil `restore`, sin `--drop`,
  sin borrar el origen. Verificación de descarga/hash, ID, descripción y CAS.
- Reinicio Compose de los seis contenedores origen/restore y nueva verificación de
  ambas apps: manifest idéntico. Reconciliación doble conserva notas y 012A.
- Mongo QA realmente detenido: notas 503, listado/descarga 200; tras arrancar,
  notas/revisión/hash intactos. Scanner QA realmente detenido: nueva carga 503,
  cero filas extra y descarga existente 200. Ambos servicios recuperados.
- Rollback funcional de rutas nuevas: 012B 404 temporal, 012A 200; reactivación sin
  pérdida del manifest. No se ejecutó downgrade destructivo de tablas.
- Diagnóstico del destino restaurado: 1 registro, 0 faltantes/corruptos, 0 huérfanos,
  0 staging. Volúmenes y backups QA se conservan para revisión, no se eliminaron.
- Laboratorio de recuperación y scanner Unix auxiliar detenidos tras verificar,
  con contenedores/volúmenes/backups conservados. Mongo/scanner QA de la suite y
  los servicios normales permanecen disponibles.

No se subieron fixtures a la base de desarrollo: tabla nueva local vacía; directorios
del volumen se inicializan en la primera carga real. SPEC-012A sigue reconciliando
su colección independiente. CI remoto y Postman manual **no ejecutados** en esta
entrega; requieren revisión y publicación/ejecución expresamente autorizadas.

## Riesgos residuales

- Antivirus no garantiza ausencia de amenazas; requiere actualización y monitoreo
  de firmas. QA congela firmas de imagen para reproducibilidad, no para producción.
- No cuarentena pública, eliminación/retención legal ni reparación automática.
- Límite multipart en memoria ~8 MiB+64 KiB por petición, más raster/inspector;
  ajustar concurrencia y límites de ingress/servidor antes de producción.
- Un administrador de host/volumen/SQL puede alterar datos; no es WORM ni auditoría
  inmutable. RPO/RTO dependen del respaldo coordinado.
- Fallos de commit ambiguo conservan huérfanos intencionalmente; requieren decisión
  humana, no limpieza automática.
- CI remoto y selección de archivos Postman deben ejecutarse tras publicación
  expresamente autorizada; no equivalen a pruebas locales.
