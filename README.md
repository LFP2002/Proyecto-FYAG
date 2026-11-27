# Proyecto FYAG

Sistema de gestión empresarial con backend **Django REST Framework** y frontend **React/Vite**. Ver la [arquitectura vigente y sus límites](docs/ARQUITECTURA.md).

## Integración continua

Los workflows se ejecutan en pull requests hacia `main` o `reajustes-visuales-frontend` y en pushes a `main`, sujetos a sus filtros de archivos:

- **Backend CI:** Python 3.13.18, PostgreSQL 18 limpio, MongoDB QA autenticado y efímero, y ClamAV QA aislado. Verifica Django, migraciones y pruebas del backend. El job de auditoría Python conserva el inventario efectivo de runtime y su informe; no instala dependencias de pruebas en ese entorno.
- **Frontend CI:** Node.js 22. Ejecuta `npm ci`, `npm test`, `npm run build` y `npm audit --omit=dev` desde `frontend/`.
- **Production Compose CI:** valida el Compose productivo base y el overlay SMTP, construye las imágenes y ejercita HTTPS/readiness, ACL SQL, respaldo/restauración y purga de Chat con datos sintéticos. El overlay se renderiza; no se usa un proveedor de correo real.

Los workflows validan cambios; **no realizan despliegues** ni certifican por sí solos una instalación productiva.

## Documentación

- **Especificaciones funcionales y contratos:** [`specs/`](specs/).
- **Precedencia OpenAPI:** [índice de contratos](backend/docs/openapi/README.md).
- **Auditoría final:** [avance y evidencia](docs/AUDITORIA-TECNICA-FINAL.md). [SPEC-027](specs/027-aprovisionamiento-recuperacion-seguridad.md) incluye [primera TI](backend/docs/SPEC-027-SETUP.md), [verificación voluntaria](backend/docs/SPEC-027-VERIFICACION.md), [recuperación por correo](backend/docs/SPEC-027-RECUPERACION.md), [recuperación excepcional TI](backend/docs/SPEC-027-RECUPERACION-TI.md) y [bloqueos opt-in](backend/docs/SPEC-027-BLOQUEOS.md). El [informe de validación](backend/docs/SPEC-027-CIERRE.md) no autoriza activación institucional.
- **Infraestructura productiva:** [Compose independiente y guía operativa](docs/INFRAESTRUCTURA-PRODUCCION.md). No usa el `.env` ni el Compose de desarrollo.
- **Entrega y puesta en producción:** [lista de verificación y riesgos residuales](docs/ENTREGA-PRODUCCION.md), [respaldo y restauración](docs/RESPALDO-RESTAURACION.md), [retención de Chat](docs/RETENCION-CHAT.md).
- **Implementación y operación del backend:** [`backend/docs/`](backend/docs/).
- **Operación, autenticación, reconciliación y respaldo de MongoDB:** [`database/README.md`](database/README.md).
- **Operación de adjuntos privados:** [`backend/docs/SPEC-012B-OPERACION.md`](backend/docs/SPEC-012B-OPERACION.md).
- **Variables de entorno:** [desarrollo](.env.example) y [producción](deploy/production.env.example). No compartirlas entre entornos ni versionar secretos.

FYAG registra documentos tributarios emitidos externamente y pagos informados; **no emite DTE ni procesa transferencias o cobros en línea**.

## QA pre-merge

El laboratorio standalone `compose.premerge-qa.yaml` no debe combinarse con el
Compose principal: usa bases y archivos efímeros exclusivos. Al detener/reiniciar
los contenedores con tmpfs se pueden perder sus datos; nunca son un respaldo.
Procedimiento y evidencias QA:
[`SPEC-012B-OPERACION.md`](backend/docs/SPEC-012B-OPERACION.md).

Regresión responsive opt-in, sin dependencias E2E: desde `frontend/`, abrir
**Usuarios y roles** con TI en QA y ejecutar `node qa/usuarios-responsive.mjs`,
definiendo `FYAG_QA_CDP` (URL CDP loopback), `FYAG_QA_ORIGIN` y
`FYAG_QA_EVIDENCE` (directorio externo). No crea cuentas ni envía escrituras.

Un frontend/API en orígenes distintos requiere HTTPS y configuración explícita
de CORS/CSRF. Las cookies `SameSite=Strict` requieren **mismo sitio schemeful**;
dos puertos HTTPS del mismo host son orígenes diferentes pero mismo sitio.
No se soporta asumir refresh entre sitios distintos por habilitar CORS.
Un certificado autofirmado con excepción de navegador no acredita confianza TLS.
El historial de PR #44 y la excepción temporal de picomatch están en el
[registro histórico](docs/AUDITORIA-TECNICA-FINAL.md#registro-histórico). La auditoría de runtime no sustituye la auditoría completa de frontend ni renueva esa excepción.

## Disponibilidad local y dependencias Python

Para desarrollo, revisar [`.env.example`](.env.example), crear una configuración
local propia sin sobrescribir una existente y usar `docker compose --env-file .env -f compose.yaml config --quiet` antes de `up -d --build`. Para el frontend local usar Node.js 22 y, desde `frontend/`, `npm ci` y `npm run dev`. Completar los secretos y la configuración de Mongo del entorno antes de arrancarlo; no usar el procedimiento de producción para inicializar desarrollo.

Compose enlaza PostgreSQL, MongoDB y backend al loopback del host; Redis y ClamAV
no publican puertos. El backend comprueba `/health/live/` (sin dependencias) y
`/health/ready/` comprueba SQL, sin consultar MongoDB, ClamAV, SMTP ni Redis de chat.
Incluir `127.0.0.1` en los hosts permitidos del backend local para el probe interno.
Docker aplica `restart: unless-stopped` si el proceso sale; `unhealthy` por sí
solo no reinicia el contenedor. Los endpoints no certifican migraciones, entrega
SMTP ni disponibilidad de módulos auxiliares.

El login requiere Redis de seguridad dedicado. Para Compose local, suministrar
`FYAG_SECURITY_REDIS_PASSWORD` (hexadecimal aleatorio, distinto del secreto de
chat) por el entorno del operador. QA standalone usa `QA_SECURITY_REDIS_PASSWORD`.
Fuera de Compose, `FYAG_SECURITY_REDIS_URL` apunta exclusivamente a la instancia
de seguridad. Sin Redis se responde 503 en vez de omitir el control. La IP es
`REMOTE_ADDR`, no `X-Forwarded-For`; detrás de proxy se comparte el cupo del peer
si todavía no se configuró un transporte confiable de la IP real.

Para revisar correo sintético: agregar `-f compose.mailpit.yaml --profile mailpit`
al Compose local o al standalone QA (no combinar ambos Compose base). SMTP
queda dentro de la red Docker y la interfaz de captura en `127.0.0.1:8025`.
Usar solo destinatarios `.test`. Para SMTP empresarial, configurar un remitente
autorizado y `FYAG_EMAIL_PROFILE=smtp`, backend SMTP de Django, URL pública HTTPS,
credenciales externas y exactamente uno de STARTTLS o TLS implícito. Para
habilitar los reenvíos voluntarios, iniciar el consumidor documentado en
[Operación de verificación](backend/docs/SPEC-027-VERIFICACION.md).

Para actualizar Python: usar una imagen limpia Python 3.13.18/Linux del mismo
tipo que CI, revisar los cambios propuestos a `backend/requirements.txt` y
`backend/constraints-runtime.txt`, reconstruir instalando runtime, comparar
`pip freeze` y ejecutar `pip check` y `pip-audit` en un entorno separado desde
el inventario resuelto. Instalar `requirements-test.txt` en otro entorno para
pruebas dirigidas y regresión. Revisar cambios transitivos en el mismo commit;
no trasladar la herramienta de auditoría ni los clientes de pruebas al runtime.
