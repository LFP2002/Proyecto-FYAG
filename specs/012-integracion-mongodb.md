# SPEC-012 — Integración funcional y segura de MongoDB (metadatos documentales)

**Estado: PROPUESTA CONTRACTUAL PARA REVISIÓN; NO IMPLEMENTADA.** Se desarrolla después de SPEC-011 Reportes (PR #37 integrado en `main`). Este documento define el siguiente incremento de backend; **no cambia aún código, datos, contenedores ni APIs**. Su implementación y cualquier modificación del Docker de desarrollo requieren revisión de este contrato y autorización del responsable.

## 1. Situación real y objetivo

**Comprobado en el repositorio:**
- `compose.yaml` define `mongodb` con imagen `mongo:8.0`, volumen `mongodb_data`, puerto publicado como `${MONGO_HOST_PORT}:27017` y `MONGO_INITDB_DATABASE`. No configura autenticación de usuario ni `healthcheck`; el backend declara una dependencia `service_started`, aunque sus módulos de negocio no utilizan MongoDB.
- `backend/requirements.txt` contiene `pymongo`, pero `backend/config/settings.py` configura PostgreSQL para Django y no existe una integración funcional de PyMongo para los endpoints de negocio.
- `database/init_mongodb.js`, `database/indices_mongodb.js` y `database/validaciones_mongodb.js` preparan nombres de colecciones `auditoria_eventos`, `alertas_eventos` y `documentos_metadata`; su mera presencia no prueba que se hayan ejecutado sobre el volumen del usuario.
- El modelo PostgreSQL `apps.obras.models.EvidenciaTurno` ya persiste identificadores de Obra/Turno, `tipo_mime`, `tamano`, `sha256`, nombre interno y fecha. Las fotos están en almacenamiento privado de Obras, NO en MongoDB.
- Los eventos de Auditoría y las Alertas son gestionados por sus módulos de dominio en PostgreSQL y poseen contratos existentes. El README declara que CI no necesita MongoDB actualmente.

**Objetivo v1 (012A):** incorporar MongoDB como **proyección NoSQL funcional** de metadatos de evidencias de turnos, con conexión autenticada, escritura idempotente y reconciliable, lectura autorizada desde Django, health/status operativo y pruebas con MongoDB real. PostgreSQL y el almacén privado de archivos siguen siendo fuentes de verdad. No introducir una segunda fuente oficial de costos, pagos, permisos ni estados.

**No confundir servicio levantado con integración:** para considerar SPEC-012A implementada debe existir al menos un flujo real PostgreSQL → MongoDB y una lectura real MongoDB → Django autenticada y cubierta por pruebas, además de control de recuperación ante indisponibilidad.

## 2. Límite de dominio y fases

- **012A, alcance obligatorio del próximo PR:** endurecimiento de seguridad MongoDB y su despliegue; cliente PyMongo de mínimo privilegio; proyección `documentos_metadata` para `EvidenciaTurno`; sincronización eventual idempotente y reconciliación; API de lectura acotada por permisos de Obras; estado técnico de integración; índices, validadores, pruebas y documentación.
- **012B, futuro y NO parte de 012A:** decidir si `auditoria_eventos` y `alertas_eventos` necesitan proyecciones derivadas en MongoDB. Requiere una SPEC/PR separado y justificar consultas o retención. No realizar doble escritura síncrona ni cambiar las APIs actuales por usar estas colecciones.
- **Nunca en MongoDB como fuente oficial:** Usuarios/JWT/roles, `Presupuesto` y sus importes, `Obra` y sus estados, `CierreCostosObra`, `DocumentoCobro`, `PagoDocumento`, eventos de Auditoría y Alertas autoritativos. No almacenar fotos o archivos exportados dentro de `documentos_metadata`.

La eventualidad de la proyección **no afecta decisiones financieras, autorizaciones ni reglas de negocio**: se consultan siempre desde PostgreSQL.

## 3. Modelo documental v1: `fyag_documentos.documentos_metadata`

**Origen real:** filas persistidas de `Obras.EvidenciaTurno`. **Clave estable:** `_id = "evidencia_turno:{id}"`, sin depender de timestamps de inserción ni de IDs autogenerados por MongoDB.

Documento BSON interno esperado (ejemplo sintético, no dato real):

~~~javascript
{
  _id: "evidencia_turno:123",
  version_esquema: 1,
  origen: "EVIDENCIA_TURNO",
  evidencia_id: NumberLong("123"),
  obra_id: NumberLong("8"),
  turno_id: NumberLong("29"),
  tipo_mime: "image/jpeg",
  tamano_bytes: NumberLong("204800"),
  sha256: "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  creado_en: ISODate("2026-11-12T21:00:00Z"),
  sincronizado_en: ISODate("2026-11-12T21:01:00Z")
}
~~~

Los únicos campos autorizados son `_id`, `version_esquema`, `origen`, `evidencia_id`, `obra_id`, `turno_id`, `tipo_mime`, `tamano_bytes`, `sha256`, `creado_en`, `sincronizado_en`. No añadir extensiones de texto libre aún: ningún atributo ajeno existe hoy en `EvidenciaTurno`.

- `_id` determinista y único, `version_esquema=1`, `origen=EVIDENCIA_TURNO`.
- Enteros BSON `Int64` o `int` compatibles con PK positiva BigInt y tamaños válidos; fechas BSON UTC reales, sin fechas en string.
- `sha256` se puede persistir para trazabilidad técnica **pero nunca se devuelve por API pública**.
- **Prohibido:** `ruta_archivo`, `nombre_interno`, paths privados, nombres legales, RUT, correos, cookies, tokens, descripciones de trabajos, datos de pacientes, contenido binario, base64, referencias de descarga pública. Un archivo nunca se expone por conocer su MongoDB `_id`.
- Índices mínimos: `_id` único implícito y `(obra_id ASC, creado_en DESC, evidencia_id DESC)` para consulta paginada. Crear índices con nombres/versiones explícitos e idempotentes; medir plan de consultas real.

**Compatibilidad con scripts existentes:** los scripts `database/*.js` son preliminares y su esquema actual exige campos `nombre`, `fecha`, `tipo_archivo` y `ruta_archivo`. Antes de implementar, adaptarlos de manera revisable al nuevo esquema, **sin eliminar datos existentes ni hacer `dropDatabase`, `drop`, `deleteMany` o `collMod` destructivo**. Detectar colecciones previas no vacías, índices conflictivos o validadores incompatibles y detenerse con informe y plan de migración. No sobrescribir silenciosamente documentos creados por otro integrante del equipo.

## 4. Seguridad de infraestructura y secretos

El `compose.yaml` actual **no es adecuado para uso compartido o productivo** porque MongoDB carece de autenticación configurada y el puerto puede quedar expuesto por la interfaz host.

La implementación debe:

1. Incorporar autenticación MongoDB y usuario de aplicación de alcance `fyag_documentos` con permisos mínimos. Si se necesitan identidades distintas para escritura y lectura, separar roles. Nunca conectar Django con la cuenta root/admin.
2. Proporcionar variables de entorno sanitizadas en `.env.example`, sin secretos reales ni defaults utilizables en producción. No registrar URI/password en logs ni errores JSON.
3. Mantener comunicación backend ↔ MongoDB **por la red interna de Docker**. El acceso host de desarrollo debe estar restringido a `127.0.0.1` o eliminarse; no publicar 27017 en todas las interfaces.
4. Agregar comprobación de salud autenticada y límites de timeout (`serverSelectionTimeoutMS`, `connectTimeoutMS`, `socketTimeoutMS`). No hacer ping indiscriminadamente en cada solicitud de negocio.
5. Proporcionar instrucciones **no destructivas** para volúmenes MongoDB preexistentes. **Atención:** agregar `MONGO_INITDB_ROOT_USERNAME` y `MONGO_INITDB_ROOT_PASSWORD` a un volumen ya inicializado puede no crear usuarios automáticamente. Diseñar la transición por etapas: inspección y respaldo → alta verificada de usuarios en DB existente → habilitar autenticación → prueba con cliente restringido. Para volúmenes nuevos usar bootstrap autenticado y script idempotente; **nunca ejecutar `docker compose down -v` ni recrear el volumen sin aprobación específica**.
6. No hacer que PostgreSQL, login, Obras, Finanzas o Reportes fallen al arrancar solo porque MongoDB esté caído. Retirar o justificar dependencia obligatoria del backend; el sincronizador sí puede depender de MongoDB saludable y reintentar.
7. En despliegue productivo: TLS sobre redes no confiables, gestión de secretos, acceso de red restringido, política de respaldos, recursos y recuperación. Local Compose no equivale a producción.

La imagen MongoDB es v8 del repositorio; antes de incorporar cambios verificar compatibilidad y versiones de PyMongo y sus transitive, fijando mínimos o rango razonable donde corresponde. No introducir URI de Atlas por defecto sin contrato y autorización.

## 5. Escritura y recuperación: proyección eventual, NO doble transacción

- Las operaciones PostgreSQL ya existentes son autoritativas. No modificar la transacción de `finalizar_turno`, crear evidencia, finalizar obra, autorizar usuarios, etc. para exigir éxito en MongoDB; no sostener locks o una transacción PostgreSQL abierta durante escritura remota.
- Dos vías complementarias:
  1. Tras confirmación de una nueva `EvidenciaTurno` en PostgreSQL, se puede emitir una señal/callback `transaction.on_commit` **best-effort** hacia un servicio idempotente, sin propagar fallos al éxito del dominio.
  2. Reconciliador recuperable `python manage.py reconciliar_documentos_mongodb` que recorre la fuente PostgreSQL por lotes/keyset y aplica `update_one(..., upsert=True)` sobre `_id` determinista.
- **No confiar solo en un high-water-mark de PK**: transacciones PostgreSQL concurrentes pueden confirmar IDs fuera de orden. El proceso periódico debe detectar y rellenar huecos (recorrido completo paginado o estrategia con prueba de cobertura equivalente).
- El reconciliador puede ejecutarse manualmente y mediante servicio independiente con cadencia configurable. Debe ser idempotente y apto para repetición después de caída entre lectura, escritura y confirmación.
- Evitar borrados de MongoDB basados en ventanas cortas o fallos temporales de consulta. La fuente `EvidenciaTurno` es de datos estables y no habilita aquí borrado de binarios. Cualquier política de borrado/protección de datos futuro requiere diseño específico.
- El comportamiento de negocio queda intacto con MongoDB inactivo: registrar nueva evidencia en PostgreSQL continúa sujeto solamente a las reglas existentes, y la proyección se pone al día cuando vuelve el servicio.
- Reconciliar debe dejar registro mínimo de `examinados`, `insertados`, `actualizados`, `fallidos`, `segundos`, última sincronización exitosa y último error sin PII. No registrar documentos completos, paths, fotos, sha256 o secretos. Un lote parcialmente fallido NO debe marcar sincronización completa.
- Incluir cancelación limpia, timeouts, backoff acotado, una instancia de reconciliación por recurso o idempotencia bajo ejecución simultánea y contención de memoria/CPU.

## 6. API de lectura y permisos

Exponer **un único endpoint de lectura** para acreditar uso funcional de MongoDB:

`GET /api/documentos-metadata/?obra=<id>&page=<n>`

**RBAC:** solo `GERENCIA` y `SUPERVISOR_OBRAS`, con JWT versionado activo, rol y sesión revalidados en PostgreSQL. `ADMINISTRATIVO_FINANZAS`, `TECNICO`, `ADMINISTRADOR_TI` → 403; identidad ausente/revocada/inactiva → 401. No conceder acceso por flags Django o claims. Esto no modifica el endpoint existente de descarga/consulta de evidencias en Obras.

- `obra` es obligatorio y debe ser un ID positivo estricto, dentro de BigInt; `page` opcional, entero positivo, tamaño fijo 25. Query duplicada/desconocida/vacía → 400. Obra ausente o inaccesible → 404 genérico según política de Obras, **validado en PostgreSQL antes de consultar MongoDB**, nunca basado exclusivamente en la proyección.
- JSON: `{"count":0,"next":null,"previous":null,"results":[],"proyeccion":"EVENTUAL","fuente_autoritativa":"POSTGRESQL"}`.
- Cada resultado contiene exclusivamente `evidencia_id`, `obra_id`, `turno_id`, `tipo_mime`, `tamano_bytes`, `creado_en`, `sincronizado_en`; ISO8601 con zona conocida. **No devolver** `_id` interno, `sha256`, `nombre_interno`, ruta de archivo, URL de archivo, usuario identificable ni binarios.
- Orden `creado_en DESC, evidencia_id DESC`; paginación estable dentro de la consulta MongoDB por solicitud, sin afirmar snapshot entre páginas. `count` y `results` reflejan la **proyección actual** y pueden estar atrasados respecto a PostgreSQL; no afirmar sincronización inmediata ni utilizar este resultado para autorizaciones de descarga.
- Si MongoDB está inaccesible o no autenticado → **503 JSON saneado** con `{"code":"proyeccion_no_disponible","detail":"..."}` y `Retry-After` razonable; **no** emitir falso `200 []`, permitir lectura anónima ni ejecutar fallback inadvertido sobre tablas de otro dominio. Si MongoDB está disponible pero aún no reconciliado → 200 con conteos reales y semántica eventual documentada.
- `HEAD/OPTIONS` con RBAC, `POST/PATCH/DELETE` 405 para autorizado, `Cache-Control: private, no-store`, `Vary: Authorization`, sin rutas públicas. Evitar N+1 contra PostgreSQL; consultar la existencia/autorización de Obra una sola vez.
- Para operaciones de archivos reales, el cliente debe seguir utilizando los endpoints oficiales existentes de Obras, no la proyección MongoDB.

**Estado técnico:** un comando `python manage.py verificar_mongodb` informa ping/autenticación, base accesible, índices, validadores, recuentos y duración, sin imprimir secretos. No crear endpoint HTTP de infraestructura pública ni permitir a `ADMINISTRADOR_TI` leer metadatos de negocio. Estado interno por logs/mando es suficiente en 012A.

## 7. Configuración de colecciones e índices

- Inicializar/proteger `fyag_documentos.documentos_metadata` por script idempotente con validador BSON `validationLevel=strict`, `validationAction=error`, campos requeridos y `additionalProperties=false` más `_id` admitido.
- `auditoria_eventos` y `alertas_eventos`: NO escribir, replicar ni activar como fuentes de negocio. Los scripts pueden mantenerlas inalteradas si ya existen; documentar estado y evitar una migración que afecte al módulo Auditoría de PostgreSQL.
- Índices idempotentes, verificables, sin reconstrucción destructiva. Si el volumen contiene documentos incompatibles, informar cuántos, obtener muestra saneada sin PII y detenerse: preservar datos y pedir autorización de migración.
- No tratar un archivo `database/*.js` como proceso automáticamente ejecutado solo por montarlo o guardarlo en Git. Crear comando/script de bootstrap controlado y documentar la ejecución real contra el contenedor.
- Registrar versión de esquema MongoDB independiente de las migraciones Django. No introducir migraciones SQL por defecto.

## 8. Arquitectura propuesta

Mantener el código aislado en un paquete claramente separado de dominio, por ejemplo `backend/apps/documentos_mongo/` o `backend/integraciones/mongodb/`; elegir y documentar una sola ubicación, sin modificar flujos financieros ni la capa ORM de Django. Separar:
- Cliente PyMongo (configuración, conexión reutilizable por proceso y cierre adecuado).
- Esquema/serialización BSON, índices y versionado.
- Fuente PostgreSQL (`EvidenciaTurno`) y transformación de proyección.
- Reconciliación y comandos de gestión.
- Consultas de MongoDB solo lectura; validar obra y permisos con PostgreSQL.
- API DRF/serializers/URLs y manejo controlado de fallos.
- Tests PostgreSQL + MongoDB real, sin degradar suites anteriores.

Documentos requeridos: `backend/docs/SPEC-012-IMPLEMENTACION.md` y `backend/docs/openapi/SPEC-012-v1.json`. Actualizar `README.md`, `.env.example` y Compose con pasos de instalación, operación y rollback **sin secretos**. Asegurar CI independiente de credenciales de desarrollo, con MongoDB temporal aislado para pruebas SPEC-012; nunca apuntar tests a volúmenes persistentes del usuario.

## 9. Pruebas y criterios de aceptación

1. MongoDB 8.0 real autenticado: contenedor, conectividad PyMongo, ping/health, mínimo privilegio, credenciales inválidas, no root en Django.
2. Bootstrap: índices y validadores idempotentes; inicialización segura con volumen nuevo y **procedimiento no destructivo** para volumen previo; rechazar datos previos incompatibles sin borrarlos.
3. Materializar registros `EvidenciaTurno` reales de pruebas en MongoDB; comparar IDs, BSON UTC, mime, tamaño, obra/turno, versión; no crear evidencias ficticias en BD de desarrollo.
4. Reconciliación repetida no crea duplicados; caída durante lote seguida de retry completa sin pérdidas y sin escribir negocios PostgreSQL.
5. Simulación de commits PostgreSQL fuera de orden: ningún ID atrasado se pierde por marca de avance.
6. Mongo caído: PostgreSQL, login, Obras/Finanzas/Auditoría/Alertas/Dashboard/Reportes siguen operativos; API Mongo devuelve 503 seguro; recuperación vuelve a sincronizar.
7. Matriz 401/403/404/405, JWT expirado/revocado, rol persistido, `HEAD/OPTIONS`, query estricta, Obra desconocida, 25/page, orden estable, `count`, sin rutas/nombres privados/sha256.
8. Verificación de esquema BSON, índices, plan de lectura real, consumo de memoria y operaciones por lotes.
9. Métricas/correlación sin PII, secretos, archivos, fotos ni trazas sensibles.
10. `manage.py check`, `makemigrations --check --dry-run`, suites PostgreSQL existentes sin regresiones, pruebas Mongo reales en CI con servicio aislado y Postman de endpoint autorizado.
11. Datos de negocio no se escriben dos veces en modo transaccional; Mongo no reemplaza fuente de verdad.
12. `docker compose down`/reconstrucción no borra volúmenes; rollback restablece rutas/worker/config previos sin tocar datos PostgreSQL ni eliminar MongoDB almacenado.

**Definición de terminado:** conexión autenticada real, colección derivada validada, reconciliador demostrado, endpoint DRF consultando MongoDB con RBAC, recuperación sin degradar PostgreSQL, pruebas Mongo/PostgreSQL, CI y Postman aprobados y PR de código integrado con autorización expresa. Tener el contenedor levantado o haber creado colecciones vacías NO basta.

## 10. Seguridad y decisiones pendientes de implementación

- **Prioridad crítica:** configurar autenticación y cerrar el puerto MongoDB expuesto antes de habilitar acceso habitual a este servicio.
- Como `mongo_data` puede contener datos de otro integrante, **nunca autorizar limpieza de volúmenes como remedio automático**.
- Elegir una estrategia robusta de creación de usuario no-root compatible con volúmenes existentes, comprobando sus credenciales sin mostrarlas. Debe poder recuperarse el servicio si MongoDB deja de estar disponible.
- La información eventual/documental no reemplaza permisos persistidos ni puede aprobar decisiones operativas.
- Mantener separados scripts de `auditoria_eventos`/`alertas_eventos`; su futura sincronización requiere contrato adicional.

## 11. Flujo de trabajo y gobierno Git

1. Esta propuesta vive en un PR **solo documental**. Revisar y fusionar exclusivamente tras autorización explícita del responsable.
2. Con `main` actualizado, crear rama nueva `feature/backend-012-mongodb`.
3. OpenCode lee esta SPEC, modelos/permiso/servicios y los tres scripts `database/`; antes de tocar MongoDB real debe **inventariar el volumen y sus colecciones** y advertir si existen datos.
4. Implementar y probar **sin borrados destructivos**. Entregar informe previo a commits/push/PR; ChatGPT revisa cambios y seguridad. No elevar la funcionalidad como integrada hasta superar CI y Postman.
5. Publicación/merge de implementación solo con autorización expresa; luego PR documental de estado integrado.

**Fuera de alcance:** migración de PostgreSQL a MongoDB, replicación financiera, almacenamiento de fotos, documentos públicos, Atlas o cloud no solicitado, cambios de UI, reportes desde MongoDB, sistemas de colas complejos no justificados, exportaciones en Mongo, y auditoría/alertas replicadas sin aprobación.

## 12. Fuentes comprobadas

`compose.yaml`, `.env.example`, `backend/requirements.txt`, `backend/config/settings.py`, `database/{init_mongodb.js,indices_mongodb.js,validaciones_mongodb.js}`, `backend/apps/obras/models.py` (`EvidenciaTurno`), `backend/apps/obras/views.py` (permisos/querysets), `backend/apps/alertas/{models.py,services.py}`, `backend/apps/auditoria/{adapters.py,services.py}`, `README.md` y SPEC-008 a 011.

Este documento describe un contrato propuesto para SPEC-012; no afirma que MongoDB haya sido integrado funcionalmente ni que el usuario haya aprobado cambios de datos o infraestructura.
