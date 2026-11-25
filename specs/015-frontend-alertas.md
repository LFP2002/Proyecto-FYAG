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

## Contrato frontend conservado — revisión local 17-11-2026

### Objetivo y exclusiones

Consultar alertas operativas y acusar atención motivada sin resolver artificialmente sus causas. No generar alertas desde React, alterar estados de Obras/documentos, enviar notificaciones externas ni sustituir auditoría. Esta revisión restaura detalle documental; no atribuye aprobación histórica ni reimplementa Alertas.

### Roles y APIs existentes

GERENCIA consulta los tipos autorizados por Django; SUPERVISOR_OBRAS solo `OBRA_SUSPENDIDA` y `TURNO_PENDIENTE_REVISION`. AF, Técnico y TI no acceden. La presencia de `ATENDER` en `acciones_permitidas` condiciona la acción; no se infiere desde el título o severidad.

| Método | Endpoint | Contrato |
| --- | --- | --- |
| GET | `/api/alertas/` | `estado`, `tipo`, `recurso_tipo`, `recurso_id`, `desde`, `hasta`, `page` |
| GET | `/api/alertas/resumen/` | Conteos del servidor, zona y estado de sincronización |
| GET | `/api/alertas/{id}/` | Alerta y acciones permitidas |
| GET | `/api/alertas/{id}/historial/` | Página independiente de eventos |
| POST | `/api/alertas/{id}/atender/` | `{motivo: string}` obligatorio |

Alerta: ID, tipo, estado `PENDIENTE/ATENDIDA/RESUELTA`, severidad `MEDIA/ALTA`, recurso, Obra, título/descripción, actores/fechas y acciones. Bandeja e historial usan `count/next/previous/results` de hasta 25 filas. Tipos completos: `PRESUPUESTO_PENDIENTE_GERENCIA`, `OBRA_SUSPENDIDA`, `TURNO_PENDIENTE_REVISION`, `COBRANZA_VENCIDA`; disponer de un tipo no concede acceso a su origen. Ver serialización y OpenAPI SPEC-009 para nulabilidad y parámetros estrictos.

### UX, seguridad y fallos

`Alertas.jsx` usa AuthContext/useApi y Pager; presenta carga, vacío, error, resumen de sincronización, detalle e historial. Cambiar selección reinicia historial; scopes descartan respuestas desplazadas. Atención requiere motivo, bloqueo de doble envío y relecturas; red/5xx o relectura fallida no confirman éxito. `400` conserva corrección, `401` usa sesión existente, `403/404` no revelan ni elevan acceso, `409` obliga a consultar nuevamente. No se reintenta POST automáticamente ni se persisten credenciales. Tablas responsivas, controles etiquetados, mensajes con rol accesible y navegación paginada nombrada.

### Aceptación y verificación

- Bandeja/resumen reflejan exclusivamente respuestas y permisos del backend.
- Filtros y páginas consultan sus parámetros reales; historial navega más allá de página uno sin mezclar selecciones.
- Supervisor nunca recibe una opción financiera; una atención no se confunde con resolución.
- Fallo o conflicto no presenta una escritura como confirmada ni duplica POST.

Pruebas locales en `frontend/tests/integrations-domain.test.js` y suite de sesión/scopes; resultados actuales en `Cosas pendientes.txt`. Pendiente QA con sesiones y sincronización reales; las simulaciones no acreditan despliegue. Revisar informe antes de publicar; no abrir PR ni fusionar sin autorización separada. Referencias: SPEC-009, `backend/apps/alertas/`, OpenAPI SPEC-009 y `frontend/src/pages/Alertas.jsx`.

## Seguimiento del worktree frontend — 25-11-2026

- La vista local continúa leyendo `GET /api/alertas/resumen/`; para GERENCIA muestra el aviso de sincronización únicamente cuando `sincronizacion.desactualizada` viene como `true`. No estima la salud del reconciliador en el navegador ni permite ocultar/editar la condición.
- En esta sesión, `main-alertas_reconciliador-1` se inició mediante `docker compose up --pull always -d alertas_reconciliador`; sus logs registraron un ciclo correcto (`examinados: 2`, `transiciones: 0`). Esto evidencia el entorno local en ese momento, no el estado continuo ni un despliegue.
- No se cambiaron rutas, esquema API ni backend. La sincronización se considera fresca solo tras una respuesta actualizada del resumen backend.
