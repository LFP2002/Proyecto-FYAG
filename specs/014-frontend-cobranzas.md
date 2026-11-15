# SPEC-014 ÔÇö Integraci├│n frontend FYAG: Cobranzas

**Estado:** Aprobada por el responsable del proyecto, pendiente de integraci├│n documental en `main`. **No iniciar la implementaci├│n hasta que el cambio documental est├® integrado.** El backend de Finanzas/007A/007B est├í implementado en `main`; esta SPEC define el consumo React de Cobranzas, hoy pendiente en frontend.

## 1. Contexto verificado

- `specs/007-finanzas-cobranzas.md` define finanzas como registro administrativo de documentos externos y pagos reales ya confirmados fuera de FYAG. FYAG **no emite DTE, factura electr├│nicamente, cobra dinero ni ejecuta transferencias**.
- Backend real en `backend/apps/finanzas/urls.py`, `views_documentos.py`, `views_pagos.py`, serializers/services y `consultas_cobranzas.py`; `/api/finanzas/cobranzas/` y `/api/finanzas/cobranzas/resumen/` est├ín disponibles.
- `PermisoFinanciero`: GERENCIA y ADMINISTRATIVO_FINANZAS pueden leer cartera/resumen/documentos; solo AF puede escribir. SUPERVISOR y T├ëCNICO no acceden. El permiso consulta rol y `is_active` persistidos; privilegios Django heredados no conceden permiso.
- `frontend/src/app.jsx` a├║n dirige `cobranzas` a `PendingIntegration`, aunque el men├║ lo muestra a Gerencia y AF. Cuentas T├®cnico usan `TecnicoApp` aparte.
- `frontend/src/auth/AuthContext.jsx` expone `request`; `frontend/src/auth/client.js` es el ├║nico cliente autorizado de sesi├│n. No implementar cliente paralelo.
- Patrones de UI/aislamiento existentes: `frontend/src/comercial/ui.jsx`, `frontend/src/comercial/scope.js`, `frontend/src/comercial/api.js`, `frontend/src/obras/`.
- No existe todav├¡a una SPEC frontend de Cobranzas en `specs/`; SPEC-007 declara el frontend fuera de su alcance.

## 2. Objetivo y l├¡mites

Integrar la **cartera Cobranzas de lectura** para G/AF desde `/api/finanzas/cobranzas/` y sus agregados desde `/api/finanzas/cobranzas/resumen/`, con filtros server-side reales, paginaci├│n y estados derivados por backend. Esta primera entrega no incluye CRUD de documentos/pagos ni reversos: requieren decisiones adicionales de UX de alto riesgo y aprobaci├│n diferenciada. Si se propone incluirlos en la misma entrega, revisar y aprobar expresamente un alcance ampliado antes de programar.

El registro de documentos/pagos no genera un DTE ni efect├║a un movimiento de dinero. Nada en la pantalla debe presentar ┬½emitir factura┬╗, ┬½cobrar┬╗, ┬½recibir pago┬╗ o ┬½reembolso┬╗ como acci├│n ejecutada por FYAG.

Exclusiones: cambios backend/DB/infraestructura/Compose/workflows; integraci├│n documental de factura externa; registrar o anular pagos; revertir documentos; cierre sin cobro; generaci├│n/env├¡o de DTE; pasarelas, transferencia, conciliaci├│n bancaria, SII, edici├│n o eliminaci├│n; adjuntos/descarga de respaldos; exportaciones; alertas y reportes.

## 3. Roles, proyecciones y privacidad

| Rol | Puede consultar cartera/resumen | Datos que muestra esta entrega |
|---|---|---|
| GERENCIA | S├¡, solo lectura | Proyecci├│n contratada de documento, origen permitido y cobranza calculada; sin mutaciones |
| ADMINISTRATIVO_FINANZAS | S├¡, solo lectura en esta entrega | Misma proyecci├│n contractual, con contexto financiero permitido |
| SUPERVISOR_OBRAS, T├ëCNICO, ADMINISTRADOR_TI | No | Sin ruta, requests ni men├║ de negocio; backend deniega acceso |

El men├║ existente autoriza navegaci├│n visual seg├║n el rol, pero backend decide realmente. Nunca usar `is_superuser`, `is_staff`, cliente-side flags o rol en query para elevar acceso. Ocultar toda acci├│n de escritura en esta primera entrega.

No mostrar documentos fuera de la respuesta financiera. Evitar logs de folios, identificaciones, respaldos, importes sensibles, Authorization y tokens. Montos vienen exclusivamente como strings decimales; fechas como ISO/civil; el frontend no calcula saldo ni estado. Renderizar nombres/IDs solo si aparecen en las proyecciones aprobadas; evitar expandir identificaci├│n de cliente o mostrar `referencia_respaldo` en la bandeja sin una decisi├│n expl├¡cita de producto.

## 4. Contrato HTTP de lectura

Todas las requests via `useAuth().request`, a rutas `/api/finanzas/...`; `GET`, `credentials`, Bearer, refresh 401 y `Cache-Control`/`no-store` obedecen el cliente existente. No almacenar datos en browser storage.

### 4.1 GET cartera

`GET /api/finanzas/cobranzas/?page=<n>` devuelve paginaci├│n DRF `{count,next,previous,results}`, 25 documentos por p├ígina, orden por vencimiento e ID. Solo incluye documentos con estado fuente `VIGENTE`; puede incluir estado de cobranza calculado `PENDIENTE`, `PARCIAL`, `PAGADA` o `VENCIDA`.

Filtros exactos que acepta `cartera_filtrada`: `estado`, `cliente`, `obra`, `fecha_vencimiento_desde`, `fecha_vencimiento_hasta`, `fecha_emision_desde`, `fecha_emision_hasta`, `page`. Fechas inicio/fin por dimensi├│n se env├¡an juntas y en formato `YYYY-MM-DD`; backend rechaza rango invertido. IDs deben ser positivos decimal-string; no enviar par├ímetros repetidos/vac├¡os/desconocidos. No hay filtro de servidor para folio, cliente por nombre ni campo no documentado. Si se decide incorporar b├║squeda local, etiquetarla como limitada a la p├ígina actual; preferencia MVP: no ofrecerla.

Schema por fila: `id`, `naturaleza` (registro administrativo de documento externo), `origen`, `tipo_documento`, `folio_externo`, `fecha_emision`, `fecha_vencimiento`, `monto_neto`, `monto_impuesto`, `monto_total`, `referencia_respaldo`, `estado`, datos de registro/reversi├│n y `cobranza` nullable. `cobranza` para documento vigente contiene `{moneda:"CLP", abonado:string, saldo:string, estado:enum}`; estado se calcula exclusivamente con backend. Validar campos/tipos y descartar campos adicionales antes de presentarlos.

### 4.2 GET resumen

`GET /api/finanzas/cobranzas/resumen/` acepta **los mismos filtros que la cartera** y agrega sobre el conjunto filtrado. Responde `moneda:"CLP"`, `documentos` entero, `conteos` para los estados, y `monto_documentado_total`, `abonado_total`, `saldo_total`, `saldo_vencido` como strings decimales. Resumen y tabla deben usar exactamente el mismo estado de filtros/paginaci├│n l├│gica, pero el agregado corresponde a todo el conjunto filtrado, no a la p├ígina visible. No calcular ni sumar en React, no reemplazar respuesta del backend con totales de p├ígina.

### 4.3 Detalle de documento y pagos (lecturas contractuales existentes)

- `GET /api/finanzas/documentos/{id}/` ofrece schema de documento y cobranza seg├║n serializer.
- `GET /api/finanzas/documentos/{id}/pagos/?page=N` paginado; filtros opcionales contractuales `activo=true|false`, `medio`, `fecha_pago_desde`, `fecha_pago_hasta` en pareja. Pago incluye medio/fecha/monto y referencias de soporte; esta SPEC de cartera no requiere mostrar el respaldo salvo aprobaci├│n de detalle/privacidad por separado.
- `GET /api/finanzas/documentos/{id}/historial/?page=N` y rutas de historial de pagos existen seg├║n urls reales. Si la entrega se limita a cartera/resumen, no a├▒adir vistas de detalle/pagos/historial sin ratificar alcance; se mantienen como opciones diferidas.

### 4.4 Permisos y errores

- 400: filtros/paginaci├│n inv├ílidos; exponer campos de error permitidos y conservar filtro.
- 401: delegar renovaci├│n compartida al AuthClient; si termina sesi├│n, limpiar datos.
- 403: indicar acceso no permitido y retirar datos; no insistir ni escalar.
- 404: recurso no disponible; no revelar existencia.
- 405: discrepancia contractual; no cambiar el m├®todo para hacer pasar UI.
- 409 (si se a├▒aden flujos futuros): conflicto de dominio; no presentar ├®xito ni reintentar escritura.
- 429: respetar `Retry-After` si lo devuelve el backend.
- 5xx/red/timeout: mostrar fallo/relectura; no inventar resultado. GET se puede reintentar a petici├│n del usuario; no iniciar mutaciones en esta entrega.

## 5. UX, arquitectura y estados

- Reemplazar `PendingIntegration` solo para `cobranzas` cuando rol G/AF y despu├®s de SPEC aprobada/integrada.
- Pantalla de cartera con resumen del conjunto filtrado, tabla responsive y accesible, estado de cobranza del backend, moneda CLP, fechas, folio/naturaleza de registro externo y neto/impuesto/total/saldo en strings exactos. No mostrar cero cuando no exista documento: la API de cartera solo lista documentos existentes vigentes.
- Filtros disponibles: estado, cliente ID, obra ID, rango emisi├│n y rango vencimiento; UI no manda par├ímetros vac├¡os. Clarificar que los filtros son globales de servidor y mantenerlos al paginar/actualizar.
- Diferenciar carga, error, vac├¡o, sin permiso y datos stale; no hay datos mock. Reconsultar simult├íneamente cartera/resumen al cambiar filtros y despu├®s de refresh, con abort/cancelaci├│n y descarte de respuestas viejas.
- Detalle: decidir y aprobar aparte antes de implementar; si se incluye tras aprobaci├│n, leer solo endpoint contractual, sin acci├│n de mutaci├│n o descarga no especificada.
- Accesibilidad: labels, foco visible, teclado, encabezados sem├ínticos, aria-live para estados, botones reales, tabla navegable m├│vil a 320/375/768/1024 px. Reutilizar tokens/componentes FYAG.

Propuesta m├¡nima de archivos despu├®s de aprobaci├│n: `frontend/src/finanzas/api.js`, `frontend/src/finanzas/domain.js`/estado UI, `frontend/src/pages/Cobranzas.jsx`, montaje acotado en `frontend/src/app.jsx`, pruebas Node en `frontend/tests/`. No tocar backend ni a├▒adir dependencia.

## 6. Seguridad y concurrencia

- Access JWT solo en memoria; refresh exclusivamente cookie HttpOnly. No incluir bearer en URLs, variables p├║blicas, logs o storage.
- La vista G/AF lee solo proyecci├│n autorizada del backend. No mostrar Finanzas a S/T/TI; nunca confiar en guards visuales como seguridad.
- Montos son strings; no `Number`, `parseFloat`, float, f├│rmulas o totales derivados en React. Backend es autoridad de saldo/estado, y la tabla evita mezclar total con neto.
- Cualquier dato que contenga PII/ref de pago se conserva en memoria solo mientras est├í montada la vista y se limpia al logout/cambio de cuenta. No persistir PII en caches duraderas.
- GETs cancelables, timeout razonable, no aplicar respuestas de filtros/usuarios viejos. No implementar escrituras/idempotencia aqu├¡.
- Backend ya impone filtros estrictos, paginaci├│n 25, roles y saldos transaccionales; frontend valida respuestas/paginaci├│n y no atribuye seguridad adicional a esas validaciones.

## 7. Plan de pruebas y aceptaci├│n

Automatizadas frontend:
1. G/AF consultan exactamente cartera y resumen; S/T/TI no hacen requests aunque se monte p├ígina de forma aislada.
2. Schemas estrictos para p├ígina, documento, origen, cobranza, conteos y decimal strings; respuesta incompleta, importes num├®ricos, estado desconocido, URL next externa/ajena se rechazan.
3. Filtros permitidos, pareja de fechas, validaci├│n ISO/IDs, ausencia de par├ímetros vac├¡os/repetidos/aliases; request lleva filtros verdaderos del servidor.
4. Cartera paginada 25, next/previous seguros, resumen refleja conjunto filtrado y no suma solo resultados de p├ígina.
5. Estados vac├¡o/cargando/error, 400/401/403/404/405/409/429/5xx/red/timeout, refresh de sesi├│n y cambio de usuario/logout con datos tard├¡os descartados.
6. No mostrar valores a├▒adidos extra, ni simular un documento/saldo/pago, ni persistir token/PII; escritura de Cobranzas no aparece en esta entrega.
7. A11y/responsive en 320, 375, 768, 1024.
8. `npm test`, `npm run build`; `npm ci` si cambian lock/dependencias. E2E dev G/AF solo con cuentas autorizadas, distinguiendo prueba API de UI.

Criterios de aceptaci├│n: cartera real y resumen consultan API; paginaci├│n/filtros del servidor; importes/estados provienen del backend sin c├ílculo cliente; roles G/AF y negativos S/T/TI correctos; m├│dulos a├║n pendientes siguen claramente indicados; errores no muestran ├®xito falso; pruebas y CI reportados con evidencia real.

## 8. Riesgos y pendientes de definici├│n

- **Decisi├│n pendiente:** si Cobranzas frontend se limita a lectura de cartera/resumen (recomendaci├│n inicial) o incluye tambi├®n alta/reverso documental, pagos/anulaciones, estado financiero, sin cobro e historial. La presente SPEC propone dejar todas las escrituras y detalle avanzado fuera de la primera fase.
- Las referencias de respaldo fiscal/bancario pueden contener datos sensibles; su presentaci├│n/retenci├│n visual necesita evaluaci├│n expl├¡cita, no asumir que deben mostrarse en la tabla.
- Un documento revertido no aparece en cartera vigente; no presentar documento hist├│rico como saldo exigible.
- Cobranza vencida es el enum calculado por backend en `America/Santiago`; frontend no calcula fecha ni estado.
- Contratos financieros son sensibles y errores de permiso deben permanecer sin filtraci├│n entre roles.

## 9. Aprobaci├│n y flujo de integraci├│n

1. Esta SPEC frontend complementa SPEC-007, aprobada por el responsable. No hay permiso de implementar mientras no est├® integrada en `main`.
2. Tras aprobaci├│n, publicar solo documentaci├│n en rama `docs/spec-014-frontend-cobranzas` con PR descriptivo, sin c├│digo de funcionalidad; no merge sin autorizaci├│n separada.
3. Tras merge documental autorizado: actualizar `main` local usando `git switch main` y `git pull --ff-only origin main`.
4. Solo despu├®s crear rama `feature/frontend-014-cobranzas` desde `origin/main` y con encargo expl├¡cito implementar la fase aprobada; pruebas e informe humano antes de commit/push.
5. No ejecutar commit/push/PR ni merge autom├íticamente. Backend de finanzas no se modifica.

## 10. Referencias

- `specs/007-finanzas-cobranzas.md` (contrato backend y l├¡mites tributarios).
- `backend/apps/finanzas/{urls.py,views_documentos.py,views_pagos.py,serializers_documentos.py,serializers_pagos.py,consultas_cobranzas.py,permissions.py,services_documentos.py,services_pagos.py,tests/}`.
- `backend/config/urls.py`.
- `frontend/AGENTS.md`, `frontend/src/app.jsx`, `frontend/src/data/constants.js`.
- `frontend/src/auth/{AuthContext.jsx,client.js}`, `frontend/src/comercial/{api.js,ui.jsx,scope.js}`.

## 11. Seguimiento de implementación local (14-11-2026)

- En el worktree local existe `frontend/src/pages/Cobranzas.jsx`, montado para GERENCIA y ADMINISTRATIVO_FINANZAS. Consulta `/api/finanzas/cobranzas/` y `/api/finanzas/cobranzas/resumen/`, con filtros/paginación de servidor y solo lectura; no implementa altas, pagos, reversos ni detalle no aprobado.
- `frontend/tests/integrations-domain.test.js` incluye pruebas de consultas/roles para Cobranzas. La suite completa local aprobó 159 pruebas y `npm run build` aprobó el 14-11-2026; CI y E2E de UI con cuentas reales no se ejecutaron.
- Los cambios siguen locales, sin commit/push/PR/merge. El estado de aprobación/integración documental de esta SPEC no cambia por esta nota; revisar y autorizar antes de publicar.
