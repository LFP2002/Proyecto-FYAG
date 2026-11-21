# SPEC-019B — Entregas y devoluciones de materiales de Bodega a Obras (FYAG)

> **Estado: propuesta documental en revisión; no autorizada para implementación, migración ni despliegue.** 21-11-2026.
> **Base verificada:** `main` en `3d1351773dcb5dcbb90838fda194785ac9d11498`. SPEC-019A de inventario está integrada mediante PR #52; SPEC-020A/B están integradas mediante PR #54/#55. El frontend se delega a otro equipo.
> **Decisión ratificada por el responsable (21-11-2026):** las salidas de Bodega se valorizarán mediante **costo promedio ponderado móvil** basado en costos netos reales y trazables de las existencias. **Aún pendientes de ratificación:** quién registra/valida el costo y sus respaldos, y el tratamiento de las existencias ingresadas antes de 019B sin costo asociado. No implementar despacho económico hasta resolverlos.

## 1. Problema y restricciones comprobadas

1. `apps.inventario` dispone de `ArticuloInventario`, `ExistenciaInventario` y `MovimientoInventario`, ingresos positivos idempotentes y libro inmutable respaldado por funciones/triggers PostgreSQL en la migración `0002_integridad_libro`. Solo existe `MovimientoInventario.Tipo.INGRESO`; el trigger de conciliación suma cantidades positivas y el de alta valida un BODEGUERO.
2. El inventario **no registra precios de adquisición ni lotes**. El campo `cantidad` es `Decimal(12,3)` y el saldo debe ser no negativo. Una entrada física NO equivale a un gasto financiero.
3. `GastoObra` registra cantidades, devoluciones, `costo_unitario_neto` `Decimal(15,2)`, tipo `MATERIAL` y eventos económicos. Las operaciones actuales las realiza Supervisor y exigen obra `EN_PROCESO` o `SUSPENDIDA`; el total de costo utiliza `cantidad - cantidad_devuelta`, redondeo `ROUND_HALF_UP`. El cierre de costos depende de versiones y validación de Supervisor.
4. `apps.obras.services_gastos` bloquea bajo el orden `Presupuesto → Obra → Gasto`; Inventario 019A utiliza `idempotencia → Artículo → Existencia`. La integración debe tener un **orden combinado explícito**, sin abrir ciclos entre módulos.
5. No se puede deducir stock de gastos de Obras anteriores ni atribuir costo de adquisición a ingresos que nunca tuvieron precio registrado. Las migraciones existentes, sus eventos y fechas deben conservarse.
6. SPEC-019C (solicitud del Técnico, aprobación, merma) sigue pendiente; **019B no debe simular que el Técnico dispone ya de esa autorización**.

## 2. Objetivo y límites

Vincular cada entrega y devolución física de Bodega a una Obra identificada, con autorización trazable de Supervisor, libro de movimientos exacto, idempotencia, stock no negativo e integración económica mediante **costo promedio ponderado móvil ratificado**, una vez definidas las responsabilidades y la valorización de existencias anteriores.

Incluye diseño de órdenes autorizadas, ejecuciones de entrega/devolución, inmutabilidad, permisos de roles, relaciones con la Obra, control de cantidades y compatibilidad de costos. Las acciones físicas no pueden convertir a Bodeguero en editor general de Obras.

Fuera del alcance: interfaz React, compras/proveedores/DTE, múltiples bodegas, reservas generales, transferencias, mermas, Técnico solicitante (019C), costeos simulados, notificaciones nuevas y cambios en roles/permisos de SPEC-020.

## 3. Flujo propuesto

### 3.1 Autorización por Supervisor

1. Supervisor selecciona una Obra en `EN_PROCESO` o `SUSPENDIDA`, artículo activo y cantidad positiva con la **misma unidad** del catálogo. Registra una autorización identificable de entrega para esa Obra y artículo. Incluye solicitante real, fecha, estado y motivo/observación, sin suplantar al autor.
2. La autorización **no descuenta stock** y no genera `GastoObra` por sí sola. El saldo se reevalúa al entregar, no se reserva informalmente.
3. Las autorizaciones pueden quedar pendientes, parcialmente entregadas, cumplidas o anuladas sin borrar su historial. Deben poder cancelarse antes de despachar; una cantidad ya entregada no puede borrarse ni reducirse por debajo de lo ejecutado. Una anulación posterior no revierte físicamente ninguna entrega.
4. La autorización es la base reutilizable para 019C: el Técnico podrá solicitar; Supervisor revisará y, si aprueba, emitirá/derivará una autorización. 019B no da al Técnico permiso de emisión.

### 3.2 Entrega física por Bodeguero

1. Bodeguero consulta las autorizaciones visibles y confirma cantidad entregada real (total o parcial), referencia y `clave_idempotencia` UUID por ejecución.
2. Al confirmar, una única transacción verifica autorización vigente, Obra habilitada, cantidad pendiente, artículo, saldo disponible y sesión Bodeguero; genera una **salida** en el libro y descuenta saldo exactamente una vez.
3. Se conservan la identidad del Supervisor que autorizó, la del Bodeguero que entregó y fecha servidor. No afirmar entrega efectiva por el solo hecho de autorizar; no registrar una salida si se rechaza por stock insuficiente.
4. Repetir la misma clave y payload devuelve la misma operación sin descontar otra vez; reutilizar la clave con datos incompatibles da 409. Se deben manejar concurrencia y fallos tras commit sin reintentar escrituras ciegamente.

### 3.3 Devolución física desde Obra

1. La Obra identifica qué entrega concreta devuelve y cuánto. Supervisor registra/autoriza la devolución, con motivo. Bodeguero confirma su **recepción física**; solo en ese momento se incrementa el saldo mediante un movimiento inverso `DEVOLUCION`.
2. Controlar `devuelto_acumulado ≤ entregado_acumulado` por entrega y artículo, sin permitir devoluciones ajenas a la Obra ni a una entrega previa. Admitir retornos parciales y repetición idempotente; no devolver contra un ingreso genérico.
3. Un artículo inactivo no puede despacharse de nuevo, pero puede recibir una devolución legítima del material previamente entregado, preservando el histórico.
4. No usar `GastoObra.devolver_gasto` como sustituto de una recepción física: una devolución económica manual no aumenta stock. No permitir dos créditos físicos por el mismo retorno.

## 4. Esquema mínimo propuesto y protección

- Modelo de autorización `AutorizacionEntregaObra` (nombre final sujeto a consistencia): Obra, Artículo, cantidad autorizada, autor Supervisor, estados/fechas, cantidad entregada calculada o mantenida transaccionalmente, motivo y eventos de cambio.
- Entidad inmutable `EntregaMaterialObra`: referencia a la autorización y a un `MovimientoInventario` de tipo `SALIDA`; cantidad, actor Bodeguero, fecha real; una ejecución no puede tener más de un movimiento físico asociado.
- Entidad inmutable `DevolucionMaterialObra`: entrega origen, autorización/validación por Supervisor, confirmación Bodeguero, movimiento `DEVOLUCION`, cantidad y motivo. Respetar unicidades y límites acumulados.
- Las tablas anteriores son una propuesta lógica: evitar columnas/relaciones redundantes cuando puedan imponerse integridad y trazabilidad de forma más simple. No copiar datos sensibles ni duplicar el saldo fuera del libro.
- Extender tipos de `MovimientoInventario` con `SALIDA` y `DEVOLUCION`. `cantidad` sigue siendo magnitud positiva; actualizar en **migración nueva** la expresión de saldo por tipo: ingreso/devolución suma y salida resta. Proteger tanto snapshots como no negatividad, actor y vínculo con operación/Obra.
- Redefinir con nuevas migraciones los triggers de validación y de conciliación de 019A para suma firmada según tipo; **nunca editar** `0001` ni `0002`. Revalidar libro histórico (solo ingresos) antes y después de la migración. El conjunto debe impedir una salida insertada arbitrariamente sin autorización de entrega válida.
- Cada autorización, movimiento y vínculo económico conserva eventos inmutables, causa, actor persistido y relojes del servidor; prohibir `UPDATE/DELETE` públicos de los registros ejecutados.

## 5. Efecto económico: costo promedio ponderado móvil RATIFICADO

**Decisión funcional aprobada el 21-11-2026:** elegir la opción A — **promedio ponderado móvil**, no FIFO, costo unitario arbitrario por despacho ni salida física sin efecto económico como flujo definitivo. Esta aprobación es del **método de cálculo** y no concede nuevas autorizaciones de registro de precios.

### 5.1 Regla del promedio móvil

- Cada ingreso valorizado registra **cantidad real y costo unitario neto** con su fuente y autor de validación, que deberán definirse. **Un ingreso físico existente de 019A no adquiere automáticamente un costo** ni se transforma en compra, factura o gasto.
- Al confirmar un ingreso valorizado, actualizar el costo promedio del artículo sobre cantidades reales, sin mezclar unidades ni precios entre artículos:

  `nuevo_promedio = (saldo_anterior × promedio_anterior + cantidad_ingresada × costo_unitario_ingreso) / (saldo_anterior + cantidad_ingresada)`.

  Si el saldo anterior es cero, el nuevo promedio corresponde al costo unitario del ingreso. Si hay stock positivo con costo desconocido, **no es válido suponer promedio cero**.
- Calcular en `Decimal` sin `float`, conservar suficiente precisión interna y establecer en la implementación una regla documentada de cuantización para el costo total y `GastoObra.costo_unitario_neto` (hoy 2 decimales). No redondear insumos prematuramente ni permitir que un error de centavos fabrique diferencias entre libro físico y libro económico; probar explícitamente fracciones y retornos.
- **Ejemplo ilustrativo:** 10 unidades a $1.000 CLP netos cada una y un ingreso posterior de 10 unidades a $1.200 CLP netos resultan en saldo 20 y promedio $1.100 CLP netos por unidad.
- **Salida:** reduce existencias y utiliza el promedio vigente **capturado en el mismo instante transaccional**; una salida ordinaria no recalcula el promedio de las unidades restantes. Persistir el costo aplicado y la referencia de su valoración como snapshot inmutable asociado a esa entrega y a su imputación económica. Nunca recalcular el costo histórico de la Obra con el promedio posterior.
- **Devolución:** reingresa físicamente al confirmar recepción y aplica como base económica el **costo original de esa entrega**, no el promedio vigente al día de devolución. El promedio futuro del stock se ajustará según el valor de retorno efectivamente reingresado. Mantener explícita la precisión y las reglas de reconciliación monetaria de cada entrega y devolución.
- **Prevención de duplicados:** una entrega valorizada originará una sola imputación en el libro económico de Obras y una sola salida física. No sumar posteriormente el importe físico al `GastoObra` ya registrado; conservar idempotencia y auditoría de ambos dominios.

### 5.2 Condiciones aún abiertas y bloqueantes

1. **Quién registra y valida costos netos de ingresos**: Administrativo/Finanzas es el candidato, con segregación de funciones respecto del Bodeguero, pero este permiso **no está ratificado**. Definir respaldo mínimo, tratamiento de correcciones y alcance de lectura por rol.
2. **Existencias 019A anteriores sin costo conocido**: solicitar valorización inicial verificable y auditada a un responsable autorizado antes de despachar como gasto; o restringir el despacho valorizado hasta que se regularicen. No asignar CLP 0, no simular compra ni modificar cantidades, fechas o movimientos físicos históricos.
3. **Persistencia de valorización**: diseñar campos o libro económico complementario con costo unitario/costo total, moneda CLP, origen, aprobador, snapshot de promedio y control contra modificación directa; actualizar triggers solamente en migraciones nuevas sin reescribir `0001/0002`.
4. **Precisión monetaria y conciliación**: definir estrategia de redondeo auditable compatible con `Decimal(15,2)` en `GastoObra`; rechazar situaciones que impidan reconciliar las cantidades y costos sin pérdida encubierta de centavos.

### 5.3 Integración económica con Obras

1. Una entrega con efecto económico debe crear **exactamente una imputación valorizada por unidad de precio/porción** de `GastoObra` o un vínculo a un costo ya reconocido, nunca dos gastos por una salida.
2. Registrar un enlace inequívoco entrega ↔ gasto/valoración y bloquear edición, devolución económica o anulación directa de un gasto ligado cuando pueda romper la correspondencia física. Proveer flujo de corrección/contramovimiento especializado y auditado, sin falsificar eventos anteriores.
3. Las devoluciones deben ajustar la cantidad imputada al costo de la misma entrega original; nunca revalorar retroactivamente el origen. La reducción del costo debe convivir con `CostoObraEvento`, `ControlCostosObra.version_actual/version_validada`, `CierreCostosObra` y reportes sin duplicaciones.
4. Una entrega/devolución con efecto económico no puede ocurrir después de finalización de Obra ni contra cierre de costos inmutable; definir tratamiento de excepciones mediante nueva política, no reabrir cierres existentes.
5. Autoría separada: Supervisor **autoriza** la entrega o decisión económica; Bodeguero **ejecuta/recibe** el movimiento físico. El sistema registra ambos realmente y no atribuye a uno una acción hecha por el otro.
6. Para cierres y reportes económicos, el costo debe provenir del libro económico oficial de Obras; no sumar directamente el valor de movimientos de inventario si ya existe un gasto enlazado.

## 6. Matriz de permisos candidata

| Operación | BODEGUERO | SUPERVISOR_OBRAS | GERENCIA | ADMINISTRATIVO_FINANZAS | TECNICO | ADMINISTRADOR_TI |
| --- | --- | --- | --- | --- | --- | --- |
| Leer saldos y libro físico | Sí | Sí | Sí | Sí | No, salvo nueva SPEC | No |
| Crear/autorizar/cancelar entrega de Obra | No | Sí | Lectura autorizada | Lectura autorizada | No (019C) | No |
| Confirmar salida física | Sí, solo con autorización vigente | No | No | No | No | No |
| Solicitar/autorizar devolución | No | Sí | Lectura | Lectura | No | No |
| Confirmar devolución física | Sí | No | No | No | No | No |
| Consultar costos de Obra | No | Sí | Sí | Solo acceso ya existente | No | No |
| Determinar precio/valoración | **Sin decidir** | **Sin decidir** | Solo lectura | **Candidato** | No | No |

- El rol del JWT, `is_superuser` o el acceso al catálogo no reemplazan la sesión y autoridad persistidas. Bodeguero nunca recibe `POST` directo de gastos de Obra.
- No exponer a Bodeguero datos de tarifas, cierre de costos, documentos privados, pagos, márgenes o sueldos. Gerencia continúa sin escrituras.

## 7. Contrato HTTP candidato (NO implementado)

Mantener `/api/inventario/` como raíz y añadir rutas organizadas por autorizaciones y acciones, siempre con slash final. Nombres candidatos:
- Supervisor: `POST /api/inventario/autorizaciones-obra/`, `GET /api/inventario/autorizaciones-obra/`, `GET /api/inventario/autorizaciones-obra/{id}/`, `POST /api/inventario/autorizaciones-obra/{id}/cancelar/`.
- Bodeguero: `POST /api/inventario/autorizaciones-obra/{id}/entregar/`.
- Supervisor y Bodeguero, según acción: `POST /api/inventario/entregas/{id}/solicitar-devolucion/`, `POST /api/inventario/devoluciones/{id}/recibir/`.
- Lectores autorizados: `GET /api/inventario/entregas/`, `GET /api/inventario/devoluciones/` y los listados existentes de existencias/movimientos con tipos nuevos.

En implementación, cerrar nombre/shape exacto, requisitos de motivo, estados, paginación 25, filtro por Obra/artículo/fecha civil Santiago, cantidades como string decimal, UUID canónico, errores 400/401/403/404/405/409 y OpenAPI. No publicar endpoints no implementados como si estuvieran disponibles.

## 8. Integridad, bloqueos y escenarios de carrera

- Proponer y probar orden global: `idempotencia por clave → Presupuesto → Obra → Autorización → Artículo(s) por PK → Existencia(s) por PK → Entrega/Devolución → Gasto/Control de costos`. El orden definitivo debe cotejarse contra el **código real** de 019A, 004B y 020, y contra handlers que toman locks en otros órdenes. Si la autorización se valida antes de ingresar a locks, releerla dentro de la transacción.
- Una operación debe ser atómica entre saldo, movimiento, ejecución, vínculo de Obra y costo si corresponde. No realizar una transacción SQL partida entre módulos para luego afirmar éxito completo. Manejar colisiones de UUID y carreras mediante constraints y locks, no por tiempos de espera del navegador.
- Pruebas de dos entregas simultáneas con stock suficiente/insuficiente, ingreso vs salida, doble devolución, dos autorizaciones por la misma Obra/artículo, cierre de Obra concurrente, cancelación vs entrega, operaciones del mismo idempotency key, fallo de escritura económica y recuperación sin movimientos huérfanos.
- El trigger de libro debe conciliar saldo final bajo transacciones concurrentes y conservar integridad de filas previas incluso si hay movimientos de tipos nuevos.

## 9. Plan de implementación después de aprobar la SPEC

1. **Documento y ratificación:** método **promedio ponderado móvil ya aprobado**. Resolver por separado quién valida costo, qué respaldos son suficientes, tratamiento de existencias anteriores sin costo y las reglas precisas de redondeo; registrar las decisiones antes de codificar.
2. **PR de implementación:** migraciones de inventario, autorizaciones y operaciones; luego integración acotada con los gastos si la política económica está aprobada. Mantener tests de 019A/004B/020A/020B.
3. **Pruebas:** migración limpia y upgrade, constraints/triggers PostgreSQL, concurrencia de conexiones reales, suite completa, OpenAPI, Postman esencial y CI. Validar rollback con movimientos nuevos y preservar histórico.
4. **Revisión y merge:** branch de código, push por OpenCode, revisión independiente en GitHub, PR, CI verde, merge **solo por aprobación expresa**.
5. **Frontend:** fuera de alcance. Sus tareas se comunicarán al equipo React al estabilizar el contrato; no modificar `frontend/` en este PR.

## 10. Decisiones para el responsable antes de codificar

1. **Valorización — RESUELTA:** se utilizará costo promedio ponderado móvil basado en ingresos valorizados; alternativas B y C descartadas para el flujo definitivo de 019B.
2. **Origen del costo:** quién puede registrarlo o validarlo (candidato: Administrativo/Finanzas) y qué evidencia mínima se considera válida; no exigir facturas reales en un sistema de QA si solo existen datos sintéticos.
3. **Stock anterior a 019B:** asignación explícita de costo histórico verificable, o bloqueo de entrega valorizada mientras no exista dato. Sin valor cero automático.
4. **Devoluciones:** la recepción física de Bodega es indispensable para reponer saldo; Supervisor confirma origen y motivo; permitir parciales y conservar fecha del movimiento.
5. **Operación de Obras:** autorizar entregas solo en `EN_PROCESO/SUSPENDIDA`; no reabrir obras finalizadas ni invalidar cierres económicos pasados.
6. **Responsabilidad:** Supervisor autoriza y Bodeguero ejecuta sin acceso a contabilidad. 019C incorporará la solicitud del Técnico después.

**El método de valorización queda ratificado; el resto del contrato continúa como propuesta de diseño, no es autorización para crear endpoints, fijar precios, conceder permisos, ejecutar migraciones o registrar gastos.**
