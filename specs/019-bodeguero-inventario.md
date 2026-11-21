# SPEC-019 — Bodeguero e inventario de materiales (backend FYAG)

> **Estado: propuesta documental para revisión, 20-11-2026.** El objetivo funcional proviene de los ajustes solicitados para FYAG: incorporar un rol de Bodeguero y un catálogo de materiales con existencias reales, como base de una futura solicitud, entrega y consumo de materiales de Obras. El presente documento **no constituye autorización de implementación, activación productiva ni cambio de permisos comerciales**. Las decisiones de valorización y salida hacia Obras se reservan expresamente para otro incremento.
>
> **Precedencia:** SPEC-002A/002B, SPEC-006B/006C, SPEC-018/018C, SPEC-004/004B y los modelos reales en `main`. No reescribir historia ni migraciones existentes. El frontend pertenece al equipo React y queda fuera de este incremento salvo autorización específica.

## 1. Situación verificada y necesidad

1. `Usuario.Rol` contiene actualmente cinco valores: `GERENCIA`, `ADMINISTRATIVO_FINANZAS`, `SUPERVISOR_OBRAS`, `TECNICO` y `ADMINISTRADOR_TI`. La migración de Usuarios más reciente es `0009_recuperacion_acceso_c2.py`; PostgreSQL valida el catálogo de roles mediante constraint.
2. No existe `backend/apps/inventario/` ni API de existencias en `backend/config/urls.py`.
3. `GastoObra` de SPEC-004B admite `MATERIAL` y otros gastos directos con `cantidad`, `cantidad_devuelta`, `costo_unitario_neto`, registro histórico y controles de revisión. **Un gasto monetario no acredita por sí mismo stock físico**. No crear saldos deduciéndolos de gastos históricos.
4. La autorización de Presupuestos actual pertenece a SPEC-003B: Finanzas crea/edita y Gerencia aprueba; cambiar quién aprueba corresponde a una futura SPEC comercial, **no a inventario**.
5. La administración de cuentas es exclusiva de TI; agregar Bodeguero no le confiere administración de usuarios ni acceso automático a Obras, Finanzas, Dashboard o presupuestos.

## 2. Objetivo y orden de entregas

Establecer una **única fuente de verdad PostgreSQL** para catálogo y existencias físicas por material, con un rol `BODEGUERO` de autoridad operativa limitada a inventario, movimientos auditados y soporte para integraciones posteriores.

Orden propuesto por dependencias, con PR independientes:

- **019A — Base de Bodega:** sexto rol persistido, catálogo de artículos, existencias, ingresos físicos y libro inmutable de movimientos; permisos y API de lectura/escritura acotados. **Es el único incremento definido aquí con contrato candidato a implementación.**
- **019B — Salidas, devoluciones y vinculación de Obra:** entrega efectiva desde Bodega, movimientos inversos, reconciliación con `GastoObra` y protección contra costos duplicados. **No implementar sin definir antes valorización, autorización y trazabilidad de entrega.**
- **019C — Solicitud y merma:** el Técnico solicita material adicional por Obra y cantidad; Supervisor aprueba/rechaza; Bodega entrega; pérdidas/mermas justificadas y auditadas. El flujo de aprobación y los tipos de merma requieren su propia ratificación.
- **Otras SPEC posteriores:** Supervisor/Finanzas en presupuestos, con decisión final de Finanzas; chat interno con archivos y retención temporal. No mezclar sus permisos ni tablas con 019A.

## 3. Alcance exacto de 019A

**Incluye:** `BODEGUERO` persistido; catálogo con identificación inequívoca; saldo físico por artículo; entrada positiva de artículos al inventario; historial append-only; filtros/paginación; API DRF; comprobación de roles; validación PostgreSQL; pruebas funcionales, negativas, concurrentes y de migraciones; OpenAPI; guía de consumo; y, al cerrar la implementación, colección Postman esencial con environment legible para la ejecución delegada.

**Excluye:** salidas por obra, descontar stock al crear `GastoObra`, compras y documentos tributarios, valoración contable, costeo FIFO/promedio, múltiples bodegas, reservas, kits, lotes, series, códigos de barras, trazabilidad por proveedor, mermas, ajustes negativos, transferencias y pantalla React. No modificar `GastoObra` ni datos históricos para hacer aparecer stock ficticio.

## 4. Modelo de datos propuesto, sin deuda de integridad

### 4.1 Artículo

Nueva app `apps.inventario`. Entidad `ArticuloInventario` con PK de servidor, `codigo` (único tras normalización y sin distinción de mayúsculas), `nombre`, `descripcion` opcional, `unidad` no vacía, `activo`, auditoría de alta/actualización y actor. No aceptar cantidades ni precio en esta tabla: el stock no es atributo editable de catálogo.

- Código y unidad se normalizan/validan una sola vez. Prohibir cambio de unidad/código cuando existan movimientos, salvo migración explícita y auditada; nunca convertir cantidades silenciosamente.
- Desactivar artículo impide nuevas entradas, pero conserva saldos, movimientos, vínculos y consultas históricas. No borrar físicamente artículos con actividad.
- No cargar artículos reales mediante migraciones de ejemplo ni inventar cantidades iniciales a partir de gastos de Obras.

### 4.2 Existencias y libro de movimientos

`ExistenciaInventario`: una fila por artículo (única), saldo `Decimal(12,3)` no negativo; operación exclusiva por servicio transaccional. Saldo 0 válido; ninguna cantidad `float`, NaN, infinita, negativa, ni escala superior a 3 decimales.

`MovimientoInventario`: PK, artículo, tipo `INGRESO` para 019A, cantidad positiva `Decimal(12,3)`, saldo anterior y posterior, motivo/referencia opcionales según acción, actor y fecha de servidor. Historial **inmutable** en operaciones normales; prohibir PATCH/DELETE público, no reutilizar movimientos como si fueran gastos financieros. Las anulaciones o correcciones futuras usarán contramovimientos con referencia; no editarán el histórico.

Se recomienda crear `ExistenciaInventario` a saldo cero atómicamente con el artículo, evitando recreaciones implícitas en lecturas. Constraints de rango, FK protegidas, unicidad y vínculo coherente `saldo_posterior = saldo_anterior + cantidad` para `INGRESO`. Cualquier mecanismo SQL de integridad que se adopte debe cubrir escrituras directas relevantes sin bloquear las migraciones; documentar su cobertura real.

### 4.3 Entrada

`registrar_ingreso` admite artículo activo, cantidad positiva string decimal, referencia y motivo cuando corresponda; **no inventa una compra, factura ni gasto**. La entrada incrementa saldo y crea movimiento en la misma transacción. En errores, ambos se revierten. Fecha y actor son del servidor.

Para repetir solicitudes ambiguas, definir una clave de idempotencia única por operación suministrada por el cliente (p. ej. UUID) y persistida con constraint; una repetición idéntica debe devolver la misma operación sin duplicar saldo y una clave usada para carga distinta debe generar conflicto. No depender solo de botones deshabilitados en React. Si se opta por otra estrategia, documentar por qué sigue evitando entradas duplicadas tras pérdida de respuesta.

## 5. Matriz de permisos candidata para 019A

| Acción | BODEGUERO | GERENCIA | SUPERVISOR_OBRAS | ADMINISTRATIVO_FINANZAS | TECNICO | ADMINISTRADOR_TI |
| --- | --- | --- | --- | --- | --- | --- |
| Leer catálogo/saldo/historial básico | Sí | Sí | Sí | Sí | No | No |
| Crear/editar/desactivar artículo | Sí | No | No | No | No | No |
| Registrar ingreso físico | Sí | No | No | No | No | No |
| Administrar usuarios/roles | No | No | No | No | No | Sí (SPEC-006B/018) |
| Operar Obras/finanzas/presupuestos por rol Bodega | No | Sin cambios | Sin cambios | Sin cambios | Sin cambios | No |

Esta tabla es un **contrato propuesto sujeto a ratificación**. De manera conservadora, las nuevas acciones de escritura quedan solo para Bodega. No habilitar autorizaciones por `is_staff`, `is_superuser`, claims JWT, correos o grupos. Comprobar siempre rol, actividad y estado de acceso persistido mediante mecanismos de autenticación existentes; revocar sesiones al cambiar a/desde BODEGUERO conforme a SPEC-006B/018. Actualizar todos los validadores de rol sin permitir acciones no relacionadas accidentalmente.

## 6. API candidata 019A — rutas claras, estables y paginadas

Bajo `/api/inventario/`, JWT/CSRF y convenciones DRF vigentes:

| Método | Recurso | Propósito |
| --- | --- | --- |
| GET | `articulos/` | Lista paginada, búsqueda por código/nombre y filtro `activo`. |
| POST | `articulos/` | Alta de artículo (Bodeguero). |
| GET | `articulos/{id}/` | Detalle y unidad del artículo. |
| PATCH | `articulos/{id}/` | Editar campos permitidos, no saldo ni código/unidad con movimientos. |
| GET | `existencias/` | Saldo paginado por artículo, sin precio ni inferencia financiera. |
| GET | `movimientos/` | Libro paginado, filtros exactos por artículo/tipo/fecha civil. |
| POST | `ingresos/` | Entrada física idempotente y auditada (Bodeguero). |

- Usar IDs enteros positivos, fechas de servidor, paginación 25 por defecto, filtros explícitos, respuestas tipadas y trailing slash coherente.
- Entradas numéricas únicamente strings decimales con punto, precisión exacta. Las salidas devuelven strings decimales; no floats.
- `400` para campos inválidos/desconocidos, `401` identidad inválida, `403` rol no autorizado, `404` recurso no visible/inexistente, `405` operación no publicada y `409` incompatibilidad o idempotencia conflictiva; no revelar información sensible de otros módulos.
- No publicar acciones 019B/019C en OpenAPI ni Postman de 019A como si estuvieran implementadas.
- Las rutas son **candidatas**; su forma definitiva debe validarse contra naming/serializadores reales antes de congelar contrato.

## 7. Transacciones, concurrencia y compatibilidad

1. Crear artículo y existencia inicial en una transacción. Para ingreso, bloquear `ArticuloInventario → ExistenciaInventario`, verificar vigencia, unicidad de idempotencia, saldo y rango; persistir libro y nuevo saldo juntos. Nunca leer saldo fuera de transacción para después escribir a ciegas.
2. Simular ingresos concurrentes al mismo artículo con conexiones PostgreSQL diferentes: suma exacta y orden coherente; también dos solicitudes con misma clave de idempotencia y cargas distintas. Sin dobles movimientos ni deadlocks.
3. Evitar bloquear `GastoObra`, `Obra` o `Presupuesto` en 019A. En 019B se deberá diseñar un **único orden global de locks** que reconcilie Inventario con el existente `Presupuesto → Obra → Gasto` antes de implementar despacho/costeo.
4. La migración de `Usuario.rol` agrega `BODEGUERO` al enum Python y a la constraint PostgreSQL vigente mediante una **nueva** migración posterior a Usuarios 0009; nunca editar 0005–0009. El nuevo inventario usa migraciones propias. Probar instalación limpia y upgrade desde esquema existente.
5. Todos los otros dominios preservan sus matrices vigentes; en particular Bodeguero no accede a cuentas TI, costos de Obras, documentos privados, reportes gerenciales ni tesorería por el solo hecho de existir el rol.
6. Fase A/C1/C2/C3 de SPEC-018 permanece sin cambios ni activación productiva por esta SPEC.

## 8. Criterios de aceptación de implementación

- Validación de esquema: `makemigrations --check --dry-run`, `manage.py check`, migraciones limpias y upgrade, constraints reales PostgreSQL.
- API: cobertura de seis roles, denegaciones, autorización persistida, campos cerrados, paginación/filtros, unidades/código únicos, desactivación, errores precisos.
- Regresión: crear artículo y saldo cero, registrar ingreso y observar nuevo saldo/único movimiento; rechazo de cantidad inválida y atomicidad; idempotencia; carreras de ingreso simultáneas; preservación de gastos existentes; acceso TI denegado a Bodega y viceversa.
- Ejecutar suites dirigidas Usuarios/Inventario y regresión completa backend, CI GitHub del SHA publicado; no sustituir CI por un informe local.
- Entregar OpenAPI y una colección Postman **de verificaciones esenciales** con su environment editable, nombres legibles y credenciales de prueba en environment; sin acoplarse a IDs fijos o estado de otra SPEC, ni requerir resultados de Runner como condición para continuar el trabajo.
- Describir alcance implementado y pruebas ejecutadas sin afirmar validaciones externas no realizadas. No modificar `frontend/`, `main`, otras SPEC ni desplegar. Todo merge de código exige autorización separada.

## 9. Decisiones funcionales pendientes antes de abordar 019B/019C

1. **Valorización:** costo del material al ingresar y al consumirlo, FIFO o promedio ponderado, precisión histórica y quién puede ver/rectificar precios. Sin ratificar, ningún despacho crea automáticamente `GastoObra`.
2. **Relación con Obras:** momento exacto en que una entrega aprobada rebaja stock y origina gasto, identificación de entrega y devolución, control de consumo contra cantidad solicitada, sin duplicar costos registrados manualmente.
3. **Abastecimiento:** proveedor/guía/factura, stock inicial real y correcciones de conteo; no inventar respaldo tributario.
4. **Mermas:** tipos, aprobación, motivo, evidencia, impacto físico/financiero y reportes.
5. **Vistas:** acceso a costos de inventario por Gerencia/Finanzas y exposición de disponibilidad a Técnico, según flujo de solicitudes que se ratifique.
6. **Bodegas múltiples y unidades:** la propuesta 019A es una sola ubicación y sin conversiones; expansión posterior necesita migración y política de consistencia.

## 10. Hoja de ruta del backend posterior

1. **SPEC-019A**: Bodeguero + catálogo + existencias + ingresos, sin integración con gastos.
2. **SPEC comercial posterior**: Supervisor y Finanzas podrán crear presupuestos, con Finanzas como autoridad final, reemplazando expresamente la aprobación histórica de Gerencia mediante estados/migración trazables.
3. **SPEC-019B/019C**: solicitud de materiales de Técnico, autorización de Supervisor, despacho de Bodega, costos de Obra y mermas, con controles transaccionales y diseño contable ratificados.
4. **SPEC de comunicación interna**: chat entre cuentas con adjuntos e higiene de retención/seguridad; no se añade chat accidentalmente a Inventario.

**Regla de ejecución:** iniciar implementación solo en rama propia después de revisar las decisiones del bloque correspondiente. No extrapolar las decisiones de 019A a presupuestos, costos o producción.
