# SPEC-019B — Bodega básica vinculada a Obras (FYAG Beta)

> **Estado: contrato documental revisado y ratificado para implementación.** 21-11-2026.
> **Decisión confirmada:** utilizar **costo promedio ponderado móvil** para valorizar materiales consumidos por Obras.
> **Prioridad del producto:** FYAG Beta se centra en la gestión económica: identificar ingresos de dinero, egresos de dinero y costos de Obras. Bodega es un módulo complementario, **no** un ERP de compras, logística ni contabilidad.
> **Antecedentes:** SPEC-019A (PR #52), SPEC-020A/B (PR #54/#55) y SPEC-021 (PR #58), integrada en `main` mediante `164f21527b88a9b32f5b283623d80a512ba639ef`. Frontend a cargo del equipo React. Este PR es solo documental: no contiene migraciones, backend ejecutable ni despliegue; su implementación se realizará en PR independiente.

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
| Pago efectivamente realizado a proveedor/tercero | Administrativo/Finanzas, mediante SPEC-021 | **Salida real de dinero registrada** en `finanzas.Egreso`; no proviene automáticamente de Bodega |

`apps.finanzas.PagoDocumento` registra **pagos recibidos** de clientes; `apps.finanzas.Egreso` (SPEC-021) registra **desembolsos realizados** y `apps.obras.GastoObra` registra **costos económicos**. Una salida de Bodega nunca debe crear un `Egreso` ni presentarse como pago bancario.

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
- El costo de consumo por Obra no es un segundo desembolso: el pago real por la compra se registra exclusivamente en **Egresos (SPEC-021)**, con identidad y respaldo propios, sin alta automática desde Bodega.
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

**SPEC-021 ya está integrada en `main`**: registra egresos externos realizados y el flujo monetario administrativo. SPEC-019B solo mueve unidades físicas y costos internos de Obras; no crea ni modifica `Egreso`, pagos de clientes, cobros, documentos o flujo monetario. Tras 019B se priorizará completar integración y QA de FYAG Beta antes de ampliar a 019C, mermas, proveedores o chat.

## 8. Flujo de entrega y autorización

1. Integración del contrato documental ratificado, sin código ni migraciones.
2. Implementación backend acotada en rama propia por OpenCode, con migraciones, pruebas, contratos y Postman; nunca en `main` directamente.
3. Auditoría del commit, PR y CI; merge de implementación permitido al revisor técnico con la autorización general concedida solo cuando no queden pendientes materiales.
4. El equipo React recibe únicamente los cambios de interfaz que efectivamente existan en el backend.

**La integración de este PR documental no implementa ni despliega SPEC-019B.** La implementación se prepara en una rama exclusiva desde `main` actualizado, con validación local y CI antes de merge.

## 9. Contrato de integración vinculante (019B)

Las reglas siguientes precisan los apartados anteriores y **prevalecen** ante ambigüedades. Se eligió el mínimo funcional compatible con los modelos de \`main\`, sin implementar un ERP de compras.

### 9.1 Semántica de entrega, costo y devolución

1. Una autorización de Supervisor identifica \`obra + articulo + cantidad_autorizada + actor + fecha\`, solo cuando la Obra está \`EN_PROCESO\` o \`SUSPENDIDA\`. No consume ni reserva stock. Admitir varios despachos parciales dentro del total autorizado, pero no despachar sobre el remanente; conservar historial. La autorización no equivale a gasto ni egreso.
2. **Cada despacho físico efectivo** tendrá su propia identidad idempotente, una fila inmutable de movimiento \`SALIDA\`, vinculación inequívoca con la autorización y **exactamente un** \`GastoObra\` tipo \`MATERIAL\` asociado a esa entrega. Un gasto de otra fuente jamás se transforma silenciosamente en gasto de Bodega. Despachos sucesivos de la misma autorización generan gastos separados porque el promedio puede variar. Repetir idéntico despacho retorna resultado original, incluso si hubo devoluciones posteriores; UUID reutilizado con otra carga da 409.
3. La entrega ejecutada por Bodega registra actor Bodeguero real en movimiento y trazabilidad de integración; la autorización deja al Supervisor real identificado. Si \`GastoObra.registrado_por\` o \`CostoObraEvento.registrado_por\` emplean al actor físico, debe quedar claro su origen \`BODEGA_019B\`, sin falsificar que el Supervisor realizó una entrega. No otorgar al Bodeguero permiso general para crear/corregir gastos ajenos a la entrega autorizada.
4. El Supervisor autoriza cada devolución con referencia a la **entrega original** y cantidad; Bodega confirma físicamente. Cada recepción confirmada genera movimiento \`DEVOLUCION\`, incrementa \`GastoObra.cantidad_devuelta\` del mismo despacho y registra \`CostoObraEvento.DEVOLUCION\` conforme al contrato 004B, todo atómico y con actor real. Una devolución pendiente no aumenta existencia ni reduce costos. La suma de devoluciones recibidas y cantidades pendientes autorizadas no debe exceder la cantidad efectivamente entregada. Si se admite devolución parcial de una autorización, controlar remanente con bloqueo e idempotencia.
5. Estado de Obra exigido en **autorización, despacho, autorización de retorno y recepción**: \`EN_PROCESO\` o \`SUSPENDIDA\`. No modificar \`FINALIZADA\` ni \`CierreCostosObra\`; carreras con finalización se serializan bajo el lock de Presupuesto y Obra. No reabrir cierres ni inventar correcciones retrospectivas.
6. Los gastos vinculados a Bodega **no admiten edición, anulación ni devolución manual por las rutas/servicios históricos** de 004B; devoluciones solo por 019B. Añadir guard explícito en servicios propietarios y constraint/trigger de integridad donde haga falta para que el vínculo no pueda reasignarse ni duplicarse. Los gastos manuales anteriores mantienen su comportamiento. No hay forma fiable de detectar por texto que un gasto manual histórico coincida con una entrega: evitar deduplicación heurística e informar al Supervisor que no vuelva a registrar manualmente el mismo consumo.

### 9.2 Valorización y precisión compatibles con 004B

1. El **método ratificado** es promedio ponderado móvil por artículo, neto CLP. Por compatibilidad con \`GastoObra.costo_unitario_neto\` (\`NUMERIC(15,2)\`) el **costo unitario aplicado y el promedio almacenado se cuantizan a dos decimales mediante \`ROUND_HALF_UP\`** tras cada evento de valorización, sin floats. Cantidades físicas con hasta tres decimales; los subtotales existentes de 004B siguen calculándose \`ROUND_HALF_UP\` a \`0.01\` sobre \`cantidad * costo_unitario_neto\`. No ampliar el esquema de costos de 004B ni crear otra fórmula paralela.
2. Para una recepción valorada: \`promedio_nuevo = redondear_centavo((saldo_valorado_anterior * promedio_anterior + cantidad_ingresada * costo_unitario_neto_respaldado) / (saldo_valorado_anterior + cantidad_ingresada))\`. Con saldo valorado anterior cero, iniciar al costo unitario neto respaldado. Al consumir: congelar el promedio de ese instante como costo unitario del gasto. Una salida ordinaria no cambia el promedio restante. Cuando se agota stock valorado, dejar sin promedio vigente hasta el siguiente ingreso valorado. Declarar explícitamente en documentación la política de redondeo centesimal y sus diferencias posibles respecto de un libro contable de precisión ilimitada.
3. Al devolver: imputar la cantidad al **costo unitario histórico de su despacho original**, y recalcular el promedio del stock físico remanente con \`(saldo_valorado_actual * promedio_actual + cantidad_devuelta * costo_unitario_original) / nuevo_saldo\`, con el mismo redondeo. Si saldo anterior es cero, usar el costo de la devolución como promedio inicial. Conservar cantidades, costos previos/posteriores y fuente de precio en historial auditable. No revalorizar el gasto histórico según precios posteriores.
4. La valoración debe mantenerse independiente de la recepción física; el Bodeguero puede ingresar unidades conforme a 019A sin fijar precios. **Administrativo/Finanzas** es el único que valida valor neto unitario respaldado; Bodega solo ve cantidad/estado pendiente o disponible, nunca montos ni detalles de costo. No inferir un pago: \`finanzas.Egreso\` sigue siendo un registro separado y nunca se escribe automáticamente.
5. Al migrar desde 019A, **capturar solo una referencia física verificable** (saldo y corte/último movimiento) de existencias anteriores, sin generar precio, actor de valoración ni pago falsos. Si hay stock histórico sin precio, **AF registra una regularización inicial explícita** del saldo anterior, con costo unitario neto, referencia, motivo, actor y fecha reales. No duplicar movimientos físicos ni crear un \`INGRESO\` adicional; el histórico de 019A permanece intacto.
6. Todo ingreso físico posterior al corte queda pendiente de valoración individual de AF. Valorizar recepciones en el orden del libro para un mismo artículo, sobre snapshot bloqueado. Mientras exista saldo no valorizado o regularización inicial pendiente, **bloquear despachos de ese artículo completos** (fail closed), no seleccionar arbitrariamente qué unidad tiene precio. Las devoluciones de entregas ya valorizadas siguen permitidas en estados operativos válidos, aunque haya nuevos ingresos pendientes, pero no pueden utilizarse para eludir ese bloqueo de despachos. Un artículo desactivado conserva historia y admite solo las devoluciones pendientes válidas de entregas previas.
7. Validación de rango: el costo neto unitario debe ser representable en \`GastoObra.costo_unitario_neto\` sin truncarlo, y los subtotales deben seguir dentro de límites actuales. Si el redondeo del promedio o el costo real no es representable, rechazar con 409 antes de mover stock. Nunca ocultar un monto por redondeo implícito a cero ni aceptar precio inventado.

### 9.3 Modelo, API mínima y RBAC

- Modelos candidatos: \`AutorizacionEntregaMaterial\`, \`EntregaMaterial\` (FK única a \`GastoObra\`), \`AutorizacionDevolucionMaterial\`, \`DevolucionMaterial\`, \`ValoracionIngreso\` y registro de costo/promedio por artículo. Se permite consolidar entidades solo si se conservan claves, invariantes, historial e idempotencia. Los movimientos siguen append-only; las autorizaciones y su remanente pueden derivarse, sin reservar unidades.
- Rutas bajo \`/api/inventario/\`:
  - \`POST/GET autorizaciones-entrega/\` (S escribe, S/G/B consultan proyección sin costos).
  - \`POST/GET entregas/\` (B ejecuta; S/G/B consultan proyección adecuada).
  - \`POST/GET autorizaciones-devolucion/\` (S escribe; S/G/B consultan proyección sin costos).
  - \`POST/GET devoluciones/\` (B ejecuta; S/G/B consultan proyección adecuada).
  - \`POST/GET valorizaciones/\` (AF escribe; AF/G solo lectura de precios; B puede conocer estado por una vista sin montos).
  - \`POST/GET regularizaciones-iniciales/\` (AF escribe; AF/G leen valores).
  - Mantener sin rupturas \`articulos/\`, \`existencias/\`, \`movimientos/\`, \`ingresos/\` de 019A. El tipo \`SALIDA\` o \`DEVOLUCION\` aparece en movimientos 019B, con respuesta en Bodega **sin información económica**.
- Acciones de escritura con **clave de idempotencia UUID obligatoria** (header o body según convención 019A; mantener contrato inequívoco en OpenAPI/Postman), huella de carga normalizada y replay sin efectos. Los permisos dependen de la acción, no del HTTP global 019A. Distinguir roles B, S, AF y G; no publicar costos a B ni a T/TI. Toda operación valida rol activo y sesión/bloqueo persistidos al ejecutar, incluso tras esperar locks. Paginación 25, filtros estrictos, cuerpo con lista cerrada de campos, cantidades como strings exactos; errores 400/401/403/404/405/409. No exponer contratos hipotéticos como implementados.
- El módulo \`apps.finanzas\` **no** se convierte en motor de costos de materiales: el valor neto respaldado de inventario es un control interno de precios, separado de \`PagoDocumento\` y \`Egreso\`. La lectura AF/G de valoración se limita al inventario, sin compartir datos sensibles de Obras.
- Compatibilidad: añadir \`SALIDA\` y \`DEVOLUCION\` con migraciones nuevas, actualizar constraints de tipos y snapshot según signo, y **reemplazar** la lógica de \`fyag_inventario_conciliar\` que hoy solo hace \`SUM(cantidad)\`. Mantener triggers de no-mutar y saldo confirmado; no alterar migraciones 0001/0002. Entradas/devoluciones suman, salidas restan. Cada movimiento efectivo valida su actor y su enlace; contra escritura SQL directa, proteger las invariantes relevantes sin confiar solo en DRF.
- Orden global de locks: en actos vinculados a Obra tomar **Presupuesto → Obra → autorización/entrega → artículo → existencia/valorización → GastoObra/control de costos**, consistente con 004B. Las entradas 019A solo toman idempotencia → artículo → existencia; no deben adquirir después locks de Obra. Verificar y documentar posibles esperas por FK, triggers y locks asesores, evitando una ruta inversa. Registrar movimiento, costo y sus eventos en **la misma transacción PostgreSQL**; fallo en cualquier paso revierte todo.

### 9.4 Criterios de aceptación y entrega

- Pruebas deterministas de promedio, ingresos con precios distintos, despacho parcial, nueva recepción, devoluciones parciales al costo original y redondeo; conservación de historiales y conciliación física.
- Migración desde esquema 019A con existencias reales sin precio: saldo no alterado, regularización explícita antes de despacho; upgrade con 021 ya integrada y sin modificar \`Egreso\`, \`PagoDocumento\` o flujo monetario.
- Protección de costo vinculado frente a PATCH, anulación/devolución manual, escritura SQL no autorizada, actor impropio y cruces de Obras; eventos de 004B y invalidación de \`ControlCostosObra\` exactamente una vez por cambio económico.
- Carreras PostgreSQL con conexiones reales: misma UUID, dos despachos sobre autorización, despacho/ingreso, retorno/retorno, valoración/ingreso, despacho/finalización y revocación de sesión durante espera. No deadlocks, saldos negativos, gastos duplicados ni alteraciones de cierres.
- Seguridad de seis roles y proyecciones de lectura diferenciadas (especialmente B sin costo); rechazo de precios no valorizados, payloads desconocidos y abuso de \`is_superuser\`.
- \`manage.py check\`, \`makemigrations --check --dry-run\`, migración limpia y upgrade real, suite dirigida y regresión completa, OpenAPI y Postman esenciales, CI del PR. Entrega de OpenCode en rama \`feature/backend-019b-entregas-devoluciones\`, commit y push, sin crear PR ni merge, sin frontend ni archivos temporales/basura. La revisión técnica de GitHub crea el PR y decide merge después de CI.

## Vista operativa de Inventario para Finanzas — 26-11-2026

- GET /api/inventario/finanzas/ exclusivo AF. Secciones inventario, movimientos, valoraciones, regularizaciones, ingresos e historicos; paginación fija de 25, búsqueda por código/nombre y filtros compatibles por sección. No amplía permisos de otras vistas.
- Inventario reúne catálogo, saldo físico, estado de valoración y valor neto de cantidades valorizadas; resumen global independiente de filtros y página. Los importes se calculan con redondeo HALF_UP del dominio. Se indica valoración parcial; no equivale a efectivo pagado.
- Ingresos elegibles: únicamente el primero no valorizado posterior al corte histórico por material, excluyendo bloqueos por saldo histórico sin regularizar. Saldos históricos elegibles: positivos y sin regularización ni valorización anterior. La escritura vuelve a comprobar las reglas bajo los bloqueos originales.
- Cuatro pestañas a ancho completo, filtros y estados vacíos, ficha de movimientos/costos y formularios guiados por selección real. Se mantienen los POST originales y UUID, motivo y referencia; ante incertidumbre solo se permite repetir el payload congelado con la misma UUID. Sin modificación de cantidades físicas ni egresos por valorización.
- Contrato complementario: backend/docs/openapi/inventario-finanzas-v1.json. Pruebas dirigidas añadidas; ejecución local y verificación visual pendientes. Sin merge.
