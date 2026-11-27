# Proyecto FYAG

Sistema de gestión empresarial con backend **Django REST Framework** y frontend **React/Vite**. PostgreSQL conserva los datos operativos y financieros; MongoDB gestiona metadatos documentales y ClamAV verifica los adjuntos privados.

## Integración continua

Los workflows se ejecutan en pull requests hacia `main` y en pushes a `main`, sujetos a sus filtros de archivos:

- **Backend CI:** Python 3.13.18, PostgreSQL 18 limpio, MongoDB QA autenticado y efímero, y ClamAV QA aislado. Verifica Django, migraciones y pruebas del backend. El job de auditoría Python conserva el inventario efectivo de runtime y su informe; no instala dependencias de pruebas en ese entorno.
- **Frontend CI:** Node.js 22. Ejecuta `npm ci`, `npm test`, `npm run build` y `npm audit --omit=dev` desde `frontend/`.

Los workflows validan cambios; **no realizan despliegues** ni certifican por sí solos una instalación productiva.

## Documentación

- **Especificaciones funcionales y contratos:** [`specs/`](specs/).
- **Precedencia OpenAPI:** [índice de contratos](backend/docs/openapi/README.md).
- **Auditoría final:** [avance y evidencia](docs/AUDITORIA-TECNICA-FINAL.md). [SPEC-027](specs/027-aprovisionamiento-recuperacion-seguridad.md) es un diseño; no describe endpoints implementados ni autorización productiva.
- **Implementación y operación del backend:** [`backend/docs/`](backend/docs/).
- **Operación, autenticación, reconciliación y respaldo de MongoDB:** [`database/README.md`](database/README.md).
- **Operación de adjuntos privados:** [`backend/docs/SPEC-012B-OPERACION.md`](backend/docs/SPEC-012B-OPERACION.md).
- **Variables de entorno de referencia:** [`.env.example`](.env.example). Nunca versionar un `.env` con secretos.

FYAG registra documentos tributarios emitidos externamente y pagos informados; **no emite DTE ni procesa transferencias o cobros en línea**.

## QA pre-merge

El laboratorio standalone `compose.premerge-qa.yaml` no debe combinarse con el
compose principal: usa bases y archivos efímeros exclusivos. Al detener/reiniciar
los contenedores con tmpfs se pueden perder sus datos; nunca son un respaldo.
Procedimiento, matriz real de navegador y pendientes del PR #44:
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
El riesgo de tooling picomatch permanece abierto: ver
[`SPEC-014`](specs/014-frontend-cobranzas.md); la auditoría runtime no sustituye
la auditoría completa ni una decisión formal de riesgo.

**Decisión histórica (17-11-2026):** el responsable aceptó temporalmente picomatch
solo para desarrollo y QA, con revisión semanal y caducidad propuesta de 30 días
(17-12-2026), sujeta a nueva evaluación. La vulnerabilidad y las cuatro alertas
correspondían a esa revisión; consultar el resultado de auditoría actual, no asumir
la vigencia de la excepción. No fue aprobación de seguridad para producción. TLS con cadena
confiable sigue pendiente de despliegue: no se autoriza instalar CA, cambiar
confianza Windows ni desactivar verificaciones. La publicación autorizada es
exclusivamente para auditoría en el PR#44 Draft, sin merge ni promoción a Ready.

## SPEC-018 — Fase A backend (desarrollo/QA)

Credencial inicial aleatoria, primer cambio obligatorio y restablecimiento TI con
revocación/auditoría: [informe técnico](backend/docs/SPEC-018-FASE-A-IMPLEMENTACION.md),
[contrato React/API](backend/docs/SPEC-018-FASE-A-CONTRATO.md) y
[OpenAPI](backend/docs/openapi/SPEC-018A-v1.json). TTL temporal de 24 h y desafío de
5 min configurables, **NO RATIFICADOS PARA PRODUCCIÓN**; entrega manual solo entre
cuentas sintéticas QA. La Fase A tiene [integración frontend](backend/docs/SPEC-018-INTEGRACION-FRONTEND.md);
el bloqueo C2 sigue restringido a [QA aislado](backend/docs/SPEC-018C-C2-IMPLEMENTACION.md).

## Disponibilidad local y dependencias Python

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

Para actualizar Python: usar una imagen limpia Python 3.13.18/Linux del mismo
tipo que CI, revisar los cambios propuestos a `backend/requirements.txt` y
`backend/constraints-runtime.txt`, reconstruir instalando runtime, comparar
`pip freeze` y ejecutar `pip check` y `pip-audit` en un entorno separado desde
el inventario resuelto. Instalar `requirements-test.txt` en otro entorno para
pruebas dirigidas y regresión. Revisar cambios transitivos en el mismo commit;
no trasladar la herramienta de auditoría ni los clientes de pruebas al runtime.
