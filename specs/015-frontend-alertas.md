# SPEC-015 — Integración frontend FYAG: Alertas

**Estado del documento:** contrato frontend con estado de aprobación/integración documental no confirmado por el checkout actual. **Estado del código verificado en la rama local:** `frontend/src/pages/Alertas.jsx` está montada para GERENCIA y SUPERVISOR_OBRAS y consume API de alertas. No se declara aprobación ni publicación en `main`.

## Implementado en la rama local

- Bandeja, resumen, filtros, paginación, detalle e historial para los roles autorizados.
- Atención motivada disponible solo cuando la respuesta incluye la acción permitida; refresh y errores se gestionan con el cliente JWT existente.
- Se preserva la separación por rol y se evita consultar los dominios de origen desde la UI.

## Pendiente de verificación

- Ejecutar pruebas contra backend QA con sesiones reales para confirmar RBAC, filtros, cursor/paginación, errores y escrituras.
- Correr pruebas frontend/build actuales y reportar resultados de esta rama, no los históricos de notas anteriores.
- Confirmar con el responsable si el texto y la implementación se aprobaron e integraron documentalmente; esta SPEC no inventa esa aprobación.

## Contrato y límites

Fuente de verdad: `specs/009-alertas-backend.md`, `backend/apps/alertas/` y rutas `/api/alertas/`. La pantalla usa `useAuth().request`, no amplía roles, no calcula conteos y no consulta directamente fuentes financieras u operativas. Un acuse se confirma desde el servidor y sus relecturas; 409 requiere relectura y no reintento de escritura. Sin cambios backend ni acciones de resolución no definidas.
