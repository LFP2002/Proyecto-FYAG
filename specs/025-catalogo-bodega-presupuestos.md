# SPEC-025 — Catálogo de Bodega en Presupuestos

> Decisión funcional autorizada: reutilizar materiales de Bodega al cotizar, manteniendo separados costo de adquisición y precio comercial. Implementación incremental en la rama de trabajo; no implica autorización de merge ni despliegue. Sustituye únicamente la prohibición de consulta/vinculación de catálogo de SPEC-024 en los incrementos expresamente definidos aquí.

## 1. Responsabilidades e invariantes

- Bodeguero administra catálogo e ingresos físicos. La valorización sigue bajo las atribuciones actuales de Finanzas (SPEC-019B). Bodega no define ni consulta precios de venta por esta integración.
- Supervisor de Obras elabora sus propios borradores; Finanzas elabora y gestiona borradores, y decide su aprobación. Gerencia conserva lectura de presupuestos; no elabora ni aprueba. No se amplían permisos de Clientes ni de Inventario.
- El precio unitario de venta de una línea vinculada es exclusivo de Administrativo/Finanzas. Nunca copiar costo de adquisición, costo promedio ni valorizaciones como precio de venta.
- Cotizar no depende de existencias y no reserva, consume, compra, despacha, genera faltantes ni registra gastos. La ejecución real de Obras mantiene los flujos SPEC-019B/C.
- Los importes conservan Decimal exacto, restricciones, cálculos, estados, alcance por autor, congelamiento y revisión de SPEC-003B/024.

## 2. Incremento A — Selector de materiales (solo lectura)

GET /api/presupuestos/materiales-elegibles/

- Roles: exclusivamente ADMINISTRATIVO_FINANZAS y SUPERVISOR_OBRAS, con sesión operativa revalidada por el dominio comercial. Otros roles: 403; no autenticado: 401. GET, HEAD y OPTIONS; escrituras no admitidas.
- Filtro fijo activo=True. Búsqueda opcional `buscar` por código o nombre (sin distinción de mayúsculas, 1–150 caracteres tras trim); `page` positiva. Rechazar parámetros desconocidos, repetidos o inválidos con 400. Paginación 25, orden por nombre e id.
- Envoltorio DRF count/next/previous/results. Proyección de cada resultado: id (entero), codigo, nombre, unidad (strings). No exponer costos, saldos, movimientos, precios, usuarios ni credenciales.
- No modificar tablas ni requerir migraciones. El selector puede reutilizar nombre y unidad para líneas libres; **no existe todavía una relación persistente**. La carga masiva atómica tampoco forma parte de A.
- UI futura: buscar/paginar, elegir material, autocompletar descripción y unidad; precio de venta manual, orden automático, líneas personalizadas. No afirmar vínculo persistente si solo se copian campos.

## 3. Incremento B — Vínculo persistente

- FK nullable `articulo` a ArticuloInventario, PROTECT; `codigo_articulo` es una instantánea administrada por servidor. Líneas históricas conservan todos sus campos y quedan con referencia nula y código vacío. Constraint exige coherencia entre FK y código. Reversión bloqueada si existen vínculos.
- POST de ítem libre conserva los cinco campos obligatorios. Para vincular un `articulo` activo, se exigen artículo, cantidad y orden; el servidor toma nombre, unidad y código bajo bloqueo de fila. Si se envían valores de descripción/unidad deben coincidir con el catálogo. El precio de una línea vinculada es opcional al crear y exclusivo de Finanzas.
- PATCH: omitir articulo conserva vínculo. Reenviar el mismo id conserva la instantánea, incluso si el artículo está inactivo. Descripción y unidad de una línea vinculada no se editan libremente: para cambiar material seleccionar otro activo con datos coincidentes, o desvincular explícitamente con null (conserva descripción/unidad salvo cambios explícitos y borra código de referencia). El CRUD general se limita a BORRADOR.
- La lectura añade articulo (id o null) y codigo_articulo (string, vacío para libre). No consultar catálogo al serializar; conservar instantáneas en revisiones incluso si el material fue desactivado o renombrado. No se permite escribir codigo_articulo directamente.
- Locks: Presupuesto -> artículo seleccionado (NO KEY UPDATE) -> revalidación de usuario existente; nunca bloquear existencias, movimientos, obras o gastos por la cotización. La selección de un artículo y su desactivación/edición se serializan por la fila del artículo. No se reserva stock. El vínculo describe la cotización, no una entrega.
- La escritura masiva/idempotente sigue fuera de B; la UI puede seleccionar materiales y guardar cada línea mediante su operación actual, sin prometer atomicidad de múltiples líneas. No se incorpora tarifario.
- OpenAPI aditiva y pruebas de compatibilidad, histórico, autorización, cambios de vínculo y ausencia de movimientos. Revisión de concurrencia y migración obligatoria antes de integrar.

## 4. Verificación y cierre

A: matriz de seis roles, JWT ausente, proyección exacta, artículo inactivo excluido, búsqueda, paginación, parámetros inválidos y métodos denegados; sin escrituras de inventario. Django check, makemigrations --check, tests dirigidos Comercial/Inventario, regresión completa. B requiere además pruebas de migración, historia, concurrencia, revocación, permisos por propietario, estados y ausencia de movimientos/gastos.

Actualizar OpenAPI por incremento y probar UI con API real, incluyendo catálogo vacío, errores y material sin existencias. No crear PR ni merge sin autorización expresa y validación. Estado de esta SPEC: A y B definidos; implementación en rama de trabajo, pendiente de pruebas y revisión de integración.

## Corrección del flujo de precios en materiales vinculados

- Supervisor indica artículo y cantidad; el servidor toma código, descripción y unidad del catálogo al vincular. Sin cambio de artículo se conserva la instantánea, incluso si el catálogo cambia. Los campos libres conservan su contrato.
- Omitir el precio de venta de un nuevo vínculo lo deja pendiente (`null` en lectura). Un cambio de artículo invalida el precio anterior; desvincular exige un precio explícito para el ítem libre. Una revisión copia vínculo, instantánea y precio tal como están, sin tocar el original.
- Con al menos una línea válida y cliente activo se puede enviar a Finanzas con precios pendientes. En revisión, solo Finanzas puede fijar o corregir el precio mediante `PATCH /api/presupuestos/{id}/items/{item_id}/precio-comercial/`; no se reabre ninguna otra edición. La fijación queda registrada con actor, artículo, línea, fecha y valores anterior/nuevo. En borrador Finanzas también puede fijar el precio mediante el CRUD de ítems.
- Un pendiente deja el subtotal de la línea y el monto neto completo en `null`. Seguimiento gerencial tampoco publica un agregado parcial para un estado con presupuestos incompletos; cuenta esos presupuestos en `sin_precio`. Cero explícito no significa pendiente; el flujo vigente exige neto positivo antes de aprobar. La aprobación y el envío no admiten pendientes bajo bloqueo del presupuesto.
- `comercial.0009` solo cambia el esquema y agrega el rastro de fijaciones; no transforma precios, vínculos ni eventos previos. La SPEC-019F sigue valorizando al despacho/devolución, no al cotizar.

### Control de concurrencia de la aprobación comercial

El detalle devuelve `version_comercial`, huella SHA-256 del contenido comercial exacto mostrado. `aprobar-finanzas` exige `version_comercial_esperada` cuando existen ítems vinculados (los únicos editables durante revisión); para presupuestos exclusivamente libres se conserva la compatibilidad y se valida la huella si se proporciona. La comparación ocurre bajo el mismo bloqueo de Presupuesto que usa la fijación de precios. Si difiere, 409 `version_comercial_obsoleta`, sin transición ni evento. No reintentar automáticamente: refrescar y confirmar nuevamente. Las aprobaciones de pendientes legados también exigen neto positivo sin cambiar la política histórica de cliente inactivo. No requiere otra migración.
