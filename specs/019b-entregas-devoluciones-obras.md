# SPEC-019B — Bodega básica vinculada a Obras (FYAG Beta)

> **Estado: propuesta documental simplificada para revisión.** 21-11-2026.
> **Decisión confirmada:** utilizar **costo promedio ponderado móvil** para valorizar materiales consumidos por Obras.
> **Prioridad del producto:** FYAG Beta se centra en la gestión económica: identificar ingresos de dinero, egresos de dinero y costos de Obras. Bodega es un módulo complementario, **no** un ERP de compras, logística ni contabilidad.
> **Antecedentes:** SPEC-019A (PR #52), SPEC-020A/B (PR #54/#55). El frontend corresponde al equipo React; la presente SPEC **no autoriza implementaciones, migraciones ni despliegue**.

## 1. Qué debe conseguir esta etapa

Para una empresa pequeña que ejecuta Obras, Bodega debe responder cuatro preguntas simples:
1. ¿Qué materiales tenemos y cuántas unidades hay disponibles?
2. ¿Qué materiales entraron a la empresa?
3. ¿Qué materiales salieron para una Obra y quién los entregó?
4. ¿Qué materiales sobrantes fueron devueltos?

La información financiera principal sigue perteneciendo a Finanzas y a los costos de Obras; ningún movimiento físico se clasificará automáticamente como entrada o salida de dinero.

### Separación fundamental

| Hecho | Lo registra | Efecto |
| --- | --- | --- |
| Recepción de materiales | Bodeguero | Aumenta stock físico; **no** registra ingreso/egreso de dinero |
| Costo neto respaldado de esa recepción | Administrativo/Finanzas | Valoriza stock con promedio ponderado; **no** equivale a pago efectuado |
| Autorización de materiales para Obra | Supervisor | Autoriza una cantidad; **no** mueve stock ni dinero |
| Entrega física a la Obra | Bodeguero | Disminuye stock; atribuye **costo interno** a la Obra, pero **no** registra un segundo pago |
| Devolución física desde Obra | Bodeguero con referencia de Supervisor | Aumenta stock y revierte el costo interno correspondiente; **no** registra ingreso de dinero |
| Pago efectivamente realizado a proveedor/tercero | Finanzas, en futura fase de Egresos | **Salida real de dinero**; hoy este módulo no existe en el backend |

En el código actual `apps.finanzas.PagoDocumento` registra **pagos recibidos** de clientes, mientras que `apps.obras.GastoObra` registra **costos económicos**. Ninguno de ellos es, por sí mismo, un registro general de dinero pagado a proveedores. No presentar un coste o una salida de Bodega como pago bancario.

## 2. Alcance mínimo de 019B

Mantener lo ya implementado en 019A (catálogo, existencias, ingresos y movimientos).

Añadir **solo tres acciones nuevas para el trabajo cotidiano**:

1. **Autorizar entrega:** Supervisor selecciona Obra, artículo y cantidad. La Obra debe estar `EN_PROCESO` o `SUSPENDIDA`; autorización trazable, sin reservas complejas.
2. **Entregar materiales:** Bodeguero confirma la cantidad realmente entregada. El stock se descuenta una vez, se identifica a qué Obra fue y se asocia su costo interno usando el promedio ponderado vigente. Admitir cantidades parciales sin crear un proceso logístico multinivel.
3. **Devolver materiales sobrantes:** Supervisor identifica la entrega original y solicita/confirma el retorno; Bodeguero verifica recepción física. Se reintegra stock y se ajusta costo de esa Obra al valor de la entrega original. Admitir devolución parcial y evitar doble devolución.

Bodeguero organiza y controla los artículos, ingresos, salidas, saldos e historial. **No** administra clientes, documentos de cobro, finanzas, costos de mano de obra ni presupuestos. Gerencia permanece en solo lectura.

**Fuera de alcance:** proveedores y órdenes de compra, DTE/facturación, múltiples bodegas, stock por ubicación, lotes/FIFO, reservas avanzadas, mermas y solicitudes del Técnico (019C), reportes de inventario sofisticados, chat, notificaciones y pantallas React.

## 3. Valorización simple: promedio ponderado móvil

El método ya está aprobado. Es **control interno de costos** y no flujo de caja.

- Bodeguero registra **unidades físicas recibidas**; Administrativo/Finanzas registra o valida **costo unitario neto respaldado** de esa recepción, con referencia breve. Es una propuesta de distribución profesional de funciones dentro del alcance mínimo.
- El costo promedio se actualiza al incorporar una recepción correctamente valorizada: `promedio_nuevo = (unidades_anteriores × promedio_anterior + unidades_recibidas × costo_unitario_neto) / unidades_totales`. Si el saldo anterior es cero, comienza con el costo neto del nuevo ingreso.
- Una salida registra el costo promedio vigente como **valor histórico fijo**: no cambia retrospectivamente si después llegan artículos a otro precio. Una salida ordinaria no cambia el promedio de las existencias restantes.
- Una devolución se vincula con la salida original, reintegra unidades y su **valor de salida original** al stock, para ajustar el promedio restante sin crear ingresos monetarios. No asignar otro precio artificial ni devolver más de lo despachado.
- Usar `Decimal`, CLP, precisión explícita y `ROUND_HALF_UP` compatible con los costos existentes de Obras. Registrar de forma auditable la valoración aplicada, conservando importes y cantidades de origen. Evitar fórmulas de presentación con `float`.

**Existencias históricas de 019A sin valor:** se mantienen físicamente intactas. Finanzas debe regularizar y justificar su valoración en un registro separado y auditable **antes de permitir una salida valorizada**. No asumir costo cero, no volver a insertar ingresos, no cambiar retroactivamente fechas o movimientos.

**Recepciones aún sin costo verificado:** permitir registrar su cantidad física, pero impedir entregas valorizadas que dependan de stock cuyo costo está pendiente. Mostrar estado `PENDIENTE_VALORIZACION` u otra señal equivalente solo en las proyecciones correspondientes; no fabricar un precio. Para conservar la secuencia del promedio, valorar recepciones pendientes en orden contable definido o bloquear su regularización inconsistente.

## 4. Costos de Obras sin contabilizar dos veces

- Al entregar material, el sistema registra **un movimiento físico** y **una sola imputación económica ligada a la entrega** en los costos oficiales de Obras, usando `GastoObra` y su historial existente cuando sea coherente.
- No registrar un segundo `GastoObra` por el mismo material si ya existe una imputación enlazada; mantener constraints y claves idempotentes.
- El costo de consumo por Obra no es un segundo desembolso: una futura salida de dinero por la compra se registraría por separado en **Egresos**, con identidad y respaldo propios.
- La devolución física ajusta la imputación de esa misma entrega. Una devolución económica manual en `GastoObra` **no debe** aumentar stock por sí sola. Proteger los gastos ligados de ediciones/anulaciones manuales que rompan la correspondencia.
- Cada entrega/devolución con costo participa en **una sola transacción PostgreSQL** con inventario y costos de Obras. Reutilizar el control de versiones y la invalidación de costos ya existente; no reabrir ni modificar cierres históricos de Obras finalizadas.
- No deducir movimientos físicos desde gastos históricos: los costos previos a esta integración conservan su significado original.

## 5. Quién puede hacer qué

| Acción | Bodeguero | Supervisor Obras | Finanzas | Gerencia |
| --- | --- | --- | --- | --- |
| Ver catálogo y cantidades | Sí | Sí | Sí | Sí |
| Registrar entrada física | **Sí** | No | No | No |
| Validar precio/costo neto de ingreso | No | No | **Sí** | Solo lectura |
| Autorizar material para Obra | No | **Sí** | No | Solo lectura |
| Confirmar salida de Bodega | **Sí** | No | No | No |
| Autorizar devolución | No | **Sí** | No | Solo lectura |
| Confirmar recepción devuelta | **Sí** | No | No | No |
| Registrar costos y gastos ajenos a Bodega | No | Permisos existentes | Permisos existentes | Solo lectura |

Técnico y TI no ganan permisos nuevos. El acceso se valida desde el rol y sesión persistidos, nunca desde flags de superusuario o claims JWT. **Esta matriz es el diseño propuesto de mínimo esfuerzo; se ratifica al aprobar la SPEC completa.**

## 6. Contrato técnico y pruebas

- Reutilizar `/api/inventario/` y los conceptos de 019A. Diseñar rutas nuevas mínimas y paginadas para autorizaciones de Supervisor, entregas de Bodeguero, devoluciones y valorización de ingresos por Finanzas. No añadir acciones para 019C.
- Mantener movimientos inmutables de 019A, adicionando `SALIDA` y `DEVOLUCION` con migraciones **nuevas**. Rediseñar el trigger de conciliación física para sumar ingresos/devoluciones y restar salidas; **no editar** las migraciones `0001/0002`.
- Una autorización debe pertenecer exactamente a una Obra y artículo. Toda entrega requiere autorización vigente, stock suficiente, cantidad no superior al saldo autorizado, artículo con unidad compatible y valoración aprobada. Ninguna acción puede dejar saldo negativo ni material sin trazabilidad.
- Idempotencia UUID en ejecuciones físicas y cargos vinculados; al repetirse una petición igual no hay segundo movimiento ni segundo costo. Usar bloqueo global consistente entre `Presupuesto → Obra`, artículo/existencia, gasto y la autorización, respetando las rutas de 019A y 004B para evitar deadlocks; estudiar la estrategia completa **antes** de escribir servicios.
- Los errores de validación/permiso/conflicto deben respetar 400/401/403/404/409 y no exponer información contable al Bodeguero.
- Probar PostgreSQL con altas, salidas parciales, retornos, ingresos con precio variable, promedio exacto, stock anterior sin costo, doble POST, carreras entre despacho y reposición, concurrencia con cierre de Obra, preservación de costos/historial previos, migraciones upgrade y regresión completa.
- Documentar rutas efectivamente implementadas con OpenAPI y Postman; mantener `frontend/` sin cambios. No realizar merge ni despliegue sin autorización.

## 7. Prioridad de FYAG Beta más allá de Bodega

**Pendiente financiero principal, independiente de 019B:** definir un módulo sencillo de **Egresos de dinero** para anotar pagos efectivamente realizados a proveedores y terceros (monto, fecha real, concepto, medio, referencia y, opcionalmente, relación con una Obra o compra de material). Integrarlo con consultas/resúmenes de dinero recibido versus dinero pagado, sin confundir costo de Obra con efectivo desembolsado ni duplicar pagos.

Antes de prometer que FYAG controla toda la entrada y salida de dinero, ese módulo necesita una SPEC propia, implementación y pruebas. **Se recomienda priorizarlo por encima de ampliar inventario hacia 019C, mermas, proveedores o chats.** No se debe añadir un ledger financiero improvisado dentro de 019B.

## 8. Flujo de entrega y autorización

1. Revisión/ratificación de esta SPEC simplificada y de la responsabilidad de Finanzas para valores de ingreso.
2. Implementación backend acotada en rama propia por OpenCode, con migraciones, pruebas, contratos y Postman; nunca en `main` directamente.
3. Auditoría del commit, PR y CI; merge solo con autorización explícita.
4. El equipo React recibe únicamente los cambios de interfaz que efectivamente existan en el backend.

**SPEC-019B permanece documental y no constituye autorización para implementar ni desplegar.**
