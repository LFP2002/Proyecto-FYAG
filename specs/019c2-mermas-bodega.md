# SPEC-019C-2 — Mermas físicas de Bodega (FYAG Beta)

> **Estado: REQUISITO DE MERMAS CONFIRMADO; MECÁNICA PENDIENTE DE RATIFICACIÓN — 21-11-2026.** El responsable ya indicó que **Bodega debe considerar mermas**; no es una funcionalidad opcional para descartar por priorización. La presente propuesta de alcance, roles, autorización y efectos económicos aún no está aprobada. NO autoriza implementación, merge, despliegue ni cambios de permisos hasta ratificar la sección 10.
>
> **Base verificada:** `main` `e2ee29ec17bb2219b1ee6b57c4e6da3a210c1690`; SPEC-019A, SPEC-019B, SPEC-019C-1, SPEC-021 y SPEC-020A/B integradas. Arquitectura de autoridad económica: PostgreSQL. Frontend React es responsabilidad de los compañeros y queda excluido. ChatGPT crea y modifica las SPEC; OpenCode no modifica `specs/`.
>
> **Prioridad:** FYAG Beta registra entradas/salidas reales de dinero y costos de Obras. La merma es una **baja física de stock y una pérdida interna de valor de existencias**, no un pago, egreso, gasto de Obra ni una compra.

## 1. Necesidad y límite explícito

El inventario actual tiene movimientos físicos `INGRESO`, `SALIDA` a Obra y `DEVOLUCION` desde Obra, además de valorización promedio móvil. No existe un procedimiento autorizado para retirar de existencias material dañado, extraviado o descartado **mientras permanece bajo custodia de Bodega**.

Este incremento añade únicamente **mermas físicas de Bodega**, con justificación, aprobación segregada y efecto contable interno congelado al confirmar la baja. No contempla:
- Pérdida, daño o consumo después de haber despachado material a una Obra: el costo ya está imputado a esa Obra por 019B. No restar nuevamente stock ni crear otro gasto. Cualquier gestión diferenciada de mermas en ejecución requerirá otro contrato.
- Proveedores, devoluciones a proveedores, compras, traspasos entre bodegas, conteos generales con ajustes arbitrarios, valor de salvataje, depreciaciones, contabilidad tributaria, DTE, tesorería, chat, notificaciones ni frontend.
- Reversar, editar o borrar un movimiento histórico; una eventual compensación futura requerirá nueva SPEC, no «ingreso ficticio» para deshacer una merma.

## 2. Propuesta de flujo de negocio

1. **Bodeguero informa una merma observada** de un artículo activo con cantidad, clase, motivo concreto y referencia de respaldo interno (ej. acta de inventario). Guardar fecha/actor del servidor, unidad histórica y referencia a corte físico/último movimiento del artículo.
2. Queda `PENDIENTE`: no descuenta stock, no reserva unidades, no cambia valoración ni modifica costo de Obra o finanzas. Puede consultarse con la proyección apropiada según rol.
3. **Administrativo/Finanzas decide** (`APROBAR` o `RECHAZAR`) con motivo obligatorio. La aprobación es por la cantidad completa solicitada (sin aprobación parcial para esta versión). Si la cantidad es incorrecta, rechazar y Bodega registra una nueva observación.
4. **Al aprobar, dentro de una sola transacción** se crea una operación auditable `MERMA` y exactamente un movimiento físico `MERMA`, se reduce el saldo y la cantidad valorizada por igual y se congela el costo unitario neto promedio vigente; no se altera el promedio restante salvo que el stock llegue a cero (en ese caso, promedio `null`). Conservar la valoración de pérdida calculada mediante `ROUND_HALF_UP` a dos decimales, sin redondeo silencioso a cero si el importe era positivo.
5. `RECHAZAR` registra evento y motivo, sin operación física, sin cambio de saldo/valoración y sin efectos económicos externos.
6. La petición queda en historial; no existe PATCH, DELETE, reapertura ni segundo ajuste. Repetir la misma decisión con la misma UUID/payload devuelve su resultado original, nunca ejecuta dos bajas.

**Regla de consistencia temporal propuesta:** la observación se asocia al último movimiento físico del artículo. Si el libro físico cambia antes de aprobar, devolver 409 `corte_desactualizado` y exigir rechazar/recontar, evitando imputar a existencias de otra recepción una pérdida observada antes. El cambio de precio/valoración sí obliga a recomputar el valor oficial actual bajo lock al confirmar; nunca confiar en un precio capturado en Bodega.

## 3. Clases de merma candidatas

`DANO` (deterioro/rotura), `VENCIMIENTO` (pérdida de aptitud), `EXTRAVIO` (faltante identificado), `DIFERENCIA_CONTEO` (conteo físico con explicación), `OTRA` (exige explicación precisa).

No permitir `OTRA` con texto genérico. La clasificación no determina por sí sola una responsabilidad laboral, causal tributaria ni registro contable.

El campo `referencia_respaldo` es un identificador textual interno obligatorio (máx. 150), no un documento tributario ni evidencia de archivo. Los adjuntos físicos quedan fuera de esta fase; no hacer que el servicio dependa de MongoDB/ClamAV para aprobar.

## 4. Permisos propuestos

| Acción | BODEGUERO | ADMINISTRATIVO_FINANZAS | GERENCIA | SUPERVISOR_OBRAS | TECNICO | ADMINISTRADOR_TI |
| --- | --- | --- | --- | --- | --- | --- |
| Crear observación de merma | Sí | No | No | No | No | No |
| Consultar observaciones y decisiones | Sí, **sin importes ni precios** | Sí, con importe histórico | Solo lectura, con importe histórico | No | No | No |
| Aprobar/rechazar | No | Sí | No | No | No | No |
| Confirmar la baja física | Se realiza atómicamente con la aprobación de AF; no hay segundo POST de Bodega | Por aprobación | No | No | No | No |
| Consultar movimientos físicos | Como 019A/019B (tipo MERMA sin precios) | Como contrato vigente | Como contrato vigente | Como contrato vigente | Sin cambios | Sin cambios |

La propuesta elige aprobación por **Administrativo/Finanzas** porque la baja afecta el valor de inventario, preservando separación frente al reportante físico; **requiere ratificación explícita**. Gerencia conserva solo lectura conforme a SPEC-020. No usar `is_staff`, `is_superuser`, roles en claims ni correos como autorización. Revalidar rol, actividad, sesión_version, credencial personal y bloqueos SPEC-018/018C en el momento de la decisión y tras espera por locks. Un Bodeguero no ve costo/importe en payloads, errores, listados ni serializadores.

## 5. Persistencia e inmutabilidad

Diseño candidato (se permite simplificar manteniendo invariantes):

- `MermaBodega`: PK, artículo, unidad histórica, tipo, cantidad `NUMERIC(12,3)`, motivo, respaldo, actor Bodeguero, fecha de observación, corte físico/último movimiento, UUID de creación, huella SHA-256 normalizada, estado proyectado `PENDIENTE/APROBADA/RECHAZADA`, actor/fecha/motivo de decisión; referencia opcional y **única** a la operación MERMA cuando aprobada.
- `MermaBodegaEvento`: libro append-only de creación y decisión, motivo, actor, sello temporal, UUID y huella idempotente. Una sola decisión por merma.
- `OperacionMaterial.MERMA`: evento de pérdida interna al precio promedio vigente, con actor aprobador real, referencia a observación, cantidad, unidad y snapshots de saldos/precios y cantidad/valor de pérdida. Sin referencia a Obra, solicitud 019C-1, autorización de entrega, ingreso valorable, gasto ni pago. Una operación MERMA corresponde a una sola observación aprobada y a **un** `MovimientoInventario.MERMA`.
- `MovimientoInventario.MERMA`: `saldo_posterior=saldo_anterior-cantidad`, actor institucional identificable, vínculo único a la operación, no mutación de origen, cantidad, saldos, actor, tipo ni fechas. La identidad del Bodeguero reportante permanece en `MermaBodega`; la de AF aprobador en evento/movimiento.

Utilizar migraciones **nuevas** para ampliar tipos/constraints (no editar 0001–0006). Extender triggers y conciliador firmado a:

`saldo = SUM(INGRESO) + SUM(DEVOLUCION) - SUM(SALIDA) - SUM(MERMA)`

La proyección `EstadoValoracion` reduce saldo valorizado en la misma cantidad; costo promedio unitario permanece idéntico si quedan unidades valorizadas. La invariante `saldo_valorado == saldo_fisico` previa a merma es obligatoria; **no consumir saldo sin valorar ni encubrir una regularización pendiente**. Un artículo inactivo no admite nuevas observaciones o bajas; las observaciones ya presentadas pueden rechazarse, pero no aprobarse si se desactivó antes de la decisión. Validar cantidad positiva, escala decimal exacta, límites y stock real suficiente.

Proteger también SQL directo relevante: FK, autor/estado, único evento/operación, coincidencia artículo/cantidad/actor, corte físico, stock/valoración, no mutación y confirmación diferida al commit. No debilitar el trigger de entregas 019B ni las restricciones SQL de solicitudes 019C-1.

## 6. API candidata

Bajo `/api/inventario/`, trailing slash obligatorio:

| Método | Ruta | Rol |
| --- | --- | --- |
| GET | `mermas/` | B/AF/G (proyección diferenciada) |
| POST | `mermas/` | B |
| GET | `mermas/{id}/` | B/AF/G |
| POST | `mermas/{id}/decidir/` | AF |
| GET | `mermas/{id}/historial/` | B/AF/G, proyección sin precios para B |

Entrada de observación: `articulo` entero BIGINT, `cantidad` string decimal hasta tres posiciones, `tipo`, `motivo`, `referencia_respaldo`, `clave_idempotencia` UUID. Nunca aceptar `saldo`, `promedio`, `costo`, `fecha`, `actor`, `estado`, `obra` o `gasto` desde el cliente.

Entrada de decisión: `decision` `APROBAR|RECHAZAR`, `motivo` obligatorio y UUID de idempotencia; no se acepta cantidad aprobada distinta ni precio enviado por AF. El valor de baja se deriva del promedio persistido bajo lock, no del cliente.

GET: `page` (25), `articulo`, `estado` y `tipo` permitidos solo donde corresponda; orden estable. Serializadores económicos exclusivamente AF/G; B siempre sin importes o costos, incluso en historial. `private, no-store`; `Vary: Authorization`. 400 payload/filtro, 401 sesión inválida, 403 rol, 404 recurso/página inexistente, 405 método, 409 saldo/corte/valoración/estado/UUID conflictivo.

Idempotencia por UUID de creación y UUID de decisión, con huella de actor y carga normalizada; UUID físicas independientes de la decisión, huellas y vínculos reconciliables; primer POST de creación 201, replays 200, decisiones 200; indicar `Idempotency-Replayed`. Una repetición histórica exacta no ejecuta otra baja aunque el estado de artículo haya cambiado. UUID con carga o actor distintos → 409. Mantener espacios de identidad coherentes con los existentes de 019A/B/C-1, sin permitir reutilización silenciosa.

## 7. Orden de locks y conservación de módulos

- Actos sin Obra: **UUID/idempotencia → artículo → existencia → valoración → observación/decisión según orden seguro explícito**. El análisis de bloqueo de observación y artículo debe garantizar que no surge una inversión con ingreso 019A, valoración 019B ni envío 019B/C-1. Se admite seleccionar primero la referencia de merma sin bloquear para conocer su artículo, luego bloquear artículo, existencia/valor y observación en orden definido, revalidar referencia y corte; probar carreras reales.
- Un nuevo tipo MERMA nunca adquiere locks de Presupuesto/Obra después de artículo. No tocar saldo de gasto, control de costos o cierre de Obra.
- La aprobación es transacción única: observación + evento + OperacionMaterial + MovimientoInventario + proyección de saldo/costo histórico; el fallo de cualquier efecto revierte todos.
- El libro de movimientos de 019A/B amplía tipo MERMA de forma compatible; las rutas de entregas/devuelves, sus schemas, eventos, costo de Obra, solicitudes 019C-1, PagosDocumento y Egresos siguen intactos.
- Ningún hecho de merma genera automáticamente un `Egreso`, `PagoDocumento`, `GastoObra` ni ajuste de flujo monetario. El valor de pérdida se conserva solo como dato de inventario interno; no presentarlo como salida de caja ni reconciliación bancaria.

## 8. Validaciones automatizadas y entrega futura

Solo después de ratificación:
1. `manage.py check`, `makemigrations --check --dry-run`, migraciones limpias y upgrade desde 019C-1/021 con historia real, sin backfill inventado.
2. Pruebas de seis roles, proyección B sin costo en cualquier ruta, filtros/paginación y negativos; idempotencia con replays tras cambios de estado; sesión bloqueada/revocada durante esperas.
3. Mermas sucesivas y promedio estable, agotamiento a cero, precisión decimal/valor congelado, artículos desactivados, saldo sin valorizar, cortes obsoletos, falta de stock, SQL directo y libros inmutables.
4. Carreras PostgreSQL reales con bloqueos observados: dos decisiones, merma vs entrega 019B, merma vs ingreso 019A, merma vs valoración AF, dos mermas sobre mismo saldo, cambio de rol/sesión. Sin costos duplicados, saldos negativos, proyecciones divergentes o deadlocks.
5. Regresión Inventario/Obras/Finanzas/Usuarios y backend completo, CI en PR.
6. OpenAPI 3.1 y documentación técnica bajo `backend/docs/`; colección Postman `SPEC-019C-2` y environment legible sin Vault para pruebas esenciales delegadas a compañeros; pruebas Postman manuales NO son bloqueantes.
7. OpenCode implementa solo `backend/` en `feature/backend-019c2-mermas-bodega`, commit/push sin PR ni merge; ChatGPT revisa GitHub, crea PR y fusiona solo tras pruebas y CI. No modificar `frontend/`, `specs/`, migraciones históricas ni introducir archivos temporales, secretos o scripts de un solo uso.

## 9. Exclusiones y condiciones antes de producción

- No mover historial de precio de 019A/019B; cero es costo permitido solo si originalmente fue valorizado y autorizado en 019B (no inventar cero por merma).
- La observación es evidencia administrativa, no certificación fiscal ni ajuste de contabilidad financiera. Corresponde a la empresa establecer política externa sobre documentación y pérdidas fiscales.
- Sin rollback destructivo con registros MERMA confirmados. Las migraciones deben bloquear retroceso que corrompa el libro o elimine historia y documentar copia de seguridad.
- Credenciales, bloqueo TI, TLS confiable y decisiones de seguridad productiva mantienen sus propias puertas; esta SPEC no las aprueba.

## 10. Decisiones funcionales a ratificar

La **inclusión de mermas en Bodega ya está confirmada**. Lo que requiere ratificación explícita antes de un contrato definitivo son las siguientes decisiones sobre su funcionamiento:

1. **Límite:** 019C-2 trata únicamente merma física localizada en Bodega, no merma de material ya despachado a Obras.
2. **Separación:** Bodeguero presenta, Administrativo/Finanzas aprueba o rechaza; aprobar hace el descuento físico de inmediato, sin segunda confirmación de Bodega. Gerencia solo consulta.
3. **Respaldo:** motivo y referencia textual interna obligatorios; sin archivos adjuntos en Beta. Tipos de la sección 3.
4. **Corte:** si otro movimiento físico ocurre entre observación y decisión, se exige recuento y una nueva solicitud; sin reservas y sin bloqueo automático de despachos pendientes.

No interpretar la confirmación de que deben existir mermas como aprobación automática de estos cuatro puntos de diseño; tampoco el silencio, un PR documental o pruebas de laboratorio los ratifican. Con acuerdo explícito, ChatGPT actualizará este encabezado, dejará constancia y fusionará la SPEC antes de emitir prompt ejecutable para OpenCode.
