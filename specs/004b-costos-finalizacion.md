# SPEC-004B — Costos reales, técnicos participantes, turnos y finalización de Obras

## 1. Estado, contexto y alcance

**Estado: implementación parcial. 004B-1 (técnicos participantes) integrado en `main` mediante PR #9, con Backend CI aprobado; 004B-2 a 004B-5 pendientes.** Las decisiones de negocio B1–B8 fueron confirmadas por el equipo el 7 de noviembre de 2026. Esta SPEC no declara finalizado el conjunto de 004B ni equivale a aprobación formal externa de FYAG.

- Proyecto: **FYAG — Sistema de Gestión de Obras y Presupuestos**.
- Documentos base: `specs/004-gestion-obras.md` (SPEC-004, especialmente D1–D9) y `specs/003b-gestion-presupuestos.md` (SPEC-003B).
- Base tecnológica: Django REST Framework, PostgreSQL, JWT, `Usuario.Rol`, React como cliente.
- Estado del repositorio: **004A integrado mediante PR #8** y **004B-1 integrado mediante PR #9**, ambos en `main` con Backend CI aprobado. Permanecen las reglas de 004A, ampliadas por las membresías de técnicos participantes incorporadas en 004B-1.
- Objetivo: registrar **lo que realmente costó ejecutar cada Obra**, incorporar técnicos participantes y turnos individuales con evidencia, validar la completitud y habilitar la transición **`EN_PROCESO → FINALIZADA`**.

**Reglas heredadas que se conservan:** una Obra por Presupuesto; presupuesto de origen inmutable y aprobado por cliente; técnico principal activo obligatorio al iniciar; bloqueo de anulación comercial cuando existe una Obra; finalización operativa distinta de facturación y pago; trazabilidad; permisos por rol sin bypass por superusuario; y prohibición de finalizar sin costos reales registrados y validados.

**Ampliaciones deliberadas de 004A:** se incorpora una relación de técnicos participantes además del responsable principal, y se otorgan permisos de escritura *exclusivamente* para los turnos y evidencias propios del técnico. El resto de las restricciones de 004A permanece igual. Estas ampliaciones deben mencionarse también en SPEC-004 al implementar 004B para evitar documentación contradictoria.

### 1.1 Dentro de 004B

1. Asignación de participantes técnicos a una Obra, además del responsable principal.
2. Inicio y fin de **turno por Obra y por técnico**, con horario registrado por el servidor.
3. Evidencia de cierre de turno: **descripción escrita obligatoria y fotografías opcionales**.
4. Revisión de turnos por Supervisor de Obras y registro manual del costo horario correspondiente.
5. Registro manual de materiales y otros gastos directos **en un mismo apartado de interfaz**, diferenciados por tipo.
6. Devoluciones, correcciones y baja lógica con historial, sin borrado físico.
7. Revisión por rubro, versión de costos, validación y fotografía inmutable de cierre.
8. Finalización operativa y constancia excepcional de **servicio sin cobro** autorizada por Supervisor, **sin borrar costos reales**.

### 1.2 Fuera de 004B

Inventario/stock, compras, guías y facturas tributarias, nómina, remuneraciones, IVA, cobranza, pagos, aplicación contable efectiva de descuentos, anticipos, rentabilidad, aprobaciones comerciales nuevas, cancelación/reapertura de Obra, gestión completa de garantías gratuitas, geolocalización, control biométrico, auditoría global, notificaciones y validación automática de veracidad física del trabajo. La evidencia de un turno no prueba por sí sola que el técnico trabajó: se añade revisión de supervisor.

## 2. Decisiones cerradas y alcance de autorización

Las decisiones siguientes reflejan las respuestas del responsable del proyecto, no supuestos extraídos de los anexos académicos.

| ID | Decisión confirmada | Consecuencia en el sistema |
| --- | --- | --- |
| B1 | **Supervisor ingresa los costos manualmente**, tanto por material/gasto como por hora de trabajo. | No hay tarifas automáticas, sueldos inferidos ni costo proveniente del Presupuesto. Se conserva costo histórico por registro. |
| B2 | Incluir gastos adicionales, **junto con materiales en la experiencia de usuario**, sin crear pantallas innecesarias. | Un recurso `GastoObra` con tipo diferenciado; mano de obra sigue en turnos. |
| B3 | **No se requiere aprobación de Gerencia por cada gasto ni para validar/finalizar**; el presupuesto comercial ya fue aprobado por Gerencia. | Supervisor registra/revisa/valida/finaliza; Gerencia consulta. No se agregan transiciones de aprobación por gasto. |
| B4 | Una Obra requiere **al menos un técnico principal** para iniciarse y **puede tener varios participantes**. | Se conserva `Obra.tecnico_responsable`; se agrega `ObraParticipante`. |
| B5 | Cada técnico registra **su propio tiempo** al presionar iniciar/finalizar turno, **por cada Obra**. | No se admiten horas digitadas libremente por técnicos. El servidor fija inicio y término. |
| B6 | Al finalizar turno se entrega **descripción escrita obligatoria**, y **fotos opcionales**. | Sin descripción no se cierra el turno; adjuntar fotos no sustituye la descripción. |
| B7 | Excepcionalmente el **Supervisor puede autorizar no cobrar** una reparación, con justificación y registro. | Registrar la decisión de cortesía separada de costos reales y Presupuesto aprobado; su ejecución financiera queda fuera de 004B. |
| B8 | **No cobrar no significa costo de empresa igual a $0**. | Una obra sin cobro sigue sumando materiales, trabajo y otros costos reales. No poner totales a cero por cortesía. |

**Precisiones técnicas derivadas (a validar mediante pruebas):** un técnico solo puede mantener un turno abierto en todo el sistema a la vez; el supervisor revisa los turnos antes del cierre; las operaciones de costo invalidan cualquier validación anterior; y finalizar exige al menos un turno completo validado, los rubros declarados y un costo real total positivo. Estas precisiones convierten las decisiones B1–B8 en reglas verificables, sin atribuirlas como requerimientos expresos del cliente.

## 3. Modelo relacional propuesto

### 3.1 `ObraParticipante`

Permite **varios técnicos en una misma Obra** sin cambiar la cardinalidad `Presupuesto ↔ Obra` ni eliminar al responsable principal de 004A.

| Campo | Definición |
| --- | --- |
| `id` | BigAutoField. |
| `obra` | FK a Obra, `PROTECT`. |
| `tecnico` | FK a Usuario, `PROTECT`; debe estar activo y tener rol `TECNICO` al asignar. |
| `activo` | Booleano; indica pertenencia operativa actual, no elimina historia. |
| `asignado_por`, `asignado_en` | Supervisor autenticado y timestamp servidor al dar de alta/reactivar. Null solo en filas históricas identificadas como migradas, cuando la información no se pueda reconstruir verazmente. |
| `desasignado_por`, `desasignado_en`, `motivo_desasignacion` | Nullable, fijados al desasignar. |
| `origen_registro` | `OPERACION` o `MIGRACION_004B`: distingue el alta real del backfill, sin inventar actor ni fecha de asignación histórica. |

- Unicidad de pareja `(obra, tecnico)` **para membresía vigente**; preferentemente una sola fila por pareja que pueda reactivarse con evento, o historial de periodos de asignación con constraint condicional de vigencia, pero no ambas estrategias a la vez. Para este MVP se adopta **una fila por pareja con `UniqueConstraint(obra, tecnico)`**, y un historial de asignación/reactivación separado.
- El **responsable principal** siempre cuenta como participante activo. Al crear Obra con responsable, sincronizar su membresía en la misma transacción; al asignar/reasignar responsable, activar al nuevo principal y registrar la transición en el historial sin crear un segundo evento de Obra 004A.
- **Compatibilidad con 004A:** al reemplazar o desasignar al principal, la membresía del antiguo principal se desactiva por defecto, por lo que pierde el acceso salvo que el Supervisor vuelva a incorporarlo expresamente como participante adicional. No se concede acceso implícito por haber sido antes el responsable. Esto conserva el comportamiento de los tests 004A de reasignación y permite que siga participando si realmente está asignado. Sus turnos históricos no se borran.
- **Backfill en migración:** cada Obra existente con `tecnico_responsable` debe obtener su relación activa sin alterar Obra, presupuesto ni ObraEvento. Identificar la membresía como `MIGRACION_004B`; no atribuir a un supervisor ni a una fecha histórica que no se pueda verificar. No duplicar eventos de creación/estado de 004A ni crear turnos ficticios.
- Ninguna Obra puede **iniciarse** sin responsable principal activo, según 004A. Los participantes adicionales **no reemplazan** al principal para ese requisito.
- El supervisor puede administrar participantes en `PLANIFICADA`, `EN_PROCESO` o `SUSPENDIDA` con motivo y evento. Un técnico **principal vigente no se puede desasignar directamente** desde la ruta de participantes: debe cambiarse mediante `cambiar-tecnico`. No desasignar una persona que tenga turno abierto; solicitar cierre/corrección primero cuando existan turnos (bloque 004B-2).
- La gestión de participantes no modifica automáticamente `Obra.tecnico_responsable`. El responsable se cambia únicamente por la acción 004A `cambiar-tecnico`.
- La lista de obras del técnico se restringe a su membresía vigente (incluye responsable principal). La lectura 004A, antes limitada al principal, se amplía a esos participantes **sin otorgar lectura global**. El filtrado ocurre antes de contar/paginar y `retrieve`; evitar duplicados al hacer JOIN, por ejemplo usando `Exists`/`distinct`.
- El historial de altas, bajas y reactivaciones debe quedar en un **modelo de eventos de participantes** append-only con actor, motivo, antes/después y timestamp, separado de `ObraEvento` para no reescribir la constraint histórica de transiciones 004A. La migración que reconstruye membresías preexistentes no simula una acción humana.
- El bloque **004B-1 está implementado**: participantes, sincronización, lectura por membresía y pruebas. No creó turnos, tarifas, gastos, fotos ni `finalizar`. El guard por turno abierto se incorpora y verifica obligatoriamente en **004B-2**, antes de permitir iniciar turnos.

### 3.2 `TurnoObra`: tiempo real por técnico y por obra

Un turno corresponde al tiempo efectivo declarado por **un técnico dentro de una Obra concreta**, no a la jornada laboral global. Se pueden registrar varios turnos históricos del mismo técnico para una Obra, sin superposiciones.

| Campo | Definición |
| --- | --- |
| `id` | BigAutoField. |
| `obra` | FK Obra, `PROTECT`. |
| `tecnico` | FK Usuario, `PROTECT`; ejecutor histórico, no reemplazado al cambiar responsable. |
| `iniciado_en` | `DateTimeField` con hora del servidor, inmutable; no recibida del cliente. |
| `terminado_en` | Nullable; se fija al finalizar turno con reloj servidor. |
| `duracion_segundos` | Duración original calculada desde timestamps del servidor; nula mientras está abierto; nunca editable por el técnico ni sobrescrita por correcciones. |
| `duracion_ajustada_segundos` | Entero positivo opcional; solo Supervisor, por rectificación excepcional motivada, sin alterar horas originales. Nulo si no hay corrección. |
| `descripcion_trabajo` | Texto obligatorio de hasta 2000 caracteres al terminar; trim, no vacío. |
| `estado_revision` | `ABIERTO`, `PENDIENTE_REVISION`, `OBSERVADO`, `VALIDADO`. |
| `costo_hora_neto` | Decimal CLP de dos decimales; **lo ingresa manualmente el supervisor**, no el técnico. Nullable hasta valoración. |
| `revisado_por`, `revisado_en`, `observacion_revision` | Auditoría de revisión; no lo controla el técnico. |
| `creado_en`, `actualizado_en` | Timestamps de servidor. |

**Reglas del turno:**

1. Solo puede **iniciar** el propio técnico autenticado, activo, rol `TECNICO`, miembro vigente de una Obra `EN_PROCESO` y sin otro turno abierto en ninguna obra. El backend verifica membresía y estado bajo bloqueo.
2. Inicio registra `iniciado_en = timezone.now()` en el servidor. No aceptar hora, fecha, usuario ni duración del body.
3. Solo el propietario puede **finalizar su turno**. Debe enviar `descripcion_trabajo` no vacía. El servidor fija `terminado_en`; la duración es `terminado_en - iniciado_en`, positiva. Fotografías son opcionales. El cierre lleva el turno a `PENDIENTE_REVISION`.
4. Una persona no puede abrir dos turnos simultáneos, ni en obras distintas. La unicidad condicional `UniqueConstraint(tecnico, condition=Q(terminado_en__isnull=True))`, más bloqueo transaccional del usuario técnico, evita la carrera entre dos solicitudes.
5. El supervisor revisa cada turno cerrado, comprueba el trabajo declarado y fija manualmente el `costo_hora_neto` histórico. Puede **VALIDAR** o **OBSERVAR**, dejando motivo y actor. Un turno observado **no cuenta para cierre** hasta subsanarse y validarse nuevamente.
6. El técnico puede **subsanar** un turno `OBSERVADO` añadiendo aclaraciones y/o fotografías opcionales, sin alterar timestamps ni duración. Se registra evento; vuelve a `PENDIENTE_REVISION`. El Supervisor puede corregir excepcionalmente el tiempo **mediante `duracion_ajustada_segundos`**, nunca sobrescribiendo `iniciado_en`, `terminado_en` o `duracion_segundos` originales, y/o rectificar `costo_hora_neto`. Toda rectificación exige motivo y evento con valores antes/después, e invalida una revisión `VALIDADO` anterior: el turno queda `PENDIENTE_REVISION` para nueva validación. El técnico jamás edita duración ni tarifa.
7. Para pasar una Obra a `SUSPENDIDA` no debe existir ningún turno abierto; el servicio 004A `suspender_obra` requiere un guard nuevo en 004B. Para finalizar tampoco puede haber turnos abiertos, pendientes u observados.
8. No se pueden iniciar turnos nuevos si la Obra está PLANIFICADA, SUSPENDIDA, FINALIZADA o CANCELADA. Turnos válidos ya cerrados se conservan al suspender o reasignar al principal.
9. Tiempos excesivos, cierres accidentales o falta de conectividad deben quedar identificados para revisión. No falsificar timestamps con el reloj del dispositivo ni eliminar registros. La corrección excepcional del supervisor deja el dato inicial original en auditoría.

**Costo de mano de obra por turno:** `ROUND_HALF_UP((duracion_ajustada_segundos si existe, de lo contrario duracion_segundos) / 3600 × costo_hora_neto, 0.01)`, calculado con `Decimal`, sin redondear duración anticipadamente a horas completas. Un turno no valorado (`costo_hora_neto = null`) o no validado **no acredita costos completos**. No tomar automáticamente salario, tarifa comercial ni precio presupuestado. Rechazar una tarifa negativa; la exigencia de costo real total positivo se verifica a nivel de Obra, no porque un servicio sea gratuito para el cliente.

### 3.3 `EvidenciaTurno`: texto obligatorio y fotografías opcionales

La evidencia principal es `TurnoObra.descripcion_trabajo`. Las fotografías se representan en `EvidenciaTurno` con FK a turno y Obra, nombre interno de archivo, tipo MIME validado, tamaño, hash opcional y actor/fecha de carga. Puede existir **cero o más fotografías** por turno; no imponer una foto mínima.

- Solo el técnico propietario puede adjuntarlas al finalizar o subsanar el turno, antes de la validación definitiva. El supervisor puede consultarlas como parte de su revisión; Gerencia puede consultarlas si su acceso al historial operativo está autorizado.
- Formatos permitidos: JPEG, PNG y WebP, máximo **5 MiB por fotografía** y hasta **5 fotos por turno** como límites técnicos iniciales revisables; validar formato real del contenido y tamaño, no solo nombre o `Content-Type` declarado.
- Usar almacenamiento **privado**, nombres generados por servidor, permisos autenticados para descargar y sin URLs públicas permanentes. Evitar exposición de rutas internas y metadatos innecesarios. En desarrollo puede usarse almacenamiento privado local; la solución de almacenamiento de producción se define antes del despliegue.
- No exigir fotografía, ubicación GPS, reconocimiento facial ni dispositivo específico. La fotografía es evidencia aportada, **no verificación automática del trabajo**.
- No borrar evidencias para ocultar una ejecución; correcciones o bajas quedan trazadas. La retención y protección de datos deben seguir las políticas del proyecto antes de uso real.

### 3.4 `GastoObra`: materiales y gastos directos en un solo recurso

Para evitar una interfaz dispersa, **materiales y otros gastos se cargan en el mismo apartado «Materiales y gastos»**, con un selector de tipo; en base de datos se mantienen claramente identificados.

| Campo | Definición |
| --- | --- |
| `obra` | FK Obra, `PROTECT`; deriva de URL. |
| `tipo` | `MATERIAL`, `TRANSPORTE`, `ARRIENDO_EQUIPO`, `SERVICIO_EXTERNO`, `OTRO`. |
| `descripcion` | `CharField(500)` obligatorio, trim, no vacío. |
| `unidad` | `CharField(30)` obligatorio: unidad, metro, servicio, viaje, etc. |
| `cantidad` | Decimal positivo con tres decimales. |
| `cantidad_devuelta` | Decimal >=0 y <=cantidad **solo para `MATERIAL`**; para otros tipos siempre 0. |
| `costo_unitario_neto` | Decimal CLP con dos decimales, >=0, **ingresado manualmente por Supervisor**. |
| `fecha_gasto` | Fecha local real, no futura ni anterior al inicio de Obra salvo corrección documentada del Supervisor. |
| `referencia_respaldo` | Texto opcional a parte de trabajo/guía/comprobante, sin crear facturas. |
| `observacion`, `vigente` | Nota breve y baja lógica; no DELETE físico. |
| `registrado_por`, `creado_en`, `actualizado_en` | Auditoría de servidor. |

- **Costo real de material**: `(cantidad - cantidad_devuelta) × costo_unitario_neto`, redondeo por registro. Una devolución reduce cantidad efectivamente consumida; nunca se contabiliza como ingreso o ajuste de stock.
- **Otros gastos directos**: `cantidad × costo_unitario_neto`, sin devoluciones. No registrar como otro gasto algo ya incluido en materiales o mano de obra; el supervisor verifica clasificación.
- Se pueden registrar gastos en `EN_PROCESO` o `SUSPENDIDA` por Supervisor, nunca en PLANIFICADA ni terminales. La corrección no altera datos anteriores sin generar evento.
- `MATERIAL` admite acción específica `devolver` con cantidad positiva, fecha, motivo y actor, verificando acumulado bajo lock; gastos de los otros tipos no admiten esa acción.
- Una devolución total genera subtotal 0 para esa fila, **sin borrar el movimiento**. La compra o despacho sin utilización no se interpreta como costo real de material hasta que se registre consumo.

### 3.5 `CostoObraEvento` y `TurnoObraEvento`

Auditoría append-only separada por sensibilidad de datos:

- **`TurnoObraEvento`**: `INICIO`, `CIERRE`, `OBSERVACION`, `SUBSANACION`, `VALIDACION`, `CORRECCION` y, cuando corresponda, `ADJUNTO`; turno/obra, actor, fecha, motivo y snapshots pertinentes. Incluye timestamps reales y cambios de duración, **pero no se expone al técnico información monetaria**.
- **`CostoObraEvento`**: alta, corrección, devolución, baja lógica, cambio de declaración, validación y decisión de cortesía; Obra, tipo de recurso, ID, actor, momento, motivo, datos anteriores/nuevos. Puede incluir importes; **solo G/S** pueden acceder a detalles económicos.

En ambos casos, sin POST/PATCH/DELETE directo de eventos. Toda mutación y su evento se confirman en una transacción. El histórico no desaparece al cambiar responsable, desasignar participante, registrar devolución o corregir un turno.

### 3.6 `ControlCostosObra`: estado de revisión y vigencia

`OneToOneField` a Obra (`PROTECT`); se crea al primer movimiento o al comenzar la revisión. No admite `costos_completos` administrado desde React.

| Campo | Definición |
| --- | --- |
| `materiales_estado`, `otros_estado` | `PENDIENTE`, `CON_REGISTROS`, `NO_APLICA`. |
| `materiales_justificacion`, `otros_justificacion` | Obligatoria si el rubro se marca `NO_APLICA`. |
| `version_actual` | Número de versión del libro de costos y turnos; administrado por servidor. |
| `version_validada` | Versión validada, nullable. |
| `validado_por`, `validado_en` | Supervisor y timestamp al validar sin errores. |
| `actualizado_en` | Timestamp. |

**Mano de obra no se declara automáticamente `NO_APLICA`:** la regla de este incremento exige al menos **un turno real cerrado y validado**. Todo turno iniciado debe cerrarse y revisarse, o documentar una rectificación excepcional que no falsee el registro original.

Cualquier alta, devolución, corrección, cierre/revisión/subsanación de turno, cambio de participantes que afecte validación, cambio de declaración o decisión de cortesía incrementa `version_actual` e invalida `version_validada`/`validado_por`/`validado_en`. La validación nunca se mantiene vigente después de un cambio económico o probatorio relevante.

### 3.7 `CierreCostosObra`: fotografía del cierre

Registro único por Obra, creado exclusivamente al finalizar; conserva en CLP netos: `materiales_total`, `otros_total`, `mano_obra_total`, `costo_total`, `version_validada`, `validado_por`, `finalizado_por` y `creado_en`. **Ningún monto se recibe en la acción de finalizar.** No es factura, saldo ni costo presupuestado.

### 3.8 `CortesiaObra`: autorización excepcional sin cobro

Registro opcional único por Obra, administrado por Supervisor; conserva `tipo=SIN_COBRO`, **justificación obligatoria**, `autorizado_por`, `autorizado_en` y evento. Debe quedar identificado también si la decisión se registra antes de finalizar o es rectificada **antes** del cierre; una rectificación exige motivo, actor y trazabilidad.

**Efectos estrictamente separados:**

1. **No altera** `Presupuesto.monto_neto`, ítems, aprobación de Gerencia ni estado `APROBADO_CLIENTE`.
2. **No altera** consumos, tiempos, costo horario ni `CierreCostosObra.costo_total`: la empresa **sí tuvo costos**, aunque decida no cobrar.
3. Registra una **decisión comercial de cortesía autorizada por el Supervisor para esa Obra**; la emisión/cancelación de factura, ingreso efectivamente cobrado, descuentos tributarios y conciliación con el presupuesto se implementarán **en Finanzas mediante una especificación posterior**. No se afirma que la constancia por sí sola haya emitido una factura de $0 ni materializado el no cobro.
4. En el resumen económico autorizado puede constar `cortesia_sin_cobro=true` con justificación visible para G/S, sin inventar una cifra de ingreso o margen. Los técnicos no conocen montos ni términos comerciales.
5. No utilizar esta excepción para simular garantía gratuita, presupuestos de neto cero, ni para saltarse la aprobación de Gerencia del presupuesto original.

## 4. Reglas monetarias y cálculos

- Moneda `CLP`, costos **netos** sin IVA; usar `Decimal` y campos PostgreSQL `NUMERIC`, no float.
- En JSON, cantidades y costos se ingresan como **strings decimales** con punto, sin notación científica ni separadores de miles. Se rechazan booleanos, floats, NaN/Infinity, valores negativos y exceso de precisión; la duración de turno **no es una entrada JSON**.
- Gastos: cantidad hasta tres decimales (`max_digits=12`, `decimal_places=3`); costo unitario con dos (`max_digits=15`, `decimal_places=2`). Validar límites superiores finitos y exclusión de NaN, como Comercial.
- Costo por hora con dos decimales, ingresado por Supervisor después del turno. El tiempo se calcula por segundos exactos de los timestamps de servidor, sin convertirlo primero a número de horas redondeado.
- Redondear cada subtotal con `ROUND_HALF_UP` a `Decimal("0.01")`; luego sumar subtotales por rubro y costo total, sin un segundo redondeo de productos agregados.
- `materiales_total`: gastos tipo `MATERIAL` vigentes, netos de devoluciones.
- `otros_total`: gastos de otros tipos vigentes.
- `mano_obra_total`: suma de costos de **turnos terminados y validados**, valorados por Supervisor. Los turnos pendientes/observados no se consideran horas certificadas; **bloquean** completitud para no subestimar costo.
- `costo_total = materiales_total + otros_total + mano_obra_total`, como monto de **costo interno**, nunca como importe a cobrar al cliente.
- La cortesía sin cobro **no cambia esta fórmula**. Ejemplo: materiales $8.000 + mano de obra $20.000 = **costo de empresa $28.000**, incluso si el Supervisor autorizó cobrar $0 al cliente. Esa cifra de $0 es decisión sobre cobro futuro, **no un costo total de $0**.
- Se admiten materiales no utilizados (`NO_APLICA` motivado) y otros costos inexistentes (`NO_APLICA` motivado). Si el costo total termina en cero, **la validación de 004B se rechaza**, aunque exista cortesía; la excepción de servicio sin cobro no es una excepción de costos reales.
- No inferir precios de venta, rentabilidad, sueldo bruto, horas de Presupuesto, IVA, retenciones o tarifas automáticas.

## 5. Completitud verificable antes de finalizar

`validar_costos(obra, supervisor)` comprueba **datos persistidos** en una transacción bloqueada, no un checkbox, flag o total enviado por la app.

Se exige **simultáneamente**:

1. Obra en `EN_PROCESO` (o `SUSPENDIDA` solo para revisión provisional; **finalizar** exige `EN_PROCESO`), con `iniciado_en` y responsable principal activo/elegible.
2. **Cero turnos abiertos**, `PENDIENTE_REVISION` u `OBSERVADO`; toda ejecución iniciada debe haber terminado y quedar revisada o rectificada de manera trazable.
3. Al menos **un turno cerrado, validado, valorado por Supervisor**; técnico y Obra correctos, tiempo real positivo y descripción obligatoria existente.
4. Todos los gastos vigentes tienen tipo, fecha, cantidad y costo válidos. Devoluciones dentro de cantidad consumida; solo `MATERIAL` admite devoluciones.
5. `materiales_estado` y `otros_estado` no están `PENDIENTE`. `CON_REGISTROS` exige registros vigentes del rubro; `NO_APLICA` requiere justificación/actor/fecha, no se infiere por ausencia.
6. **Costo total real positivo**, calculado desde movimientos y turnos validados. Ninguna «gratuidad» altera los registros reales ni puede convertirlos en cero para pasar la validación.
7. No hay rectificaciones pendientes, costos horarios nulos para turnos acreditados ni evidencias de turno incompletas. Las fotografías son opcionales: su ausencia **nunca bloquea** por sí sola.
8. La revisión deja actor/fecha y `version_validada=version_actual`. Si cualquier dato relevante cambia, invalidar validación automáticamente; solo una validación nueva permite finalizar.

La revisión del Supervisor **no es aprobación de Gerencia de cada gasto** ni garantiza por sí sola que el trabajo físico ocurrió. Es un control operativo auditable.

| Caso | Resultado |
| --- | --- |
| Técnico inició turno pero no lo cerró | Bloquear validación y finalización. |
| Técnico cierra sin descripción | Rechazar cierre del turno; continúa abierto hasta completar datos. |
| Técnico cierra con descripción y sin fotos | Permitido; queda pendiente de revisión. |
| Técnico cierra con evidencia y Supervisor observa trabajo | Bloquear validación hasta subsanar y revisar. |
| Se registraron materiales pero falta valorar un turno | Bloquear; falta costo de mano de obra. |
| No se usaron materiales; Supervisor declaró `NO_APLICA` y justificó | Permitido si demás controles se cumplen. |
| Reparación sin cobro, costos empresa $28.000 y evidencia completa | Puede validar/finalizar; costos siguen $28.000. |
| Reparación sin cobro, costo real reportado $0 | Rechazar completitud; no presumir cero costo por gratuidad. |
| Se corrige una devolución después de validar | Invalidar versión; solicitar nueva validación. |
| Obra suspendida | No finalizar; primero reanudar. |

## 6. Transición terminal `finalizar`

**Única transición nueva de estado:** `EN_PROCESO → FINALIZADA`, por `SUPERVISOR_OBRAS`.

**Entrada:** `{"motivo": "Trabajo terminado, turnos y costos revisados"}`. Motivo/resumen obligatorio hasta 2000 caracteres. No admitir `estado`, `finalizado_en`, `costo_total`, `costos_validados`, `turnos_completos`, `monto_cobrado` ni campos administrados por servidor.

En **una sola transacción**:

1. Releer y bloquear `Presupuesto → Obra` como en 004A; autorizar Supervisor desde su rol persistido.
2. Exigir obra `EN_PROCESO`, principal elegible, motivo normalizado y ausencia de turnos abiertos/pending/observados.
3. Comprobar `ControlCostosObra.version_validada == version_actual`, actor/fecha de validación y todas las condiciones del §5, recalculadas desde DB.
4. Obtener los gastos, devoluciones, turnos valorados y decisiones de cortesía persistidos **sin confiar en valores del cliente**.
5. Crear **un** `CierreCostosObra` con fotografía de costos; actualizar `Obra.estado=FINALIZADA`, `finalizado_en=timezone.now()`.
6. Crear **un** `ObraEvento(CAMBIO_ESTADO)` con `EN_PROCESO → FINALIZADA`, actor, motivo y timestamp, **sin importes ni tarifas en el JSON operativo**.
7. Confirmar juntos; cualquier excepción revierte estado, snapshot y evento. Repetir finalización responde 409 y no duplica registros.

No requiere factura, cobro, saldo cero, autorización gerencial adicional, margen objetivo ni aprobación del cliente posterior. **Finalizar no libera el Presupuesto ni activa la cancelación.**

La constraint histórica `obra_evento_transicion_valida` necesita nueva migración **posterior a 0004** que permita solo `EN_PROCESO → FINALIZADA` (además de las transiciones 004A); nunca permitir `PLANIFICADA → FINALIZADA`, `SUSPENDIDA → FINALIZADA` ni estados `CANCELADA` no especificados. Se conservan los CHECK existentes para `finalizado_en`.

## 7. Matriz de autorización 004B

G = Gerencia; AF = Administrativo/Finanzas; S = Supervisor de Obras; T = Técnico. Se conservan los enums reales de `Usuario.Rol`, sin bypass por `is_superuser`.

| Operación | G | AF | S | T |
| --- | --- | --- | --- | --- |
| Ver Obras según 004A (T: principal o participante vigente) | Todas | Proyección mínima | Todas | Solo asignadas |
| Gestionar participantes y responsable principal | No | No | Sí | No |
| Iniciar/cerrar turno propio | No | No | No | **Sí, solo propio y Obra asignada** |
| Subsanar turno propio observado y adjuntar fotografías opcionales | No | No | No | **Sí, propio** |
| Ver turnos/evidencias operativas | Sí | No | Sí | Solo propios; sin tarifas/costos |
| Revisar/observar turnos y registrar costo horario | No | No | Sí | No |
| Alta/corrección/devolución/baja de materiales y otros gastos | No | No | Sí | No |
| Consultar gastos/tarifas y eventos económicos | Sí | No | Sí | No |
| Ver resumen de costos | Sí | Sí, proyección mínima | Sí | No |
| Declarar rubros, validar completitud y finalizar Obra | No | No | Sí | No |
| Autorizar/rectificar cortesía sin cobro, con motivo | Lectura | No | **Sí** | No |
| Modificar costos, horas o participantes en Obra FINALIZADA | No | No | No | No |

**El permiso de T se amplía solamente en recursos propios de turnos/evidencias**. No se autoriza al técnico para POST/PATCH de Obra, reasignación, costes unitarios, validación o estados. En sus listados, contar y paginar *después* de filtrar membresías vigentes. Turnos ajenos y evidencias ajenas responden 404, no se filtran nombres ni existencia.

**No incluir costos, tarifas, importe de cortesía, margen, ítems de Presupuesto ni eventos económicos** en `ObraLecturaSerializer`/`ObraFinanzasSerializer` de 004A, ni en el serializer para T. AF usa un resumen mínimo de costos por rubro y estado, sin importes por técnico, horas individuales, motivaciones ni fotos. El Supervisor es el único autorizador de cortesía, no de modificaciones al Presupuesto comercial.

## 8. Contrato HTTP propuesto

Los endpoints son **futuros: NO existen en el backend actual**. Todos requieren JWT; no PUT ni DELETE físico; IDs enteros estrictos; paginación fija 25 con orden determinista. URL de Obra siempre determina el ámbito del recurso hijo.

| Método / ruta | Actor | Función |
| --- | --- | --- |
| GET/POST `/api/obras/{id}/participantes/` | G/S lee; S crea/reactiva | Consultar y asignar técnicos participantes. |
| POST `/api/obras/{id}/participantes/{participante_id}/desasignar/` | S | Desasignar con motivo, sin borrar historia ni turnos. |
| GET `/api/obras/{id}/participantes/historial/` | G/S | Historial paginado de altas, bajas y reactivaciones de membresía. |
| GET `/api/obras/mis-obras/` | T | Listado de Obras con membresía vigente; sin datos económicos. |
| GET `/api/obras/{id}/turnos/` | G/S todos; T propios | Listar turnos autorizados. |
| POST `/api/obras/{id}/turnos/iniciar/` | T | Crear turno propio abierto; hora servidor. |
| POST `/api/obras/{id}/turnos/{turno_id}/finalizar/` | T propietario | Cerrar turno con descripción obligatoria y fotos opcionales. |
| POST `/api/obras/{id}/turnos/{turno_id}/subsanar/` | T propietario | Aclarar evidencia de turno observado. |
| POST `/api/obras/{id}/turnos/{turno_id}/revisar/` | S | Validar u observar; fijar manualmente costo/hora para validación. |
| POST `/api/obras/{id}/turnos/{turno_id}/corregir/` | S | Rectifica opcionalmente `duracion_ajustada_segundos` y/o `costo_hora_neto`, con motivo; conserva timestamps y duración original, deja revisión pendiente y registra evento. |
| GET `/api/obras/{id}/turnos/{turno_id}/fotos/{foto_id}/` | G/S, T propietario | Descarga autenticada de foto autorizada. |
| GET/POST `/api/obras/{id}/gastos/` | G/S lectura; S crea | Materiales y otros gastos en una sola colección. |
| PATCH `/api/obras/{id}/gastos/{gasto_id}/` | S | Corrección motivada. |
| POST `/api/obras/{id}/gastos/{gasto_id}/devolver/` | S | Solo materiales: devolución motivada. |
| POST `/api/obras/{id}/gastos/{gasto_id}/anular/` | S | Baja lógica, sin DELETE. |
| GET/PATCH `/api/obras/{id}/costos/control/` | G/S lectura; S cambia | Declarar rubros `CON_REGISTROS` o `NO_APLICA` con motivo. |
| POST `/api/obras/{id}/costos/validar/` | S | Validar completitud y versión. |
| GET `/api/obras/{id}/costos/resumen/` | G/AF/S | Totales, con proyección acotada para AF. |
| GET `/api/obras/{id}/costos/historial/` | G/S | Eventos de costo y cortesía. |
| POST `/api/obras/{id}/cortesia-sin-cobro/` | S | Registrar o rectificar decisión excepcional con justificación. |
| POST `/api/obras/{id}/finalizar/` | S | Finalización operativa atómica. |

### 8.1 Contrato incremental de participantes (004B-1)

- `GET /api/obras/{id}/participantes/`: Gerencia/Supervisor, paginado de 25, orden por `id`; incluye membresías actuales e históricas (`activo` y `es_responsable` como campos de solo lectura). Filtro opcional `activo=true|false`, validado estrictamente. No exponer correos, contraseñas ni datos financieros.
- `POST /api/obras/{id}/participantes/`: solo Supervisor, JSON `{ "tecnico": 7, "motivo": "Apoyo a la ejecución" }`. Valida usuario activo rol `TECNICO`, motivo no vacío y Obra no terminal. Un alta nueva devuelve 201; una reactivación auditada devuelve 200; si ya está activo devuelve 409 `sin_cambios`. La Obra se determina por la URL, no por el body.
- `POST /api/obras/{id}/participantes/{participante_id}/desasignar/`: solo Supervisor, JSON `{ "motivo": "Reasignado a otra tarea" }`; devuelve 200 al desactivar. Si ya está inactivo o es el principal actual: 409, sin cambios ni evento. Si el participante no pertenece a esa Obra: 404.
- `GET /api/obras/mis-obras/`: técnico autenticado, muestra exclusivamente las Obras con membresía activa; mantiene la misma proyección operativa de lectura 004A sin datos monetarios. El GET `/api/obras/` y detalle del técnico usan el mismo filtro.
- Todas las nuevas entradas rechazan campos desconocidos o administrados por el servidor. La subruta `GET /api/obras/{id}/participantes/historial/` es exclusiva para G/S, paginada, orden `(creado_en,id)` y con actor, motivo y cambios antes/después; no expone costos ni altera el historial de 004A.
- No habilitar todavía `TurnoObra` ni otras entidades de 004B en este primer PR.

### 8.2 Ejemplos de solicitudes

**Iniciar turno:**

```http
POST /api/obras/42/turnos/iniciar/
Authorization: Bearer <token>
Content-Type: application/json

{}
```

La respuesta incluye `turno_id`, `obra`, `tecnico` autenticado, `iniciado_en` de servidor y `estado_revision=ABIERTO`; no contiene tarifa ni montos.

**Finalizar turno sin fotos** (las fotos no son requisito):

```json
{
  "descripcion_trabajo": "Se revisó el sistema de frío, se ajustaron conexiones y se verificó su funcionamiento."
}
```

Con fotos, aceptar `multipart/form-data`: `descripcion_trabajo` obligatorio más archivos opcionales `fotos[]`, con mismos controles de autorización. **No** recibir `terminado_en` ni `horas` en ningún caso.

**Revisar un turno y valorarlo** (Supervisor):

```json
{
  "decision": "VALIDAR",
  "costo_hora_neto": "8000.00",
  "motivo": "Trabajo y duración contrastados con evidencia aportada"
}
```

Una observación requiere `decision=OBSERVAR`, `motivo` explicativo y no genera costo validado; el costo horario puede informarse después. Validar requiere turno cerrado, descripción y costo hora válido. **La tarifa horaria y la revisión forman parte de 004B-2**; 004B-3 implementa los materiales y otros gastos, no pospone el registro por turno.

**Rectificación excepcional de duración (Supervisor):** `POST .../corregir/` con `{"duracion_ajustada_segundos": 3600, "motivo": "Corrección excepcional respaldada por revisión del trabajo"}`. Se admite `null` para retirar un ajuste previo y volver a la duración original; solo para turno cerrado, nunca para uno abierto. Un cambio real exige motivo y siempre vuelve a `PENDIENTE_REVISION`, exigiendo revalidación. No se aceptan timestamps ni campos de actor del cliente.

**Registrar gasto de material:**

```json
{
  "tipo": "MATERIAL",
  "descripcion": "Tubería de cobre",
  "unidad": "metro",
  "cantidad": "2.500",
  "costo_unitario_neto": "12500.00",
  "fecha_gasto": "2026-11-07"
}
```

**Registrar gasto no material en el mismo apartado:**

```json
{
  "tipo": "TRANSPORTE",
  "descripcion": "Traslado para atención de obra",
  "unidad": "viaje",
  "cantidad": "1.000",
  "costo_unitario_neto": "6500.00",
  "fecha_gasto": "2026-11-07"
}
```

**Autorizar excepcionalmente un servicio sin cobro** (Supervisor):

```json
{
  "justificacion": "Se resolvió una falla menor y se otorgó esta atención como cortesía comercial excepcional."
}
```

El resultado registra autor y fecha, pero **no** borra costos ni cambia el monto del Presupuesto. La aplicación contable/facturación futura queda expresamente pendiente.

### 8.3 Precedencia de errores

- **400:** campos inválidos/desconocidos o server-managed, descripción de turno vacía, costo decimal inválido, fecha/cantidad inválida, devolución en tipo distinto de MATERIAL, archivo inválido, rubro sin justificación.
- **401:** JWT ausente/inválido/expirado.
- **403:** rol sin capacidad para esa acción; no hay bypass por superusuario.
- **404:** Obra/turno/foto/gasto no existente o fuera del queryset autorizado para el usuario.
- **405:** método no habilitado; nunca DELETE físico.
- **409:** estado incompatible, doble turno activo, intentar desasignar técnico con turno abierto, turno ya cerrado, revisión inconsistente, validación obsoleta, finalizar con turnos pendientes/costos incompletos, repetir transición.

Evaluar autenticación → permisos → recurso autorizado → contrato HTTP → invariantes persistidas bajo lock; sin filtrar datos sensibles en errores.

## 9. Concurrencia y orden de bloqueos

Extender el orden 004A sin invertir los bloqueos ya utilizados:
**Presupuesto → Obra → categoría (si aplica) → Usuario técnico (si se valida) → participantes/turnos/gastos/control** cuando se requieran esas filas. Las operaciones que no necesitan una clase omiten su lock. No bloquear un Usuario antes de su Obra; tras leer IDs para localizar la fila, revalidar bajo lock. El inicio de turno requiere verificar que un mismo técnico no tenga otro turno abierto en cualquier Obra; para serializar esa carrera sin invertir el orden sobre Obra, **todos los inicios de turno deben adquirir el bloqueo del Usuario técnico en un orden global definido antes de consultar/crear el turno**, o apoyarse en la unicidad condicional y reintentos controlados. Se debe elegir y probar una estrategia uniforme para evitar interbloqueos con `cambiar_tecnico` y `iniciar_obra`; no mezclar órdenes distintos.

**Decisión técnica para 004B:** mantener primero Presupuesto → Obra como en 004A, usar `UniqueConstraint` parcial sobre turno abierto para seguridad final y capturar únicamente esa colisión conocida como 409; no tomar un lock de usuario antes de la Obra. La relectura del turno y la respuesta al conflicto ocurren dentro del servicio; la DB es autoridad de unicidad global.

Casos a serializar y probar:

1. Dos inicios simultáneos del mismo técnico en la misma Obra o en distintas: exactamente **un turno abierto**.
2. Cerrar dos veces el mismo turno: un cierre, una evidencia y un evento; segundo 409.
3. Cerrar turno vs suspender Obra: suspender solo si ya se cerró el turno; si suspender obtiene lock primero con turno abierto, rechaza sin cambiar estado.
4. Desasignar participante vs iniciar turno: ambos flujos se resuelven con membresía actual bajo lock, sin permisos retenidos por caché.
5. Corregir tiempo/costo o devolver material vs validar/finalizar: modificación invalida versión; cerrar bloquea cambios posteriores.
6. Dos finalizaciones simultáneas: una confirma, otra 409; snapshot y evento terminal únicos.
7. Reasignar principal con turnos históricos: no sobrescribir autor/ejecutor ni costo horario del turno ya validado.
8. Obra se suspende y reanuda: ningún turno nuevo mientras suspendida, turnos validados se preservan.

Toda escritura y su evento son atómicos. Bloquear Obra antes de decidir completitud; ninguna escritura de gasto, turno, validación o cortesía debe saltarse esa regla. La FK única del Presupuesto sigue impidiendo duplicar Obra.

## 10. Integridad de PostgreSQL y migraciones

- **No modificar** migraciones `obras.0001` a `0004`. Crear migraciones 004B nuevas, incrementales y reversibles cuando sea seguro.
- `ObraParticipante`: FK a Obra/Usuario; unicidad de pareja `(obra,tecnico)`; validaciones de activo/rol y pertenencia en servicios, no CHECK con JOIN.
- `TurnoObra`: FK reales, `terminado_en IS NULL OR terminado_en > iniciado_en`, estados de revisión consistentes, `duracion_segundos > 0` al cerrar; `duracion_ajustada_segundos` es null o entero positivo y no altera timestamps originales. Constraint parcial única por técnico donde `terminado_en IS NULL`, incluso entre Obras diferentes. La fila abierta puede tener descripción y costo nulos; el servicio de cierre/revisión los exige cuando corresponda.
- `EvidenciaTurno`: FK, metadatos validados por aplicación; archivo privado y control de acceso. Las DB CHECK no validan contenido binario ni veracidad de imágenes.
- `GastoObra`: tipo permitido, cantidad finita >0, costo unitario finito >=0, `0 <= cantidad_devuelta <= cantidad`, y si tipo !=MATERIAL entonces `cantidad_devuelta=0`; IDs/fechas/actor válidos.
- `ControlCostosObra` y `CierreCostosObra`: unicidad por Obra; versiones no negativas, snapshot costo total igual suma de componentes (misma fila); consistencia con tablas hijas validada por servicio bajo lock.
- `CortesiaObra`: única por Obra, autor y motivo obligatorio/normalizado; **nunca modificar estado ni neto del Presupuesto**.
- La `CheckConstraint` de `ObraEvento` acepta `EN_PROCESO → FINALIZADA` solo con motivo; no habilitar `CANCELADA`, reapertura, ni saltos de estado. `finalizado_en` se administra por servidor.
- No fabricar turnos/materiales históricos, horas o costos para que una Obra antigua «parezca completa». Las obras existentes requieren datos reales antes de finalizar.
- Validaciones de fila bajo PostgreSQL (`IntegrityError`) y de relaciones bajo transacción; no asumir que un CHECK puede consultar otras tablas ni que `full_clean()` reemplaza bloqueos.

## 11. Pruebas y criterios de aceptación

**Obligatorias sobre PostgreSQL real**, con JWT válido y permisos por rol. Conservar la regresión completa existente (**347 pruebas locales al cerrar 004B-1**, crecerá el total) y exigir Backend CI verde en PR.

1. **Compatibilidad:** 004A sin regresiones; Presupuesto usado no anulable; una Obra por Presupuesto; no autorización comercial extraordinaria; migraciones previas intactas.
2. **Participantes:** principal queda asociado, varios técnicos por obra, duplicados rechazados, asignación/desasignación/reactivación auditable, miembro inactivo sin acceso nuevo, antiguo principal con turnos históricos intactos, no remover con turno abierto.
3. **Acceso T:** técnico ve solo sus Obras asignadas, inicia/cierra únicamente turno propio y nunca edita costos/estado; consulta de obra/turno/fotos ajenas 404; roles falsificados/superusuario no hacen bypass.
4. **Turno:** timestamps del servidor, cuerpo de inicio sin horas, único abierto global, duración calculada, cierre exige descripción y **no** foto; validación sin foto permitida; cierre doble rechaza.
5. **Evidencia:** JPEG/PNG/WebP validados, tamaño/número máximo, acceso privado, cero fotos aceptado, subsanación auditada, foto ajena no visible.
6. **Revisión:** Supervisor observa o valida con costo horario manual; técnico no inventa tiempo ni tarifa; OBSERVADO y PENDIENTE_REVISION bloquean cierre, la subsanación requiere nueva revisión.
7. **Costos:** `Decimal` en materiales/gastos/tarifas, round HALF_UP, devoluciones parciales/totales, monto real positivo, cero imputable solo si se justifica conforme a la política; rechazados float/NaN/booleanos y fechas inválidas.
8. **Rubros:** material NO_APLICA con justificación, otros NO_APLICA con motivo, mano de obra acreditada con al menos un turno validado; no asumir que falta de registros significa cero verificado.
9. **Gratuidad:** Supervisor registra justificación/actor/fecha, Gerencia puede consultar, técnico no ve montos; **costos permanecen >0 y sin alterarse**, Presupuesto aprobado intacto; no facturar ni marcar cobro real desde 004B.
10. **Validación:** no basta monto positivo, exige turnos cerrados/validados, gastos verificados, justificación rubros; foto opcional; versión invalidada con cualquier cambio relevante; revalidación necesaria.
11. **Finalización:** `EN_PROCESO` y principal elegible, sin turnos abiertos, versión actual, costo consolidado, motivo, snapshot y evento únicos; rollback y segunda finalización 409; SUSPENDIDA rechazada.
12. **Regresión de suspensión:** un turno abierto bloquea suspender, cierre previo permite; no crear turno si obra no está en proceso.
13. **Concurrencia:** doble inicio global, doble cierre, desasignación vs inicio, suspensión vs cierre, corrección/validación vs finalizar, doble finalización; pruebas con conexiones reales y bloqueo observable.
14. **HTTP:** 400/401/403/404/405/409, rutas hijas acotadas a Obra, serializer estricto, no DELETE, paginación, sin N+1 y sin filtración de costos en ficha 004A/T.
15. **Migraciones:** base vacía y base con datos 004A, `check`, `makemigrations --check --dry-run`, `migrate --noinput`, suite total y CI.

### 11.1 Verificación previa al merge

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py migrate --noinput
python manage.py test
```

No declarar 004B implementada hasta que modelos, API, control de turnos, evidencia, finalización y tests estén integrados y CI aprobado.

## 12. Entregas de implementación sugeridas

1. **004B-1 — Modelos y participantes (INTEGRADO):** `ObraParticipante`, eventos de membresía, migración/backfill del principal histórico, sincronización del principal, API de asignación/desasignación, permisos de T, pruebas relacionales y acceso por membresía. PR #9 fusionado en `main`; 347 pruebas locales reportadas y Backend CI aprobado.
2. **004B-2 — Turnos/evidencia (SIGUIENTE):** inicio/cierre por Obra, timestamps servidor, descripción obligatoria, fotos opcionales privadas, revisión del Supervisor **con costo horario manual**, subsanaciones, correcciones excepcionales auditadas y concurrencia de turnos. Activar los guards de turno abierto en suspensión, reasignación y desasignación. Sin gastos ni finalización de Obra.
3. **004B-3 — Materiales y gastos:** un recurso clasificado, valorización manual, devoluciones, correcciones, historial de costos.
4. **004B-4 — Completitud/cortesía:** control de rubros, versionado de validación, decisión excepcional sin cobro sin manipular costos ni Presupuesto.
5. **004B-5 — Finalización:** guard, snapshot, migración de evento terminal, regresión completa, Backend CI, PR. No habilitar finalización prematuramente.

Cada entrega debe contener código y tests coherentes; no activar endpoints terminales antes de que **todo** el guard de costos esté desarrollado.

## 13. Aspectos técnicos a verificar durante implementación

Estos puntos **no reabren B1–B8**; se resuelven mediante pruebas e implementación sin inventar aprobaciones nuevas:

- Definir el almacenamiento privado de evidencias en el entorno de despliegue y su política de retención, manteniendo fotos opcionales.
- La corrección excepcional del tiempo utiliza `duracion_ajustada_segundos` con auditoría, sin alterar `iniciado_en`, `terminado_en` ni la duración original; siempre requiere revalidación por Supervisor.
- Verificar el efecto de reasignar principal y desasignar miembros con turnos abiertos para no perder acceso o crear horas huérfanas.
- Elegir las reglas exactas de redondeo de duración en UI sin cambiar el cálculo económico sobre segundos reales.
- Ajustar SPEC-004 en la parte de roles/asignaciones: sigue habiendo un responsable principal, **pero también participantes**; T conserva prohibición de editar Obra y obtiene permiso limitado para sus turnos/evidencias.
- El tratamiento fiscal/contable de la cortesía se definirá en la SPEC de Finanzas. No afirmar «ingreso real $0» desde una decisión operativa sin documentación de cobro.

## 14. Fuentes, precedencia y relación entre especificaciones

1. [SPEC-004, `main`](https://github.com/LFP2002/Proyecto-FYAG/blob/main/specs/004-gestion-obras.md): D1–D9, máquina de estados y guard comercial. **004B extiende técnicos participantes/horas y habilita solamente FINALIZADA**.
2. [SPEC-003B, `main`](https://github.com/LFP2002/Proyecto-FYAG/blob/main/specs/003b-gestion-presupuestos.md): precio comercial aprobado, inmutabilidad y bloqueo de anulación; **un gasto interno no cambia el precio del Presupuesto**.
3. [Backend de Obras integrado, `main`](https://github.com/LFP2002/Proyecto-FYAG/tree/main/backend/apps/obras): 004A y 004B-1 (participantes) integrados; migraciones `obras.0001`–`0006` vigentes, modelo `Obra.tecnico_responsable`, membresías, permisos y filtros. **No modificar migraciones históricas**.
4. Decisiones B1–B8: respuestas expresas del responsable del proyecto en esta conversación (7-11-2026); se presentan como decisiones del equipo académico, no como términos acordados externamente con FYAG.

**Precedencia de implementación:** preservar integridad de 004A; modificar sus servicios/permisos únicamente donde B4–B6 lo requieren y con nuevas pruebas. Si una decisión futura amplía el cobro/contabilidad, crear una SPEC financiera; no convertir una cortesía en costo empresa cero ni en anulación retroactiva de presupuesto.
