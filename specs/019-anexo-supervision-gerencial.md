# SPEC-019 — Anexo de supervisión gerencial de inventario

GET /api/inventario/supervision-gerencial/ exclusivo GERENCIA. Solo lectura; no modifica permisos de endpoints existentes. Paginación 25, parámetros page, seccion (existencias/mermas), filtro (sin_stock/pendiente o bodega/obra según sección), buscar (código/nombre, máximo 100).

Resumen global independiente de filtros: valor_stock_valorado (suma del saldo valorizado por promedio, redondeo monetario por material; no representa valor total si hay stock sin valorar), sin_stock (solo activos), pendientes_valoracion (diferencias físicas/valoradas o falta de dato), mermas_bodega_neto, mermas_obra_informativo, mermas_bodega, mermas_obra, mermas_sin_valor (aprobadas en el mes calendario actual hasta hoy, fecha de decisión), mermas_pendientes (todos los períodos), desde/hasta. Los importes de obra no se agregan a la baja de bodega ni al costo de obra por segunda vez. Incluye stock valorizado de materiales inactivos. Se conservan cantidades y monedas como cadenas decimales; null para valor no disponible. Fecha civil zona horaria configurada del sistema.

UI exclusiva Gerencia: nueve módulos principales, Auditoría secundaria en cabecera, Solicitudes y Mermas salen del menú principal, Mermas se integra a Inventario en consulta consolidada. Los otros roles conservan navegación y permisos. No modifica registros ni requiere migración. El servicio lee por lotes y ordena filas proyectadas; validar rendimiento con inventario grande. No constituye cierre transaccional.

Pruebas dirigidas: apps.inventario.tests.test_supervision_gerencial, frontend/tests/navigation-mobile.test.js, frontend/tests/inventory-manager.test.js.
