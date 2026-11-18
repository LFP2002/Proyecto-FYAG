# SPEC-016 — Integración frontend FYAG: Dashboard gerencial

**Estado documental:** no se declara aprobación ni integración documental en `main`; confirmar con responsable. **Código comprobado en la rama local:** `frontend/src/pages/Dashboard.jsx` está montada para GERENCIA y consume resumen, serie mensual y obras activas. La validación de fecha actual usa `America/Santiago`. El código local no demuestra despliegue, integración en `main` ni aprobación.

## Alcance implementado en frontend local

- Consulta autenticada de `GET /api/dashboard/resumen/`, `/api/dashboard/serie-obras/` y `/api/dashboard/obras-activas/` mediante `useAuth().request`/el hook autorizado.
- Periodo civil, selección de meses, paginación de obras en proceso, estados de carga/error y lectura de métricas devueltas por backend.
- Solo GERENCIA solicita el Dashboard. Los importes y estados se muestran desde respuestas de API; no se calculan montos ni rentabilidad en React.
- `validDashboardRange()` obtiene hoy en la zona IANA `America/Santiago`, comprueba fechas civiles y limita rangos según el contrato.

## Verificación local

- Antecedente de revisión previa: 165 pruebas y build informados como aprobados; no constituye resultado de esta revisión. Ejecución vigente en `Cosas pendientes.txt`.

## Pendiente de verificación y decisiones

- Probar con backend QA autorizado schemas, permisos, límites de fechas, paginación y errores.
- Confirmar explícitamente el estado de aprobación/integración documental con el responsable; no se presume por este archivo ni por el código local.
- No se declara ejecución de E2E, CI, despliegue o revisión de producción.

## Contrato y límites

Fuente de verdad: `specs/010-dashboard-backend.md`, OpenAPI SPEC-010 y `backend/apps/dashboard/`. Solo GET bajo `/api/dashboard/`; no incluir escrituras, exportaciones, alertas, auditoría ni datos mock. Backend autoriza acceso. El frontend no presenta datos privados no incluidos en la proyección, porcentajes inventados, rentabilidad proyectada ni cálculos financieros cliente. La validez de fecha futura debe seguir `America/Santiago` como backend.

## Contrato frontend conservado — revisión local 17-11-2026

### Objetivo, roles y arquitectura

Presentar indicadores gerenciales existentes sin convertir presupuesto en ingreso ni margen en utilidad contable. Solo GERENCIA monta consultas; AF/S/T/TI no solicitan estos recursos. `Dashboard.jsx`, `useApi`, AuthContext, Pager y helpers civiles `integrations/dates.js` forman la implementación; no se agregan dependencias ni contratos backend.

| GET existente | Parámetros y respuesta |
| --- | --- |
| `/api/dashboard/resumen/` | `desde/hasta`; generado_en, zona_horaria, moneda, periodo, operacion, rentabilidad_cerrada_periodo, cobranza_actual |
| `/api/dashboard/serie-obras/` | `meses` de 1 a 12; métrica OBRAS_FINALIZADAS, zona y puntos mes/cantidad |
| `/api/dashboard/obras-activas/` | `page`; página DRF de Obras EN_PROCESO, hasta 25 filas |

Resumen separa estados actuales de Obras y presupuestos pendientes, finalizaciones/rentabilidad del período y cartera actual sin reconstrucción histórica. Importes CLP como strings; margen puede ser negativo. Período requiere fechas ISO civiles reales juntas, orden ascendente, máximo 366 días inclusivos y hasta no posterior a hoy en America/Santiago. Serie y obras activas son consultas independientes; no se suman páginas para fabricar totales.

### Estados de interfaz, concurrencia y seguridad

Carga, vacío, error y filtro incompatible se distinguen. Snapshots se asocian a su URL; cambiar fechas invalida la generación anterior incluso si el rango nuevo no produce GET. Un error retira las cifras afectadas, sin seguir mostrando el resumen antiguo como actual. Cambiar usuario/rol desmonta el contexto. `401` conserva el protocolo de sesión, `403/404` no conceden acceso y errores de infraestructura se muestran sin valores ficticios. Solo lecturas, sin archivos ni tokens persistentes. Controles etiquetados, fecha máxima visible, tablas desplazables y paginación accesible.

### Criterios de aceptación y pruebas

1. Solo Gerencia solicita los tres endpoints y muestra únicamente campos contractuales.
2. Fechas imposibles, futuras o rangos excesivos no generan resumen.
3. Cambiar a rango inválido descarta respuesta pendiente; fallo posterior retira cifras anteriores.
4. Meses y página se corresponden con su consulta; los importes no se recalculan.

Regresiones en `frontend/tests/integrations-domain.test.js`: calendario, Santiago, lectura de los tres recursos, respuesta tardía y error. Estado del código: corrección local implementada; estado documental: revisión local sin aprobación histórica acreditada. Pendientes: QA real y revisión visual en 320/375/768/1024 px; no se afirma validación visual/E2E. Publicación solo después del informe y autorización; sin cambios de backend. Referencias: SPEC-010, OpenAPI SPEC-010 y serializers de Dashboard.
