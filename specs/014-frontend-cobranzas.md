# SPEC-014 — Integración frontend FYAG: Cobranzas

> **Revisión autorizada 17-11-2026:** el responsable autorizó expresamente en esta tarea las correcciones frontend y las tres operaciones existentes de SPEC-007: obras elegibles, estado financiero y cierre administrativo sin cobro. Se implementan y prueban **localmente**, sin autorizar commits, push, PR, merge ni cambios backend. Esta autorización de alcance no acredita aprobaciones documentales históricas ni integración de esta revisión en `main`. Los párrafos anteriores a esta revisión se conservan como antecedentes y se precisan en las secciones de seguimiento al final.

**Antecedente documental previo a la revisión del 17-11-2026:** el texto reducido describía únicamente cartera/resumen y dejaba pendientes las operaciones administrativas. Se conserva ese antecedente, pero el estado local actual se detalla a continuación. La aprobación/integración documental histórica no se acredita con este checkout.

## Alcance vigente en código

La interfaz de cartera consulta `/api/finanzas/cobranzas/` y `/api/finanzas/cobranzas/resumen/` con filtros y paginación del servidor. GERENCIA y ADMINISTRATIVO_FINANZAS pueden consultar conforme al backend; el frontend no calcula saldos, no emite DTE, no procesa pagos ni transfiere dinero.

La rama en curso agrega una interfaz administrativa de Finanzas sobre endpoints ya definidos para documento externo, pagos reales informados, historiales, reversión/anulación y adjuntos de respaldos. La autorización efectiva pertenece al backend; solo ADMINISTRATIVO_FINANZAS ve escrituras. La validación de contrato, confirmación de relecturas y pruebas de integración siguen pendientes hasta completar verificaciones reales.

## Pendiente y decisiones

- Verificar que los endpoints financieros están disponibles en el backend desplegado, confirmar esquemas completos y filtros/paginación de historiales.
- Revisar con el responsable el alcance de escritura de SPEC-014; esta actualización no acredita aprobación separada.
- Validar con entorno QA autorizado registro/replay idempotente de pagos, conflictos de saldo, pagos activos antes de revertir, errores y cargas antimalware.
- No añadir emisión de DTE, cobro en línea, transferencias, cálculos financieros de frontend, ni acceso directo a PostgreSQL.

## Contrato backend de referencia

- Cartera y resumen: `GET /api/finanzas/cobranzas/` y `/api/finanzas/cobranzas/resumen/`.
- Documento: `GET/POST /api/finanzas/documentos/`, `GET /api/finanzas/documentos/{id}/`, `POST /api/finanzas/documentos/{id}/revertir/` y `GET .../historial/`.
- Pagos: `GET/POST /api/finanzas/documentos/{id}/pagos/`, `GET .../pagos/{pago_id}/`, `POST .../pagos/{pago_id}/anular/`, historial paginado.
- Los detalles de respuestas, validaciones, RBAC y errores están en `backend/apps/finanzas/` y `specs/007-finanzas-cobranzas.md`; validar contra fuentes reales antes de ampliar schemas cliente.
- Respaldo privado documental: SPEC-012B y rutas `/api/adjuntos/`; verificación antivirus es fail closed.

## Seguridad y límites

- Reutilizar `useAuth().request`; no almacenar tokens o datos financieros en almacenamiento persistente.
- GERENCIA lectura; ADMINISTRATIVO_FINANZAS puede escribir según permiso del backend; los demás roles no deben invocar rutas financieras.
- Usar strings decimales y estados devueltos por API sin cálculos cliente. Los pagos son registros de hechos externos, no movimientos de dinero de FYAG.
- Confirmar anulaciones/reversiones con motivo y referencia externa; ante 409 no mostrar éxito ni reintentar automáticamente.
- Informar en este documento lo implementado localmente, pruebas realmente ejecutadas y pendientes; no declarar CI/E2E o aprobación sin evidencia.

## Revisión contractual local — 17-11-2026

### Objetivo, alcance y exclusiones

Completar la administración frontend de SPEC-007 usando los servicios existentes. `Cobranzas.jsx` conserva cartera/resumen; `FinanceAdmin.jsx` organiza documentos, selección elegible y consulta por ID; `FinanceDocument.jsx` presenta detalle, pagos y sus historiales. `finance.js` valida proyecciones, sin calcular montos. No cambia autenticación, backend, Obras, cortesías históricas, contabilidad, SII ni bancos. MongoDB no determina estados o saldos.

### Roles

| Operación | GERENCIA | ADMINISTRATIVO_FINANZAS | S / T / TI |
| --- | --- | --- | --- |
| Cartera, resumen, documentos, pagos, historiales, estado financiero | Lectura | Lectura | Sin acceso |
| Obras elegibles | No | Lectura | No |
| Registrar/revertir documento, registrar/anular pago, registrar sin cobro | No | Según validación Django | No |
| Respaldos y anotaciones 012B | Lectura | Lectura/escritura autorizada | No |

### APIs y contratos

Todos los endpoints son existentes, verificados en `backend/apps/finanzas/`; no son propuestas futuras. Prefijo `/api/finanzas/`:

| Método y ruta relativa | Entrada / respuesta principal |
| --- | --- |
| GET `cobranzas/`, `cobranzas/resumen/` | Filtros `estado`, `cliente`, `obra`, `fecha_vencimiento_desde/hasta`, `fecha_emision_desde/hasta`; página solo en cartera; importes y conteos calculados por backend |
| GET `obras-elegibles/?page=N` | Orígenes financieros paginados, identificados por `obra`, **sin campo id**; excluye SIN_COBRO |
| GET `obras/{id}/estado-financiero/` | `origen`, `estado_financiero`, `documento_vigente`, `cierre_sin_cobro` |
| POST `obras/{id}/registrar-sin-cobro/` | Exclusivamente `{motivo_registro: string}`; cierre con `id`, `obra`, `cortesia`, actor, fecha y estado |
| GET/POST `documentos/` | Página o registro externo con `obra` entero, tipo, folio string, fechas ISO, montos decimales string y referencia |
| GET `documentos/{id}/`, `documentos/{id}/historial/` | Documento / eventos paginados |
| POST `documentos/{id}/revertir/` | `{motivo, referencia_rectificacion_externa}` |
| GET/POST `documentos/{id}/pagos/` | Página / `{monto, fecha_pago, medio, referencia_respaldo, observacion}` y `Idempotency-Key` |
| GET `documentos/{id}/pagos/historial/` | Eventos paginados independientes |
| POST `documentos/{id}/pagos/{pago_id}/anular/` | `{motivo, referencia_reversion_externa}` |

Origen: Obra, presupuesto, cliente, moneda, monto neto aprobado, finalización y cortesía. Estados financieros: `PENDIENTE_FACTURACION`, `PENDIENTE_REGISTRO_SIN_COBRO`, `SIN_COBRO`, `DOCUMENTADO`. Documento `VIGENTE` o `REVERTIDO`; en este último `cobranza=null`, nunca saldo cero fabricado. Páginas DRF de hasta 25 filas con `count/next/previous/results`; las tres paginaciones de pagos e historiales no se mezclan ni se presentan como completas.

### UX, concurrencia y seguridad

- Selector elegible paginado conserva el ID elegido al cambiar página; consulta independiente por ID permite localizar SIN_COBRO.
- Registro sin cobro exige consulta previa, estado compatible, finalización informada, cortesía SIN_COBRO, motivo y confirmación. La proyección **no expone presupuesto.estado ni cierre histórico de costos**: no se inventan campos y Django valida definitivamente esos requisitos.
- Cada mutación invalida vistas afectadas y exige relecturas del detalle, documentos y cartera/resumen antes de confirmar éxito o limpiar formularios. Si fallan, se conserva el bloqueo y no se repite automáticamente.
- Un pago incierto conserva payload y clave en memoria, bloquea edición y requiere relectura más reintento explícito idempotente. Una intención rechazada solo se descarta mediante decisión explícita; contenido nuevo usa clave nueva.
- Contextos keyed por usuario/rol/recurso y scopes descartan respuestas tardías. `400` conserva datos, `403/404` no escalan acceso, `409` exige revisión, red/5xx no prueban fracaso. `401` usa el cliente de sesión existente.
- Adjuntos privados: FormData, límites PDF 8 MiB e imagen 5 MiB, descarga autenticada, anotaciones scoped con revisión CAS, sin edición por Gerencia. `413/422/503` no se presentan como éxito.
- Etiquetas accesibles, estados de carga/vacío/error/bloqueo, tablas desplazables y paginación nombrada; no hay recarga completa de página ni almacenamiento persistente de datos sensibles.

### Aceptación, pruebas y publicación

1. Roles ajenos no solicitan APIs financieras; Gerencia no consulta elegibles ni escribe.
2. Selector navega páginas sin perder elección; sin cobro usa consulta independiente y un único POST contractual.
3. Cambiar documento reinicia las tres páginas y descarta lecturas del anterior.
4. Escritura y relectura fallida nunca se anuncian como éxito; pago incierto conserva clave/payload.
5. Reversión/anulación actualizan vistas afectadas con importes del servidor.

Pruebas sintéticas contractuales en `frontend/tests/integration-corrections.test.js`, fixtures en `tests/helpers/finance-contract.js`, regresiones en `integrations-domain.test.js` y `obras-costos-ui.test.js`. Resultados de la ejecución vigente en `Cosas pendientes.txt`; no equivalen a QA real. Pendientes: revisión técnica, QA aislado autorizado, concurrencia real, permisos y ClamAV. Estado documental: revisión local de alcance autorizado; estado código: implementado localmente, sin publicación acreditada. Procedimiento: informe y revisión antes de cualquier commit/push/PR; merge requiere autorización posterior separada. Rollback de esta revisión, si se autoriza, mediante reversión acotada de su diff, nunca descartando trabajo ajeno.
