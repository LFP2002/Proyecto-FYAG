# SPEC-012A — Integración MongoDB documental

## Estado, base y alcance

Implementación local en `feature/backend-012a-mongodb`, iniciada limpia y sin
diferencias con `origin/main` en `beb9b69aaabb211849304814ecbd5a00a595e5ea`
(PR #39). Leída íntegramente la SPEC revisada `specs/012-integracion-mongodb.md`.
No se implementa 012B, frontend, OCR, documentos tributarios, cloud, GridFS ni
réplicas de Auditoría/Alertas. No se modifican modelos, migraciones o reglas
económicas. Flujos de cierre/subsanación y descarga privada de Obras intactos.
Al cerrar la validación local no se habían realizado commits, push, PR ni merge.
Posteriormente el responsable autorizó publicar commits y abrir un PR en borrador
exclusivamente para revisión técnica; no autoriza merge ni operaciones adicionales
sobre datos o credenciales. La evidencia de CI remoto se comunica en ese PR.

Guía operativa: [database/README.md](../../database/README.md).
Contrato: [OpenAPI 3.1 SPEC-012](openapi/SPEC-012-v1.json).

## Arquitectura y archivos

Nuevo módulo `backend/apps/documentos/` sin modelos SQL:

| Archivo | Responsabilidad |
| --- | --- |
| `apps.py`, `__init__.py` | Registro del módulo, sin conexiones al importar |
| `esquema.json` | Fuente canónica BSON v1 compartida con mongosh |
| `mongo.py` | Cliente por PID/configuración, pool, timeout, cierre y diagnóstico estructural |
| `permissions.py` | Roles permitidos y relectura persistida de sesión |
| `validaciones.py` | IDs/query, normalización, vocabulario documental y límites |
| `parsers.py` | JSON UTF-8 estricto, claves duplicadas y tamaño de entrada |
| `services.py` | Autoridad SQL, proyección técnica, lectura segura y CAS de anotaciones |
| `exceptions.py` | 409 pendiente/obsoleta y 503 saneado |
| `views.py`, `urls.py` | Las tres operaciones REST, HEAD/OPTIONS y privacidad |
| `testing.py` | Runner que exige Mongo QA separado, nunca usa desarrollo |
| `management/commands/verificar_mongodb.py` | Diagnóstico autenticado sin secretos |
| `management/commands/reconciliar_documentos_mongodb.py` | Barrido completo recuperable, modo único/continuo |
| `tests/base.py`, `tests/test_api.py`, `tests/test_operacion.py` | Fixtures SQL, fotos por API/servicios reales, BSON, concurrencia y rendimiento |
| `management/__init__.py`, `management/commands/__init__.py`, `tests/__init__.py` | Paquetes Python |

Cambios externos necesarios:

- `backend/config/settings.py`: registra app, configuración Mongo perezosa y
  runner de tests separado; logger INFO documental específico, sin alterar el
  nivel de los módulos preexistentes.
- `backend/config/urls.py`: include de `/api/documentos-metadata/`.
- `backend/requirements.txt`: fija PyMongo ya existente a 4.20.0. No biblioteca
  nueva ni ORM Mongo; Django sigue usando exclusivamente PostgreSQL.
- `compose.yaml`: auth/localhost/health/bootstrap Mongo, QA tmpfs y worker propio;
  retira dependencia Mongo del arranque del backend y evita pasar root de
  desarrollo a procesos Django. No toca volúmenes de otros proyectos.
- `.env.example`: nombres de variables y passwords vacíos; `.env` local ignorado
  fue actualizado con claves nuevas aleatorias, sin imprimirlas ni versionarlas.
- `.github/workflows/backend-ci.yml`: paths de database, Mongo efímero autenticado,
  secretos generados/enmascarados y bootstrap doble, antes de suite completa.
- `database/{init_mongodb.js,indices_mongodb.js,validaciones_mongodb.js}`: conserva
  nombres/rutas existentes, reemplaza esquema preliminar y elimina activación de
  colecciones de Auditoría/Alertas. Colecciones viejas no se borran automáticamente.
- `database/usuarios_mongodb.js`, `database/health_mongodb.js`, `database/README.md`.
- Este informe y OpenAPI. El README de database constituye la sección técnica
  de operación de MongoDB, sin duplicar instrucciones contradictorias en la raíz.

## Fuente documental y proyección

Colección `fyag_documentos.documentos_metadata` (QA: `fyag_documentos_test`).
`_id="evidencia_turno:{id}"`. Campos técnicos derivados de SQL exclusivamente:
`version_esquema=1`, `origen=EVIDENCIA_TURNO`, `evidencia_id`, `obra_id`, `turno_id`,
`tipo_mime`, `tamano_bytes`, `sha256`, `creado_en`, `sincronizado_en`. Los IDs/tamaño
se escriben explícitamente como Int64, fechas BSON UTC con precisión milisegundo.
No se consulta ni copia `nombre_interno`, rutas, bytes, descripción laboral,
tarifas ni datos financieros. Hash técnico permanece interno.

Mongo es autoridad solo de `descripcion`, `etiquetas`, `atributos`, `revision`,
`anotado_en`, `anotado_por_id`. Defaults de inserción: texto vacío, lista vacía,
objeto vacío, revisión 0 y ambos campos de anotación null. Actualizaciones de
anotación incrementan revisión y fijan fecha/actor persistido.

Sincronizar usa `$set` solo técnico y `$setOnInsert` para anotaciones. Dos
inserciones simultáneas toleran DuplicateKeyError refrescando solo el espejo.
No hay borrado ni reinicialización de anotaciones por reconciliación/reinicio.
No se modifica `_id`; no se reciben operadores ni IDs BSON desde el cliente.

### Recuperación

Worker independiente de 60 s, lotes 200, sin side effects en AppConfig/runserver.
Comando de una pasada por defecto y `--continuo --intervalo=1..3600`; SIGTERM/SIGINT
detienen y cierran PyMongo, conexión SQL reciclada entre ciclos. Backoff 1-60 s en
fallos Mongo; modo único falla explícitamente con estado/cantidad confirmada.

Cada ciclo reinicia el barrido en PK 0; el cursor por PK solo sirve dentro de
esa pasada. No existe checkpoint que descarte evidencias con commit tardío y PK
menor. Interrupción o commit fuera de orden se recupera en el siguiente ciclo.
Prueba real mantiene una inserción baja sin commit, confirma otra alta, reconcilia,
confirma la baja y vuelve a reconciliar: ambas están presentes, sin perder notas.

No se cambiaron servicios de turnos ni se incorporaron callbacks remotos al
negocio. La fotografía registrada genera la ficha en el próximo ciclo exitoso;
no hay garantía de proyección inmediata. Un servicio rechaza Mongo si detecta
atomic SQL exterior o autocommit deshabilitado, para no operar remotamente
mientras el caller mantiene bloqueos transaccionales SQL.

## Seguridad y configuración

Identidades separadas root/bootstrap y aplicación. Rol de aplicación custom:
find/insert/update/listIndexes de una sola colección + listCollections para
verificar el esquema de esa DB; sin delete, administración, collMod, creación de
índices ni escritura en otras colecciones. AuthSource explícito. Se comprobaron
rechazo anónimo, credenciales inválidas y operaciones privilegiadas denegadas.

Cliente PyMongo perezoso reutilizado por proceso/configuración, PID en clave,
pool máximo10, mínimo0; selección/conexión/socket/operación/espera de pool2000ms,
retryWrites deshabilitado (Mongo standalone) y cierre explícito/atexit. No ping por
petición de negocio; los endpoints documentales sí verifican colección, validador
e índice antes de operar. No se llama Mongo al iniciar Django ni migraciones.
Configuración de puerto inválida se trata al acceder al módulo, no al importar
settings: el backend SQL no cae por ese valor. No se aceptan URIs/cloud en host.

Mongo publica puerto únicamente sobre localhost; tráfico app por red Docker.
Healthcheck autentica como aplicación, hace ping y lectura autorizada. Bootstrap
de nueva instalación y ruta explícita de volumen previamente inicializado están
documentados por separado. No se asume que añadir root a Compose cree usuarios
en un volumen antiguo. Con datos incompatibles, bootstrap se detiene sin borrar.

### Autenticación API y privacidad

GERENCIA y SUPERVISOR_OBRAS consultan/editan todas las evidencias SQL autorizadas
por esa matriz. TECNICO, ADMINISTRATIVO_FINANZAS y ADMINISTRADOR_TI reciben403.
Se revalida usuario real, actividad, rol, versión y token contra PostgreSQL, sin
bypass por staff/superuser/claims. Servicios repiten relectura antes de Mongo.
Se comprueba evidencia existente y coincidencia `evidencia.obra_id=turno.obra_id`;
el listado confirma la Obra antes de Mongo. Los permisos originales de fotos de
Obras quedan intactos, incluidos técnicos participantes y su ámbito.

Headers privados no-store, Vary Authorization, nosniff y UUID de correlación.
Proyección pública cerrada sin `_id`, hash, ruta, nombre interno, fecha/actor de
anotación privados ni URL de archivos. Logs JSON de anotaciones solo contienen
actor ID, evidencia ID, revisión, resultado y correlación; no valores de texto.
Reconciliador informa cantidad/resultado, no hashes ni contenidos. Los logs no
se presentan como Auditoría inmutable/persistente.

## Validación documental

- `descripcion`: string de0-1000caracteres; NFKC, trim y blancos colapsados.
- `etiquetas`:0-12strings de1-40, letras/números/espacio/_/-, NFKC y casefold;
  rechaza duplicados normalizados, ordena lexicográficamente.
- `atributos`:0-12pares planos, strings hasta200 o booleanos exactos; nunca null,
  números, arrays, binarios u objetos anidados. JSON UTF-8 compacto
  ensure_ascii=false/separadores coma-dos puntos <=4096bytes.
- Vocabulario de claves cerrado para concretar el dominio acotado/auditado de
  la SPEC: `ubicacion_general`, `vista`, `componente`, `condicion`, `tipo_evidencia`,
  `fase_trabajo`, `iluminacion`, `orientacion`, `equipo_tipo`, `zona_tecnica`,
  `requiere_revision`, `estado_visual`. Todas cumplen el patrón ASCII contractual;
  no claves libres para introducir nombres, datos financieros, operadores o PII.
- Textos rechazan controles/zero-width, HTML, patrones de email/RUT, URLs/paths,
  tokens, credenciales, base64 largo y términos financieros sensibles. Reglas
  conservadoras, no un clasificador semántico infalible de PII/nombres humanos.
  Uso exclusivamente técnico y revisión humana siguen siendo obligatorios.
- Documento BSON total <=16KiB. Validador strict/error, campos requeridos,
  additionalProperties=false, tipos BSON y coherencia del ID/revisión/anotación.
  Campo atributos BSON <=4KiB como defensa adicional; el límite JSON exacto se
  aplica además en Python. BSON leído se valida de nuevo y compara con SQL.
- JSON de entrada <=32KiB, UTF-8, objeto, sin duplicados en ningún nivel ni NaN;
  revisión int exacta0..BIGINT-1. Campos presentes reemplazan completos,
  ausentes se conservan. No se construyen filtros u operadores desde el body.

## API e integración frontend

```http
GET /api/documentos-metadata/?obra=8&page=1
GET /api/documentos-metadata/evidencias/123/
PATCH /api/documentos-metadata/evidencias/123/
Authorization: Bearer <JWT>
Content-Type: application/json

{"revision":0,"descripcion":"Estado inicial del equipo","etiquetas":["antes"],"atributos":{"vista":"frontal","requiere_revision":true}}
```

Fila de respuesta sintética (no datos locales):

```json
{"evidencia_id":123,"obra_id":8,"turno_id":29,"tipo_mime":"image/png","tamano_bytes":2048,"creado_en":"2026-11-12T21:00:00+00:00","descripcion":"Estado inicial del equipo","etiquetas":["antes"],"atributos":{"requiere_revision":true,"vista":"frontal"},"revision":1,"sincronizado_en":"2026-11-12T21:01:00+00:00"}
```

Listado: `count,next,previous,results,proyeccion="EVENTUAL",fuente_autoritativa=
"POSTGRESQL"`. Tamaño25, orden creado_en DESC/evidencia_id DESC. Cuenta solo fichas
ya proyectadas verificadas por SQL, no fotos pendientes. No materializa todas las
fichas en memoria: cursor Mongo y lotes SQL de200, conserva solo25 resultados.
Para no autorizar por BSON ni contar huérfanos recorre candidatos completos de
esa Obra; costo O(N) documentado, sin N+1. Un huérfano/corrupción devuelve503, no
datos parciales engañosos. No hay snapshot distribuido entre bases.

`obra` obligatorio y `page` opcional, enteros positivos ASCII sin ceros iniciales
ni overflow, signos/exponentes. Rechaza query desconocida/repetida/vacía,
incluido format. Página fuera de rango400; sin documentos página1 válida.
Detalle/PATCH no admiten query; no usar revision en URL.

200real;400validación o Content-Type incompatible;401sesión;403rol;
404recurso SQL genérico;405método;409`metadata_pendiente_sincronizacion` o
`revision_obsoleta`;503`documentos_no_disponibles`. HEAD/OPTIONS autenticados y
con RBAC. No Retry-After fijo si no se conoce el tiempo de recuperación.
Detalle/PATCH pendiente no efectúa escritura incidental; esperar/reconciliar y
reintentar. Mongo caído nunca retorna un éxito vacío.

El frontend debe mantener revision de GET, enviar PATCH solo con campos a
reemplazar y resolver409 recargando/mostrando conflicto; no reintentar revision
vieja silenciosamente. Usar JWT en header, no URLs ni acceso directo a Mongo.
IDs BIGINT pueden exceder Number.MAX_SAFE_INTEGER: parser JSON sin pérdida en
clientes JS; no cambiar contrato backend a strings sin nueva revisión. Escapar
siempre textos al renderizar, aunque estén normalizados. Fotos se descargan por
su API original autorizada, no desde estos metadatos.

## Pruebas y evidencia real

QA usa Mongo8.0 autenticado tmpfs separado `mongodb_test`, DB
`fyag_documentos_test` e identidades QA distintas; PostgreSQL usa test_fyag_db.
No fixtures en desarrollo. Runner falla si falta QA en lugar de usar Mongo de
desarrollo o saltar pruebas. No ejecutar suites paralelas sobre la colección QA.

| Verificación | Resultado |
| --- | --- |
| Suite documental final disponible | 31 Passed,0Failed,10,787s |
| Regresión anterior al último endurecimiento del cliente y prueba OpenAPI | 837 Passed,0Failed,205,159s |
| Regresión completa final | 838 Passed,0Failed,204,003s; base de pruebas retirada |
| `manage.py check` | Sin incidencias |
| `makemigrations --check --dry-run` | No changes detected |
| `migrate --plan` | No planned migration operations |
| Compose --profile test config --quiet | Exit0 |
| `pip check` | No broken requirements found |
| `verificar_mongodb` con aplicación | Autenticación/esquema/índice correctos |
| Bootstrap autenticado repetido en volumen existente | Dos ejecuciones correctas, sin borrado |
| Construcción/arranque Compose | Correctos, incluido QA efímero |
| Revisión de Git/secretos | 34 archivos; diff --check correcto, siete valores secretos locales cotejados sin mostrarlos, cero coincidencias |

Cobertura: BSON/Int64/fechas/persistencia, edición/reposición parcial/normalización,
roles5/HEAD/OPTIONS/flags/claims/sesiones, errores400-503, filtros/paginación,
JSON duplicado/operadores/HTML/sensibles, índice/validador alterado/BSON corrupto,
denegación anónima y privilegios, reconciliación repetida/concurrente, dos PATCH
simultáneos (un200/un409), rollback SQL, commit fuera de orden, conexión rechazada,
conservación de anotaciones y ausencia de SQL lazy al renderizar la respuesta.

Prueba real de caída operacional: se detuvo **solo** el Mongo de desarrollo, no
QA. Ocho solicitudes HTTP reales autenticadas al backend: auth/me, Obras,
Finanzas/documentos, Auditoría/eventos, Alertas, Dashboard/resumen y
Reportes/catálogo devolvieron200; Documentos devolvió503. Mongo se reinició y el
diagnóstico autenticado volvió a pasar. Suite QA adicional prueba login real,
lectura financiera y cierre/subsanación con fotos mientras la conexión Mongo es
rechazada y recupera luego las tres evidencias mediante reconciliación.

Problemas encontrados y corregidos: fixture de orden que no contemplaba el reloj
simulado del cierre; ruta de Auditoría incorrecta en el test de independencia.
No eran fallos económicos. Se endureció la configuración para que puerto Mongo
inválido no impidiera iniciar Django, y se separaron secretos root de procesos
Django. También se vacía la referencia al cliente cerrado antes de validar una
configuración nueva, con prueba de recuperación al volver a la configuración
anterior. OpenAPI probado por referencias, proyección y vocabulario canónico.
No se declara CI remoto/Postman aprobado: aún no hay publicación.

### Perfil local 1.000 fichas

Suite específica final: reconciliación0,3490s; listado25filas/count1000 en0,1755s;
9consultas SQL; pico Python tracemalloc686.847B. Explain Mongo: índice
`documentos_obra_creacion_evidencia`, sin SORT bloqueante;1000claves y1000documentos
examinados, execution1ms. El escaneo completo permite validar pertenencia SQL de
todos los candidatos. No es SLA ni mide RSS completo/disco/red de producción.
No se creó índice por etiquetas sin una consulta que lo justifique.

## Dependencias

PyMongo ya existía: fijado4.20.0, Python>=3.11, Apache-2.0. Verificado sobre
Python3.13.18/Mongo8.0.34/PostgreSQL18.6. PyPI/OSV consultados por versión: sin avisos
conocidos devueltos para4.20.0, no garantía absoluta de ausencia de vulnerabilidades.
No nuevos motores/servicios cloud/bibliotecas runtime. Docker reconstruido con
pip check correcto. Resto de dependencias conserva el alcance previo.

## Inventario local, respaldos y limpieza

Contexto Docker `desktop-linux`, Compose `proyecto-fyag` y carpeta de este repo.
Contenedores originales: fyag_backend,fyag_postgres,fyag_mongodb y reconciliador
Alertas. Volúmenes reales verificados: `proyecto-fyag_postgres_data`,
`proyecto-fyag_mongodb_data`, `proyecto-fyag_evidencias_data`; Mongo también tenía
volumen anónimo de configdb. No se elimina ninguno.

Estado inicial:0EvidenciaTurno,0archivos privados,30cuentas (incluidos roles
administrativos),6clientes,9presupuestos,6obras,5turnos,5documentos de cobro y5pagos
de pruebas. Mongo solo contenía admin/config/local internos, sin colecciones de
aplicación. No se encontraron fotografías ni datos ajenos identificados.

Respaldo privado fuera de Git creado antes del endurecimiento:
`%LOCALAPPDATA%/Temp/opencode/fyag-012a-respaldo-20261112-210112/` con ACL Windows
restringida al usuario actual, dump PostgreSQL custom227.527B, archiveMongo594B y
manifiesto SHA256. pg_restore --list y mongorestore --dryRun correctos; además
restauración PostgreSQL completa --exit-on-error en DB temporal separada,
30cuentas verificadas, y eliminación únicamente de esa DB de comprobación.
El manifiesto privado incluye hashes; no se publica contenido/datos de backups.

**Plan de limpieza limitado:** solo tablas de negocio de Comercial/Obras/Finanzas
y proyección Alertas de pruebas, en una transacción de mantenimiento; preservar
usuarios/hash/roles, su historial de seguridad, sesiones/tokens/blacklist,
catálogos y eventos de categorías, auth/permisos/contenttypes y django_migrations.
No se eliminan cuentas ni se inventan contraseñas o elevan flags. Conservar
credenciales evita bloquear al responsable; no borrar blacklist de sesiones.
No eliminar colección documental ni identidades Mongo: está vacía en desarrollo.
Detener writers del Compose y exigir cero evidencias/archivos y respaldo válido.
Si aparece recurso compartido, dato no clasificado o foto: detener limpieza.

Lista cerrada de las23tablas del plan (sin CASCADE ni selección por prefijo):

```text
alertas_alerta
alertas_alertaevento
alertas_estadoreconciliacion
comercial_cliente
comercial_presupuesto
comercial_presupuestoevento
comercial_presupuestoitem
finanzas_cierresincobro
finanzas_documentocobro
finanzas_finanzasevento
finanzas_pagodocumento
obras_cierrecostosobra
obras_controlcostosobra
obras_cortesiaobra
obras_costoobraevento
obras_evidenciaturno
obras_gastoobra
obras_obra
obras_obraevento
obras_obraparticipante
obras_obraparticipanteevento
obras_turnoobra
obras_turnoobraevento
```

**Ejecución de limpieza:** completada el12-11-2026 a21:21local, DESPUÉS del OK de
las838pruebas finales. Procedimiento manual fuera de Git, con argumentos
`--pruebas-finalizadas --confirmo-fyag-local`, guardas contra CI, verificación del
contexto/proyecto/carpeta/volúmenes no compartidos y respaldo validado. Se
detuvieron backend y los dos workers; se generaron respaldos nuevos con writers
detenidos, antes de ejecutar SQL: PostgreSQL227.529B y Mongo7.483B, SHA256 en el
manifiesto privado, pg_restore --list y mongorestore --dryRun correctos.

Una única transacción de mantenimiento verificó DB local fyag_db, ausencia de
bases test activas, conteos esperados, cero evidencias/archivos y colección Mongo
vacía. Ejecutó TRUNCATE de la lista cerrada anterior con RESTART IDENTITY, **sin
CASCADE**; cualquier FK ajena o guarda fallida habría abortado sin borrado. No
deshabilitó constraints ni triggers, ni alteró migraciones. Resultado:193filas de
prueba retiradas en23tablas (Comercial62, Obras102, Finanzas24, Alertas5).

Preservados30usuarios con credenciales/roles originales,55migraciones,
11categorías y su historial, permisos Django, sesiones, tokens/blacklist y
historial de seguridad. No se crearon contraseñas administrativas ni se
reescribieron montos/estados como lógica de aplicación: se retiró únicamente el
conjunto de pruebas autorizado en mantenimiento. No se borraron documentos
Mongo, usuarios Mongo, archivos o volúmenes. Los dos scripts manuales, resultado
JSON y respaldos permanecen solo en el directorio privado externo indicado.

Se reiniciaron backend/workers con migraciones oficiales (sin pendientes).
Smoke posterior: auth/me, Obras, Finanzas/documentos, Auditoría/eventos, Alertas,
Dashboard/resumen y Reportes/obras:7/7HTTP200. Diagnóstico Mongo y reconciliación
manual correctos,0fichas/0archivos. El worker de Alertas puede recrear su fila
operativa de reconciliación sin recrear negocio de prueba. No se genera limpieza
en CI, migraciones, post_migrate ni arranque automático.

## Operación y rollback

1. Configurar claves locales separadas sin publicarlas; volumen nuevo usa
   entrypoint, volumen antiguo requiere bootstrap local explícito tras respaldo.
2. `docker compose --profile test up -d --build`; comprobar health y diagnóstico.
3. Ejecutar check, migraciones dry-run, suite documental y regresión completa.
   Para runtime sin QA usar construcción por defecto de requirements.txt;
   backend de desarrollo usa requirements-test para lectores de Reportes.
4. Worker independiente reconcilia cada60s; manual una pasada tras recuperar Mongo.
   Supervisar resultados/backoff/espacio de Mongo, no arrancarlo desde runserver.
5. No desplegar con runserver en producción. No se configura cloud en 012A.
   Definir TLS/secret store/backups/recursos para una fase de despliegue posterior.

Rollback: detener worker documental, volver a imagen/config de aplicación previa
con rutas012A retiradas, **conservar Mongo autenticado**, anotaciones y archivos
SQL privados. No necesita reversión de esquema SQL. No borrar ni restaurar encima
de datos actuales sin clasificar/respaldo. Mantener esquema v1 y bootstrap para
leer los documentos; si se debe restaurar, hacerlo primero en base aislada y
coordinar con las evidencias SQL. No reabrir puerto público ni activar no-auth al
volver a una imagen antigua. La pérdida de anotaciones no se repara desde SQL.

## Riesgos residuales y punto de detención

- Consistencia eventual, sin transacción distribuida ni garantía de misma revisión
  entre listado y detalle. CAS evita sobrescritura, no ofrece historial de notas.
- Listado O(N) por Obra para validar candidatos/count en SQL; perfil local de1000
  no garantiza rendimiento ilimitado. Escalar con nuevas decisiones contractuales.
- Patrones conservadores no detectan todos los nombres/PII semánticos; política
  de uso, claves técnicas cerradas y revisión de contenido siguen siendo necesarias.
- Logs operativos no son Auditoría inmutable. No contienen anotaciones.
- Protección de transporte interno local; TLS y cloud fuera de alcance.
- QA requiere Mongo autenticado separado; sin `--parallel` por colección compartida.
- Usuarios bootstrap con capacidad administrativa solo en Mongo/operación y QA;
  no usar env_file de desarrollo completo para un despliegue productivo.
- No hay detección de acceso/guardado del archivo: este módulo nunca entrega bytes.

Publicación autorizada exclusivamente en PR en borrador para revisión técnica.
Detenerse tras comunicar el resultado real de CI; auditoría independiente y
Postman siguen pendientes. No realizar merge ni limpiar datos adicionales.
