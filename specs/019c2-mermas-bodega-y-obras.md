# SPEC-019C-2 — Mermas de Bodega y de Obras (FYAG Beta)

> **Estado: CONTRATO FUNCIONAL RATIFICADO — 21-11-2026.** El responsable confirmó que las mermas deben registrarse tanto en Bodega como en Obras: **Bodeguero reporta y Administrativo/Finanzas valida las de Bodega; Técnico reporta y Supervisor de Obras valida las de Obra.** El material inutilizable en una Obra no se devuelve como stock utilizable y **no provoca un segundo descuento físico ni otro GastoObra**. Esta SPEC define el mínimo operativo de FYAG Beta, sin convertir Bodega en ERP. Ratificación documental no significa implementación, CI aprobado ni despliegue.
>
> **Base técnica inspeccionada:** `main` `e2ee29ec17bb2219b1ee6b57c4e6da3a210c1690`. Se reutilizan SPEC-019A (saldo y movimientos), SPEC-019B (entregas, devoluciones, costo fijo por despacho y valoración), SPEC-019C-1 (solicitudes), SPEC-004B (participantes, gastos, cierre), SPEC-020A/B (Gerencia) y SPEC-021 (egresos reales). **ChatGPT es responsable exclusivo de `specs/`; OpenCode implementa solo backend.** React corresponde a compañeros.

## 1. Objetivo y distinción económica

Registrar dos hechos diferentes:

- **Merma de Bodega (MB):** unidades deterioradas, extraviadas o no aprovechables que **todavía forman parte del saldo físico de Bodega**. La aprobación produce una baja física de inventario y un registro histórico de pérdida de valor, **sin Egreso, PagoDocumento ni GastoObra**.
- **Merma de Obra (MO):** unidades ya entregadas físicamente a una Obra mediante una `OperacionMaterial` `ENTREGA` de SPEC-019B, que por corte, daño o circunstancias del trabajo **ya no pueden reutilizarse ni volver como saldo apto a Bodega**. La aprobación clasifica parte de lo despachado como pérdida/desperdicio de esa Obra. **No mueve nuevamente el stock** y **no incrementa ni vuelve a registrar el costo de Obra**: ese costo ya quedó imputado por el despacho. Si luego hay devolución real de material reutilizable, 019B sigue reduciendo el costo por la cantidad efectivamente recibida.

Ejemplo vinculante (6 m de manguera, 4 m aplicados, 2 m sobrantes):

| Situación | En Bodega | En el costo de Obra |
| --- | --- | --- |
| Se despachan 6 m | -6 m al entregar | + costo histórico de 6 m por 019B |
| Sobran 2 m **reutilizables** y se devuelven físicamente | +2 m por DEVOLUCION 019B | Disminuye costo neto de Obra al costo unitario original |
| Sobran 2 m **inutilizables**; Técnico informa 2 m de merma y Supervisor aprueba | **0 m de movimiento adicional** | Mantiene el costo neto de 6 m, con 2 m clasificados como merma |
| Se reportan 2 m pero todavía no se aprueban | Sin movimiento | Sin cambio de costo ni merma confirmada |

El sistema no debe inferir que toda unidad no devuelta fue efectivamente utilizada: cantidad no devuelta ni clasificada sigue siendo **remanente sin clasificación confirmada**. La merma confirmada se informa separadamente como subconjunto del material entregado no retornado. Un agregado informativo de merma × costo unitario histórico **nunca se suma otra vez a `GastoObra` ni al flujo de caja**.

## 2. Estados y tipologías

Ambos flujos tienen `PENDIENTE`, `APROBADA`, `RECHAZADA`, con un evento inmutable de creación y máximo un evento de decisión. No se permite modificar ni borrar solicitudes/eventos o cambiar una decisión confirmada. El rechazo no produce movimiento.

- **Bodega:** `DANO`, `VENCIMIENTO`, `EXTRAVIO`, `DIFERENCIA_CONTEO`, `OTRA` (motivo descriptivo obligatorio). No se confunde con devolución a proveedor ni con ajuste contable tributario.
- **Obra:** `CORTE_NO_REUTILIZABLE`, `DANO_EN_OBRA`, `EXTRAVIO_EN_OBRA`, `OTRA`. `OTRA` obliga explicar por qué no es reutilizable. No clasificar material apto para retorno como merma.
- Justificación y referencia interna de respaldo en Bodega (ej. acta): texto obligatorio, sin adjuntos nuevos para esta Beta. Justificación y lugar/actividad del uso o daño en Obra: texto obligatorio; puede tener referencia interna opcional. Sin nuevo servicio de archivos.

La decisión aprueba **la cantidad informada completa** o rechaza, con motivo obligatorio; para corregir una cantidad equivocada se rechaza la solicitud y se crea otra. No hay aprobación parcial, edición, cancelación, reapertura ni flujos multinivel en esta fase.

## 3. Flujo MB: merma de Bodega

1. Bodeguero declara artículo **activo**, cantidad positiva (string decimal de tres posiciones como máximo), motivo específico, tipo, referencia interna y UUID de creación. Guardar artículo/unidad, actor, fecha de servidor y **corte físico del último movimiento del artículo**, para comparar al validar. Registrar solicitud PENDIENTE y evento CREACION; sin efecto en saldo o promedio.
2. Administrativo/Finanzas decide mediante UUID distinto, con motivo obligatorio. Solo puede **aprobar** si artículo sigue activo, existe saldo suficiente, **todo su saldo está valorizado** (`EstadoValoracion.saldo_valorado == ExistenciaInventario.saldo`), existe promedio cuando saldo positivo y el último movimiento físico sigue siendo el observado. Si el libro cambió, 409 `corte_desactualizado`: rechazar y recontar, no descontar ciegamente unidades de una recepción posterior. Una valoración sin nuevo movimiento físico obliga recalcular bajo lock al precio oficial vigente.
3. La aprobación atómica crea exactamente **una** `OperacionMaterial.MERMA`, exactamente **un** `MovimientoInventario.MERMA`, evento de aprobación y estado final. Actualiza saldo físico y saldo valorizado en la misma cantidad. Congela costo promedio unitario vigente de inventario (neto CLP); el promedio de las unidades restantes no cambia, y pasa a null si el saldo llega a cero. La pérdida histórica se computa con Decimal y HALF_UP a centavo; no fabricar ni redondear silenciosamente a cero un valor positivo.
4. El actor aprobador AF queda identificado en evento y movimiento de baja; el Bodeguero informante permanece identificado en la observación. Distinguir **quién reportó la pérdida** de **quién autorizó su baja**.
5. RECHAZAR produce solo evento/historial, sin operación ni movimiento físico. Una repetición exacta del POST no genera otra baja.

**Regla contable:** la pérdida MB es un ajuste de valor de existencias, **no** una salida efectiva de dinero. No modificar `finanzas.Egreso`, `PagoDocumento`, flujo monetario ni `obras.GastoObra` por esta aprobación.

## 4. Flujo MO: merma atribuible a Obra

1. Técnico autenticado y **participante activo** reporta, mediante el ID de la `ENTREGA` original 019B (no por nombre de artículo), cantidad positiva, tipo, motivo, detalle del trabajo/uso y UUID. `obra`, `articulo`, unidad y costo unitario se **derivan de la entrega**; no se aceptan como autoridad desde el body. La Obra debe estar `EN_PROCESO` o `SUSPENDIDA`. La entrega identifica inequívocamente la imputación de origen a `GastoObra`.
2. La observación PENDIENTE y su evento no altera devolución autorizada, stock físico, gasto, cierre de costos o saldo financiero, ni reserva cantidades.
3. Supervisor de Obras decide con motivo y UUID; al **aprobar**, verifica Obra operativa, Técnico originalmente informante todavía activo/participante válido, entrega perteneciente a la Obra, gasto BODEGA_019B vigente y cantidad disponible para clasificar. Una aprobación aprobada crea evento y clasificación MO irreversible, **pero no `OperacionMaterial` física, `MovimientoInventario` ni nuevo `GastoObra`**.
4. La cantidad aprobada se vincula a una sola entrega; la suma `mermas MO aprobadas + devoluciones FÍSICAS recibidas` de esa entrega debe ser menor o igual a su cantidad entregada. Esto impide clasificar como merma algo ya restituido a Bodega.
5. La **recepción posterior de una devolución 019B** también debe verificar `cantidad_mermada_aprobada + cantidad_ya_recibida + cantidad_a_recibir <= cantidad_entregada`, con locks sobre la misma entrega, incluso si la autorización de devolución fue emitida **antes** de aprobar la merma. La autorización previa permanece en el historial, pero su saldo recibible efectivo se reduce; nunca admitir retorno físico de una cantidad ya perdida. Al crear **nuevas** autorizaciones de devolución, no reservar más que `entregado - mermas_aprobadas - otras cantidades ya autorizadas`; las autorizaciones previas válidas no se reescriben.
6. El costo neto del `GastoObra` original sigue calculándose exclusivamente por la fórmula 004B/019B usando cantidad entregada y `cantidad_devuelta` realmente recibida. No incrementar `GastoObra`, `ControlCostosObra`, `CierreCostosObra` ni generar un segundo evento económico por solo clasificar merma. Puede mostrarse **valor informativo no aditivo** `cantidad_mermada * costo_unitario_neto_historico_de_entrega`; no incluirlo de nuevo en totales ni como dinero pagado.
7. Si el Técnico se desasigna o la Obra finaliza, conservar observación/decisión histórica accesible por su autor conforme a RBAC. Una merma pendiente no bloquea la finalización por sí sola; después de finalizar no puede aprobarse ni reabrirse el cierre para declararla retrospectivamente. Puede rechazarse solo mientras la Obra siga operativa (consistente con 019C-1).
8. No solicitar a Bodeguero confirmar recepción de material inutilizable: **no existe retorno físico apto**. La decisión de MO es una clasificación del material ya fuera de Bodega, no un movimiento inventarial adicional.

## 5. Matriz de permisos y visibilidad

| Recurso/acción | Técnico | Supervisor | Bodeguero | AF | Gerencia | TI |
| --- | --- | --- | --- | --- | --- | --- |
| Reportar MB | No | No | **Sí** | No | No | No |
| Ver MB | No | No | Sí, **sin costos** | Sí, con valoración | Solo lectura, con valoración | No |
| Aprobar/rechazar MB | No | No | No | **Sí** | No | No |
| Reportar MO | **Sí, participante activo** | No | No | No | No | No |
| Ver MO | **Solo propias**, incluso históricas | Sí | No | No | Solo lectura | No |
| Aprobar/rechazar MO | No | **Sí** | No | No | No | No |
| Operar devoluciones/entregas 019B | Sin cambios | Sin cambios | Sin cambios | Sin cambios | Sin cambios | Sin cambios |

La vista de MO para Técnico excluye costo, importe, stock y datos económicos de `GastoObra`; el filtro de solicitudes propias debe aplicarse a la consulta SQL, nunca solo a serialización. Supervisor/Gerencia pueden consultar importe **informativo** de merma MO cuando corresponde a la visibilidad de costos de Obras vigente; ninguna otra autorización económica se amplía por esta SPEC. Bodeguero nunca obtiene costos de MB por serializadores, filtros, mensajes, errores ni historial. Las seis identidades dependen de rol, actividad, sesión_version y estado de seguridad persistidos; sin bypass por flags superusuario, staff o claims JWT. Revalidar tras esperas de bloqueo. Respuestas privadas `Cache-Control: private, no-store` y `Vary: Authorization`.

## 6. Modelos y trazabilidad

Se permiten tablas independientes MB/MO o una base compartida con restricciones fuertes **siempre que** se mantengan identidades y permisos inequívocos. Diseño conceptual mínimo:

- `MermaBodega` + evento append-only: artículo, unidad histórica, cantidad NUMERIC(12,3), tipo, referencia, motivo, actor B, fecha, corte físico, UUID/huella y estado/decisión proyectados; vínculo OneToOne a `OperacionMaterial.MERMA` solo cuando aprobada.
- `MermaObra` + evento append-only: **FK a la entrega específica 019B**, Obra/artículo/unidad derivados o snapshots verificables, técnico actor, cantidad, clasificación/motivo/actividad, fecha, UUID/huella, estado/decisión proyectados; no vínculo físico nuevo ni gasto duplicado.
- `OperacionMaterial.MERMA` (solo MB): sin Obra, sin entrega/autorización/solicitud material, sin GastoObra, con costo unitario histórico, saldo y promedio previo/post, actor AF y enlace único a MB. No generar nombre engañoso `MERMA` para MO en el libro de movimientos.
- `MovimientoInventario.MERMA` (solo MB): vínculo 1:1 con operación, cantidad positiva y diferencia exacta `saldo_posterior = saldo_anterior - cantidad`. Conciliar el saldo firmado:
  `SUM(INGRESO + DEVOLUCION - SALIDA - MERMA)`.
- Cada creación/decisión tiene UUID canónico y huella de tipo + actor + payload normalizado; idempotencia real y únicas transiciones; eventos y originales inmutables, proyecciones de decisión garantizadas también frente a SQL directo.

**No modificar migraciones históricas** 0001–0006 de inventario ni migraciones de Obras. Introducir migraciones nuevas aditivas para tablas, tipo de operación y movimiento, constraints, triggers, conciliación, proyecciones y validación cruzada MO/devoluciones. Proteger upgrade de saldos y entregas históricas: todas las filas existentes permanecen; no crear mermas ni precios ficticios. Con historia de MERMA no permitir rollback que quite su validación o destruya libro, y explicitar preservación/backup.

## 7. API mínima para backend

Rutas bajo `/api/inventario/` con trailing slash:

| Método y ruta | Acción |
| --- | --- |
| GET/POST `mermas-bodega/` | B crea; B/AF/G leen según proyección |
| GET `mermas-bodega/{id}/` | Detalle e historial, B sin importes |
| POST `mermas-bodega/{id}/decidir/` | AF aprueba o rechaza |
| GET/POST `mermas-obra/` | Técnico crea; Técnico solo propias, S/G leen |
| GET `mermas-obra/{id}/` | Detalle e historial con scope y costos restringidos |
| POST `mermas-obra/{id}/decidir/` | Supervisor aprueba o rechaza |

POST MB: `articulo`, `cantidad` (string Decimal), `tipo`, `motivo`, `referencia_respaldo`, `clave_idempotencia`. POST MO: `entrega` (ID 019B), `cantidad`, `tipo`, `motivo`, `actividad` (descripción de uso/daño), `clave_idempotencia`, referencia opcional. POST decisión: `decision=APROBAR|RECHAZAR`, `motivo`, `clave_idempotencia`. Cuerpos cerrados, nunca actor, fecha, stock, saldo, monto, costo ni gasto desde cliente. Identificadores positivos BIGINT; cantidades string positivo Decimal(12,3), máximo 999999999.999; textos trim, sin controles y con límites explícitos. Usar la convención 019C-1 para normalización y respuestas.

GET: 25 por página, orden determinista, filtros `page`, `articulo`, `estado`, `tipo`, y para MO `obra`, `entrega` dentro de su scope. Técnico no filtra por otros actores. Replay idéntico devuelve respuesta original sin mutar nada (200 con `Idempotency-Replayed: true`), creación inicial 201 y decisión inicial 200. Otro payload/actor/acción con misma UUID devuelve 409. Usar 400/401/403/404/405/409 consistentes; recurso ajeno al Técnico retorna 404. Si la imagen inicial de POST ya cambió de estado, el replay de creación devuelve su estado de creación PENDIENTE y GET devuelve el estado actual (misma semántica 019C-1).

El catálogo de movimientos de 019A/B añade el tipo MERMA físico **solo para Bodega**, sin costos visibles al rol B. No cambiar contratos 019B o 019C-1 salvo adaptación compatible para proteger retornos contra MO aprobadas. Documentar OpenAPI 3.1 y colección Postman corta con environment legible, sin Vault ni credenciales reales; pruebas manuales delegadas no detienen el trabajo.

## 8. Atomicidad, concurrencia y controles cruzados

1. **MB:** al aprobar utilizar `UUID/idempotencia → artículo → existencia → EstadoValoracion → solicitud MB`, con relectura/validación de estado, último movimiento y precio. No tomar locks de Obra después de artículo. Rechazo sin efecto físico. Las funciones existentes de 019B exigen actualmente Obra o actor B para varias operaciones; adaptarlas de forma controlada mediante migraciones/funciones nuevas (no modificando migraciones viejas), sin abrir caminos SQL de origen falso.
2. **MO:** `UUID/idempotencia → Presupuesto → Obra → entrega original 019B → declaración de merma/participante`; evitar tomar artículo y locks económicos de costo porque no hay nuevo stock/gasto. Usar el **mismo lock de la entrega original** que 019B utiliza para devoluciones; comprobar `MO aprobada + devoluciones realmente recibidas <= entrega`.
3. **019B interoperable:** adaptar, bajo bloqueo de entrega original, la **autorización de devolución nueva** para considerar mermas ya aprobadas; adaptar la **recepción efectiva** para no recibir unidades marcadas como inutilizables aunque hubiese autorizaciones anteriores. No reescribir ni borrar autorizaciones históricas, movimientos, eventos o gastos. Mostrar remanente efectivamente retornable sin declarar que una autorización antigua fue anulada.
4. **Evitar bloqueos inversos:** revisar cómo 019B adquiere locks de autorización original/entrega, artículos y triggers; el circuito de merma MO no debe tomar en secuencia `artículo → Obra` ni `merma → entrega` si otro camino usa orden inverso. Probar con transacciones PostgreSQL independientes que la carrera MO vs devolución, MO vs finalización, dos MO simultáneas y MB vs entrega/ingreso/valoración no introduce deadlock ni saldos incorrectos.
5. Verificar que modificar clasificación MO jamás escriba `GastoObra`, `CierreCostosObra`, `Egreso`, `PagoDocumento`, `EstadoValoracion` ni `MovimientoInventario`. Los dashboards/reportes económicos existentes **no** sumarán la valoración de MO sobre el costo de la entrega.
6. Comprobar SQL directo: no permitir actor/Obra/entrega/cantidad falsos, dos decisiones, reapertura, evento sin original, autorización/devolución que supere remanente luego de merma o saldo no conciliado. Los triggers diferidos verifican exactamente un efecto MB, y ninguno para MO, al commit. Si se altera el núcleo de 019B, preservar sus garantías de inmutabilidad y conciliación.

## 9. Pruebas, operación y entrega

- **Ejemplo 6 metros:** recepción valorizada; despacho 6 m desde Bodega; MO aprobada por 2 m; no cambia stock posterior al despacho; costo neto permanece por 6 m. Si en vez de MO se devuelve físicamente 2 m reutilizables, subir stock 2 m y costo neto debe quedar por 4 m. Si existen devolución y merma sobre una misma entrega, su suma jamás supera los 6 m.
- Aprobar MB reduce stock y saldo valorado exactamente una vez y congela promedio; rechazar MB/MO deja estado previo. Corte desactualizado, artículo inactivo, falta de valoración y falta de stock → rechazo controlado. MO requiere Obra operativa, Técnico participante, entrega auténtica y Supervisor; ninguna merma MO genera movimiento físico ni nuevo gasto.
- Seis roles y proyección diferenciada, revocación de sesión/cuenta bloqueada durante espera, datos de otro Técnico ocultos, errores sin fuga, solicitud y decisiones con idempotencia, replays históricos, SQL directo y constraints.
- Carreras PostgreSQL reales con bloqueos observados: MB vs despacho/ingreso/valoración y dos MB; MO vs devolución autorizada, devolución recibida, finalización, desasignación, dos MO concurrentes, mismo UUID y UUID distintos; sin doble descuento, clasificación doble, inconsistencias ni deadlocks.
- Migración limpia, upgrade desde `main` actual con inventario, GastoObra y devoluciones reales; `manage.py check`, `makemigrations --check --dry-run`, suite Inventario/Obras/Finanzas/Usuarios, regresión completa, OpenAPI y Postman. La implementación de pruebas no depende de conteos globales ni IDs fijos. CI del HEAD del futuro PR antes de merge.
- Permisos heredados de seguridad SPEC-018/018C; no activar TLS/risks productivos ni desplegar. Nunca borrar datos persistidos de usuario ni introducir scripts de desarrollo, secretos, temporales o cambios a `frontend/`.
- OpenCode trabaja en **`feature/backend-019c2-mermas-bodega-obras`**, desde `main` actualizado, prueba, commitea y hace push; **no crea PR, no hace merge, no modifica `specs/` ni `frontend/`**. ChatGPT realiza revisión de código GitHub, PR y CI, y decide merge; documentación técnica permanente `backend/docs/` únicamente.

## 10. Decisiones ratificadas y frontera del proyecto

El usuario aprobó explícitamente:
1. **Ambas categorías:** merma de Bodega y merma de Obra.
2. **Merma de Obra:** Técnico informa material inutilizable y Supervisor valida; los sobrantes reutilizables se tramitan mediante devolución 019B.
3. **Integridad económica:** merma MO ya despachada no resta stock de nuevo y mantiene el costo original; merma MB sí baja stock y registra pérdida interna sin generar pago o gasto de Obra.
4. **Simplicidad empresarial:** no crear ERP de compras, inventario multibodega, motor contable, trazabilidad de lotes, notificaciones, chat, nuevo frontend ni archivos nuevos.

Se adopta como decisión técnica complementaria de mínima segregación de funciones para MB que **Bodeguero reporta y Administrativo/Finanzas aprueba o rechaza**, manteniendo Gerencia en solo lectura. El diseño prioriza invariantes de entrega/retorno y control económico: cualquier conflicto con los contratos existentes se debe **reportar a ChatGPT sin cambiar esta SPEC**.

La aprobación de este documento autoriza exclusivamente preparar implementación backend mediante PR y controles CI posteriores; no equivale a producción autorizada. La auditoría integral final de FYAG Beta queda programada para cuando concluyan las funcionalidades del backend.

## Seguimiento del frontend local — 25-11-2026

- `frontend/src/pages/Mermas.jsx` expone la presentación por ámbito y conserva la matriz del contrato: Bodeguero informa mermas de Bodega; Técnico informa mermas de Obra; Administrativo/Finanzas decide Bodega y Supervisor de Obras decide Obra. El Técnico no recibe campos monetarios.
- La vista mapea códigos API a etiquetas en español solo para presentar, mantiene payloads con códigos originales y ofrece filtros, formulario, detalle, historial y paginación. Se añadió `frontend/src/styles/pages/mermas.css`, enlazado desde `main.jsx`.
- Test de contrato existente `tests/inventory-actions.test.js` comprueba scope, paginación y ocultación de importes a Técnico. Estado local de frontend; no implica cambios backend, CI completa, merge ni despliegue.
