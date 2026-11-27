# SPEC-004 — Anexo de supervisión gerencial de obras

## Contrato
GET /api/obras/supervision-gerencial/ — exclusivamente GERENCIA autenticada. Solo lectura; sin cambios de permisos de otros endpoints, sin migraciones.

Parámetros: page (25 filas), estado (estado de Obra), atencion (todas, requiere, sin_alertas), prioridad (sin_programar, presupuesto_superado, suspendidas), buscar (máximo 100 caracteres, código/cliente/categoría/responsable). Se rechazan parámetros desconocidos o repetidos.

Respuesta paginada count/next/previous/results y resumen global independiente de filtros: total, en_ejecucion, sin_programar, presupuesto_superado, suspendidas, requieren_atencion. Fila: id, codigo, cliente_nombre, categoria_nombre, tecnico_nombre, estado, fecha_programada, presupuesto_neto, costo_total, diferencia_neta, porcentaje_utilizado, costos_provisionales, sin_cobro, alertas, nivel.

Importes netos CLP en cadenas decimales; porcentaje con un decimal y null si presupuesto cero. Costos de cierre histórico cuando existe, en otro caso gastos vigentes (descontando devoluciones) y turnos acreditados, con las reglas de services_costos. No equivale a avance físico, margen contable ni flujo de caja. Se indica provisionalidad y cortesía. Alertas de supervisión derivadas: presupuesto superado, suspendida, planificada sin programar, obra activa sin responsable y finalizada sin cierre. No sustituyen el módulo Alertas ni significan ausencia de otras incidencias. Prioridad crítica, atención, normal; dentro de cada grupo, orden de creación descendente. Indicadores globales antes de filtros.

## Implementación y verificación
Lectura por lotes de 100 con prefetch de ítems, gastos vigentes y turnos validados; reutiliza reglas Decimal del dominio, no N+1 ni peticiones individuales desde el navegador. El cálculo recorre la cartera completa en cada consulta y guarda filas proyectadas para ordenar/paginar; validar rendimiento con volumen productivo antes de adoptar agregados persistidos. Es una lectura de supervisión, no un cierre transaccional: cambios concurrentes pueden afectar lecturas de distintos lotes. Sin cambios al flujo Supervisor/Finanzas/Técnico.

Pruebas dirigidas: apps.obras.tests.test_supervision_gerencial y frontend/tests/obras-ui.test.js. Pendiente ejecución local/CI y revisión visual.

OpenAPI: `backend/docs/openapi/SPEC-004-supervision-gerencial-v1.json`.
