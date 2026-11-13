# SPEC-012B — Adjuntos documentales privados de Obras y Finanzas

**Estado: PROPUESTA CONTRACTUAL DOCUMENTAL, PENDIENTE DE APROBACIÓN.**
**Base:** main en e2f29cf96cbb4e6bc507ed1b2e1dd5c9f2af348b, posterior a SPEC-012A / PR #41.
**No implementada:** este documento no altera contenedores, bases, archivos locales, credenciales, migraciones ni APIs.

## 1. Objetivo y alcance

Incorporar carga, listado, detalle, descarga privada y anotaciones para dos tipos de archivos:
- **RESPALDO_FACTURA:** escaneo o copia PDF/JPEG/PNG asociado a un DocumentoCobro externo registrado.
- **INFORME_TECNICO:** PDF/JPEG/PNG asociado a una Obra.

Situación comprobada: DocumentoCobro.referencia_respaldo y PagoDocumento.referencia_respaldo son referencias textuales, NO archivos; no existe subida de escaneos. EvidenciaTurno ya guarda fotos en volumen privado, con sus metadatos editables en MongoDB SPEC-012A. No modificar ese flujo.

**Autoridades:** PostgreSQL = existencia, parentesco, actor, roles, estado y datos técnicos de cada adjunto; MongoDB = descripciones, etiquetas y atributos variables; almacenamiento privado = bytes. Nunca duplicar archivos en PostgreSQL, MongoDB o GridFS. Los archivos adjuntos NO emiten DTE, no verifican SII, no representan nuevos cobros y no modifican montos, folios, estados ni pagos.

## 2. Registro PostgreSQL

Agregar modelo relacional propio AdjuntoDocumento mediante migración Django nueva, sin modificar tablas o migraciones ya integradas:
- id BigAutoField; tipo enum RESPALDO_FACTURA / INFORME_TECNICO.
- documento_cobro FK PROTECT opcional; obra FK PROTECT opcional; exactamente una debe ser no nula y coincidir con el tipo.
- nombre_visible saneado, sin segmentos de ruta/controles, solo para respuesta y Content-Disposition; clave_interna UUID/aleatoria opaca única (no serializarla).
- mime servidor, tamano_bytes, sha256 hash de bytes finales, estado de seguridad DISPONIBLE cuando todas las comprobaciones finalizaron.
- registrado_por FK PROTECT, registrado_en fecha servidor.
- clave_idempotencia UUID, huella_solicitud hash de tipo, destino y archivo para evitar carga repetida accidental.
- Restricciones SQL CHECK/unicidad para campos enumerados, parent exclusivo, tamaño, digest y claves; índices de orden por destino/registrado_en/id.
- Corroborar relación y estado de documento/obra y permisos **bajo lock** de los registros necesarios. No confiar en IDs o tipo del cliente.

**Invariantes:** no reemplazar ni eliminar físicamente adjuntos vía 012B; corregir agregando uno nuevo. DocumentosCobro revertidos conservan archivos históricos para lectura autorizada, pero no reciben nuevas subidas. No crear archivos retrospectivamente a partir del campo referencia_respaldo. No declarar un archivo existente por tener solamente ese string.

Una Idempotency-Key UUID en cada alta: replay idéntico devuelve mismo ID y 200; clave con payload diferente 409. Concurrencia y colisiones de archivo/SQL no pueden crear dos adjuntos disponibles. Registrar de modo seguro errores y rollback.

## 3. Almacenamiento, tipo real y análisis de archivos

- Volumen persistente separado **adjuntos_data**, raíz configurable FYAG_ADJUNTOS_ROOT, fuera de static/MEDIA_URL y sin publicación directa Docker; evidencias_data preexistente no se modifica.
- Un archivo por POST, subido por multipart/form-data campo archivo; máximo PDF 8 MiB o PNG/JPEG 5 MiB, imágenes hasta 12 millones de píxeles. Rechazar vacíos, falsificaciones de tipo, payloads truncados, MIME engañoso, nombres maliciosos, archivos poliglota, SVG, ZIP, DOC, HTML, ejecutables y cualquier formato no contratado.
- Validación real de imágenes mediante Pillow con decodificación y copia de píxeles para eliminar EXIF/GPS/metadata; hash posterior al saneamiento.
- PDF: biblioteca mantenida de inspección estructural, firma/cabecera real, límite de complejidad; rechazar cifrado, JavaScript, acciones automáticas, archivos incrustados y PDFs malformados. No reescribir PDF firmado para no invalidar su firma; si no puede validarse de forma segura, rechazarlo.
- **Política antimalware obligatoria y fail closed**: integrar un escáner real privado, por ejemplo clamd, con timeout/límites. Contenido malicioso o sospechoso no se publica; scanner inactivo/timeout => subida falla con 503 y rollback sin fila DISPONIBLE ni archivo accesible. La disponibilidad del scanner no condiciona login, Finanzas, Obras ni descargas de archivos ya aceptados. No afirmar que MIME o una extensión equivalen a antivirus.
- Flujo seguro: autorización y destino SQL → lectura acotada en streaming → staging privado → validar/sanear → hash bytes finales → escanear bytes finales → archivo privado opaco → commit SQL → limpieza de staging. Diseñar proceso de diagnóstico de huérfanos (dry-run por defecto), para las fallas entre filesystem y commit; no prometer transacción distribuida.
- Usar permisos restrictivos; proteger contra path traversal/symlinks; descarga únicamente por endpoint autorizado, con Content-Disposition attachment, Content-Type permitido, Cache-Control private,no-store, X-Content-Type-Options nosniff y Vary Authorization. No rutas, keys internas ni URLs de descarga firmadas en JSON.
- Acotar hasta 10 adjuntos por documento/obra en 012B (revisable por contrato posterior). Sin borrado automático, ni siquiera al revertir DocumentoCobro. La retención legal se evaluará después.

## 4. RBAC de 012B

| Función | GERENCIA | SUPERVISOR_OBRAS | ADMINISTRATIVO_FINANZAS | TECNICO | ADMINISTRADOR_TI |
|---|---|---|---|---|---|
| Respaldo factura, subida | No | No | Sí, documento VIGENTE | No | No |
| Respaldo factura, listar/ver/descargar | Sí | No | Sí | No | No |
| Respaldo factura, editar notas Mongo | Lectura | No | Sí | No | No |
| Informe técnico, subida | No | Sí | No | Sí, miembro activo EN_PROCESO | No |
| Informe técnico, listar/ver/descargar | Sí | Sí | No | Solo miembro activo de la Obra | No |
| Informe técnico, editar notas Mongo | Lectura | Sí | No | Solo miembro activo de la Obra | No |

Supervisor puede adjuntar informes cuando Obra esté EN_PROCESO, SUSPENDIDA o FINALIZADA. Técnico solo cuando EN_PROCESO y participe activamente. Técnico desasignado pierde acceso incluso si fue quien lo adjuntó. Gerencia lee pero no muta. AF no obtiene acceso a informes técnicos por las rutas de Finanzas. ADMINISTRADOR_TI no se habilita por is_staff o is_superuser.

Cada petición comprueba token JWT versionado y usuario/rol/actividad/membresía en PostgreSQL antes de abrir archivo o consultar Mongo. No hay privilegios por conocer un ID. Rechazo 401/403/404 según el contrato de seguridad existente.

## 5. API DRF de 012B

Prefijo nuevo /api/adjuntos/, sin colisión con las rutas actuales:
- POST /api/adjuntos/documentos-cobro/{id}/ — subir respaldo factura.
- GET /api/adjuntos/documentos-cobro/{id}/ — listar adjuntos de documento financiero.
- POST /api/adjuntos/obras/{id}/ — subir informe técnico.
- GET /api/adjuntos/obras/{id}/ — listar informes técnicos.
- GET /api/adjuntos/{id}/ — detalle SQL, sin hash o clave física.
- GET /api/adjuntos/{id}/descargar/ — descarga privada.
- GET /api/adjuntos/{id}/anotaciones/ — notas Mongo.
- PATCH /api/adjuntos/{id}/anotaciones/ — editar notas Mongo con revisión CAS.

POST: multipart/form-data obligatorio, un archivo bajo campo archivo y nombre_visible opcional; Idempotency-Key UUID requerida; tipo/destino exclusivos de la URL; rechazar URL remota, base64, JSON binario, campos inesperados, duplicados y múltiples archivos. 201 inicial, 200 replay. Respuesta SQL con id,tipo,destino,nombre_visible,mime,tamano_bytes,estado,registrado_por,registrado_en. No exponer sha256, clave interna ni paths.

Listados SQL: paginación 25 fija, orden registrado_en DESC/id DESC, count/next/previous/results. Mongo inaccesible no bloquea listado SQL ni descarga; metadata flexible pendiente retorna 409 y Mongo inactivo retorna 503. HEAD/OPTIONS respetan RBAC.

Errores saneados: 400 entrada inválida, 401 sesión inválida, 403 prohibido, 404 recurso SQL, 405 método, 409 idempotencia/estado/CAS, 413 tamaño, 415 medio no soportado, 422 contenido rechazado, 503 scanner o Mongo según endpoint. No eco de bytes, rutas, contenidos, nombres privados o credenciales.

## 6. MongoDB sin interferir con SPEC-012A

Crear **colección nueva fyag_documentos.adjuntos_metadata**, validador JSON Schema/BSON estricto e idempotente, _id determinista adjunto:{id}, versión esquema 1. Nunca cambiar ni resetear la colección documentos_metadata de fotografías.

El espejo técnico deriva de SQL (id/tipo/destino/mime/tamaño/fecha). Anotaciones Mongo: descripcion, etiquetas, atributos técnicos permitidos y revisión CAS, misma filosofía de 012A: longitud hasta 1000, 12 etiquetas de 40, hasta 12 pares simples y 4 KiB JSON, sin operadores, HTML, enlaces, RUT, identificadores personales, montos, fechas financieras o contenido OCR. Mantener vocabulario específico para cada tipo y no copiar nombres visibles ni contenido de archivos en BSON.

Bootstrap autenticado e idempotente y usuario aplicación de mínimo privilegio sobre ambas colecciones, sin root/delete/drop/collMod en runtime. Comando/worker reconciliar_adjuntos_mongodb por lotes 200, recorrido repetible sin watermark irreversible, $set técnico solamente y $setOnInsert notas para preservar ediciones. Leer y editar notas tras validar la fila SQL del adjunto y sus relaciones. Edición CAS 409 si revisión vieja, sin modificar archivo ni registro SQL. Reconciliación eventual: POST SQL puede triunfar con Mongo caído; proyección aparece al recuperar Mongo. Aislar fallos de 012A y 012B por colección.

## 7. Seguridad, recuperación y operaciones

- Nunca tocar los volúmenes ya existentes postgres_data, mongodb_data, evidencias_data para limpiar o recrear; añadir adjuntos_data persistente.
- Evitar import side effects, escrituras Mongo bajo atomic PostgreSQL, y fallos del backend cuando scanner o Mongo están caídos. Scanner solo es dependencia de nuevas subidas.
- Respaldar y poder restaurar de forma coordinada **PostgreSQL + MongoDB + adjuntos_data**. La restauración aislada de SQL no recupera notas Mongo ni los archivos, y una restauración Mongo no reconstruye la relación SQL.
- Controlar volumen/disco, hash de almacenamiento y faltantes; jamás servir archivos ausentes o con hash inesperado. Diagnóstico de archivos huérfanos sin borrado automático.
- Logs seguros: actor ID, adjunto ID, tipo de evento, resultado y correlación; no tokens, datos del archivo ni texto documental. Los logs operativos no equivalen a auditoría inmutable.
- Producción/cloud, object storage y políticas comerciales se documentarán después. No habilitar ahora endpoints públicos o servicios externos de pago.

## 8. Pruebas obligatorias

1. Subida real de PDF válido a DocumentoCobro vigente; subida PNG/JPEG saneada a Obra; GET listado/detalle y descarga de bytes originales PDF / normalizados imagen.
2. Matriz de los cinco roles con JWT versionado, actividad, cambios de rol, pertenencia activa/inactiva y pruebas IDOR cruzando obras y documentos.
3. Archivos corruptos/truncados, MIME falso, PDF activo/cifrado, EXIF, zip bomb/pixel bomb, límite de bytes, doble field y filename traversal: rechazo seguro, sin fila visible.
4. Motor antimalware de QA real (inocuo y EICAR), fallo/timeout scanner: rechazo fail closed y datos SQL/archivo sin duplicados. Nunca abrir puertos del scanner al host.
5. Idempotencia y concurrencia: replay mismo contenido => mismo ID, clave reusada distinta carga => 409, dos solicitudes simultáneas => 1 fila/archivo.
6. Caída de disco, rollback SQL, archivo ausente/alterado y reintento: cero filas DISPONIBLE sin bytes íntegros, scanner fuera no impide descargas existentes.
7. DocumentoCobro revertido: sigue legible históricamente pero no se puede añadir; montos, estado, folio y pagos inalterados.
8. Mongo autenticado con validador propio, 012A existente intacta; reconciliador idempotente que preserva notas, recuperación de commits fuera de orden, PATCH CAS concurrente.
9. Mongo caído => listados/descargas SQL y Finanzas/Obras siguen operativos; solo anotaciones 503; después de reiniciar recupera.
10. Suite regresión completa PostgreSQL/Mongo, Django check, migraciones nuevas y dry-run, CI con scanner/Mongo QA aislados, pruebas reales reproducibles y Postman importable. No tocar bases, archivos ni cuentas locales fuera de QA.
11. Postman con carga real de archivos seleccionados manualmente por el usuario en Body form-data File; evitar afirmar que el ZIP de Postman transfiere la ruta/adjunto automáticamente.
12. Test de reinicio Compose, backups y rollback sin pérdida de files, SQL, Mongo y sin cambios en 012A.

**Definición de terminado:** ambos tipos de adjunto disponibles mediante API y almacenamiento privado, permisos verificados, escaneo efectivo, integridad SQL/archivo, metadatos Mongo editables, regresión en verde, pruebas CI y Postman, merge explícitamente autorizado.

## 9. Entregables y gobierno Git

- backend/docs/SPEC-012B-IMPLEMENTACION.md y backend/docs/openapi/SPEC-012B-v1.json, con guía frontend.
- Migración Django nueva de AdjuntoDocumento, sin modificar tablas financieras existentes; tests y nuevos servicios.
- Ajustes Compose/.env.example sin credenciales, scanner QA y volumen privado adjuntos_data, bootstrap Mongo ampliado y reconciliador específico.
- Procedimiento de mantenimiento, diagnóstico, backup/restore y rollback de archivos.
- PR de implementación separado, tras aprobación de este PR **solo documental**.

**Flujo:** aprobar/fusionar esta SPEC, actualizar main local, crear rama feature/backend-012b-adjuntos, ejecutar OpenCode solo backend hasta pruebas locales, auditar código, luego commits/PR Draft autorizados, GitHub CI y Postman, y merge autorizado.

**No implementar:** OCR, emisión DTE/SII, pagos adjuntos, frontend, PDF editor, antivirus de producción cloud, subidas públicas, eliminación física automática ni modificaciones de reglas económicas.

## 10. Fuentes reales revisadas

specs/012-integracion-mongodb.md; backend/apps/documentos/; backend/apps/finanzas/models.py, permissions.py, views_documentos.py, urls.py; backend/apps/obras/evidencias.py, views_turnos.py, services_turnos.py; compose.yaml; backend/requirements.txt y backend/docs/SPEC-012-IMPLEMENTACION.md.

Esta SPEC define requisitos; no afirma que 012B esté implementada ni que el Docker local se haya verificado remotamente.
