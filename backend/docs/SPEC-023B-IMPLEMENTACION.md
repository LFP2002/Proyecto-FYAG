# SPEC-023B — Chat local ASGI

Base: `adeb73047fb59cfc659147a711bb1f8cd44af345`. Extensión aditiva de
023A; sin frontend, cloud o privilegios de lectura para TI/Gerencia/superusuario.

## Arquitectura

`config.asgi.application` distribuye HTTP a Django y `/ws/chat/` a Channels.
La ejecución normal Compose usa Daphne en lugar de runserver, sin access log
(`--verbosity 0`) y con límites de frame/mensaje de 1024 bytes en transporte.
HTTP/WS local se publica exclusivamente en `127.0.0.1:8000`, no en interfaces LAN.
Daphne no usa autoreload: reiniciar el backend local tras cambios de código;
reconstruir su imagen si cambian dependencias.
PostgreSQL conserva mensajes, membresías, idempotencia, tickets y leases de
conexión. Redis comunica exclusivamente avisos efímeros con IDs; nunca texto,
archivos, JWT, contraseñas o tickets. No constituye historial ni cola fiable.

Dependencias: Channels 4.3.2, Daphne 4.2.3, channels-redis 4.3.0,
redis-py 6.4.0; runner TCP: websockets 17.4. Redis Docker 7.4.7-alpine.
No se cambian la retención, compensación de archivos ni purga de mensajes 023A.
La purga también retira tickets y leases caducados; cupos ignoran leases vencidos.

## Configuración local

Generar `FYAG_CHAT_REDIS_PASSWORD` hexadecimal aleatorio independiente de JWT
en el `.env` local (no versionarlo). La plantilla contiene solo un marcador.
Redis no publica puertos al host; usa contraseña, protected-mode, healthcheck
autenticado, tmpfs, `save ""`, `appendonly no`, 128 MiB y noeviction. El secreto
se introduce por configuración stdin, no por argumentos del proceso Redis.
El resto de servicios HTTP y reconciliadores conserva sus rutas/volúmenes.
La puesta en marcha normal requiere revisar `.env` y reconstruir backend;
no se autoriza aplicar migraciones o purgas a datos institucionales automáticamente.

Variables:

| Variable | Valor predeterminado |
|---|---|
| FYAG_CHAT_REDIS_HOST / PORT | redis / 6379 |
| FYAG_CHAT_REDIS_PASSWORD | obligatorio en Compose |
| FYAG_CHAT_WS_ALLOWED_ORIGINS | http://localhost:5173,http://127.0.0.1:5173 |
| FYAG_CHAT_WS_TICKET_TTL | 45 s (1–45) |
| FYAG_CHAT_WS_HEARTBEAT | 5 s (1–10) |

Origin es una lista exacta, independiente de CORS/ALLOWED_HOSTS: sin wildcard,
rutas, credenciales, query ni fragmentos. Ausente, duplicado o ajeno se rechaza
antes del upgrade. No confiar en X-Forwarded-For: IP observada por ASGI. Un
proxy futuro requiere diseño explícito, HTTPS/WSS y no registrar URLs/frames.
WS local solo para laboratorio loopback/red privada Docker.

## Tickets y estados

1. Cliente autenticado hace `POST /api/chat/conexion/` con JWT y JSON `{}`.
   Respuesta 201 `{"ticket":"…","vence_en":"…Z"}`, privada/no-store.
2. Abrir `ws://localhost:8000/ws/chat/` con Origin permitido. No añadir query,
   JWT, ticket ni subprotocolos. El ticket no es un JWT.
3. Primer frame de texto, antes de 5 segundos desde admisión:
   `{"tipo":"autenticar","ticket":"…"}`. No se aceptan claves extra.
4. El servidor consume una sola vez bajo bloqueo PostgreSQL y responde
   `{"tipo":"chat.conectado"}`. Hasta entonces no ingresa a ningún grupo.
5. Conectado: solo `{"tipo":"ping"}` (respuesta `{"tipo":"pong"}`) o
   `{"tipo":"pong"}`. No hay escritura, selección de grupos ni suscripciones.
6. Cierre/revocación: descartar el ticket, pedir otro y reconectar si procede.

Ticket = nonce criptográfico de 256 bits + sello HMAC opaco ligado a usuario,
versión y firma de contraseña. Solo se persisten digest SHA-256 del ticket
completo, usuario, versión, fechas de creación/vencimiento/consumo e ID técnico.
No se persisten nonce, sello, contraseña ni segundo hash de contraseña.
Trigger SQL impide modificación, segundo consumo y borrado antes de caducar.
La migración nueva no altera migraciones históricas; reversión exige que no
queden tickets/leases vigentes.

Leases PG compartidos por todos los procesos: usuario 3, IP 64, global 512,
pendientes global 64/IP 8; pendientes caducan a los 7 s, autenticados a los 30 s
con renovación periódica. Mutex PG breve evita carreras de cupos y consumo.
Handshakes 60/IP/minuto (también cuentan rechazos de cupo); tickets 10/usuario,
30/IP/minuto; máximo 10 frames/10 s y 1024 bytes. Seudónimo IP HMAC persistido,
sin dirección en claro. Cambiar límites en settings requiere mantener sus invariantes.

## Autorización y revocación

Solo grupo interno `chat.usuario.{id}` derivado del servidor. Los seis roles
usan membresía ordinaria. Verificación SQL al emitir/consumir, antes de cada
evento saliente (incluido pong) y periódicamente. Relee usuario activo, rol
válido, versión, firma de contraseña, PERSONAL y estado operativo compartido
de Usuarios; conserva exactamente la activación de política C2 vigente.
Desactivación, cambio de contraseña/versión, credencial temporal/bloqueada o
inconsistencia cierran 4401. Evento de mensaje revalida además membresía y vigencia.
ORM fuera del event loop mediante database_sync_to_async; tiempos SQL/acceso
acotados. Fallos de infraestructura cierran de forma segura, sin excepciones SQL.

| Código | Motivo genérico |
|---|---|
| 4400 | Protocolo/JSON/frame inválido o escritura WS |
| 4401 | Ticket/identidad no disponibles o revocados |
| 4403 | Origin/opciones no autorizados (pre-upgrade: HTTP 403) |
| 4408 | Plazo de autenticación |
| 4429 | Cupo/frecuencia |
| 4503 | Infraestructura no disponible |
| 1009 | Tamaño excesivo |

El límite de transporte Daphne/Autobahn puede abortar la conexión antes del
consumer: en ese caso el navegador observa 1006, no un frame de cierre 1009.
Ambos son fallo cerrado sin procesar el mensaje excesivo.
Los rechazos de admisión previos a `accept` (incluidos cupos) se observan como
HTTP 403 durante el upgrade, no como código de cierre WebSocket.

Los cierres no contienen ticket, contenido, SQL o detalles internos. Los logs
propios son códigos técnicos constantes y, en fallo de canal, nombre de clase
de excepción (sin mensaje/traceback); no se habilita access log de Daphne.

## Eventos y recuperación (equipo React)

Formato único de aviso:
`{"tipo":"chat.mensaje","conversacion_id":123,"ultimo_mensaje_id":456}`.
Al publicar texto o archivo REST, se registra callback on_commit únicamente
para mensaje nuevo. Rollback y replay no notifican. El fallo del aviso después
del commit se registra sin propagarlo: HTTP conserva éxito y mensaje confirmado.
Los destinatarios se resuelven desde membresías y elegibilidad actuales.

No asumir entrega exactamente una vez, orden global, presencia de lectura ni
recepción del destinatario. Puede haber avisos duplicados o perdidos por caída,
caducidad Redis (30 s), capacidad o desconexión. No existe outbox persistente.
Un socket conectado tampoco acredita lectura; marcar leído sigue siendo REST.

React debe mantener ticket solo en memoria, no registrar frames y descartar
ticket tras usarlo. Al conectar/reconectar y al recibir aviso, consultar
`GET /api/chat/conversaciones/` y el historial autorizado correspondiente.
Para recuperar desde el último ID local, empezar **sin cursor** (página reciente)
y recorrer `siguiente_antes_id` usando `antes_id` hasta alcanzar el ID conocido o
fin; no usar `antes_id=ultimo_conocido` como consulta incremental (traería antiguos).
Deduplicar por ID de mensaje, ordenar para mostrar y renderizar como texto plano.
Concurrencia durante recorrido: refrescar la cabeza otra vez. Retención puede
hacer imposible recuperar mensajes ya vencidos; no son error ni república.

Reconexión con backoff exponencial y jitter, respetando 429/Retry-After. Ante
4401 detener reconexión automática y renovar sesión por el flujo FYAG vigente.
Ante respuesta HTTP perdida al publicar, reintentar **misma** clave idempotente;
nunca generar otra por falta de aviso WS. REST funciona aunque Redis no esté.

## Runner permanente y laboratorio

Runner automático desde host: `python backend/scripts/qa_chat_ws.py --full`.
Genera nombre de proyecto y secretos únicos fuera del repositorio, exige DB QA,
ejecuta check/drift/migraciones/Chat/regresión completa y retira exclusivamente
su propio proyecto y secretos al terminar. Sin `--full`, ejecuta solo Chat.
Requiere Python host y Docker Compose; no lee `.env` real.

Usar `compose.premerge-qa.yaml` standalone, proyecto con nombre exclusivo,
secretos QA externos y override externo para DB `fyag_spec018c_c2_qa` cuando se
pruebe C2. Nunca combinar con Compose normal ni reutilizar volúmenes existentes.
Definir QA_POSTGRES_PASSWORD, QA_MONGO_ROOT_PASSWORD, QA_MONGO_PASSWORD,
QA_DJANGO_SECRET, QA_JWT_SECRET y QA_REDIS_PASSWORD aleatorios en env-file externo.

```powershell
docker compose --env-file <qa.env> -f compose.premerge-qa.yaml -f <qa.override.yaml> -p <proyecto-exclusivo> up -d --build --wait
docker compose --env-file <qa.env> -f compose.premerge-qa.yaml -f <qa.override.yaml> -p <proyecto-exclusivo> exec -T backend python manage.py check
docker compose --env-file <qa.env> -f compose.premerge-qa.yaml -f <qa.override.yaml> -p <proyecto-exclusivo> exec -T backend python manage.py makemigrations --check --dry-run
docker compose --env-file <qa.env> -f compose.premerge-qa.yaml -f <qa.override.yaml> -p <proyecto-exclusivo> exec -T backend python manage.py test apps.chat --noinput
```

`apps.chat.tests.test_ws_real` es runner de integración y contrato: crea DB
test, arranca dos procesos Daphne TCP sobre loopback y uno con puerto Redis
inaccesible para fallo real de transporte; limpia procesos al terminar. No usa
mocks ni InMemoryChannelLayer. PostgreSQL y Redis deben estar aislados. El
runner exige DB `test_fyag_spec018c_c2_qa`, habilita C2 solo en sus procesos
y crea dos cuentas TI recuperadoras QA dedicadas; prueba bloqueo operativo real.
También pausa temporalmente solo Redis QA y comprueba persistencia y recuperación.
Comprueba también que logs de esos procesos no contengan JWT, tickets o texto
privado de los casos de prueba. El runner de tickets añade carrera PG con
conexiones separadas. `test_upgrade_023b` compara íntegramente filas 023A antes
y después del upgrade y prueba guard de reversión. Regresión completa:
`python manage.py test --noinput` en el mismo backend QA (sin procesos de otros tests).

OpenAPI: extensión HTTP `openapi/SPEC-023B-v1.json`; contrato 023A permanece
inmutable.

## Evidencia local de validación

Entorno: Python 3.13.18, Django 5.2.19, DRF 3.18.3, psycopg 3.3.9,
Twisted 26.10.0, Autobahn 26.11.1, PostgreSQL 18 y Redis 7.4.7.

- `check`: sin incidencias; `makemigrations --check --dry-run`: sin drift.
- Migración desde DB vacía: OK. Upgrade con comparación completa de filas de
  conversaciones, participantes, mensajes y recibos 023A: OK; reversión con
  tickets activos rechazada sin retirar el esquema.
- Runner autónomo `qa_chat_ws.py --full`, proyecto `fyag-023b-15714cfbb3b3`:
  **81 pruebas Chat OK en 37,668 s** (59 heredadas + 22 nuevas).
- Entre las nuevas: 14 casos de integración con TCP real, dos Daphne
  distribuidos y un tercero con Redis inaccesible; commit/rollback/replay,
  dos participantes, terceros/TI superusuario, revocación de versión/contraseña/
  actividad/PERSONAL/bloqueo C2, pendientes, tamaño/frecuencia/cupos, consumo
  concurrente entre procesos, Origin y recuperación REST. Incluye pausa real
  de Redis QA con HTTP 201 conservado, sin duplicar mensajes.
- OpenAPI 3.1 validado con openapi-spec-validator; ambos Compose validan.
- Primera regresión completa: **1346 pruebas OK en 412,460 s**; precede a los
  últimos cuatro casos nuevos.
- Regresión final ampliada del runner autónomo: **1350 pruebas OK en 405,224 s**.
  Incluye todas las pruebas heredadas y las 22 nuevas; sin omisiones declaradas.
- Los dos proyectos QA creados para esta tarea fueron retirados con sus datos
  efímeros y secretos. Se conservaron activos los siete contenedores preexistentes
  con sus mismos IDs; no se migraron sus bases ni se eliminaron sus volúmenes.
- Sin modificaciones de frontend, specs, Usuarios/credenciales ni módulos
  históricos protegidos; sin migraciones históricas editadas ni secretos QA en Git.

Estas son verificaciones locales, no aprobación de CI, auditoría final ni
autorización de despliegue. La publicación de la rama se informa por separado.
