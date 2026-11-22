# SPEC-023A — Chat REST temporal y archivos privados

Base obligatoria `main` `13fcf1417ba5859ab306f0e63a8f8b2382d80277`.
Rama `feature/backend-023a-chat-rest-adjuntos`. Solo fase A: sin WebSocket,
Redis, `/api/chat/conexion/`, cloud ni cambios de frontend/SPEC. PostgreSQL es
fuente oficial; Mongo no almacena chat. No modifica contraseñas, JWT, bloqueos,
modelos de negocio ni migraciones históricas.

## Modelo y migraciones

Aplicación independiente `apps.chat`, con separación de consultas, validación,
servicios, permisos, almacenamiento, parsers, vistas y mantenimiento.

| Modelo | Responsabilidad |
| --- | --- |
| ConversacionChat | DIRECTA/GRUPAL, título solo grupal, creador/fecha servidor. Par directo menor/mayor calculado por servidor, índice único por par no ordenado. Sin edición. |
| ParticipanteChat | Membresía fija única conversación/usuario, fecha y watermark individual nullable. Grupo 3–20 incluyendo creador; directa exactamente los dos integrantes del par. |
| MensajeChat | Autor real, texto 0–2000, fechas servidor/UTC, vencimiento congelado, UUID/huella. Contenido obligatorio: texto, un archivo o ambos. Append-only hasta su purga por expiración. |
| ArchivoChat | Metadata SQL, clave UUID aleatoria, nombre/MIME validados, tamaño/SHA256 y mensaje OneToOne. Nunca bytes en PostgreSQL. Estados RESERVADO/PUBLICADO/RETIRAR. Recibo durable antes del primer byte. |
| ActoChat | Recibo de idempotencia por autor/acción/UUID, resultado y huella normalizada. Tras purgar mensaje conserva exclusivamente una tumba sin texto, hash de contenido ni ID de mensaje, para no republicar un replay vencido. |
| CupoChat | Contadores técnicos por minuto, claves HMAC usuario/IP/acción. No almacena IP en claro, cuerpos ni tokens. Ventanas antiguas eliminadas por mantenimiento. |

`chat.0001_initial` añade tablas, constraints e índices: par directo, miembros,
UUID, conversación/cursor, fecha de vencimiento y objetos pendientes.
`chat.0002_integridad_chat` añade triggers de originales/membresías fijas,
mensajes/archivos/recibos, cursor monotónico y comprobaciones diferidas de grupo,
creación auditada y contenido. Una inserción SQL no participante, un grupo
incompleto, un mensaje vacío/sin recibo, una edición o archivo añadido después
de confirmar el mensaje fallan. La purga SQL solo puede retirar mensajes
realmente vencidos, dejando primero las referencias de retiro.

No hay backfill ni escrituras en otras apps. La migración nueva depende del
usuario swappable, sin imponer una hoja tardía de Usuarios que cambie los
estados de sus migraciones históricas. Sus funciones de seguridad se ejecutan
con el esquema vigente al operar la aplicación. Reversión bloqueada si hay
conversaciones u objetos pendientes; preservar backup y recibos, no retirar
validadores con historia. Upgrade limpio compara Usuarios exactamente; la
regresión conserva las pruebas históricas de inventario, costos, adjuntos y
asociaciones de usuarios.

## Permisos y privacidad

Los seis roles acceden bajo **la misma regla de membresía**, sin privilegios de
TI/Gerencia/staff/superuser. JWT, actividad, sesion_version, credencial PERSONAL
y política operativa persistida se reutilizan; se releen después de esperas y
antes de confirmar. Un cambio entre roles válidos no concede acceso a otra
conversación; una revocación efectiva de sesión/credencial/actividad lo impide.

Cada lista, ficha, historial y archivo se limita por membresía SQL. Ajeno e
inexistente responden el mismo 404. El directorio solo incluye cuentas activas,
PERSONAL y operativas, con `id/nombre/rol`, excluyendo al propio usuario. La
elegibilidad efectiva se aplica antes de contar/paginar, con select_related de
seguridad; no informa email, teléfono, bloqueo ni credenciales. Las fichas de
conversación pueden conservar miembros históricos inactivos, sin habilitarles
acceso. No hay CRUD de participantes ni permisos sobre negocio por usar chat.

Todas las respuestas, incluidos errores y descargas, tienen:

```http
Cache-Control: private, no-store
Vary: Authorization
X-Content-Type-Options: nosniff
```

Sin registrar texto, bytes, nombres de archivo, JWT o contraseñas. Errores
inesperados de estas vistas solo producen un código técnico de correlación,
sin traceback/SQL/rutas privadas en log o respuesta. No sustituye la política
operativa de logs de un futuro proxy/APM. Mantener DEBUG desactivado fuera del
laboratorio y no habilitar CORS wildcard, exposición media/static o HTTP no
local; HTTPS/proxy productivo sigue fuera de esta entrega.

## API real y consumo frontend

Contrato verificable: `openapi/SPEC-023A-v1.json`. Prefijo `/api/chat/`:

| Método | Ruta | Resultado |
| --- | --- | --- |
| GET | `usuarios/?buscar=&page=` | Directorio elegible mínimo, ID ASC, 25/página |
| GET/POST | `conversaciones/` | Propias paginadas / crear o recuperar directa; crear grupo |
| GET | `conversaciones/{id}/` | Ficha, miembros mínimos, no_leidos y watermark propio |
| GET | `conversaciones/{id}/mensajes/?antes_id=` | Vigentes ID DESC, máximo 25, cursor exclusivo |
| POST | `conversaciones/{id}/mensajes/` | Publicar texto |
| POST | `conversaciones/{id}/archivos/` | Mensaje con un archivo y texto opcional |
| POST | `conversaciones/{id}/leido/` | Avanzar solo watermark propio |
| GET | `archivos/{id}/descargar/` | Bytes privados autenticados y verificados |

No `/conexion/` hasta 023B. No búsquedas de contenido, edición de mensajes,
cambios de título/membresía ni eliminación individual.

Ejemplos con IDs y UUID obtenidos localmente, no valores de negocio fijos:

```javascript
// DIRECTA (no consigo mismo). Conservar la UUID ante respuesta perdida.
{tipo: "DIRECTA", destinatario: destinatarioId, clave_idempotencia: uuidDirecta}
// GRUPAL: de 2 a 19 destinatarios distintos; excluir al actor, que añade servidor.
{tipo: "GRUPAL", titulo: "Equipo de trabajo", participantes: destinatariosIds,
 clave_idempotencia: uuidGrupo}
// Texto normalizado NFC/trim. Sin controles, surrogates, campos auxiliares o fechas.
{texto: "Material disponible", clave_idempotencia: uuidMensaje}
// Lectura naturalmente idempotente; no requiere UUID.
{ultimo_mensaje_id: ultimoMensajeVisibleId}
```

JSON cerrado; claves repetidas, tipos incorrectos o campos desconocidos 400.
IDs positivos BIGINT canónicos, UUID canónica, texto hasta 2000 caracteres y
título 1–100. No aceptar el creador/autor o fechas desde cliente. JSON de
transporte acotado a 32KiB; multipart a 8MiB+64KiB. Fechas en salida UTC ISO8601.
Filtros vacíos/repetidos/desconocidos y ceros iniciales en IDs/página: 400.

GET historial responde `{results: [...], siguiente_antes_id: idOnull}`. Los
mensajes contienen `id/conversacion/autor/texto/creado_en/vence_en/archivo/
clave_idempotencia`; `archivo` es null o `{id,nombre,mime,tamano_bytes}`. Nunca
incluye clave interna, ruta o hash. La ficha agrega miembros mínimos y solo el
cursor del actor. No_leidos deriva de mensajes **vigentes de otros autores**
con ID mayor que el watermark, en una consulta SQL sin N+1 por mensaje.

Frontend: invertir visualmente DESC si desea; deduplicar por ID, cargar páginas
antiguas con cursor y refrescar recientes sin cursor mediante polling moderado
en fase A. Mantener UUID estable al reintentar y mostrar estados 429/503 sin
inventar confirmación. Texto siempre en `textContent`, no innerHTML o Markdown
confiable; secuencias parecidas a HTML son texto literal, no formato ejecutable.

Para archivo usar FormData con `archivo` y `texto` opcional, encabezado
`Idempotency-Key: <UUID>` y Authorization. No poner UUID en multipart ni fijar
Content-Type/boundary manual en navegador. Para descargar hacer fetch con Bearer
y usar Blob temporal; no convertir IDs en URLs públicas ni persistir JWT en URLs.
Respetar Content-Disposition attachment, nombre saneado y revocar ObjectURL.

| HTTP | Semántica |
| --- | --- |
| 201 | Conversación/mensaje nuevo |
| 200 | Consulta, lectura, replay vigente o pareja directa ya existente |
| 400 | Body/query/ID/UUID/Unicode/formato/contenido inválidos, malware |
| 401 | JWT/sesión/cuenta/credencial/bloqueo no operativos |
| 404 | Recurso ajeno/inexistente, mensaje o archivo no visible, página inexistente |
| 405 | Método no publicado |
| 409 | idempotencia_conflictiva, mensaje_caducado o estado_incompatible |
| 413 | Límite de transporte/archivo |
| 429 | Cuota técnica; esperar Retry-After |
| 503 | Scanner/almacén/integridad física/infraestructura no disponibles, sin detalles internos |

Cuotas por minuto, configurables en `settings.CHAT_LIMITES`: usuario/IP de
conversaciones 10/30, texto 60/180 y archivos 10/30. PostgreSQL y mutex corto
2302 garantizan consistencia multiproceso; se libera antes de recursos de chat.
Se usa REMOTE_ADDR, nunca un X-Forwarded-For no autenticado. Un futuro proxy
deberá resolver IP confiable explícitamente; múltiples usuarios detrás de NAT
comparten cuota IP. Replays también consumen cuota de transporte. Las pruebas
ajustan settings sin desactivar mecanismos en ejecución real.

## Archivos, seguridad y fallos intermedios

Raíz propia `FYAG_CHAT_ARCHIVOS_ROOT` (default `/var/lib/fyag/chat`), nunca media,
static, ADJUNTOS_ROOT o EVIDENCIAS_ROOT. La capa rechaza raíces relativas,
solapamientos con otros almacenes y componentes symlink. POSIX dentro de Docker:
dirfd/O_NOFOLLOW, directorios 0700 y ficheros 0600; no degradar a accesos inseguros
en Windows nativo. Staging y publicados propios, nombres UUID impredecibles.
Publicación hardlink no-clobber con fsync y comprobación de identidad del inode.
Descarga abre regular file sin symlinks, comprueba tamaño/SHA256 y copia a un
temporal privado antes de responder; falta/alteración falla cerrada.

| Formato | Límite | Validación |
| --- | --- | --- |
| JPEG/PNG | 5MiB; <=2048×2048 | Firma, framing/chunks/CRC, sin trailing/polyglot/ZIP, Pillow verify/load, límites/bombas, una imagen estática. Se reescribe sin metadatos/EXIF y sin escalar ni cambiar proporción. Dimensiones superiores se rechazan. |
| PDF | 8MiB | Firma/EOF, no ZIP, inspector pypdf en subproceso con memoria 256MiB, CPU 5s y timeout 8s. Rechaza cifrado, acciones/scripts, adjuntos embebidos, estructuras corruptas y complejidad excesiva. Máximo 100 páginas, 2000 referencias, streams acumulados 16MiB. |
| DOCX/XLSX | Deshabilitados | No existe validador OOXML seguro aprobado para expansiones, relaciones externas y contenido activo. No se habilitan por extensión/MIME ni como ZIP genérico; el contrato permite esta restricción explícita. |

El MIME se detecta de bytes reales, no del declarado. Se conserva extensión
compatible y nombre visible saneado hasta 150, sin rutas/controles/bidi. Se
reutilizan **solo primitivas sin modificación** de SPEC-012B: framing PNG/JPEG,
inspector PDF acotado (recibe un FD ya abierto) y cliente ClamAV INSTREAM. No se
usa AdjuntoDocumento ni su almacenamiento/metadata/historia. PDF o imagen
sospechosos abortan; scanner ausente/error/límite de inspección es fail-closed.
Se analiza original antes de sanitizar, y también imagen normalizada, para no
sanear malware y aceptarlo inadvertidamente. ClamAV no recibe rutas/volúmenes.

Protocolo recuperable DB/FS:

1. Validar sesión, scope y entrada; confirmar `ArchivoChat RESERVADO` antes de
   escribir un byte. Caller sin transacción externa/ATOMIC_REQUESTS, para que
   ese recibo sobreviva a rollback o SIGKILL.
2. Bloquear recibo reservado; staging, límites, estructura y escaneo. Solo luego
   tomar UUID/mutex de publicación y conversación; revalidar sesión.
3. Crear mensaje, enlazar archivo PUBLICADO y recibo de idempotencia, publicar
   inode verificado. Confirmar transacción con checks diferidos de contenido.
4. Limpiar hardlink staging. Si falla después del commit, **mantener éxito** y
   dejarlo al recolector. No falsear un 500/503 de mensaje no guardado.
5. Fallo antes de commit: compensar únicamente recibo propio RESERVADO→RETIRAR,
   retirar staging/publicado y borrar recibo **después** de fsync. Si falla
   retiro, conservar referencia durable y reintentar. Nunca retirar PUBLICADO
   si la confirmación de commit fue ambigua. Un replay resuelve el resultado.

Una repetición puede crear staging/recibo provisional propio para verificar los
bytes originales, pero lo retira; nunca crea otro objeto confirmado. El namespace
fija autor/acción; su huella incluye conversación/tipo/texto/nombre normalizados
y SHA256 original. No sobrescribe el archivo previo. Tras caducar,
replay devuelve 409 y no vuelve a publicar ni permite acceso al original.

## Idempotencia, locks y lectura

Namespace DB de recibos: **autor + acción CONVERSACION|MENSAJE + UUID**. Texto y
archivo comparten acción MENSAJE. Otra carga dentro del mismo namespace: 409;
distintos autores/acciones tienen namespaces independientes. Las claves del
cliente no determinan la pareja directa. 201/200 y header Idempotency-Replayed
false/true distinguen efectos; pareja existente usa 200/true incluso con UUID
nueva, guardando su recibo. Metadata actual de conversación puede cambiar.

Locks: advisory UUID2300 → par2301 si directa → conversación → participante/
mensaje/archivo publicado. Una sola clave por namespace; no advisory después
de conversación o sus recursos compartidos. Los uploads adquieren antes su recibo **RESERVADO exclusivo y no
visible** para escanear, luego UUID/conversación. Descarga/purga solo toman
recibos PUBLICADO de mensajes ya confirmados, por lo que no hay dependencia
inversa sobre el mismo recurso. Reservas abandonadas se toman con skip_locked.
No locks de negocios/Obras/stock ni de Usuarios después de raíz; sesión releída
tras esperas. Creación directa inversa serializada e índice único de respaldo.

Cursor de lectura es un **watermark ordinal BIGINT**, no FK a desreferenciar:
la purga no lo pone null ni permite retroceso. Solo se avanza validando mensaje
vigente de esa conversación y bloqueando conversación/participante. Un ID de
otra conversación, futuro o inexistente es 404, no permite adelantar a ciegas.
Si expira el mensaje que originó el watermark, se conserva el umbral; IDs de
secuencia nuevos no se reciclan. No hay confirmación individual por destinatario.

## Retención, purga y Docker local

`FYAG_CHAT_RETENCION_DIAS`: default 30, entero 1–90, validado al arrancar. Se
congela vence_en al publicar; cambios aplican a mensajes nuevos, sin reescribir
historia. Vencidos se excluyen inmediatamente de historial, descarga y contadores.

```shell
python manage.py purgar_chat --dry-run
python manage.py purgar_chat --once
python manage.py purgar_chat --continuo
```

Un modo explícito es obligatorio. Dry-run no cambia SQL/FS. Once ejecuta un paso
acotado (hasta 250 conversaciones y 250 mensajes por conversación; 250 objetos
por fase). Las cifras JSON son candidatos anteriores al paso y fallos, no una
promesa de filas efectivamente eliminadas si hay concurrencia. Continuo repite
con `FYAG_CHAT_PURGA_INTERVALO` (default 3600s, 60–86400), reconecta DB y maneja
SIGTERM/SIGINT con salida controlada, sin locks dentro del signal handler. Un
error no pierde referencias ni imprime excepciones o datos sensibles.

Primero lock conversación con skip_locked y DELETE exclusivamente vencidos.
El trigger retira el vínculo a Archivo, lo marca RETIRAR y elimina el hash/ID
de mensaje del recibo idempotente en la misma transacción. Después se eliminan
bytes por UUID/dirfd bajo lock de recibo; solo al terminar se elimina la fila.
Reservas abandonadas de más de una hora se retiran con skip_locked; staging
residual de publicaciones confirmadas se limpia sin borrar archivo vigente.
Dos recolectores son seguros. Una descarga bloqueada/activa se omite y se
reintenta; una descarga autorizada iniciada vigente puede terminar desde su
copia privada aunque posteriormente se retire origen. No abre nuevas descargas
vencidas. No se exploran ni barren carpetas ajenas u objetos sin recibo propio.

Conversaciones, miembros, watermarks y tumbas mínimas de UUID quedan para
continuidad/idempotencia; se purgan texto/archivo/metadata de contenido, no se
promete eliminar identificadores de conversaciones ni backups/WAL fuera de sus
ciclos. Revisar política operativa de privacidad/backup antes de usar datos reales.

`compose.yaml` añade volumen **chat_data** independiente al backend y servicio
`chat_purgador` bajo profile **chat-mantenimiento**, no habilitado por defecto.
Solo monta código readonly y ese volumen, sin volúmenes de adjuntos históricos.
Depende de migraciones/PostgreSQL; no requiere Redis/Mongo o scanner para purgar.
Ejecutar primero dry-run sobre QA; solo tras autorización de retención habilitar
el profile local. No se ejecutó sobre datos institucionales ni se reiniciaron
contenedores preexistentes. `.env` no se modifica; `.env.example` añade variables.
QA standalone conserva tmpfs independiente `/qa/chat` y servicios exclusivos.

## QA y contratos

Proyecto exclusivo `fyag-spec023a-20261121`, PostgreSQL 18, Mongo/ClamAV QA;
credenciales efímeras fuera del repositorio. Código montado readonly. No usar
compose principal ni bases/volúmenes de usuarios para pruebas. Ejecución:

```shell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py migrate --noinput
python manage.py test apps.chat apps.usuarios.tests.test_migracion_006 --noinput
python manage.py test --noinput
```

Pruebas permanentes en `apps/chat/tests`: contratos/configuración, seis roles,
IDOR, credenciales/bloqueos/sesiones, no-leídos/cursor, integridad SQL, upgrade,
concurrencia con PostgreSQL real, scanner real PNG/PDF/EICAR/indisponibilidad,
imágenes corruptas/bombas/animación, PDF cifrado/activo, symlinks, fallos de
publicación/commit/retirada, replays y retención. Pruebas unitarias de formato
usan scanner stub explícito; no acreditan AV. Las pruebas de integración y
Newman usan el ClamAV real aislado, sin desactivar la política fail-closed.

El primer pase completo detectó dependencia tardía incompatible con prueba
histórica de Usuarios; se corrigió exclusivamente en migración nueva. La prueba
operativa SIGTERM detectó el uso de Event en handler; se reemplazó por interrupción
controlada, conservando referencias para reintento. Ambos hallazgos se verifican
de nuevo antes de publicación, sin modificar pruebas o módulos históricos.

Newman: **33 solicitudes, 175 aserciones, 0 fallos**. OpenAPI 3.1/referencias
válidos; **32 respuestas JSON + 1 binaria**, **8 cuerpos JSON + 4 multipart**
conformes. Purgador QA real: primer ciclo correcto y SIGTERM con **exit 0**,
sin errores. Los resultados manuales de compañeros no bloquean implementación.

Resultados finales verificados:

| Verificación | Resultado |
| --- | --- |
| Django check | 0 problemas |
| makemigrations --check --dry-run | Sin drift |
| PostgreSQL limpio y upgrade conservador | OK |
| Suite específica de Chat final | 59 pruebas OK, 8.395 s |
| Chat + migración histórica 006 Usuarios | 60 pruebas OK, 10.690 s |
| Backend completo final | **1328 pruebas OK, 360.532 s** |
| Pruebas nuevas permanentes de Chat | 59 |
| Carreras PG con bloqueo observado | 11 aprobadas, incluida doble carga de archivo |
| Descarga/purga con skip_locked y copia estable | Aprobada |
| ClamAV real | PNG/PDF aceptados; EICAR rechazado; indisponibilidad cerrada |
| Compose local | config --quiet válido; profile institucional no iniciado |

Colección `postman/SPEC-023A.postman_collection.json`, compatible con environment
FYAG-Beta existente: base_url y variables locales legibles de tres usuarios,
sus IDs y rutas a fixtures PNG/JPEG/PDF/DOCX rechazado. Ningún token/ID real o
Vault en Git. Conservar UUID por reintento; repetir usa la misma pareja directa
y grupos nuevos, sin conteos globales ni IDs fijos. Respetar cuotas entre pases.

## Limitaciones y continuidad 023B

- DOCX/XLSX no habilitados; requieren validación OOXML segura y revisión propia.
- Almacén POSIX local; no degradación insegura a Windows nativo o cloud.
- Membresía/título fijos, texto plano y máximo un archivo. Sin indicadores de
  conexión, ticket, eventos de negocio o confirmaciones individuales.
- Directorio evalúa la elegibilidad operativa antes de paginar; apropiado para
  la escala Beta, sin búsqueda global de mensajes ni optimización para millones
  de cuentas. Cuotas IP pueden compartir NAT; revisar proxy cuando corresponda.
- No garantía de borrado inmediato de backups/WAL. Tumbas mínimas de UUID sin
  contenido son necesarias para impedir republicación tras retención.
- No activar recolector sobre datos institucionales sin autorización/backup.
- 023B puede añadir avisos solo post-commit y ASGI/Redis sin sustituir REST,
  cursores o almacén oficial. No se inició automáticamente esa fase.
- Sin contradicción material que obligue editar SPEC. CI del futuro PR queda
  pendiente; no se declara aprobado ni se crea PR/merge/despliegue.
