# Proyecto FYAG

Sistema de gestión empresarial con backend **Django REST Framework** y frontend **React/Vite**. PostgreSQL conserva los datos operativos y financieros; MongoDB gestiona metadatos documentales y ClamAV verifica los adjuntos privados.

## Integración continua

Los workflows se ejecutan en pull requests hacia `main` y en pushes a `main`, sujetos a sus filtros de archivos:

- **Backend CI:** Python 3.13.18, PostgreSQL 18 limpio, MongoDB QA autenticado y efímero, y ClamAV QA aislado. Verifica Django, migraciones, aplica las migraciones y ejecuta las pruebas del backend.
- **Frontend CI:** Node.js 22. Ejecuta `npm ci`, `npm test`, `npm run build` y `npm audit --omit=dev` desde `frontend/`.

Los workflows validan cambios; **no realizan despliegues** ni certifican por sí solos una instalación productiva.

## Documentación

- **Manual de implementacion empresarial:** [`MANUAL-IMPLEMENTACION.md`](MANUAL-IMPLEMENTACION.md).
- **Manual de usuario por rol:** [`MANUAL-USUARIO.md`](MANUAL-USUARIO.md).
- **Especificaciones funcionales y contratos:** [`specs/`](specs/).
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

**Decisión vigente (17-11-2026):** el responsable aceptó temporalmente picomatch
solo para desarrollo y QA, con revisión semanal y caducidad propuesta de 30 días
(17-12-2026), sujeta a nueva evaluación. La vulnerabilidad y las cuatro alertas
siguen vigentes; no es aprobación de seguridad para producción. TLS con cadena
confiable sigue pendiente de despliegue: no se autoriza instalar CA, cambiar
confianza Windows ni desactivar verificaciones. La publicación autorizada es
exclusivamente para auditoría en el PR#44 Draft, sin merge ni promoción a Ready.

## SPEC-018 — Fase A backend (desarrollo/QA)

Credencial inicial aleatoria, primer cambio obligatorio y restablecimiento TI con
revocación/auditoría: [informe técnico](backend/docs/SPEC-018-FASE-A-IMPLEMENTACION.md),
[contrato React/API](backend/docs/SPEC-018-FASE-A-CONTRATO.md) y
[OpenAPI](backend/docs/openapi/SPEC-018A-v1.json). TTL temporal de 24 h y desafío de
5 min configurables, **NO RATIFICADOS PARA PRODUCCIÓN**; entrega manual solo entre
cuentas sintéticas QA. El frontend actual requiere integración posterior; bloqueos
escalonados y despliegue siguen fuera de esta fase. SPEC-018 no está completada.
