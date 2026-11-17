# SPEC-016 — Integración frontend FYAG: Dashboard gerencial

**Estado documental:** no se declara aprobación ni integración documental en `main`; confirmar con responsable. **Código comprobado en la rama local:** `frontend/src/pages/Dashboard.jsx` está montada para GERENCIA y consume resumen, serie mensual y obras activas. La validación de fecha actual usa `America/Santiago`. El código local no demuestra despliegue, integración en `main` ni aprobación.

## Alcance implementado en frontend local

- Consulta autenticada de `GET /api/dashboard/resumen/`, `/api/dashboard/serie-obras/` y `/api/dashboard/obras-activas/` mediante `useAuth().request`/el hook autorizado.
- Periodo civil, selección de meses, paginación de obras en proceso, estados de carga/error y lectura de métricas devueltas por backend.
- Solo GERENCIA solicita el Dashboard. Los importes y estados se muestran desde respuestas de API; no se calculan montos ni rentabilidad en React.
- `validDashboardRange()` obtiene hoy en la zona IANA `America/Santiago`, comprueba fechas civiles y limita rangos según el contrato.

## Verificación local

- `npm test`: 165 pruebas frontend aprobadas en el worktree revisado.
- `npm run build`: aprobado.

## Pendiente de verificación y decisiones

- Probar con backend QA autorizado
- Probar con backend QA autorizado schemas, permisos, límites de fechas, paginación y errores.
- Confirmar explícitamente el estado de aprobación/integración documental con el responsable; no se presume por este archivo ni por el código local.
- No se declara ejecución de E2E, CI, despliegue o revisión de producción.

## Contrato y límites

Fuente de verdad: `specs/010-dashboard-backend.md`, OpenAPI SPEC-010 y `backend/apps/dashboard/`. Solo GET bajo `/api/dashboard/`; no incluir escrituras, exportaciones, alertas, auditoría ni datos mock. Backend autoriza acceso. El frontend no presenta datos privados no incluidos en la proyección, porcentajes inventados, rentabilidad proyectada ni cálculos financieros cliente. La validez de fecha futura debe seguir `America/Santiago` como backend.
