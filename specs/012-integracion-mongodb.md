# SPEC-012 — Integración MongoDB y gestión documental real (backend)

**Estado: CONTRATO REVISADO EN PR DOCUMENTAL; PENDIENTE DE APROBACIÓN E IMPLEMENTACIÓN.** Revisión de SPEC-012 posterior al Informe 2 y a la integración de SPEC-011 (PR #37). No afirma que exista un módulo de adjuntos de facturas ni que ya se almacenen imágenes de usuarios. **Este documento no ejecuta limpieza, cambia infraestructura ni crea endpoints por sí mismo.**

## 1. Objetivo y decisiones revisadas

Se adopta MongoDB por una **necesidad documental real**: atributos flexibles, notas y etiquetas de evidencia según tipo de documento. No se instalará únicamente para repetir en BSON una tabla SQL. La integración se realizará mediante Django/DRF; React no accede directamente a los motores.

**Separación de responsabilidades:**

| Información | Fuente autoritativa / almacén |
| --- | --- |
| Usuarios, credenciales, JWT, roles y permisos | PostgreSQL |
| Clientes, Presupuestos, Obras, turnos y participantes | PostgreSQL |
| Costos, márgenes, documentos de cobro, folios, importes, pagos y saldos | PostgreSQL |
| Eventos de negocio de Auditoría y Alertas | PostgreSQL; no se duplican por defecto |
| Registro de existencia de evidencia de turno y sus relaciones | PostgreSQL: \`EvidenciaTurno\` |
| Descripción documental, etiquetas y atributos variables relacionados con evidencias | MongoDB, en documento flexible de dominio restringido |
| Bytes de fotografías, PDF escaneados y adjuntos | Almacenamiento privado (actualmente volumen \`evidencias_data\` para fotos de turnos; futuro objeto/almacenamiento privado para adjuntos) |
| PDF/XLSX/CSV de Reportes | Archivos temporales generados bajo demanda, sin persistencia documental |

**Estado comprobado en el código:**
- MongoDB 8.0 está configurado en Compose y PyMongo instalado; **no existe integración funcional**.
- \`backend/apps/obras/models.py\` registra fotos de turno en \`EvidenciaTurno\`, y \`backend/apps/obras/evidencias.py\` guarda los bytes privados. \`views_turnos.py\` expone descarga autenticada. El usuario confirmó que **hoy no hay imágenes reales guardadas**; de todos modos se inspeccionarán los volúmenes locales antes de limpiar.
- Finanzas registra \`DocumentoCobro.referencia_respaldo\` como texto, **no** recibe ni guarda un escaneo adjunto. Un \`folio_externo\` o referencia no acredita la existencia de un archivo.
- Los scripts \`database/{init_mongodb.js,indices_mongodb.js,validaciones_mongodb.js}\` son preliminares; contienen nombres de campos distintos a esta revisión. Se debe versionarlos/adaptarlos en la implementación y no confundir archivos en Git con cambios ya aplicados en MongoDB.
- En el Informe 2 se propuso una colección \`evidencias_obra\` con descripción, etiquetas, archivo y metadatos. Esta revisión conserva ese **uso documental**, pero adecua colección/esquema al backend real y evita guardar bytes o rutas privadas en MongoDB. No se exige mantener un nombre provisional del informe si rompe consistencia.

## 2. Entrega incremental: 012A y 012B

**SPEC-012A (siguiente incremento y alcance del primer PR de implementación):**
1. Conexión MongoDB autenticada y endurecimiento Compose; mínimo privilegio, healthcheck, timeouts.
2. Colección \`fyag_documentos.documentos_metadata\` con origen \`EVIDENCIA_TURNO\`, datos técnicos de origen referencial más **campos documentales editables** (\`descripcion\`, \`etiquetas\`, \`atributos\`).
3. Sincronización idempotente recuperable de \`EvidenciaTurno\` desde PostgreSQL; **nunca sobrescribir** anotaciones de MongoDB al reconciliar.
4. API protegida para **consultar y editar metadatos documentales**, y comando de diagnóstico/operación.
5. Pruebas reales de ambos motores, seguridad, concurrency, rollback y documentación de uso; NO frontend en esta fase.

**SPEC-012B (siguiente incremento, contrato de alcance; NO implementarlo dentro de 012A):**
- Carga, consulta y descarga de **adjuntos documentales reales** (por ejemplo, escaneo de factura externa o informe técnico), con binarios en almacenamiento privado y metadatos flexibles en MongoDB, mientras que la relación/autorización se valida en PostgreSQL.
- Diseñar una entidad relacional mínima de **registro de adjunto** (sin modificar montos, folio, estado ni reglas del \`DocumentoCobro\`) o un contrato equivalente que garantice integridad y restauración; exigir definición y pruebas de ciclo de vida. No escribir una FK SQL ficticia hacia MongoDB ni declarar respaldo presente cuando solo existe una referencia textual.
- Un escaneo **no reemplaza** la factura tributaria real, ni crea factura ni registra pago. No OCR, emisión DTE, lectura automática de importes ni reconocimiento automático sin especificación adicional.
- Definir endpoints, matríz RBAC para Finanzas, validación estricta de PDF/JPEG/PNG, límites de tamaño, detección de tipo real, sanitización, hash, antivirus/política antimalware, rollback de archivos huérfanos, retención y borrado antes de la implementación 012B; no improvisar cambios de Finanzas en 012A.
- Si se decide implementar 012B más tarde, hacerlo en otra rama/PR autorizado; el frontend solo consumirá endpoints reales, nunca nombres de archivo privados.

**Futuro fuera de ambas fases:** evaluar proyecciones de \`auditoria_eventos\` y \`alertas_eventos\` en MongoDB solo si existe necesidad demostrada. PostgreSQL sigue siendo fuente oficial.

## 3. Colección MongoDB 012A: esquema flexible pero acotado

Base: \`fyag_documentos\`; colección: \`documentos_metadata\`. Identificador Mongo determinista \`_id = "evidencia_turno:{evidencia_id}"\`. Proyección técnica desde PostgreSQL más anotación documental real de MongoDB.

Ejemplo **sintético** BSON:

~~~javascript
{
  _id: "evidencia_turno:123",
  version_esquema: 2,
  origen: "EVIDENCIA_TURNO",
  evidencia_id: NumberLong("123"),
  obra_id: NumberLong("8"),
  turno_id: NumberLong("29"),
  tipo_mime: "image/jpeg",
  tamano_bytes: NumberLong("204800"),
  sha256: "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  creado_en: ISODate("2026-11-12T21:00:00Z"),
  sincronizado_en: ISODate("2026-11-12T21:01:00Z"),
  descripcion: "Estado inicial del equipo",
  etiquetas: ["antes", "unidad_exterior"],
  atributos: { ubicacion_general: "exterior", vista: "frontal" },
  revision: NumberInt(1),
  anotado_en: ISODate("2026-11-12T21:05:00Z"),
  anotado_por_id: NumberLong("17")
}
~~~

**Propietario de campos:**
- **Espejo técnico SQL, NO editable por cliente:** \`_id\`, \`version_esquema\`, \`origen\`, \`evidencia_id\`, \`obra_id\`, \`turno_id\`, \`tipo_mime\`, \`tamano_bytes\`, \`sha256\`, \`creado_en\`, \`sincronizado_en\`.
- **Documento flexible, propiedad MongoDB y editable vía API autorizada:** \`descripcion\`, \`etiquetas\`, \`atributos\`, \`revision\`, \`anotado_en\`, \`anotado_por_id\`.

**Contrato de validación 012A:**
- \`descripcion\`: string UTF-8 de 0 a 1000 caracteres, normalizada, sin HTML activo.
- \`etiquetas\`: lista de 0 a 12 strings únicos, longitud 1-40, contenido legible, normalización y orden determinista documentados; sin etiquetas duplicadas tras normalización.
- \`atributos\`: documento plano de 0 a 12 pares; claves ASCII permitidas \`[a-z][a-z0-9_]{0,39}\`; valores solo strings de hasta 200 caracteres o booleanos (no arrays, objetos anidados, null ambiguo, ni datos binarios). Máximo 4 KiB de JSON serializado. Rechazar claves que empiecen por \`$\`, contengan \`.\`, sean reservadas del esquema o puedan crear inyecciones de operadores MongoDB.
- Documento total sujeto a tamaño acotado (máximo 16 KiB BSON por documento de este dominio), aunque el límite general de MongoDB sea mayor.
- \`revision\` entero positivo incremental; asignación inicial 0, actualización mediante comparación atómica \`revision\` (CAS), rechazo 409 a actualizaciones obsoletas.
- Fecha BSON almacenada en UTC; representación ISO8601 en API, identificadores enteros positivos BigInt. No confiar en IDs de MongoDB enviados por frontend.
- \`sha256\` solo técnico/interno, jamás en respuesta API. **Nunca guardar** \`nombre_interno\`, paths, URLs firmadas, contenido de archivos, base64, RUT, emails, tokens, credenciales, nombres de personas o valores financieros.
- No confundir \`atributos\` con una vía de almacenar PII: contrato de claves y valores restringido, documentado y auditado; rechazar claves específicas sensibles y no registrar textos completos en logs.
- El validador Mongo debe usar esquema BSON con \`validationLevel=strict\`, \`validationAction=error\`, campos requeridos, \`additionalProperties=false\` considerando \`_id\`; versiones de esquema explícitas y una transición idempotente para datos de prueba existentes.

Índices iniciales: \`_id\` implícito, \`(obra_id ASC, creado_en DESC, evidencia_id DESC)\` y, si las consultas por etiquetas se habilitan realmente, \`(obra_id ASC, etiquetas ASC)\`; índices solo por consultas justificadas.

**Regla crítica de sincronización:** utilizar \`$set\` únicamente en campos espejo técnicos y \`$setOnInsert\` para \`descripcion=""\`, \`etiquetas=[]\`, \`atributos={}\`, \`revision=0\` y \`anotado_en/anotado_por_id=null\`. Nunca resetear notas/etiquetas con un \`upsert\` posterior. Un cambio de anotaciones usa actualización atómica por revisión y afecta solo campos Mongo editables.

## 4. Seguridad e infraestructura

El Compose actual expone \`mongodb\` sin autenticación y publica el puerto con \`\${MONGO_HOST_PORT}:27017\`. Es adecuado solo como preparación de laboratorio, no como configuración definitiva.

La implementación 012A debe:
1. Activar autenticación, crear **identidad de aplicación NO root** con privilegios mínimos en \`fyag_documentos\` y credenciales locales por variables sin valores publicables. Prohibido habilitar acceso anónimo o pasar contraseñas en código, commits, URLs HTTP o logs.
2. Conservar PyMongo como cliente; reutilización por proceso y cierre en worker; límites \`serverSelectionTimeoutMS\`, \`connectTimeoutMS\`, \`socketTimeoutMS\`, pool razonable y ping/health verificado, no en cada solicitud de negocio.
3. Mantener tráfico interno Docker y retirar el puerto host o restringir a \`127.0.0.1\`; CORS de Django no es seguridad de MongoDB.
4. Tener healthcheck seguro, bootstrap de colecciones, usuarios, validadores e índices **idempotente**, documentando la versión de esquema y la orden exacta de ejecución; no asumir que guardar \`database/*.js\` ejecuta los scripts.
5. Controlar volúmenes existentes: credenciales root agregadas a Compose **no crean usuarios en un volumen inicializado**. Preparar ruta segura para volumen nuevo y ruta de migración para volumen existente, sin sobrescribir datos sin clasificación previa.
6. El backend principal, PostgreSQL, Finanzas, Obras, Auditoría, Alertas, Dashboard y Reportes deben poder operar si MongoDB falla. El reconciliador sí depende de Mongo; reintenta con backoff acotado.
7. No habilitar conexiones de cloud ni cargar credenciales reales de Render/Neon/Atlas durante implementación local. Una configuración cloud es una tarea posterior.
8. Usar variables separadas para desarrollo y pruebas con Mongo aislado. CI no debe conectarse a los volúmenes locales del usuario.

## 5. Escritura, recuperación y consistencia

PostgreSQL sigue siendo autoridad para existencia, pertenencia y permisos de \`EvidenciaTurno\`. MongoDB es autoridad SOLO de las anotaciones documentales 012A.

- Mantener sin cambios los flujos transaccionales ya validados de \`finalizar_turno\` y \`subsanar_turno\`. No realizar escritura Mongo dentro de una transacción abierta de PostgreSQL ni agregar bloqueo de éxito de negocio por indisponibilidad Mongo.
- Proyección idempotente después del commit mediante callback best-effort opcional y un **reconciliador recuperable** \`python manage.py reconciliar_documentos_mongodb\` que recorre \`EvidenciaTurno\` por lotes. Usar upsert determinista, con timeouts, manejo de fallos y logs sanitizados.
- Un high-water-mark simple de PK es insuficiente ante commits fuera de orden: recorrer o probar otra estrategia que rellene huecos, incluso después de interrupciones.
- El servicio de escritura documental verifica JWT y rol en PostgreSQL, confirma existencia y vínculo de evidencia/obra/turno antes de modificar Mongo, y opera con **optimistic locking** por \`revision\`; si la proyección aún no existe, intentar una sincronización puntual post-commit y luego escribir, o devolver error explícito reintentable si la fuente o Mongo no están disponibles.
- Distinguir pérdida temporal de Mongo (503) de colisión de edición (409). Nunca responder 200 vacío por fallo de base ni transformar indisponibilidad de un motor en caída del otro.
- Ediciones de metadatos no alteran estados de Obra, validación de turnos, costos, montos o historia financiera.
- Registrar operaciones estructuradas con actor ID, evidencia ID, resultado, revisión y correlación sin descripción, etiquetas completas, atributo libre, tokens, paths, SHA ni importes.
- Prueba de reconciliador concurrente/repetido que **preserva** \`descripcion\`/\`etiquetas\`/\`atributos\`; prueba de dos PATCH simultáneos con una sola actualización por revisión.

## 6. API DRF 012A y RBAC

**Endpoints definidos:**
1. \`GET /api/documentos-metadata/?obra=<id>&page=<n>\` — listado y metadatos documentales de evidencias de una Obra.
2. \`GET /api/documentos-metadata/evidencias/<id>/\` — detalle documental para evidencia existente y autorizada.
3. \`PATCH /api/documentos-metadata/evidencias/<id>/\` — actualización atómica de anotaciones flexibles.

**Permisos:** \`GERENCIA\` y \`SUPERVISOR_OBRAS\` acceden a consulta y edición de anotaciones 012A; \`TECNICO\`, \`ADMINISTRATIVO_FINANZAS\` y \`ADMINISTRADOR_TI\` reciben 403. La carga y descarga de fotos existente en Obras conserva sus permisos, sin ampliar accesos por este módulo. No confiar en \`is_staff\`, superuser o claims manipulables; JWT versionado y actividad/rol \`sesion_version\` se comprueban en PostgreSQL en cada solicitud.

**GET listado:** \`obra\` obligatorio, ID positivo ASCII ≤ BIGINT; \`page\` opcional, entero positivo, 25 registros. Rechazar query vacía, repetida, desconocida, signos, notación científica, overflow y ceros iniciales: 400. Validar Obra en PostgreSQL antes de usar Mongo; Obra inexistente 404 genérico. Leer solo documentos \`origen=EVIDENCIA_TURNO\` vinculados a esa Obra; ordenar \`creado_en DESC, evidencia_id DESC\`.

Respuesta:

~~~json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [{
    "evidencia_id": 123,
    "obra_id": 8,
    "turno_id": 29,
    "tipo_mime": "image/jpeg",
    "tamano_bytes": 204800,
    "creado_en": "2026-11-12T21:00:00+00:00",
    "descripcion": "Estado inicial del equipo",
    "etiquetas": ["antes", "unidad_exterior"],
    "atributos": {"ubicacion_general": "exterior", "vista": "frontal"},
    "revision": 1,
    "sincronizado_en": "2026-11-12T21:01:00+00:00"
  }],
  "proyeccion": "EVENTUAL",
  "fuente_autoritativa": "POSTGRESQL"
}
~~~

**GET detalle:** misma representación de fila, sin \`_id\`, \`sha256\`, \`nombre_interno\`, URLs privadas ni registros de otros dominios. Verificar la evidencia en PostgreSQL y la autorización de la Obra; si aún no existe proyección: 409 \`metadata_pendiente_sincronizacion\` o sincronización puntual segura (documentar comportamiento exacto), jamás un 404 ambiguo por lag Mongo.

**PATCH detalle:** \`Content-Type: application/json\` estricto, cuerpo objeto con \`revision\` entero no negativo **obligatorio**, y al menos uno de \`descripcion\`, \`etiquetas\`, \`atributos\`. Solo estos campos, sin modificar metadatos de PostgreSQL. Campos presentes se **reemplazan completos**; campos ausentes se conservan. Sin claves desconocidas, duplicadas o valores nulos no definidos. Respuesta 200 con representación actual y revisión incrementada, 409 \`revision_obsoleta\` cuando otro actor modificó antes, 503 al no disponer de Mongo. Rechazar reintentos que intenten actualizar datos desde una revisión antigua; no aceptar \`revision\` en la URL.

**HTTP:** 200, 400, 401, 403, 404, 405, 409 y 503 con errores saneados; encabezados \`Cache-Control: private, no-store\`, \`Vary: Authorization\`, \`X-Content-Type-Options: nosniff\`; \`Retry-After\` solo cuando corresponda. HEAD/OPTIONS siguen permiso/autenticación; mutaciones no previstas → 405 para actor autorizado. Sin rutas públicas ni accesos directos desde React a Mongo.

**Importante:** las descripciones y etiquetas en Mongo son anotaciones documentales, **no** reemplazan la descripción laboral oficial de \`TurnoObra\`. No permitir que este endpoint cambie o valide el trabajo de un técnico.

## 7. Scripts de \`database/\` e índices

Reorganización controlada sugerida:

~~~text
database/
  mongodb/
    init_mongodb.js
    indices_mongodb.js
    validaciones_mongodb.js
  README.md
~~~

- Cambiar rutas solo con ajuste de documentación y comandos Compose/CI que las referencien, sin romper scripts de compañeros. No tocar datos SQL mediante scripts sueltos: estructura relacional se administra con migraciones Django.
- Bootstrap para \`documentos_metadata\` idempotente con \`validationLevel=strict\`, campos espejo + anotaciones, índice ordenado por Obra/fecha; compatibilidad con scripts antiguos \`auditoria_eventos\` y \`alertas_eventos\` sin añadir escritura de negocio. No afirmar que ya existe un índice por solo tener un JS.
- Con datos previos no compatibles, inspeccionar y clasificar antes de una operación destructiva; debido a la autorización de limpieza de datos **locales de prueba**, se permite preparar una transición controlada tras el diagnóstico, pero no borrar automáticamente colecciones de otras apps.

## 8. Limpieza autorizada del entorno de desarrollo

**Autorización del responsable:** eliminar datos basura exclusivamente de **entornos locales de pruebas de FYAG**; no hay datos empresariales relevantes ni imágenes guardadas actualmente, según el responsable. Esta autorización **NO** se extiende a servicios cloud, volúmenes de otros proyectos, credenciales, repositorios, documentos de diseño ni archivos fuera del proyecto.

**Procedimiento obligatorio, separado de la implementación 012A:**
1. Detectar \`docker context\`, carpeta de Compose, nombre de proyecto, contenedores, volúmenes nominados reales y conexiones PostgreSQL/Mongo; mostrar inventario y comprobar que no son servicios compartidos. No inferir nombres de volúmenes por el YAML.
2. Contabilizar filas/colecciones/documentos y existencia de archivos privados; verificar efectivamente el volumen de evidencias aunque el responsable indicó que está vacío.
3. Generar **respaldo de seguridad local** restaurable (PostgreSQL y MongoDB si hay documentos; metadatos/volúmenes si procede) en una ubicación privada fuera de Git. Verificar que el respaldo se puede leer/restaurar en entorno de prueba o, como mínimo, integridad de artefactos y manifiesto; NO subir datos ni secretos a GitHub.
4. Ofrecer un plan de limpieza **limitado al stack FYAG de desarrollo**, describiendo exactamente qué se borraría y qué cuentas de administración deberán preservarse o recrearse. No hacer \`docker compose down -v\` sin identificar alcance real; no truncar tablas protegidas de Finanzas/Auditoría sin estrategia transaccional/migratoria.
5. Ejecutar la limpieza solo mediante un comando/procedimiento explícito de desarrollo, con protecciones contra entornos no locales y registro de ejecución. La autorización de esta conversación cubre ese conjunto de datos de prueba **una vez confirmada la identidad del entorno**; si se descubren datos no clasificados, backups ajenos o recursos compartidos, detenerse e informar.
6. Reconstruir esquema desde **migraciones Django oficiales** y bootstrap Mongo revisado; verificar creación/uso de cuentas por rol y ejecución de smoke tests. No alterar archivos de migraciones ni generar una \`dump.sql\` versionada.
7. **No ejecutarlo antes de cerrar las pruebas de integración que dependan de datos actuales.** La limpieza no reemplaza tests ni prueba disponibilidad de Mongo; preferir efectuarla al final de las verificaciones locales, en una fase operacional separada.
8. Dado que el usuario usa Django para crear cuentas de prueba y credenciales, nunca hardcodear una nueva clave ni imprimir secretos en el informe. Anotar los pasos para recrear usuarios autorizados.

**No ejecutar ninguna limpieza desde un workflow CI, PR, despliegue o \`post_migrate\`.** En CI usar siempre bases efímeras separadas.

## 9. Pruebas obligatorias

1. Mongo real autenticado, versión y compatibilidad PyMongo, no root, acceso denegado sin credenciales y health/timeout robusto.
2. Bootstrap/índices/validadores ejecutados y verificados contra Mongo real, dos ejecuciones idénticas sin efectos, datos previos detectados sin borrar por sorpresa.
3. \`EvidenciaTurno\` de fixture PostgreSQL, luego proyección Mongo con IDs/tipos correctos, fechas UTC, campos técnicos cerrados; datos no se introducen en base de desarrollo por fixtures de test.
4. PATCH válido para \`descripcion\`, \`etiquetas\`, \`atributos\` diferenciados; GET devuelve valores reales y paginación, filtros y formatos exactos.
5. Reconciliación repetida **no borra ni resetea anotaciones Mongo**. Dos ediciones concurrentes con misma revisión → solo una exitosa; conflicto 409 estable.
6. Fallo de Mongo entre commit PostgreSQL y proyección → no perder evidencia, recuperable. Comprobación de commits PostgreSQL fuera de orden sin perder IDs; sin consultas lazy fuera de control.
7. Mongo desconectado, credenciales inválidas, índices faltantes y documentos BSON corruptos → 503/errores sanitizados, sin comprometer login, Obras, Finanzas, Auditoría, Alertas, Dashboard, Reportes.
8. Matriz RBAC 401/403/404/405 para todos los roles, JWT revocado/inactivo, cambios de rol persistido, validación de pertenencia de evidencia/Obra, no acceso por flags superuser.
9. Inyección de operador MongoDB, claves \`$\`/punto, anidamientos, strings grandes, duplicados de claves JSON, BSON malicioso, HTML, Unicode, etiquetas repetidas, elementos sensibles: 400 y nada de filtraciones.
10. Revisión de secretos, paths, nombres internos, sha256 y contenidos de anotación en API/logs, y de no escrituras de importes o estados financieros.
11. Pruebas Compose PostgreSQL + Mongo, CI con Mongo autenticado aislado, pruebas de migraciones y regresión completa Django existentes. Reportar counts/duración reales; no afirmar ejecución de CI remoto antes de abrir PR.
12. Perfil de 1.000 metadatos: tiempo, índices/explain, memoria y consultas bajo paginación de 25; resultados como evidencia local, no SLA.
13. Inspección y plan de limpieza de solo datos de prueba, respaldo, preservación/recreación de cuentas, sin eliminar imágenes inexistentes ni volúmenes ajenos.
14. Contrato OpenAPI completo, ejemplos JSON y guía de integración para compañeros del frontend, sin modificar el frontend.

**Aceptación 012A:** una fotografía de turno registrada mediante API existente genera una ficha documental en Mongo; Gerencia/Supervisor pueden consultar y **editar anotaciones**; reiniciar/sincronizar no pierde anotaciones; Mongo caído no rompe el sistema SQL; no se exponen archivos; suites CI/Postman verificadas tras publicación autorizada. Una colección vacía o un simple espejo SQL no cumple la SPEC.

## 10. Operación, documentación y despliegue

Entregables de implementación: \`backend/docs/SPEC-012-IMPLEMENTACION.md\`, \`backend/docs/openapi/SPEC-012-v1.json\`, \`database/README.md\`, \`.env.example\` actualizado sin secretos, comandos de bootstrap, diagnóstico \`python manage.py verificar_mongodb\` y reconciliación \`python manage.py reconciliar_documentos_mongodb\`.

- Documentar cómo iniciar/reconstruir backend y Mongo con \`docker compose\`, preservar volúmenes e inicializar sin root de aplicación.
- Si se agrega un reconciliador permanente, definir proceso único o idempotente, cadencia, límites y salida limpia; no se inicia dentro de \`runserver\` ni mediante import side effects.
- Archivos reales quedan privados en volumen/almacenamiento dedicado; en la nube deberían migrarse a almacenamiento persistente de objetos. **No** guardar archivos en las bases por comodidad ni usar \`GridFS\` sin decisión separada.
- Monitoreo de fallo Mongo y recuperación; rollback de versión de API/servicio y scripts sin eliminación de datos SQL o Mongo; observar cambios de esquema y límites de rutas.
- Producción (Render/Neon/Atlas/Azure o similares) no se configura todavía: estos servicios gratuitos están destinados a demostración; los planes comerciales se evaluarán posteriormente.

## 11. Flujo de Git y alcance de la primera implementación

1. Revisar y fusionar el PR **solo documental** de actualización SPEC-012 mediante autorización expresa. No implementar contra una copia antigua de SPEC-012.
2. Actualizar \`main\` local vía \`git pull --ff-only origin main\` tras el merge; confirmar que el nuevo contrato está disponible.
3. Crear rama \`feature/backend-012a-mongodb\` desde \`main\` actualizado. Implementar **exclusivamente 012A**, sin implementar uploads de facturas de 012B, sin frontend y sin cambios financieros no aprobados.
4. OpenCode ejecuta validaciones locales sobre contenedores y bases de pruebas independientes, registra inventario y plan de limpieza, y **se detiene antes de cualquier commit, push, PR o merge**. Entrega informe con tests reales y riesgos.
5. Revisión del informe y archivos por ChatGPT; publicación de código solo tras autorización explícita del responsable; CI y Postman; merge por autorización.
6. Luego abrir e implementar 012B en otro incremento, no modificar el contrato de facturación ya integrado sin nueva revisión de SPEC.

**Fuera de alcance de 012A:** emisión DTE, OCR, subidas de PDFs/facturas, nuevas tablas financieras, migración PostgreSQL→MongoDB, modificación de estados/costos/roles, replicación global de Auditoría/Alertas, UI/React, servicios cloud y borrado de recursos ajenos.

## 12. Fuentes revisadas

\`compose.yaml\`, \`.env.example\`, \`backend/requirements.txt\`, \`backend/config/settings.py\`, \`database/*.js\`, \`backend/apps/obras/{models.py,evidencias.py,services_turnos.py,views_turnos.py}\`, \`backend/apps/finanzas/{models.py,views_documentos.py,serializers_documentos.py}\`, \`specs/011-reportes-backend.md\`, SPEC-004/007/008/009 y Documento de Informe 2 de FYAG.

Este contrato revisado incorpora el uso documental flexible definido en el Informe 2 pero prioriza integridad, seguridad, recuperación y pruebas del backend definitivo. El usuario confirmó que el entorno local no contiene datos de negocio relevantes ni fotografías reales y autorizó limpiar datos de prueba; **esa autorización no implica que ya se haya ejecutado la limpieza**.
