# SPEC-017 — Integración frontend FYAG: Reportes

**Estado documental:** aprobación e integración documental en `main` no se confirman aquí; verificarlo con el responsable. **Código comprobado en esta rama local:** `frontend/src/pages/Reportes.jsx` contiene catálogo y listados JSON para GERENCIA y ADMINISTRATIVO_FINANZAS, además de una ruta de descarga binaria autenticada. Esto no acredita despliegue, aprobación del alcance de exportación, ni validación contra el backend real.

## Alcance presente en código local

- Consumo autenticado del catálogo `/api/reportes/catalogo/` y de listados autorizados para Obras, Rentabilidad y Cobranzas según el rol.
- Filtros, paginación, schemas/errores y totales se proyectan desde el backend; el cliente no calcula totales financieros.
- El cliente AuthClient local admite respuesta Blob autenticada. La UI implementa exportación CSV/XLSX/PDF según los formatos que declara el catálogo y gestiona respuestas binarias localmente.
- Administrativo/Finanzas no accede a Obras ni Rentabilidad; roles no autorizados no montan la pantalla.

## Verificación local

- `npm test`: 165 pruebas frontend aprobadas en el worktree revisado.
- `npm run build`: aprobado.

## Pendiente de verificación y decisiones

- Validar descargas reales, MIME, Content-Disposition, refresh de sesión, límites y permisos contra backend QA; pruebas simuladas no certifican exportación real.
- Confirmar que el alcance de fase 2/exportaciones está aprobado antes de tratarlo como operativo.
- Confirmar aprobación e integración documental con el responsable; no se inventan aprobaciones ni resultados de CI/E2E/despliegue.

## Contrato y límites

Fuente de verdad: `specs/011-reportes-backend.md`, `backend/docs/openapi/SPEC-011-v1.json` y `backend/apps/reportes/`. Reutilizar solo `useAuth().request`; no incluir URL pública/token, almacenamiento persistente de archivos o PII, acciones financieras, archivos ficticios ni cálculos cliente. Backend mantiene la autoridad RBAC y catálogo. Los formatos no ofrecidos por catálogo no se presentan como disponibles.
