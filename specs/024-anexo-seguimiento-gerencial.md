# SPEC-024 — Anexo de seguimiento comercial gerencial
GET /api/presupuestos/seguimiento-comercial/ exclusivamente GERENCIA autenticada. Solo lectura. Paginación 25, filtros page, estado, desde/hasta (fecha de creación civil inclusiva), buscar (código, cliente, descripción, máximo 100), sin_actualizar=true (revisión interna, aprobación interna o enviado al cliente, sin actualización en al menos siete días).

Resumen de la cohorte temporal antes de estado/búsqueda/antigüedad: total, sin_actualizar, dias_sin_actualizar, respuestas_cliente, tasa_aceptacion, estados (cantidad y monto_neto). Tasa = aceptados/(aceptados+rechazados) según estado actual, null sin respuesta. Se cuentan registros incluidas revisiones; no oportunidades únicas ni decisiones históricas. Históricos de Gerencia agrupados para revisión interna; estado_original preservado. Importes cotizados netos CLP, no ingresos. Prioriza pendientes sin actualizar; luego orden de creación descendente.

Lectura por lotes de 100, prefetch de ítems y cliente, Decimal y redondeo del dominio. Sin migraciones ni cambios al flujo operativo. Validar rendimiento productivo: recorre cohorte completa y ordena filas proyectadas; lectura no equivale a cierre transaccional.

OpenAPI: backend/docs/openapi/SPEC-024-seguimiento-gerencial-v1.json. Pruebas: apps.comercial.tests.test_seguimiento_gerencial.
