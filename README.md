# Proyecto FYAG

Sistema de gestión empresarial con backend **Django REST Framework** y frontend **React/Vite**. PostgreSQL conserva los datos operativos y financieros; MongoDB gestiona metadatos documentales y ClamAV verifica los adjuntos privados.

## Integración continua

Los workflows se ejecutan en pull requests hacia `main` y en pushes a `main`, sujetos a sus filtros de archivos:

- **Backend CI:** Python 3.13.18, PostgreSQL 18 limpio, MongoDB QA autenticado y efímero, y ClamAV QA aislado. Verifica Django, migraciones, aplica las migraciones y ejecuta las pruebas del backend.
- **Frontend CI:** Node.js 22. Ejecuta `npm ci`, `npm test`, `npm run build` y `npm audit --omit=dev` desde `frontend/`.

Los workflows validan cambios; **no realizan despliegues** ni certifican por sí solos una instalación productiva.

## Documentación

- **Especificaciones funcionales y contratos:** [`specs/`](specs/).
- **Implementación y operación del backend:** [`backend/docs/`](backend/docs/).
- **Operación, autenticación, reconciliación y respaldo de MongoDB:** [`database/README.md`](database/README.md).
- **Operación de adjuntos privados:** [`backend/docs/SPEC-012B-OPERACION.md`](backend/docs/SPEC-012B-OPERACION.md).
- **Variables de entorno de referencia:** [`.env.example`](.env.example). Nunca versionar un `.env` con secretos.

FYAG registra documentos tributarios emitidos externamente y pagos informados; **no emite DTE ni procesa transferencias o cobros en línea**.
