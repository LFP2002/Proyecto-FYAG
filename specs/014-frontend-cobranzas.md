# SPEC-014 — Integración frontend FYAG: Cobranzas

**Estado del documento:** texto previo a la implementación; la aprobación/integración documental descrita en el historial no se considera confirmada por el checkout. **Estado del código verificado:** la rama local contiene `frontend/src/pages/Cobranzas.jsx` con cartera/resumen de solo lectura. **Pendiente de implementación:** detalle administrativo de documentos, registro/listado/historial de pagos y reversión/anulación desde la interfaz; revisar y aprobar expresamente ese alcance antes de publicarlo. **Sin aprobación inventada:** este cambio no declara aprobaciones ni integración en `main`.

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
