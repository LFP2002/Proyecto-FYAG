# SPEC-012B — Implementación local de adjuntos privados

> **Aclaración pre-merge PR #44, 17-11-2026:** se conserva el informe histórico inferior. Estado contractual actual en SPEC-012B §12: AF edita notas de factura solo VIGENTE; REVERTIDO conserva lecturas y rechaza PATCH con 409 `documento_no_vigente` sin cambiar BSON/CAS. Informes técnicos no cambian. Se revalida SQL al autorizar y antes del CAS, fuera de transacciones SQL; no se promete atomicidad distribuida frente a reversión solapada tras la última comprobación. Replay idéntico previo no crea una carga y conserva 200. La evidencia histórica inferior no certifica esta corrección; resultados nuevos se añaden tras ejecutar QA.

### Evidencia nueva pre-merge — 17-11-2026

- HEAD local inicial y sin mover: `e4113419f5b97b1d0aaffb08debf28b335338534`; referencia remota `efa33327eca2285496d871f482660867926ea2e9`. Se conservaron en el working tree los cuatro archivos de esa diferencia remota; no se ejecutó merge/rebase ni se crearon commits.
- Laboratorio real `fyag-pr44-qa-20261117a`, únicamente `compose.premerge-qa.yaml`: PostgreSQL 18/Mongo 8 autenticado en tmpfs, ClamAV 1.5.4 con firmas 28178 del 09-11-2026, backend Python 3.13.18/Django 5.2.19. Docker inspect verificó red interna exclusiva, sin puertos host, volúmenes persistentes ni mounts de datos FYAG; solo código/esquemas read-only.
- `python manage.py check`: sin incidencias; `makemigrations --check --dry-run`: No changes detected. No se modifican modelos/migraciones ni servicios financieros.
- Primera pasada relevante `test apps.adjuntos apps.finanzas --noinput`: **112 pruebas OK, 43.489 s**. Incluye nuevas pruebas de VIGENTE/REVERTIDO, lectura histórica, BSON/revisión intactos, 401/403/404 y reversión SQL real entre autorización y CAS. El hook de intercalado controla el momento de la reversión; no simula Mongo ni el servicio financiero y no prueba atomicidad distribuida.
- Primera suite completa: **872 pruebas OK, 224.366 s**, antes de agregar una regresión adicional de edición de informes en estados terminales/planificado. La validación final de esa prueba se registra por separado, no se atribuye a esta primera pasada.
- Repetición con la nueva regresión: **873 pruebas, 1 error de fixture, 213.626 s**. La instancia en memoria de Obra conservaba `iniciado_en=null` después de prepararla mediante otro objeto; el CHECK SQL de coherencia rechazó SUSPENDIDA. Se corrigió exclusivamente la fixture mediante `refresh_from_db()`, sin relajar restricciones ni modificar producción.
- Suite relevante final tras corregir fixture: **113 pruebas OK, 46.793 s**; incluye edición de informes por Supervisor/Técnico en SUSPENDIDA/FINALIZADA/CANCELADA/PLANIFICADA con revisión CAS incremental, sin conceder nuevas cargas.
- Suite backend completa definitiva `test --noinput`: **873 pruebas OK, 232.186 s** (869 de referencia + 4 nuevas). Motores QA reales, incluyendo ClamAV/EICAR, CAS, finanzas, autenticación, Obras/turnos/evidencias/costos, auditoría, Dashboard, Alertas y exportaciones CSV/XLSX/PDF; no equivale a recorrido de navegador.
- Frontend final `npm test`: **204 aprobadas, 0 fallos/canceladas/omitidas, 2862.4925 ms** (Node 24.18.0/npm 12.0.2). Incluye 200 pruebas de la referencia remota y 4 nuevas sobre proxy/split-origin, enlaces maliciosos y navegación adelante/atrás con filtros de Cobranzas/Reportes/012A. Respuestas sintéticas, no integración navegador/API.
- `npm run build`: **OK**, Vite 6.4.5, 99 módulos, **2.01 s**. JS 370.59 kB (gzip 108.16), CSS 253.95 kB (gzip 35.41). `npm ci` ejecutado; npm informó postinstall de esbuild bloqueado por política local, sin impedir tests ni build; no se relajó esa política.
- Primera ejecución de la nueva prueba UI de paginación: 203/204 por aserción que confundía cartera con `/resumen/`; corregida seleccionando pathname exacto. Fixtures ajustadas a una factura vigente por Obra; no se cambiaron tests previos para ocultar errores.
- `npm audit --json` y `npm audit`: **4 altas, salida 1**; `npm audit --omit=dev`: **0, salida 0**. Causa única picomatch/ReDoS GHSA-fc5q-39xc-vjpf, sin versión corregida publicada al consultar. Árbol, versiones/exposición y motivo para no degradar Vite en SPEC-014, sección pre-merge. package.json/lock sin cambios; no se ejecutó audit fix/force.
- `git diff --check`: sin errores de whitespace (advertencias locales LF/CRLF). OpenAPI regenerado desde el generador; Postman no cambió. Las SPEC solo reciben aclaraciones adicionales respecto de la referencia remota; no se borran sus antecedentes.
- **PENDIENTE crítico:** recorrido React/API real, cookies/CORS HTTPS split-origin, descargas desde navegador y revisión visual 375/768/1280 px. Procedimiento exacto en `SPEC-012B-OPERACION.md`. Las pruebas backend reales incluyen dominios y exportaciones, pero no sustituyen ese recorrido manual. Dependencias dev altas siguen abiertas. **No listo para merge.**
- Sin commit/push/merge/rebase/PR nuevo, sin cambios a main ni datos FYAG existentes; las únicas escrituras de prueba son fixtures en motores QA nuevos y archivos temporales.
- Laboratorio propio detenido al terminar mediante `docker compose ... -p fyag-pr44-qa-20261117a stop`, sin down/prune ni borrado de volúmenes. Los tmpfs QA son efímeros; servicios FYAG originales no se detuvieron ni recrearon. Configuración secreta temporal permanece fuera del repositorio; no se imprime ni versiona.

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

### Revalidación final reconciliada PR #44 (17-11-2026)

Rama `feature/frontend-005c-integracion-modulos`: HEAD actualizado por
fast-forward protegido de `e4113419f5b97b1d0aaffb08debf28b335338534` a
`efa33327eca2285496d871f482660867926ea2e9` (cuatro commits; fetch realizado).
El árbol ya contenía esos commits: no se reescribieron/reaplicaron archivos.
Comparación SHA-256 de todo el árbol y patch contra remoto antes/después idénticos;
staging vacío y main conservado en `567d8aebdf95ef2f78aaf55a31857669bcf1f185`.
Adjuntos.jsx, FinanceDocument.jsx y su test coinciden con remoto; SPEC-014 conserva
el contenido remoto como prefijo. Respaldo recuperable externo conservado:
`C:\Users\jugue\AppData\Local\Temp\opencode\fyag-pr44-backup-20261117-181222`
(19 archivos locales, índice, patches, bundle e inventario SHA-256 verificados).

| Comprobación posterior a reconciliación | Resultado |
| --- | --- |
| `npm ci` | 71 instalados/72 auditados; lock sin cambios; aviso esbuild postinstall bloqueado por política local |
| `npm test` | **204/204**, cero fallos, **3397,2057 ms** |
| `npm run build` | **OK**, Vite 6.4.5, 99 módulos, **1,74 s** |
| Inventario Rollup externo | 92 módulos runtime, cero módulos Vite/picomatch/fdir/tinyglobby; build adicional 1,24 s |
| `npm audit` | **4 high**, salida 1; vulnerabilidad abierta, no corregida |
| `npm audit --omit=dev` | **0**, salida 0 |
| Django `check` | Sin problemas |
| `makemigrations --check --dry-run` | No changes detected |
| Suite backend completa | **874 pruebas OK, 244,157 s**; 873 anteriores + una prueba concurrente nueva |

Laboratorio independiente `fyag-pr44-final-20261117`: PostgreSQL/Mongo con tmpfs,
scanner propio, red interna, sin volúmenes FYAG ni puertos host de motores.
La suite terminó antes de sembrar datos para navegador. La prueba nueva acredita
la ventana posterior a la tercera autorización (SPEC-012B §12), no atomicidad
distribuida. Finanzas no fue modificado. No se ejecutó commit/push/merge ni se
modificó main. Los antecedentes de otras ejecuciones se conservan.

**Navegador real y dictamen:** recorrido Edge/CDP en QA HTTP loopback ejecutado,
matriz detallada/evidencia y pasos manuales en SPEC-012B-OPERACION §«Ejecución
real de navegador de cierre». Cinco roles con sesión real, paginación G/AF,
pago AF por formulario (201), históricos/CAS/PDF/PNG por fetch autenticado,
CSRF negativo403, Mongo/scanner realmente detenidos (503 aislados) y offline UI.
Sin excepciones JS; errores de red negativos esperados registrados.

**NO APTO para merge**: picomatch sigue vulnerable sin aceptación de riesgo;
Usuarios TI desborda a375/a768 (scrollWidth929/933); falta HTTPS split-origin;
descarga por botones de exportación solo acreditó HTTP200, no entrega al disco;
resta recorrido operativo completo y todas las pantallas/paginaciones por UI.
La navegación TI fallida del primer runner era un selector erróneo y se confirmó
posteriormente; los dos desbordes sí son fallos de producto y no se ocultaron.
Los ficheros CSV/XLSX/PDF obtenidos por fetch auxiliar sí se guardaron/parsearon,
sin confundir eso con aprobación de sus botones o revisión visual en Excel.
También debe acordarse expresamente la garantía SQL/Mongo documentada antes de
exigir un orden global absoluto. No se amplió el contrato para aparentar cumplirlo.

### Actualización del seguimiento funcional tras reanudación (17-11-2026)

El dictamen anterior se conserva como histórico. **Se resolvieron Usuarios TI y
la entrega real de descargas**: regiones accesibles de scroll local, estilos solo
en Usuarios, regresión CDP versionable a375/768/1280, cinco archivos recibidos por
botones con eventos Browser completed y parsing. No hubo cambios en Table/layout
compartidos ni en la lógica de descarga React. Se amplió la evidencia UI de TI,
turnos/fotos/revisión, gastos/costos, documentos/pagos/anulación/reversión/cierre
sin cobro y CAS de dos pestañas. La matriz completa distingue lecturas, escrituras,
fetch auxiliar, fallos inyectados y pendientes en SPEC-012B-OPERACION.

Tras reiniciar Docker los tmpfs estaban vacíos. Se verificó aislamiento y se
reconstruyó solo el laboratorio mínimo para pendientes, sin repetir operaciones
financieras ni cambios de cuentas ya confirmados. UI de reanudación: página2 TI,
relevo S200, Técnico404 sin ficha retenida, revalidación de nueva versión y cierre
operativo S200. Scanner detenido y Mongo pausado provocaron503 desde botones,
manteniendo descargas200; unpause conservó revisión0. Ningún motor FYAG ajeno
fue utilizado o detenido.

Última validación frontend: **204/204,3602.6882ms**, build **1.90s**; audit completo
**4high/salida1**, runtime **0/salida0**. Inventario actual:92módulos runtime,
ninguno de tooling afectado. Backend check y dry-run actuales limpios. El backend
runtime/tests sigue byte a byte igual al de **874OK/244.157s**; no se reejecutó la
suite completa sobre el Mongo de fixtures navegador ni se atribuye una nueva
ejecución. Package/lock permanecen sin cambios.

**NO APTO continúa**: falta decisión formal de riesgo picomatch, HTTPS sin
excepción de certificado y el recorrido integral/paginaciones/variantes UI aún
parciales. HTTPS same-site funcional sí pasó, con cookies Secure/HttpOnly/Strict y
CORS explícito; la excepción SPKI y ERR_CERT_AUTHORITY_INVALID están registrados,
no son confianza TLS validada. No se declara una vulnerabilidad solucionada.

### Cierre dirigido posterior del recorrido pendiente

Se completó por UI un flujo nuevo Cliente#2 → PRE-000002 y aprobaciones →
OB-000002/participante → turno#2 y foto → revisión/gasto/costos → finalización →
documento externo folio441117212424 → pago5.00 → cartera/reporte saldo11895.00.
Journal externo:13pasos,36medidas responsive y un solo POST de documento/pago.
Se agregaron11combinaciones dirigidas (página2 Presupuestos/Obras/Reportes,
auditoría cursor/filtros,409 presupuesto utilizado,012A edición/relectura,
cortesía S, catálogo G y lectura restringida S) con21medidas responsive más.
No se repitieron operaciones históricas ni se atribuyeron fixtures a acciones UI.

No cambió código productivo: se conservan los resultados automáticos previos
solo si sus hashes/commit coinciden. Auditoría npm repetida:4high y runtime0,
sin parche oficial ni cambios de lock. Riesgo formal preparado para decisión en
SPEC-014, todavía no aprobado. Edge nuevo sin flags de excepción confirma
ERR_CERT_AUTHORITY_INVALID en la cadena autofirmada; se documentaron CA/SAN,
almacenes consultados y pasos concretos para intervención autorizada del operador.
No se instaló ninguna raíz. La matriz y el dictamen más recientes están en
SPEC-012B-OPERACION §«Cierre dirigido del recorrido UI pendiente»: **NO APTO**
hasta TLS confiable y decisión expresa de riesgo. PR permanece sin publicación.

### Autorización posterior para publicar el PR Draft (17-11-2026)

El responsable aceptó temporalmente GHSA-fc5q-39xc-vjpf/CVE-2026-112366 **solo en
desarrollo y QA**, con revisión semanal, riesgo residual vigente y caducidad
propuesta de30días (17-12-2026) sujeta a nueva evaluación. El registro formal de
SPEC-014 cita la autorización conversacional, sin inventar firma ni ticket;
las4alertas siguen visibles y la vulnerabilidad no se declara solucionada.

No se autoriza instalar CA raíz, modificar confianza Windows o desactivar TLS.
Validar HTTPS con cadena confiable permanece como requisito de despliegue, no
como aprobación derivada del QA funcional/SPKI. No se cambia configuración TLS.

Se autoriza commit y push normal exclusivamente a la rama del PR#44 existente,
manteniéndolo Draft. Las conclusiones anteriores de NO APTO para merge/despliegue
no prohíben esta publicación limitada para auditoría. No se autorizan merge,
push a main, force push, eliminar ramas, crear otro PR o convertirlo a Ready.

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

### Validación repetida antes del commit autorizado

En QA exclusivo `fyag-pr44-publish-20261117`, sin puertos host y con PostgreSQL y
Mongo en tmpfs: Django check limpio, dry-run sin cambios, migraciones aplicadas
solo al laboratorio nuevo y migrate --check OK; **874 pruebas backend OK en
222.740 s**. Frontend: npm ci OK sin cambio de lock, **204/204 pruebas OK en
3697.3954 ms** y build OK en **2.03 s** (99 módulos). Audit runtime: **0**;
audit completo: exactamente **4 high/salida 1** de la cadena picomatch autorizada,
sin hallazgos nuevos. Detalle en el acta final de operación. No se modifica
confianza TLS ni se equiparan pruebas locales con aprobación de CI o producción.
