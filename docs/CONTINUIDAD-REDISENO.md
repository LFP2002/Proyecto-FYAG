# FYAG — Continuidad del rediseño
Actualizado: 26-11-2026. Nota de traspaso de desarrollo, no contrato funcional. Retirar o archivar antes del cierre de producción si corresponde; conservar SPEC y OpenAPI.

## Contexto
Repositorio LFP2002/Proyecto-FYAG, rama reajustes-visuales-frontend. No merge a main sin autorización expresa. Backend Django REST Framework/PostgreSQL/MongoDB/Redis, Docker Compose; frontend React/Vite. Rediseño por roles, actualmente Administrativo/Finanzas. Último commit de código al redactar: bebefdcc5cf7e3aa248aa0c091a65b2a3d8dce5a. Confirmar HEAD y estado local/remoto.

## Método acordado
- ChatGPT revisa capturas y archivos reales de la rama; propone diseño centrado en las tareas del rol, reutilizando componentes y patrones existentes. Para rediseños significativos presentar maqueta renderizada/interactiva en chat (no imagen generada), esperar aprobación. Correcciones pequeñas solicitadas directamente se implementan.
- ChatGPT implementa directamente mediante GitHub; no delegar copia manual al usuario si existe acceso. OpenCode solo para operaciones locales complejas que ChatGPT no puede realizar, con prompts cortos. El usuario ejecuta pruebas locales.
- Revisar permisos, contratos y alcance por rol; no alterar otras vistas ni reglas de negocio. Mantener idempotencia, bloqueo de doble envío, relectura, reconciliación y trazabilidad. No inventar datos ni ampliar permisos. Cambios de contrato: SPEC, OpenAPI y pruebas dirigidas. Antes de publicar verificar imports, sintaxis, duplicados, diff y releer archivos. En sustituciones JS usar función de reemplazo o cortes de cadena, no cadenas con secuencias especiales de dólar. El fallo reciente de Egresos duplicó el componente.
- Respuestas breves en español, commit confirmado, comandos PowerShell con carpeta exacta, pendientes honestos. No pedir suite completa por defecto. Frontend desde raíz: git pull --ff-only; cd frontend; node --test tests/<archivo>.test.js; npm run build. Backend desde raíz: git pull --ff-only; docker compose restart backend cuando proceda; docker compose exec -e POSTGRES_DB=fyag_spec018c_c2_qa backend python manage.py test <modulos> (verificar configuración QA vigente). Sin reinicio por CSS/JS.

## Diseño permanente
- Interfaz autoexplicativa, textos humanos, nombres/códigos/referencias en lugar de IDs internos, estados legibles; formato CLP exacto y fechas dd/mm/aaaa; cantidades con unidad y decimales significativos. Consistencia azul institucional, modo oscuro, responsive y tipografía de FYAG.
- Ancho completo estable para fichas, evitar contenedores anidados y tarjetas estrechas que cambian de tamaño. Formularios horizontales coherentes en escritorio; botón Volver compacto a la izquierda. Acciones contextuales, no mostrar operaciones incompatibles o imposibles, separar acciones destructivas. Encabezados y celdas alineados: montos a derecha, estado y acciones coherentes.
- Búsqueda global y filtros plegables con limpiar; paginación solo si necesaria, conservar filtros y validar enlaces. No derivar totales globales de una página.
- Estados vacíos obligatorios con icono discreto, título y explicación útil: sin registros, sin selección/período, sin resultados; carga discreta, error y reintento; explicar acción no disponible. Evitar pantallas aparentemente rotas.
- Gráficos solo si aportan interpretación, no abusar de barras de progreso. No sumar cantidades de unidades incompatibles; no inventar precios, valores o estados. Distinguir costo, pago real, documento externo y saldo bancario.

## Avance AF
Clientes: tabla, búsqueda y detalle/formulario independiente. Presupuestos: selección real cliente/material, ítems compactos; no reordenar si contrato no lo permite; 59 pruebas backend SPEC-024 confirmadas por usuario.
Obras: vista económica AF, neto aprobado, situación financiera, costos provisionales/validados, acceso a presupuesto/cobranza; endpoint /api/finanzas/obras-resumen/, SPEC-007. Commit referencia 24fc1c1.
Cobranzas: indicadores, búsqueda, ficha a ancho completo, pagos contextuales, anulación/reversión bajo demanda, respaldos; revertidas solo consulta; no emitir DTE ni mover dinero. Referencias bfd99c0, 5316b76.
Alertas: bandeja reutilizada de Gerencia, prioridades reales, atención con motivo, enlaces contextuales, resolución automática backend; 259f412.
Reportes: presentación Gerencia adaptada a único reporte autorizado, filtros y menú Excel/PDF/CSV, período consultado; b081ca3.
Egresos: búsqueda/total global de activos, ficha, selector de obras, anulación contextual, flujo separado; estados vacíos; columnas y waterfall firmado con eje cero. SPEC-021 y OpenAPI; 5d1cc54, 044ab40, d72a20f; reparación bebefdc. Compilación posterior no confirmada explícitamente. La mayoría de pruebas locales y revisión visual no consta expresamente; no declarar aprobadas.

## Inventario y bodega AF

Implementado el 26-11-2026. Cuatro pestañas: Inventario, Movimientos, Valoración y Saldo inicial. Consulta exclusiva /api/inventario/finanzas/ con búsqueda, totales globales, valor neto de cantidades valorizadas, filas con nombres/códigos y candidatos elegibles por orden. Formularios guiados, UUID congelada ante incertidumbre, POST originales intactos. Fichas a ancho completo, estados vacíos y paginación condicional. SPEC-019B y OpenAPI complementario inventario-finanzas-v1.json; pruebas apps.inventario.tests.test_finanzas_inventario y frontend/tests/inventario-finanzas-ui.test.js. Pendiente: ejecución local, compilación y validación visual. No merge.

## Siguiente módulo AF

Continuar con Mermas cuando el usuario confirme o solicite avanzar. Revisar capturas y contratos, reutilizar patrones de otros roles sin ampliar permisos y presentar propuesta antes de implementar un rediseño significativo.
