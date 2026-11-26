# SPEC-023 — Chat interno temporal en tiempo real (FYAG Beta)

> **Estado: contrato de implementación local del backend, 21-11-2026.** Base verificada: main 8a1ca1b86b5f29a4be0e7b2b9cae30a8959e9609, tras PR #65. La retención inicial de 30 días es una decisión operativa CONFIGURABLE de la Beta local, no una autorización para aplicar borrados a datos institucionales o productivos. Esta SPEC no habilita despliegue a Render, Neon, Atlas, ni cambios del frontend.
>
> **Alcance:** Django/DRF, PostgreSQL, Django Channels/ASGI, Redis local, ClamAV y almacenamiento privado local; frontend React desarrollado exclusivamente por el equipo responsable. **Fases:** 023A (mensajería REST, archivos y retención) → 023B (eventos WebSocket, presencia de conexión y recuperación). Cada fase debe pasar pruebas y revisión antes de integrarse.

## 1. Objetivo y límites

Habilitar una ventanita de comunicación interna entre cuentas de FYAG, sin depender de correo, WhatsApp o un tercero. Conversaciones **directas** entre dos trabajadores y **grupos** pequeños; textos, imágenes y documentos; mensajes nuevos visibles casi al instante cuando exista conexión WebSocket. PostgreSQL es la fuente oficial de conversaciones, mensajes, membresías, cursores de lectura y metadatos de archivos. Redis solo distribuye eventos transitorios; no guarda mensajes ni archivos.

No es un sistema de autorizaciones, trámites o evidencia permanente. Las decisiones de Obras, Bodega, presupuestos, Finanzas, incidencias, credenciales y adjuntos documentales históricos deben seguir en sus módulos respectivos, no en el chat. No emitir alerta de negocio ni cambio de estado mediante chat.

**No incluye:** llamadas, video, cifrado de extremo a extremo, push móvil/notificaciones externas, mensajes a usuarios ajenos a FYAG, integración con correos, bots, envío masivo, mensajes editables o reversibles, búsqueda global del contenido, enlaces de descarga públicos, enlaces de previsualización remota, indicadores de actividad permanente, mensajería en MongoDB, ni cloud en esta fase. Indicador "escribiendo" y cambios dinámicos de integrantes son mejoras posteriores; no bloquear la Beta por ellos.

## 2. Roles, autenticación y acceso

1. Participan los **seis roles** existentes: GERENCIA, ADMINISTRATIVO_FINANZAS, SUPERVISOR_OBRAS, TECNICO, ADMINISTRADOR_TI y BODEGUERO. El permiso para usar chat es transversal, pero **no otorga acceso a datos de negocio ni permisos de administración de usuarios**. Un Administrador TI puede comunicarse, pero no leer conversaciones ajenas por ser TI, staff o superuser.
2. Cada petición HTTP exige JWT FYAG vigente mediante la autenticación existente, con revalidación de usuario activo, sesion_version, credencial PERSONAL y bloqueo operativo conforme a SPEC-018/018C. El rol, actividad y versión se leen de PostgreSQL, no se aceptan del cliente.
3. Solo miembros actuales de una conversación pueden ver su ficha, mensajes, contadores, descargar archivos y enviar. Una conversación ajena y una inexistente producen indistintamente 404. No se permite enumerar ID de mensajes, nombres ni adjuntos ajenos.
4. El directorio para iniciar chat lista únicamente cuentas activas y elegibles, con proyección mínima: ID, nombre/alias y rol; no expone email, estado de bloqueo, teléfono, hash ni información económica. No se incluyen cuentas inactivas ni credenciales iniciales/pendientes. Un listado de conversaciones solo muestra aquellas donde el titular sea miembro.
5. Los grupos de esta primera Beta tienen **participantes fijos desde su creación**, entre 3 y 20 personas incluyendo al creador. No hay agregar/eliminar miembros, historial retroactivo por incorporación ni transferencia de administración en 023A/B; requeriría SPEC correctiva propia. Un cambio de actividad/estado personal impide acceso de forma inmediata en nuevas solicitudes.
6. La revocación de sesión debe cerrar o desautorizar también el canal WebSocket (ver §7). Nunca asumir que un socket abierto conserva permisos.

## 3. Conversaciones y mensajes (PostgreSQL)

- ConversacionChat: ID BIGINT, tipo DIRECTA/GRUPAL, titulo solo grupal (1–100), creador, fecha servidor, sin permisos de edición de títulos. Conversación directa única por **par no ordenado de IDs** con índice/constraint DB para impedir duplicados bajo concurrencia. No usar una clave proporcionada por el cliente para identificar el par.
- ParticipanteChat: Conversacion FK, Usuario FK, incorporado_en servidor, ultimo_leido_mensaje_id nullable; unicidad (conversacion, usuario); inmutable la pertenencia en esta fase. Cada consulta filtra membresía en SQL antes de recuperar contenido.
- MensajeChat: Conversacion FK, autor FK, texto (texto plano UTF-8, no HTML; 0–2000 caracteres; mensaje texto requiere contenido no vacío), creado_en servidor, UUID idempotencia y huella SHA-256, vence_en servidor, referencia de archivo opcional. Mensaje debe contener texto no vacío, archivo o ambos; un solo archivo por mensaje. IDs BIGINT y orden estable (ID).
- ArchivoChat: mensaje uno a uno, clave interna aleatoria no derivada del nombre, nombre visible normalizado, MIME validado, tamano_bytes, sha256 y ruta privada controlada. **No reutilizar AdjuntoDocumento de SPEC-012B** ni su regla de inmutabilidad sin caducidad; los archivos de chat se eliminan junto con los mensajes.
- Cada usuario puede tener múltiples conversaciones, pero sin privilegio para inspeccionar participantes de otros grupos. No permitir enviar "en nombre de" otro usuario ni manipular autor, fecha, leído o vencimiento desde JSON.
- Los mensajes ya creados no se editan ni anulan individualmente. El historial expira de acuerdo con §8.
- Lectura: cursores de mensajes por ID (< antes_id), máximo 25, DESC; el cliente invierte visualmente si desea. Solo se sirven mensajes todavía vigentes. Contador no leído derivado de mensajes vigentes de otros autores con ID mayor que el cursor, sin usar totales históricos expirados. Marcación de lectura monotónica, solo hasta el último mensaje visible de la propia conversación. No modificar otro cursor.

## 4. API REST (023A, /api/chat/)

| Método | Ruta | Contrato |
| --- | --- | --- |
| GET | usuarios/?buscar=&page= | Directorio elegible mínimo, 25 por página |
| GET/POST | conversaciones/ | Mis conversaciones / creación |
| GET | conversaciones/{id}/ | Detalle y miembros autorizados |
| GET/POST | conversaciones/{id}/mensajes/ | Lista con antes_id / publicar texto |
| POST | conversaciones/{id}/archivos/ | Publicar un mensaje con un archivo y texto opcional (multipart) |
| POST | conversaciones/{id}/leido/ | Avanzar ultimo_leido_mensaje_id sin retroceder |
| GET | archivos/{id}/descargar/ | Archivo privado autenticado, verificación de integridad y vigencia |
| POST | conexion/ | Ticket efímero de WebSocket; se incorpora en 023B |

**Cuerpos cerrados:** crear DIRECTA {tipo:"DIRECTA",destinatario:<ID>,clave_idempotencia:<UUID>}; crear GRUPAL {tipo:"GRUPAL",titulo:<str>,participantes:[IDs distintos],clave_idempotencia:<UUID>}, el actor se agrega por servidor. Publicar texto {texto:<str>,clave_idempotencia:<UUID>}; multipart archivo usa encabezado Idempotency-Key (UUID), archivo obligatorio y texto opcional. Marcar leído {ultimo_mensaje_id:<ID>}. Ningún campo auxiliar ignorado silenciosamente.

Crear DIRECTA con la misma pareja devuelve la conversación existente sin abrir otra; el UUID idempotente repetido con misma carga devuelve el mismo resultado y con carga diferente 409. Crear GRUPAL con participantes iguales pero UUID distinto crea un grupo distinto. Para mensajes y archivo: misma UUID+payload normalizado (y hash de archivo) → replay 200 sin segunda fila/archivo/evento; nueva UUID → 201; reutilización incompatible → 409. No almacenar secretos en huellas, eventos o logs.

JSON: decimales no aplican, IDs estrictamente positivos canónicos, UUID canónica, fechas UTC ISO-8601 en respuesta, validación estricta de paginación/filtros y Unicode de control, longitud y tipo. Errores 400/401/403/404/405/409/413/429/503 estables, sin trazas ni detalles de infraestructura. Todos los datos privados se envían con Cache-Control private,no-store y Vary Authorization; descargas con nosniff y Content-Disposition attachment y nombre saneado.

## 5. Archivos y análisis local (023A)

- Formatos admitidos al inicio: JPEG y PNG hasta 5 MiB, **dimensiones máximas 2048×2048**; PDF hasta 8 MiB; DOCX y XLSX hasta 5 MiB si su validación estructural segura es viable (no aceptar ZIP genérico, archivos con macros, cifrados, rutas inseguras, ZIP bombs, vínculos/plantillas externas explotables). Si la validación segura DOCX/XLSX exige dependencias o tiempo no previstos, reportar explícitamente antes de habilitarlos: **nunca aceptar por solo extensión/content-type**. Formatos no enumerados (SVG, HTML, JS, EXE, ZIP, SVG animado, etc.) denegados.
- No confiar en MIME declarado; detectar firma, contenido y estructura. Limitar body y bytes transmitidos antes de crear registros; comprobar tamaño/dimensiones con Pillow, evitar decompression bombs, normalizar imágenes eliminando metadatos/EXIF y mantener proporción sin escalar hacia arriba. Permitir solo una imagen estática. No renderizar HTML en un mensaje.
- Reutilizar diseños seguros de SPEC-012B: staging privado, archivos no alcanzables por static/media ni proxy, nombres internos aleatorios, acceso POSIX protegido contra symlinks/race, hash de integridad, ClamAV INSTREAM fail-closed. No unir el registro efímero a las tablas AdjuntoDocumento. Almacenar bajo ruta independiente FYAG_CHAT_ARCHIVOS_ROOT montada como volumen local persistente, privada.
- Escaneo indisponible o archivo sospechoso: abortar publicación, sin mensaje visible, sin abrir acceso al archivo; no permitir fallback de "aceptar igual". No enviar rutas ni contenido a Redis/Mongo. Descarga reautoriza membresía y fecha de expiración, comprueba hash, y no filtra ruta interna; también falla cerrado si el objeto desapareció.
- Transacción DB + publicación de archivo: resolver fallos intermedios con compensación idempotente, no borrar archivos de otros ni duplicar filas. Registrar errores solo con correlación y IDs no sensibles. Adjuntos históricos de facturas e informes permanecen intactos.

## 6. Límite de carga y seguridad transversal

- Una conversación grupal tiene hasta 20 miembros, por ende el fanout es acotado. Consultas con SQL indexado; paginación estable; no N+1 por mensaje, autor o adjunto.
- Rate limit por usuario y por IP para crear conversación, mensajes, archivos, ticket y conexiones; definir límites conservadores comprobables en pruebas, sin hardcode arbitrario de negocios. En tests se pueden ajustar por settings.
- Exigir HTTPS/WSS para entornos no locales y prohibir CORS/Origin wildcard. El despliegue real se diseñará después del cierre del backend local.
- Mensajes plain text; no interpolación HTML, plantillas ni render de Markdown confiando en texto recibido. Nunca registrar cuerpos, contenido de archivos, tickets ni JWT.
- Fecha de servidor y tiempos de expiración no controlables por el cliente; zonas UTC/aware y corte consistente.

## 7. Eventos WebSocket (023B)

- Servir HTTP DRF y WebSocket bajo ASGI/Daphne (o servidor ASGI compatible) en Docker **local**, sin modificar la API JWT actual. Route WebSocket: /ws/chat/ ; eventos desde backend al navegador en tiempo real.
- El navegador no puede adjuntar Authorization Bearer arbitrario al handshake. Evitar access/refresh JWT en query strings, URLs, subprotocolos públicos, localStorage o logs. **Contrato elegido:** POST /api/chat/conexion/ autenticado via JWT emite ticket opaco aleatorio >= 128 bits, guardando solo su hash SHA-256, user_id, sesion_version, emitido_en, vence_en (máximo 45 s), usado_en nullable; respuesta no-store. Abrir WebSocket con Origin autorizado y enviar {tipo:"autenticar",ticket:"..."} como **primer frame** dentro de 5 s. Validar y consumir una sola vez bajo lock PG; fallar cerrado sin suscribir a grupos si es inválido/expirado/usado. Nunca devolver el ticket en un evento.
- La conexión autenticada se incorpora exclusivamente al grupo interno derivado del ID del usuario (no admite nombres de grupo enviados por cliente). Después de autenticar, cada evento saliente revalida usuario, estado de credencial PERSONAL, bloqueo operativo y sesion_version; además ping/heartbeat de verificación máximo cada 15 s y cierre de socket ante revocación. No retransmitir el contenido del mensaje por Redis/WS: transmitir solo un aviso minimal {tipo:"chat.mensaje",conversacion_id,ultimo_mensaje_id}; el navegador solicita mensajes por HTTP autorizado. Esto impide filtrar contenido sensible si se pierde una membresía.
- Al crear un mensaje REST, registrar primero mensaje/archivo en PostgreSQL y **solo tras commit confirmado** emitir aviso mediante channels_redis a los usuarios miembros autorizados. Sin broadcast global, sin acceso ajeno, sin depender de un callback antes de commit.
- Si Redis/canal falla, **el mensaje ya confirmado permanece en PostgreSQL**; no reintentar escritura ni emitir falso 500 de "mensaje no guardado". El usuario reconecta y recupera mensajes con GET+cursor; WebSocket es señal de actualización, no transporte autorizado ni almacenamiento durable.
- Los sockets no aceptan mensajes de negocio ni escritura directa; solo autenticar y ping/pong (y códigos de cierre definidos). No "escribiendo", "presencia global", lectura de historial, adjuntos o gestión de roles por WS en 023B.
- Origen del WebSocket: validación explícita de Origin estricto con lista propia FYAG_CHAT_WS_ALLOWED_ORIGINS derivada/configurada para los orígenes aprobados; controles de tamaño, concurrencia y handshakes fallidos. Nunca depender solo de ALLOWED_HOSTS o CORS. Sin acceso sin ticket.
- Al cambiar permisos, versión de sesión o cuenta, el próximo evento/ping cancela el socket. Enviar datos sensibles solo por REST reautorizado. Seguir el estado persistido, no los claims iniciales de ticket.
- Redis usa channel layer oficial channels_redis (sin persistencia de mensajes), contenedor local privado sin publicar puerto al host, con healthcheck y controles de acceso. No poner contenido de mensajes ni archivos en claves Redis.

## 8. Retención y borrado (023A + 023B)

**Política inicial para Beta local:** mensajes y archivos asociados expiran **30 días después de creado_en** (configurable por FYAG_CHAT_RETENCION_DIAS, rango seguro 1–90; default 30). Los GET y las descargas **excluyen de inmediato** mensajes vencidos, aunque el recolector todavía no haya eliminado bytes. No hay "vaciar chat" que suprima evidencia de negocio: chat nunca es fuente de autorización formal.

Un comando de Django de purga (modo --dry-run y --once) y proceso local periódico (frecuencia configurable; inicial 1 h) eliminan metadatos vencidos y objetos privados, con concurrencia e idempotencia. Respetar una fase segura de eliminación: no perder la clave para borrar un archivo después de eliminar su fila; marcar trabajo de retiro/tumba irreversible, retirar el archivo con handle protegido, confirmar DB y reintentar ante error. No tocar evidencias de turnos, adjuntos documentales, archivos de otra conversación ni volúmenes ajenos. Sin rutas de descarga de vencidos, aunque exista fichero; reconciliación sin acceso privilegiado.

El recolector solo opera en el almacenamiento privado nuevo y tablas de chat. Pruebas de caducidad y purga exclusivamente sobre QA; **no activar purga en datos institucionales sin revisión de retención/backup y autorización operativa**. Mantener logs técnicos mínimos sin conservar el contenido purgado. No prometer borrado de copias de seguridad fuera de su ciclo de retención.

## 9. Integridad/concurrencia

- UUID idempotencia único por autor/acción en namespace documentado; huella determinística y cuerpo normalizado; proteger contra doble POST y respuesta perdida. Un proceso no publica mensaje sin autorización actual, ni dos conversaciones DIRECTA para la misma pareja.
- Usar transaction.atomic, constraints e índices para pertenencia/relaciones, no check-then-insert sin exclusión; SQL scoped en list/detail/descarga; revalidar actividad y version de sesión después de esperas y antes de commit.
- Prohibir que un reintento con el mismo UUID genere un segundo archivo, mensaje o notificación de nueva escritura. Un replay puede devolver metadata actual sin expuestos.
- Marcas de lectura monotónicas y sin decrementos, no permitir IDs futuros o de otra conversación; el borrado por vencimiento no causa punteros colgantes ni consultas costosas. Al usuario inactivo no se le envía nuevo evento.
- Si hay fallo parcial de scanner/almacenamiento/DB/Redis, no confundir mensaje confirmado con intento fallido. Documentar semántica exacta de error; sin side-effects en GET.

## 10. Docker local y compatibilidad

- Nueva app Django apps.chat con modelos, migraciones aditivas, API, capa WebSocket y tests, sin tocar por defecto apps de Obras/Finanzas/Bodega, SPEC-012B ni migraciones anteriores.
- Fase A: app REST compatible con servidor HTTP local; Fase B: preparar config/asgi.py, dependencias Channels/Daphne/channels_redis y compose.yaml con servicio Redis privado, sin abrir puertos externos de Redis. Pasar backend local de runserver a ASGI explícitamente en un cambio controlado, conservando rutas HTTP y tests.
- Almacen chat y purgador con volumen independiente. No cambiar secretos en .env ni sobrescribir configuraciones existentes; agregar exclusivamente variables de ejemplo, configuración local segura y procedimientos de arranque/rollback.
- No introducir neon/render/atlas, render.yaml, DNS, certificados productivos, almacenamiento cloud ni integraciones con servicios de pago ahora. Preparar abstracciones que permitan adaptarlos después.
- Mantener funcionamiento de PostgreSQL, Mongo, ClamAV, reconciliadores y 1269 tests existentes (conteo de referencia pre-chat); ejecutar check, makemigrations --check, migración limpia y upgrade conservador, regresión total, Postman y pruebas de WebSocket con Redis real. No borrar datos locales existentes.

## 11. Entrega y criterios de aceptación

**023A / PR propio:** conversaciones DIRECTA y GRUPAL, roles y membresía, mensajes, cursores de lectura, archivos privados escaneados, expiración/purga configurable y HTTP OpenAPI/Postman. Pruebas de matriz seis roles, terceros 404, roles/credenciales revocados, idempotencia y concurrencia, imágenes malformadas/bombas, DOCX/XLSX si se habilitan, MIME y malware EICAR en QA, fallos de scanner, almacenamiento, eliminación y retención. Sin frontend ni Socket.

**023B / PR propio posterior:** canal ASGI local, Redis, ticket de un solo uso autenticado por REST, Origin, mensaje de aviso post-commit y revalidación continua, pérdida de Redis y recuperación por GET/cursor, reconexión, tests de origin/credencial/rol/sesión, varios usuarios y procesos, pruebas reales de handshake y carga acotada, CI ampliado y contrato de consumo WebSocket. No cloud.

**Cada fase entrega:** documentación backend/docs/SPEC-023A|B-IMPLEMENTACION.md, OpenAPI HTTP, documentación del protocolo WS, colección Postman y/o runner WebSocket reproducible sin secretos; tests de integración; comparación de contrato con SPEC, lista de archivos modificados, conteos de pruebas, límites QA y posibles hallazgos. OpenCode puede implementar solo backend y documentación técnica; **nunca tocar specs/ ni frontend/**, no hacer PR ni merge; ChatGPT revisa código, CI y fusiona tras autorización conforme al flujo del proyecto.

### Definición de backend local listo

023A y 023B integradas con CI verde y pruebas manuales aisladas; API y WS disponibles mediante Docker local; almacenamiento/retención y recuperación documentados; sin cambios de frontend ni despliegue. La auditoría integral y adaptación a nube son etapas posteriores.

## Seguimiento del frontend local — 25-11-2026

- `frontend/src/pages/Chat.jsx` consume las rutas REST especificadas para conversaciones, usuarios elegibles, mensajes, lectura, adjuntos y ticket de conexión WebSocket. El WebSocket solo autentica con el ticket recibido por REST y recupera contenido por REST; no incluye mensajes ni el ticket en la URL.
- La vista incluye estado de conexión/reconexión, creación directa/grupal, lista con no leídos, paginación, carga de mensajes anteriores, envío de texto/archivo y descarga autenticada. Los nombres personalizados son alias locales en estado de React y no se sincronizan ni persisten.
- Los mensajes muestran únicamente hora y minuto de envío; la UI omite fecha y `vence_en`, sin cambiar la retención ni el contrato backend.
- La presentación se define en `frontend/src/styles/pages/chat.css`, importado por `main.jsx`. No hay modificación del protocolo ni backend en esta nota; la integración real E2E de sockets/archivos sigue requiriendo QA.

## Anexo de presentación 023A/023B — vista previa e información de grupo

Conversacion/Detalle añaden ultimo_mensaje (objeto nulo si no existen mensajes vigentes): id, autor, texto limitado a los primeros 120 caracteres, creado_en y vence_en UTC. Se selecciona el ID mayor entre los mensajes vigentes mediante subconsultas correlacionadas, sin N+1 adicionales ni cambios de orden de paginación. Texto vacío identifica un mensaje con archivo; no se devuelve el nombre del archivo ni claves privadas. Solo miembros autorizados; GET sin escrituras; contador no_leidos y vigencia conservados. Frontend común a los seis roles: vista previa y contador del servidor, nombres/roles reales de integrantes, panel de grupo sin edición, avatares por iniciales, fechas civiles de Santiago, menú de adjuntos con límites visibles antes de seleccionar, composición adaptable y retorno móvil. Sin cambios en WebSocket, retención, idempotencia, permisos ni esquema SQL. OpenAPI SPEC-023A-v1 versión 1.1.0.
