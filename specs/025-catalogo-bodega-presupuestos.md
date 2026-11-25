# SPEC-025 — Catálogo de Bodega en Presupuestos

> Decisión funcional autorizada: reutilizar materiales de Bodega al cotizar, manteniendo separados costo de adquisición y precio comercial. Implementación incremental en la rama de trabajo; no implica autorización de merge ni despliegue. Sustituye únicamente la prohibición de consulta/vinculación de catálogo de SPEC-024 en los incrementos expresamente definidos aquí.

## 1. Responsabilidades e invariantes

- Bodeguero administra catálogo e ingresos físicos. La valorización sigue bajo las atribuciones actuales de Finanzas (SPEC-019B). Bodega no define ni consulta precios de venta por esta integración.
- Supervisor de Obras elabora sus propios borradores; Finanzas elabora y gestiona borradores, y decide su aprobación. Gerencia conserva lectura de presupuestos; no elabora ni aprueba. No se amplían permisos de Clientes ni de Inventario.
- El precio unitario de venta es un dato comercial por línea, ingresado explícitamente por el usuario autorizado. Nunca copiar costo de adquisición, costo promedio ni valorizaciones como precio de venta.
- Cotizar no depende de existencias y no reserva, consume, compra, despacha, genera faltantes ni registra gastos. La ejecución real de Obras mantiene los flujos SPEC-019B/C.
- Los importes conservan Decimal exacto, restricciones, cálculos, estados, alcance por autor, congelamiento y revisión de SPEC-003B/024.

## 2. Incremento A — Selector de materiales (solo lectura)

GET /api/presupuestos/materiales-elegibles/

- Roles: exclusivamente ADMINISTRATIVO_FINANZAS y SUPERVISOR_OBRAS, con sesión operativa revalidada por el dominio comercial. Otros roles: 403; no autenticado: 401. GET, HEAD y OPTIONS; escrituras no admitidas.
- Filtro fijo activo=True. Búsqueda opcional `buscar` por código o nombre (sin distinción de mayúsculas, 1–150 caracteres tras trim); `page` positiva. Rechazar parámetros desconocidos, repetidos o inválidos con 400. Paginación 25, orden por nombre e id.
- Envoltorio DRF count/next/previous/results. Proyección de cada resultado: id (entero), codigo, nombre, unidad (strings). No exponer costos, saldos, movimientos, precios, usuarios ni credenciales.
- No modificar tablas ni requerir migraciones. El selector puede reutilizar nombre y unidad para líneas libres; **no existe todavía una relación persistente**. La carga masiva atómica tampoco forma parte de A.
- UI futura: buscar/paginar, elegir material, autocompletar descripción y unidad; precio de venta manual, orden automático, líneas personalizadas. No afirmar vínculo persistente si solo se copian campos.

## 3. Incremento B — Vínculo persistente (diseño, aún no implementado)

- FK opcional protegida de PresupuestoItem a ArticuloInventario mediante migración nueva, sin inferir relaciones para líneas anteriores. Conservar descripción y unidad comerciales como instantánea; estudiar conservación del código de origen.
- Seleccionar materiales activos al crear o cambiar vínculo; conservar referencias históricas y revisiones de material posteriormente desactivado. No reescribir instantáneas por cambios en catálogo.
- Mantener líneas personalizadas sin vínculo (servicios, mano de obra u otros). Revisar orden global de locks con Inventario y Obras; no introducir inversiones de bloqueo. Validar relectura del catálogo y autorización bajo transacción.
- Contrato HTTP aditivo, campo opcional, compatibilidad con clientes anteriores, actualización de OpenAPI y pruebas de migración limpia/upgrade. Decidir en diseño detallado comportamiento de cambio de material y creación masiva idempotente antes de implementarlos.

## 4. Verificación y cierre

A: matriz de seis roles, JWT ausente, proyección exacta, artículo inactivo excluido, búsqueda, paginación, parámetros inválidos y métodos denegados; sin escrituras de inventario. Django check, makemigrations --check, tests dirigidos Comercial/Inventario, regresión completa. B requiere además pruebas de migración, historia, concurrencia, revocación, permisos por propietario, estados y ausencia de movimientos/gastos.

Actualizar OpenAPI por incremento y probar UI con API real, incluyendo catálogo vacío, errores y material sin existencias. No crear PR ni merge sin autorización expresa y validación. Estado de esta SPEC: contrato A definido; B pendiente de implementación y validación.
