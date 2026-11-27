# Infraestructura independiente de producción (AUD-009)

`compose.production.yaml` es autónomo. No se combina con `compose.yaml`, `.env` de desarrollo ni overlays de QA. La topología es para **un nodo**: Nginx sirve el build de Vite y termina HTTPS/WSS; solo él publica puertos. El frontend, la API y el WebSocket comparten origen. Daphne no escucha TCP: Nginx y Django comparten exclusivamente el socket Unix, en un volumen privado de UID 10001. Réplicas, balanceadores L7, CDN o terminación TLS en otro punto requieren otro diseño y otra validación.

## Preparación

1. Preparar un host Linux administrado con Docker Engine/Compose v2, DNS, firewall, sincronización horaria, capacidad y alertas de disco. Copiar [`deploy/production.env.example`](../deploy/production.env.example) a una ruta de operación fuera del repo. Conservar loopback en el laboratorio. Abrir solo HTTP/HTTPS en la interfaz aprobada al autorizar la exposición; revisar IPv4/IPv6, NAT y las reglas efectivas de Docker, no solo el firewall declarado.
2. Preparar un directorio externo de secretos. Conceder lectura **solo** al operador y al UID que lo requiere (ACL por fichero o mecanismo de secretos del host). Compose local monta ficheros y no aplica `uid/gid/mode` a su origen: verificar desde el contenedor no privilegiado; no hacer `chmod 644` a claves o contraseñas. El directorio completo no se monta. No poner secretos en env de Compose, argumentos, build context ni logs.

| Archivos en `FYAG_SECRET_DIR` | Consumidores |
| --- | --- |
| `web-fullchain.pem`, `web-key.pem` | Solo Nginx, UID 10001. PEM del dominio público, hoja seguida de intermediarias, clave sin passphrase legible solo por el proxy. |
| `django-secret`, `jwt-signing-key` | Solo backend web, UID 10001. Valores aleatorios independientes, ≥50 caracteres. |
| `postgres-password` | PostgreSQL y los procesos Django que usan SQL. No separa roles SQL: AUD-025 es independiente. |
| `mongo-root-password`, `mongo-app-password` | Root solo bootstrap Mongo; contraseña de aplicación en Mongo, web y reconciliadores documentales. La inicialización del volumen nuevo usa el rol documental existente. |
| `redis-security-password`, `redis-ca.pem` | Redis seguridad, web y consumidor de correo si se habilita. Contraseña aleatoria de 64 hex. CA dedicada, sin modificar la confianza global de Python ni del host. |
| `redis-cert.pem`, `redis-key.pem` | Solo Redis seguridad (UID 999 en la imagen probada). SAN DNS `redis-seguridad`, cadena PEM con intermedias si corresponde. Sin listener en claro; el cliente exige CA, hostname y contraseña. |
| `redis-chat-password` | Solo Redis Chat y web; otra contraseña aleatoria de 64 hex. Tráfico privado, sin persistencia de avisos. |
| `smtp-password` | Solo web y consumidor con el overlay SMTP; no es requisito del stack predeterminado. |

3. Usar CA pública/institucional confiable por los navegadores, con renovación y alerta de expiración. Para laboratorio usar CA efímera con SAN y `keyUsage` (CA: `keyCertSign`, hoja: `digitalSignature`), cargarla **solo** en el cliente de prueba mediante `cafile` o `--cacert`; no usar `-k` ni instalarla en el sistema. Redis usa su CA explícita. La emisión/renovación es externa: revalidar cadena y SAN y recrear los contenedores afectados cuando se reemplacen ficheros (un bind puede conservar el inodo anterior).

## Arranque y operación

Ejemplo con rutas externas y un nombre de proyecto propio:

```sh
docker compose -p fyag-prod --env-file /srv/fyag/production.env -f compose.production.yaml config --quiet
docker compose -p fyag-prod --env-file /srv/fyag/production.env -f compose.production.yaml build backend proxy mongodb
docker compose -p fyag-prod --env-file /srv/fyag/production.env -f compose.production.yaml up -d --wait
docker compose -p fyag-prod --env-file /srv/fyag/production.env -f compose.production.yaml ps -a
docker compose -p fyag-prod --env-file /srv/fyag/production.env -f compose.production.yaml exec backend python -m config.production_server ready
```

- El contenedor de migraciones debe terminar en 0 antes de web y workers. Web/worker/migraciones son UID 10001 y solo escriben en sus volúmenes y `/tmp`. Nginx usa el mismo UID solo para cruzar el socket; no ve SQL, Redis ni archivos privados. No escalar backend a más de una réplica por socket. `/admin/`, `/health/`, archivos privados y rutas WS distintas a `/ws/chat/` no se publican. Para bootstrap de una **instalación nueva**, seguir [SPEC-027 Setup](../backend/docs/SPEC-027-SETUP.md); la CLI autorizada requiere TTY y no es recuperación de TI existente.
- PostgreSQL, MongoDB, archivos privados, AOF de Redis seguridad y firmas ClamAV tienen volúmenes propios. No usar `down -v` sobre operación. Redis Chat es efímero. El proxy aplica 10 MiB de cuerpo, 30 solicitudes API/s por IP con ráfaga 60, y 5 handshakes WS/s con ráfaga 12; Django conserva sus límites por IP/identidad y las cuotas WS. No usa `real_ip_header` ni PROXY protocol: reemplaza la IP con el peer de transporte y descarta cabeceras reenviadas. Django obtiene `REMOTE_ADDR` y el esquema seguro solo del adaptador ASGI sobre el socket; Chat recibe el mismo peer. Verificar que la topología del host preserva la IP (Desktop/NAT/LB pueden entregar la IP del intermediario); no corregirlo confiando en XFF público.
- Cookies CSRF, refresh y sesión `Secure`, `HttpOnly` y `SameSite=Strict`; CSRF y origen WS exactos, sin CORS cross-site. HSTS, CSP, `nosniff`, `DENY`, política de referentes y permisos en el borde. TLS 1.2/1.3, sin compatibilidad en claro fuera de la redirección HTTP. Las cabeceras, parámetros, cookies y cuerpos de solicitudes no van al access log del proxy.
- Monitorizar HTTPS desde fuera, `live` y `ready` desde el contenedor, estado de motores/ClamAV y ciclos de los workers. `live` no depende de SMTP/Redis/Mongo; `ready` comprueba SQL. Los reconciliadores de Alertas, Documentos y Adjuntos corren por defecto. Se reintentan por la política de reinicio ante error/timeout; el healthcheck exige un ciclo exitoso reciente. Ajustar cadencia/timeout al tamaño del inventario. Docker no reinicia por `unhealthy` por sí solo: alertar por estado/edad del ciclo y seguir el runbook de incidente. ClamAV obtiene firmas por egress separado; exigir frescura de firmas y permitir únicamente destinos aprobados. El purgador Chat usa `--profile chat-mantenimiento` solo tras revisión `purgar_chat --dry-run` y aprobación de retención.
- Correo apagado por defecto. Para SMTP autorizado, añadir `-f deploy/compose.production.smtp.yaml` **después** del Compose base en todos los comandos operativos. Configurar `FYAG_SMTP_HOST`, `FYAG_SMTP_USER`, `FYAG_SMTP_FROM`, `FYAG_SMTP_PORT` (587 por defecto) y exactamente uno entre `FYAG_SMTP_STARTTLS=true` o `FYAG_SMTP_IMPLICIT_TLS=true`; añadir `smtp-password`. Habilitar egress restringido al proveedor. El overlay arranca el consumidor de verificación/recuperación y añade egress al web por los envíos tras commit. No habilita SPEC-027 productivo por sí mismo.
- `FYAG_BLOQUEOS_PERFIL=deshabilitado` es el valor por defecto; C2 QA no se admite en el perfil runtime. Cualquier cambio a `produccion` sigue sujeto a la [constancia y preflight SPEC-027](../backend/docs/SPEC-027-BLOQUEOS.md) y a referencias TI/SMTP/remitente. No introducir bypasses para arrancar ni usar certificados de laboratorio institucionalmente.

## Pruebas y salida a producción

Pruebas dirigidas: `PYTHONPATH=backend python -m unittest discover -s deploy/tests -p test_unix_proxy.py`. Para `deploy/tests/smoke_edge.py`, preparar un proyecto independiente, dominio `.test`, puertos loopback separados, CA de laboratorio y una cuenta sintética activa. `websockets` se instala en el entorno de prueba, no en runtime. El smoke fija loopback sin alterar DNS y requiere verificación de certificados e inicio WSS con ticket. Usar solo datos sintéticos y eliminar los recursos del proyecto de laboratorio al terminar.

Pendientes institucionales: asignación del host y DNS, firewall/egress real, aprovisionamiento y renovación de certificados, pin de digests aprobados y escaneo de imágenes, monitoreo/SLO y dimensionamiento, SMTP autorizado, prueba de red real para IP de origen, continuidad operativa y aprobaciones. No cubre auditoría de roles del motor (AUD-025), restauración coordinada (AUD-023), HA ni despliegue. Volúmenes persistentes no equivalen a un respaldo validado.
