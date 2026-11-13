# SPEC-014 — Integración frontend FYAG: Cobranzas

**Estado:** Aprobada por el responsable del proyecto, pendiente de integración documental en `main`. **No iniciar la implementación hasta que el cambio documental esté integrado.** El backend de Finanzas/007A/007B está implementado en `main`; esta SPEC define el consumo React de Cobranzas, hoy pendiente en frontend.

## 1. Contexto verificado

- `specs/007-finanzas-cobranzas.md` define finanzas como registro administrativo de documentos externos y pagos reales ya confirmados fuera de FYAG. FYAG **no emite DTE, factura electrónicamente, cobra dinero ni ejecuta transferencias**.
- Backend real en `backend/apps/finanzas/urls.py`, `views_documentos.py`, `views_pagos.py`, serializers/services y `consultas_cobranzas.py`; `/api/finanzas/cobranzas/` y `/api/finanzas/cobranzas/resumen/` están disponibles.
- `PermisoFinanciero`: GERENCIA y ADMINISTRATIVO_FINANZAS pueden leer cartera/resumen/documentos; solo AF puede escribir. SUPERVISOR y TÉCNICO no acceden. El permiso consulta rol y `is_active` persistidos; privilegios Django heredados no conceden permiso.
- `frontend/src/app.jsx` aún dirige `cobranzas` a `PendingIntegration`, aunque el menú lo muestra a Gerencia y AF. Cuentas Técnico usan `TecnicoApp` aparte.
- `frontend/src/auth/AuthContext.jsx` expone `request`; `frontend/src/auth/client.js` es el único cliente autorizado de sesión. No implementar cliente paralelo.
- Patrones de UI/aislamiento existentes: `frontend/src/comercial/ui.jsx`, `frontend/src/comercial/scope.js`, `frontend/src/comercial/api.js`, `frontend/src/obras/`.
- No existe todavía una SPEC frontend de Cobranzas en `specs/`; SPEC-007 declara el frontend fuera de su alcance.

## 2. Objetivo y límites

Integrar la **cartera Cobranzas de lectura** para G/AF desde `/api/finanzas/cobranzas/` y sus agregados desde `/api/finanzas/cobranzas/resumen/`, con filtros server-side reales, paginación y estados derivados por backend. Esta primera entrega no incluye CRUD de documentos/pagos ni reversos: requieren decisiones adicionales de UX de alto riesgo y aprobación diferenciada. Si se propone incluirlos en la misma entrega, revisar y aprobar expresamente un alcance ampliado antes de programar.

El registro de documentos/pagos no genera un DTE ni efectúa un movimiento de dinero. Nada en la pantalla debe presentar «emitir factura», «cobrar», «recibir pago» o «reembolso» como acción ejecutada por FYAG.

Exclusiones: cambios backend/DB/infraestructura/Compose/workflows; integración documental de factura externa; registrar o anular pagos; revertir documentos; cierre sin cobro; generación/envío de DTE; pasarelas, transferencia, conciliación bancaria, SII, edición o eliminación; adjuntos/descarga de respaldos; exportaciones; alertas y reportes.

## 3. Roles, proyecciones y privacidad

| Rol | Puede consultar cartera/resumen | Datos que muestra esta entrega |
|---|---|---|
| GERENCIA | Sí, solo lectura | Proyección contratada de documento, origen permitido y cobranza calculada; sin mutaciones |
| ADMINISTRATIVO_FINANZAS | Sí, solo lectura en esta entrega | Misma proyección contractual, con contexto financiero permitido |
| SUPERVISOR_OBRAS, TÉCNICO, ADMINISTRADOR_TI | No | Sin ruta, requests ni menú de negocio; backend deniega acceso |

El menú existente autoriza navegación visual según el rol, pero backend decide realmente. Nunca usar `is_superuser`, `is_staff`, cliente-side flags o rol en query para elevar acceso. Ocultar toda acción de escritura en esta primera entrega.

No mostrar documentos fuera de la respuesta financiera. Evitar logs de folios, identificaciones, respaldos, importes sensibles, Authorization y tokens. Montos vienen exclusivamente como strings decimales; fechas como ISO/civil; el frontend no calcula saldo ni estado. Renderizar nombres/IDs solo si aparecen en las proyecciones aprobadas; evitar expandir identificación de cliente o mostrar `referencia_respaldo` en la bandeja sin una decisión explícita de producto.

## 4. Contrato HTTP de lectura

Todas las requests via `useAuth().request`, a rutas `/api/finanzas/...`; `GET`, `credentials`, Bearer, refresh 401 y `Cache-Control`/`no-store` obedecen el cliente existente. No almacenar datos en browser storage.

### 4.1 GET cartera

`GET /api/finanzas/cobranzas/?page=<n>` devuelve paginación DRF `{count,next,previous,results}`, 25 documentos por página, orden por vencimiento e ID. Solo incluye documentos con estado fuente `VIGENTE`; puede incluir estado de cobranza calculado `PENDIENTE`, `PARCIAL`, `PAGADA` o `VENCIDA`.

Filtros exactos que acepta `cartera_filtrada`: `estado`, `cliente`, `obra`, `fecha_vencimiento_desde`, `fecha_vencimiento_hasta`, `fecha_emision_desde`, `fecha_emision_hasta`, `page`. Fechas inicio/fin por dimensión se envían juntas y en formato `YYYY-MM-DD`; backend rechaza rango invertido. IDs deben ser positivos decimal-string; no enviar parámetros repetidos/vacíos/desconocidos. No hay filtro de servidor para folio, cliente por nombre ni campo no documentado. Si se decide incorporar búsqueda local, etiquetarla como limitada a la página actual; preferencia MVP: no ofrecerla.

Schema por fila: `id`, `naturaleza` (registro administrativo de documento externo), `origen`, `tipo_documento`, `folio_externo`, `fecha_emision`, `fecha_vencimiento`, `monto_neto`, `monto_impuesto`, `monto_total`, `referencia_respaldo`, `estado`, datos de registro/reversión y `cobranza` nullable. `cobranza` para documento vigente contiene `{moneda:"CLP", abonado:string, saldo:string, estado:enum}`; estado se calcula exclusivamente con backend. Validar campos/tipos y descartar campos adicionales antes de presentarlos.

### 4.2 GET resumen

`GET /api/finanzas/cobranzas/resumen/` acepta **los mismos filtros que la cartera** y agrega sobre el conjunto filtrado. Responde `moneda:"CLP"`, `documentos` entero, `conteos` para los estados, y `monto_documentado_total`, `abonado_total`, `saldo_total`, `saldo_vencido` como strings decimales. Resumen y tabla deben usar exactamente el mismo estado de filtros/paginación lógica, pero el agregado corresponde a todo el conjunto filtrado, no a la página visible. No calcular ni sumar en React, no reemplazar respuesta del backend con totales de página.

### 4.3 Detalle de documento y pagos (lecturas contractuales existentes)

- `GET /api/finanzas/documentos/{id}/` ofrece schema de documento y cobranza según serializer.
- `GET /api/finanzas/documentos/{id}/pagos/?page=N` paginado; filtros opcionales contractuales `activo=true|false`, `medio`, `fecha_pago_desde`, `fecha_pago_hasta` en pareja. Pago incluye medio/fecha/monto y referencias de soporte; esta SPEC de cartera no requiere mostrar el respaldo salvo aprobación de detalle/privacidad por separado.
- `GET /api/finanzas/documentos/{id}/historial/?page=N` y rutas de historial de pagos existen según urls reales. Si la entrega se limita a cartera/resumen, no añadir vistas de detalle/pagos/historial sin ratificar alcance; se mantienen como opciones diferidas.

### 4.4 Permisos y errores

- 400: filtros/paginación inválidos; exponer campos de error permitidos y conservar filtro.
- 401: delegar renovación compartida al AuthClient; si termina sesión, limpiar datos.
- 403: indicar acceso no permitido y retirar datos; no insistir ni escalar.
- 404: recurso no disponible; no revelar existencia.
- 405: discrepancia contractual; no cambiar el método para hacer pasar UI.
- 409 (si se añaden flujos futuros): conflicto de dominio; no presentar éxito ni reintentar escritura.
- 429: respetar `Retry-After` si lo devuelve el backend.
- 5xx/red/timeout: mostrar fallo/relectura; no inventar resultado. GET se puede reintentar a petición del usuario; no iniciar mutaciones en esta entrega.

## 5. UX, arquitectura y estados

- Reemplazar `PendingIntegration` solo para `cobranzas` cuando rol G/AF y después de SPEC aprobada/integrada.
- Pantalla de cartera con resumen del conjunto filtrado, tabla responsive y accesible, estado de cobranza del backend, moneda CLP, fechas, folio/naturaleza de registro externo y neto/impuesto/total/saldo en strings exactos. No mostrar cero cuando no exista documento: la API de cartera solo lista documentos existentes vigentes.
- Filtros disponibles: estado, cliente ID, obra ID, rango emisión y rango vencimiento; UI no manda parámetros vacíos. Clarificar que los filtros son globales de servidor y mantenerlos al paginar/actualizar.
- Diferenciar carga, error, vacío, sin permiso y datos stale; no hay datos mock. Reconsultar simultáneamente cartera/resumen al cambiar filtros y después de refresh, con abort/cancelación y descarte de respuestas viejas.
- Detalle: decidir y aprobar aparte antes de implementar; si se incluye tras aprobación, leer solo endpoint contractual, sin acción de mutación o descarga no especificada.
- Accesibilidad: labels, foco visible, teclado, encabezados semánticos, aria-live para estados, botones reales, tabla navegable móvil a 320/375/768/1024 px. Reutilizar tokens/componentes FYAG.

Propuesta mínima de archivos después de aprobación: `frontend/src/finanzas/api.js`, `frontend/src/finanzas/domain.js`/estado UI, `frontend/src/pages/Cobranzas.jsx`, montaje acotado en `frontend/src/app.jsx`, pruebas Node en `frontend/tests/`. No tocar backend ni añadir dependencia.

## 6. Seguridad y concurrencia

- Access JWT solo en memoria; refresh exclusivamente cookie HttpOnly. No incluir bearer en URLs, variables públicas, logs o storage.
- La vista G/AF lee solo proyección autorizada del backend. No mostrar Finanzas a S/T/TI; nunca confiar en guards visuales como seguridad.
- Montos son strings; no `Number`, `parseFloat`, float, fórmulas o totales derivados en React. Backend es autoridad de saldo/estado, y la tabla evita mezclar total con neto.
- Cualquier dato que contenga PII/ref de pago se conserva en memoria solo mientras está montada la vista y se limpia al logout/cambio de cuenta. No persistir PII en caches duraderas.
- GETs cancelables, timeout razonable, no aplicar respuestas de filtros/usuarios viejos. No implementar escrituras/idempotencia aquí.
- Backend ya impone filtros estrictos, paginación 25, roles y saldos transaccionales; frontend valida respuestas/paginación y no atribuye seguridad adicional a esas validaciones.

## 7. Plan de pruebas y aceptación

Automatizadas frontend:
1. G/AF consultan exactamente cartera y resumen; S/T/TI no hacen requests aunque se monte página de forma aislada.
2. Schemas estrictos para página, documento, origen, cobranza, conteos y decimal strings; respuesta incompleta, importes numéricos, estado desconocido, URL next externa/ajena se rechazan.
3. Filtros permitidos, pareja de fechas, validación ISO/IDs, ausencia de parámetros vacíos/repetidos/aliases; request lleva filtros verdaderos del servidor.
4. Cartera paginada 25, next/previous seguros, resumen refleja conjunto filtrado y no suma solo resultados de página.
5. Estados vacío/cargando/error, 400/401/403/404/405/409/429/5xx/red/timeout, refresh de sesión y cambio de usuario/logout con datos tardíos descartados.
6. No mostrar valores añadidos extra, ni simular un documento/saldo/pago, ni persistir token/PII; escritura de Cobranzas no aparece en esta entrega.
7. A11y/responsive en 320, 375, 768, 1024.
8. `npm test`, `npm run build`; `npm ci` si cambian lock/dependencias. E2E dev G/AF solo con cuentas autorizadas, distinguiendo prueba API de UI.

Criterios de aceptación: cartera real y resumen consultan API; paginación/filtros del servidor; importes/estados provienen del backend sin cálculo cliente; roles G/AF y negativos S/T/TI correctos; módulos aún pendientes siguen claramente indicados; errores no muestran éxito falso; pruebas y CI reportados con evidencia real.

## 8. Riesgos y pendientes de definición

- **Decisión pendiente:** si Cobranzas frontend se limita a lectura de cartera/resumen (recomendación inicial) o incluye también alta/reverso documental, pagos/anulaciones, estado financiero, sin cobro e historial. La presente SPEC propone dejar todas las escrituras y detalle avanzado fuera de la primera fase.
- Las referencias de respaldo fiscal/bancario pueden contener datos sensibles; su presentación/retención visual necesita evaluación explícita, no asumir que deben mostrarse en la tabla.
- Un documento revertido no aparece en cartera vigente; no presentar documento histórico como saldo exigible.
- Cobranza vencida es el enum calculado por backend en `America/Santiago`; frontend no calcula fecha ni estado.
- Contratos financieros son sensibles y errores de permiso deben permanecer sin filtración entre roles.

## 9. Aprobación y flujo de integración

1. Esta SPEC frontend complementa SPEC-007, aprobada por el responsable. No hay permiso de implementar mientras no esté integrada en `main`.
2. Tras aprobación, publicar solo documentación en rama `docs/spec-014-frontend-cobranzas` con PR descriptivo, sin código de funcionalidad; no merge sin autorización separada.
3. Tras merge documental autorizado: actualizar `main` local usando `git switch main` y `git pull --ff-only origin main`.
4. Solo después crear rama `feature/frontend-014-cobranzas` desde `origin/main` y con encargo explícito implementar la fase aprobada; pruebas e informe humano antes de commit/push.
5. No ejecutar commit/push/PR ni merge automáticamente. Backend de finanzas no se modifica.

## 10. Referencias

- `specs/007-finanzas-cobranzas.md` (contrato backend y límites tributarios).
- `backend/apps/finanzas/{urls.py,views_documentos.py,views_pagos.py,serializers_documentos.py,serializers_pagos.py,consultas_cobranzas.py,permissions.py,services_documentos.py,services_pagos.py,tests/}`.
- `backend/config/urls.py`.
- `frontend/AGENTS.md`, `frontend/src/app.jsx`, `frontend/src/data/constants.js`.
- `frontend/src/auth/{AuthContext.jsx,client.js}`, `frontend/src/comercial/{api.js,ui.jsx,scope.js}`.
