# SPEC-004C — Consulta operativa del Técnico

## Alcance
Interfaz de Mis obras (tarjetas, búsqueda, filtros, prioridad de ejecución) y Mis turnos (turno activo independiente del historial paginado), exclusiva de Técnico. La consulta no cambia asignaciones ni permisos; solo obras con participación activa, turnos propios y campos ya permitidos en 004B-2. Los turnos de obras fuera de alcance no aparecen. Los otros roles conservan las rutas y vistas actuales.

## API
GET /api/obras/mis-obras/ conserva los filtros existentes y añade buscar (1–150 caracteres, sin controles; código OB exacto o coincidencia parcial insensible a mayúsculas de cliente/categoría). Por defecto ordena EN_PROCESO, PLANIFICADA, SUSPENDIDA, restantes; dentro de cada grupo fecha de creación e ID descendentes. El ordering explícito anterior prevalece. GET /api/obras/ no incorpora el filtro.
GET /api/obras/mis-turnos/ acepta page y estado opcional OBSERVADO, PENDIENTE_REVISION, VALIDADO. La respuesta incluye count, next, previous, results (hasta 25 turnos cerrados propios en obras asignadas, observados primero y luego inicio/ID descendentes), activo (turno abierto propio o null, independiente de filtros/paginación), hora_servidor (ISO 8601). Cada turno usa TurnoLecturaSerializer y añade obra_codigo, categoria_nombre, obra_estado. Sin costos ni observaciones económicas. Respuesta privada no-store. Parámetros repetidos/desconocidos: 400. Roles ajenos: 403. La hora del servidor ancla una estimación visual usando reloj monotónico del navegador; no modifica duración oficial. La lectura no reserva ni bloquea recursos. Inicio desde la obra elegible, cierre/subsanación y descarga privada reutilizan rutas y validaciones 004B-2. No hay reenvíos automáticos; ante incertidumbre reconsultar antes de continuar. No se introducen migraciones.

## Interfaz
Menú Mis obras, Mis turnos, Solicitudes de materiales, Mermas, Chat interno. Ficha técnica sin información económica ni identificadores internos redundantes. Turnos propios, descripción obligatoria de cierre y fotos opcionales conforme al contrato vigente. Adjuntos: menú de opciones exclusivamente en ficha técnica, descarga directa, CAS y permisos preservados. Modo oscuro, responsive, Bootstrap Icons originales. Solicitudes y Mermas no cambian en este incremento.
## Verificación
Pruebas backend de alcance, filtro y turno activo independiente; pruebas frontend de navegación y cierre. Compilación, regresión y verificación móvil pendientes de ejecución en el entorno local.
