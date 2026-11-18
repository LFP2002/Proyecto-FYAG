# SPEC-017 — Integración frontend FYAG: Reportes

**Estado documental:** aprobación e integración documental en `main` no se confirman aquí; verificarlo con el responsable. **Código comprobado en esta rama local:** `frontend/src/pages/Reportes.jsx` contiene catálogo y listados JSON para GERENCIA y ADMINISTRATIVO_FINANZAS, además de una ruta de descarga binaria autenticada. Esto no acredita despliegue, aprobación del alcance de exportación, ni validación contra el backend real.

## Alcance presente en código local

- Consumo autenticado del catálogo `/api/reportes/catalogo/` y de listados autorizados para Obras, Rentabilidad y Cobranzas según el rol.
- Filtros, paginación, schemas/errores y totales se proyectan desde el backend; el cliente no calcula totales financieros.
- El cliente AuthClient local admite respuesta Blob autenticada. La UI implementa exportación CSV/XLSX/PDF según los formatos que declara el catálogo y gestiona respuestas binarias localmente.
- Administrativo/Finanzas no accede a Obras ni Rentabilidad; roles no autorizados no montan la pantalla.

## Verificación local

- Antecedente de revisión previa: 165 pruebas y build informados como aprobados; no constituye resultado de esta revisión. Ejecución vigente en `Cosas pendientes.txt`.

## Pendiente de verificación y decisiones

- Validar descargas reales, MIME, Content-Disposition, refresh de sesión, límites y permisos contra backend QA; pruebas simuladas no certifican exportación real.
- Confirmar que el alcance de fase 2/exportaciones está aprobado antes de tratarlo como operativo.
- Confirmar aprobación e integración documental con el responsable; no se inventan aprobaciones ni resultados de CI/E2E/despliegue.

## Contrato y límites

Fuente de verdad: `specs/011-reportes-backend.md`, `backend/docs/openapi/SPEC-011-v1.json` y `backend/apps/reportes/`. Reutilizar solo `useAuth().request`; no incluir URL pública/token, almacenamiento persistente de archivos o PII, acciones financieras, archivos ficticios ni cálculos cliente. Backend mantiene la autoridad RBAC y catálogo. Los formatos no ofrecidos por catálogo no se presentan como disponibles.

## Contrato frontend conservado — revisión local 17-11-2026

### Objetivo, alcance y roles

Consultar reportes y descargar las exportaciones existentes que autorice el catálogo, sin generar archivos simulados en React. GERENCIA consulta Obras, Rentabilidad y Cobranzas; ADMINISTRATIVO_FINANZAS únicamente Cobranzas. Supervisor, Técnico y TI no acceden. Excluye escrituras de negocio, emisión de documentos fiscales, BI externo, generación cliente de totales y rentabilidad proyectada. Se documenta código ya presente, sin reimplementación ni aprobación de exportaciones por inferencia.

### Endpoints y contratos existentes

| GET | Filtros |
| --- | --- |
| `/api/reportes/catalogo/` | Sin filtros; moneda, zona, formatos y reportes autorizados |
| `/api/reportes/obras/` | `desde/hasta`, `cliente`, `estado`, `fecha_base`, `page` |
| `/api/reportes/rentabilidad/` | `desde/hasta`, `cliente`, `page` |
| `/api/reportes/cobranzas/` | `desde/hasta`, `cliente`, `estado`, `page` |
| `/api/reportes/{tipo}/exportar/` | Filtros del tipo y `formato=csv/xlsx/pdf`, sin page |

Páginas JSON: `count/next/previous/results/totales/periodo/moneda/fecha_corte`, hasta 25 filas. Totales pertenecen al conjunto filtrado, no a la página. Rentabilidad muestra presupuesto/costo real/margen neto de cierres reales; Cobranzas muestra cartera actual, no historia reconstruida. Valores decimales son strings y el backend determina todos los importes. Cambio de tipo elimina parámetros incompatibles. FINALIZACION requiere estado FINALIZADA en Obras. Fechas civiles juntas, ordenadas, máximo 366 días inclusivos; cliente es entero positivo.

Exportación usa Blob autenticado y metadatos Content-Type/Content-Disposition, valida MIME por formato y nombre contractual `fyag-{tipo}-YYYYMMDD-HHMMSS.ext`; crea URL temporal local y la revoca. No construye enlaces públicos ni lleva JWT en URL. Límites, campos completos y nulabilidad: OpenAPI SPEC-011 y serializers Django son autoridad.

### Arquitectura, fallos y accesibilidad

`Reportes.jsx` usa AuthContext, useApi y Pager; catálogo acota tipos/formatos. Estados carga/vacío/error/descarga se diferencian; generaciones descartan listados desplazados al cambiar tipo/filtros. No se guardan PII ni archivos en almacenamiento persistente. `400` informa filtros inválidos, `401` sigue refresh existente, `403/404` no revelan recursos, `409` no muestra totales parciales, `413` informa límite, `429` respeta Retry-After y red/5xx no confirman descarga. La descarga no modifica datos de negocio. Controles etiquetados, mensajes accesibles y tabla responsiva con paginación nombrada.

### Aceptación, pruebas y pendientes

- AF nunca recibe opciones Obras/Rentabilidad ni consulta esos reportes.
- Catálogo gobierna las descargas; filtros exclusivos no se trasladan a otro tipo.
- Navegación utiliza páginas del servidor y totales no calculados en React.
- MIME/nombre incompatibles y errores no producen un archivo confirmado.

Pruebas en `frontend/tests/integrations-domain.test.js` y `auth-client.test.js` (transporte); resultados actuales en seguimiento de rama. QA de descargas reales, permisos, límites y revisión visual siguen pendientes. Estado documental: revisión local, aprobación histórica no acreditada; código: integración local presente, sin certificar despliegue. Revisar informe antes de cualquier publicación y solicitar autorización separada de merge. Referencias: SPEC-011, OpenAPI SPEC-011, `backend/apps/reportes/`, `frontend/src/pages/Reportes.jsx`.
