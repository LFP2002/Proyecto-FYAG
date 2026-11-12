# SPEC-007 — Finanzas: facturación documental, pagos y cobranzas (backend)

> **Estado vigente (11-11-2026): IMPLEMENTADA E INTEGRADA EN `main` (007A y 007B).** [PR #22](https://github.com/LFP2002/Proyecto-FYAG/pull/22) incorporó documentos externos y cortesías; [PR #23](https://github.com/LFP2002/Proyecto-FYAG/pull/23) agregó pagos, idempotencia y cobranzas. [PR #21](https://github.com/LFP2002/Proyecto-FYAG/pull/21) fue únicamente la especificación inicial. Las instrucciones «no implementada» y «no iniciar 007B» son antecedentes históricos. El sistema **registra** documentos fiscales emitidos fuera de FYAG y pagos confirmados fuera de la aplicación; **no emite DTE, cobra dinero, realiza transferencias ni concilia con bancos o SII**. Para validación: `backend/apps/finanzas/` y sus pruebas; la integración React de finanzas es un alcance distinto.

**Estado:** especificada para implementación; **no implementada**. Fecha: 10 de noviembre de 2026.

**Proyecto:** FYAG, pyme chilena de servicios de frío y agroindustria. **Rama documental:** `docs/spec-007-finanzas-cobranzas`. **Implementación prevista:** `feature/backend-007a-facturacion` y luego `feature/backend-007b-pagos-cobranzas`. Dos incrementos acumulativos: **007A primero, 007B después**. En cada etapa se exige revisión, pruebas, PR y Backend CI antes de pasar a la siguiente.

## 1. Contexto confirmado y precedencia

- `apps.comercial.Presupuesto` conserva un precio comercial **neto en CLP** calculado desde ítems inmutables después de salir de BORRADOR. Solo `APROBADO_CLIENTE` habilita la creación de Obra; el Presupuesto asociado no se puede anular.
- `apps.obras.Obra` es **OneToOne** respecto del Presupuesto. El estado `FINALIZADA` exige revisión, validación económica y un único `CierreCostosObra` histórico que almacena **costos internos netos**, no precio de venta.
- `CortesiaObra` registra decisión **SIN_COBRO** del Supervisor sin cambiar el precio aprobado ni los costos; no constituye por sí misma una factura, nota de crédito, ingreso ni pago.
- `apps.finanzas` está creado como esqueleto, sin modelos ni rutas operativas.
- `apps.usuarios` mantiene JWT, CSRF, actividad y autorización por rol persistido en PostgreSQL, incluyendo revocación de sesiones de SPEC-006.
- El frontend existente, MongoDB, alertas, reportes y otros scripts de colaboradores quedan **fuera** de esta SPEC.

**Precedencia:** SPEC-002A/002B/006 (identidad), 003A/003B (clientes/presupuestos), 004A/004B (obras/costos/cortesías). Ningún contrato de Finanzas puede modificar esos modelos de dominio, saltar la aprobación de Gerencia o convertir costos en ingresos.

Las reglas de unicidad y procesos propuestas en este documento son **decisiones técnicas de alcance del MVP**, no requisitos tributarios confirmados por la empresa ni sustitutos de un criterio contable externo.

## 2. Objetivo, límites tributarios y etapas

Registrar en PostgreSQL documentos comerciales **ya emitidos por un sistema autorizado externo**, registrar pagos comprobados y calcular el saldo de cobranza de cada documento.

**FYAG NO emite DTE, factura electrónica, boleta, guía ni nota de crédito ante el SII.** No firma, timbra, envía, consulta, certifica ni valida documentos tributarios electrónicos; tampoco genera PDFs que aparenten ser DTE válidos. Los folios y montos se registran contra **respaldo externo existente** y quedan identificados como *registro administrativo*. Los funcionarios deben verificar el respaldo fuera de FYAG. Nunca declarar que un documento se emitió al guardarlo en este sistema.

- **007A: Facturación documental.** Registro, consulta, reversión administrativa respaldada, re-registro correcto y registro de cierre sin cobro cuando existe cortesía. No crea pagos ni saldos exigibles distintos de la ausencia de pago.
- **007B: Pagos y cobranza.** Registrar comprobantes de pago real, correcciones por anulación respaldada, saldos, vencimientos y listado de cobranza; deriva estados sin inventar ingresos.

Sin integración bancaria ni pasarela de pago. La creación de un registro no mueve dinero. Cualquier ajuste tributario real se hace **fuera** del sistema y se registra solo cuando existe evidencia.

## 3. Roles y visibilidad

| Capacidad | GERENCIA (G) | ADMINISTRATIVO_FINANZAS (AF) | SUPERVISOR_OBRAS (S) | TECNICO (T) |
| --- | --- | --- | --- | --- |
| Listar/ver registros de facturación, pagos y cobranza | Sí | Sí | No | No |
| Registrar/revertir documento, cierre sin cobro | No | Sí | No | No |
| Registrar/anular administrativamente un pago | No | Sí | No | No |
| Leer eventos financieros | Sí | Sí | No | No |
| Consultar referencias de Obra/Presupuesto autorizadas | Según permisos existentes | Solo proyección financiera de esta API | Solo dominio de Obras | Solo Obras asignadas, sin dinero |

- Releer `is_active` y `rol` desde PostgreSQL; ignorar `is_staff`, `is_superuser`, grupos y claims como elevación de permisos. Sin endpoints públicos, sin bypass de superusuario ni permisos por visibilidad frontend.
- G consulta, audita y supervisa, **no escribe** la contabilidad. AF registra operaciones y responde por el respaldo externo. S no registra cobranzas, T no accede a importes comerciales.
- No incluir costos individuales, tarifas horarias, evidencias privadas, descripciones operativas ni datos completos de Cliente/Usuario en serializers financieros.
- El rol AF puede consultar en esta API únicamente los campos de origen necesarios: ID/código de Obra y Presupuesto, identificación de Cliente, precio neto aprobado, finalización, referencia de cortesía. El acceso no autoriza a consultar otros detalles operativos protegidos.

## 4. Reglas monetarias comunes

- Moneda fija `CLP`. PostgreSQL `NUMERIC` y Python `Decimal`; todos los importes JSON **strings** no negativos de máximo **dos decimales**; pagos estrictamente positivos. No `float`, boolean, NaN/Infinity, exponentes, separadores de miles ni coma decimal. Rechazar exceso de precisión o magnitud sin redondear entradas silenciosamente.
- Utilizar `DecimalField(max_digits=38, decimal_places=2)` para totales y sumas financieras. Validar rango y overflow (incluida suma de neto e impuesto) antes de persistir. Responder importes siempre como strings con dos decimales.
- Un registro externo debe conservar `monto_neto`, `monto_impuesto` y `monto_total` **tal como constan en el documento**, comprobando `total = neto + impuesto`. No calcular IVA imponiendo una tasa fija, no asumir tipo de operación ni generar un tributo a partir del Presupuesto.
- El `monto_neto` del documento **vigente** debe igualar exactamente `Presupuesto.monto_neto` aprobado. Una diferencia, descuentos, pagos anticipados, facturación parcial, intereses, propinas o gastos extra requieren procedimiento distinto fuera de este MVP: registrar conflicto, **no** alterar el Presupuesto para hacer coincidir datos.
- Para documento marcado `FACTURA_EXENTA`, `monto_impuesto = 0.00`; `FACTURA_AFECTA` exige impuesto positivo documentado. Estas etiquetas son categorías internas de registro; no sustituyen la verificación tributaria real.
- `CierreCostosObra.costo_total` jamás se usa para inferir monto a facturar, IVA, recaudación o saldo. La diferencia entre ingreso y costo/rentabilidad queda para una SPEC posterior; nunca equiparar *emitido* con *pagado*.

## 5. 007A — Facturación documental

### 5.1 Política de elegibilidad y cardinalidad

- Solo se registra documento externo a una `Obra.estado == FINALIZADA` con Presupuesto de origen `APROBADO_CLIENTE` y `CierreCostosObra` presente. **Finalizar Obra sigue siendo independiente de facturar**, como en SPEC-004B.
- En este MVP existe **a lo sumo un documento vigente por Obra**. Es válido conservar múltiples documentos históricos **revertidos**, y registrar uno nuevo únicamente después de una reversión externa acreditada; se impide la doble facturación activa.
- El mismo folio externo, en el mismo `tipo_documento` y para el único emisor FYAG de este MVP, **no** puede usarse dos veces, incluso si el registro original fue revertido.
- Si la Obra tiene `CortesiaObra(tipo=SIN_COBRO)`, bloquear facturación con `409 cortesia_sin_cobro`. La decisión de cortesía no hace cero el Presupuesto ni el costo de la empresa.
- Un Cliente puede estar inactivo hoy: si su Presupuesto se aprobó y su Obra se finalizó correctamente, conservar la elegibilidad documental sin alterar el Cliente histórico. Se exige referencia de respaldo del documento emitido y cotejo humano de receptor/folio.

### 5.2 Modelos nuevos

**`DocumentoCobro`** (nombre de modelo sugerido; adoptar uno único coherente en código):
- PK BigAutoField; FK `obra` `PROTECT`; FK `presupuesto` **derivada** de Obra o propiedad, no una segunda FK editable; `cliente` **derivado** del Presupuesto, no una relación asignable por cliente.
- `tipo_documento`: `FACTURA_AFECTA` / `FACTURA_EXENTA`; `folio_externo` cadena de dígitos ASCII normalizados sin espacios ni ceros antepuestos artificialmente por FYAG (conservar folio exacto del documento externo); unicidad conjunta de tipo + folio.
- `fecha_emision`, `fecha_vencimiento` (fechas civiles ISO); `fecha_vencimiento >= fecha_emision` y `fecha_emision` no futura según zona `America/Santiago`. El comprobante puede haberse emitido **antes** del registro en FYAG; nunca declarar que lo emitimos al guardar.
- `monto_neto`, `monto_impuesto`, `monto_total` numéricos Decimal; `monto_neto` exacto igual al Presupuesto aprobado, `monto_total = monto_neto + monto_impuesto`; `monto_total > 0`.
- `referencia_respaldo` obligatoria, texto normalizado hasta 500, sin URL pública automática ni descarga remota; puede ser folio/verificador/ubicación documental interna.
- `estado` `VIGENTE` o `REVERTIDO` manejado solo por servicios; `registrado_por`, `registrado_en` de servidor; `revertido_por`, `revertido_en`, `motivo_reversion`, `referencia_rectificacion_externa` nulos hasta reversión.
- Constraints DB de valores válidos, unicidad folio, no negativos y suma, estado/metadatos coherentes, **UniqueConstraint condicional de Obra con estado VIGENTE**.
- Datos esenciales inmutables luego de crear: no PATCH libre ni DELETE. Se rechaza `PUT`. Reversión es acción específica auditable y no cambia la identidad ni el importe de un documento original.

**`CierreSinCobro`**:
- `obra` OneToOne PROTECT, `cortesia` FK PROTECT o referencia al modelo con comprobación de la misma Obra, `registrado_por` AF, `registrado_en` servidor y `motivo_registro` no vacío.
- Solo si Obra FINALIZADA y cortesía vigente autorizada por Supervisor; sin documentos vigentes ni revertidos para esa Obra, para evitar encubrir operaciones fiscales preexistentes.
- No guarda monto cero ficticio ni modifica `CortesiaObra`, `Presupuesto`, `CierreCostosObra`. Es un **cierre administrativo sin cobro**, no DTE, reverso ni comprobante tributario. No admite DELETE ni modificación; no puede registrarse factura después.
- La lectura administrativa de Obras puede indicar que existe cierre sin cobro mediante una proyección financiera, nunca alterar serializers operativos T/S ni permitir a AF consulta de detalles de cortesía más allá de la decisión.

**`FinanzasEvento`**:
- Historial append-only con FK de documento o cierre sin cobro (según evento; exactamente una referencia pertinente), `tipo` (`DOCUMENTO_REGISTRADO`, `DOCUMENTO_REVERTIDO`, `SIN_COBRO_REGISTRADO`; 007B agregará pago/ajuste), `actor` FK PROTECT, `motivo`, snapshot anterior/nuevo restringido, timestamp de servidor.
- No escribir credenciales, tokens, datos bancarios completos ni datos privados operativos; no exponer PUT/PATCH/DELETE sobre eventos. Toda mutación y evento en una transacción.

### 5.3 Endpoints 007A

Base `/api/finanzas/` (incluir en `config/urls.py` sin cambiar rutas actuales):

| Método | Ruta | Rol | Éxito |
| --- | --- | --- | --- |
| GET | `documentos/` | G/AF | 200 lista paginada |
| POST | `documentos/` | AF | 201 |
| GET | `documentos/{id}/` | G/AF | 200 |
| POST | `documentos/{id}/revertir/` | AF | 200 |
| GET | `documentos/{id}/historial/` | G/AF | 200 |
| GET | `obras-elegibles/` | AF | 200 |
| POST | `obras/{obra_id}/registrar-sin-cobro/` | AF | 201 |
| GET | `obras/{obra_id}/estado-financiero/` | G/AF | 200 |

**POST documentos**: `obra` entero positivo, `tipo_documento`, `folio_externo`, `fecha_emision`, `fecha_vencimiento`, `monto_neto`, `monto_impuesto`, `monto_total`, `referencia_respaldo`. No aceptar `presupuesto`, `cliente`, `estado`, `actor`, fechas de servidor ni campos desconocidos. Se exige coincidencia con la Obra real bajo lock. Respuesta con IDs/códigos de origen, identificador del documento, fechas, montos y `estado`, sin datos comerciales u operativos excesivos.

**POST revertir**: `motivo` obligatorio y `referencia_rectificacion_externa` obligatoria (documento o comprobación externa de corrección, **no** creada por FYAG). Solo `VIGENTE`. Si existen pagos activos (007B), rechazar `409 pagos_pendientes_de_resolver`; no borrar ni compensar dinero por reversión de documento. Una segunda reversión retorna 409, sin evento duplicado. La reversión administrativa **no** anula legalmente el DTE: debe existir rectificación externa comprobable.

**GET listado**: paginado fijo 25 y orden determinista `(-registrado_en,-id)`; filtros estrictos `estado`, `tipo_documento`, `obra`, `cliente`, `fecha_emision_desde`, `fecha_emision_hasta`, `page`. `obras-elegibles` lista finalizadas sin cierre sin cobro ni documento vigente, sin cortesía, paginada de forma equivalente; siempre filtrar en servidor.

**GET estado financiero**: si no hay documento ni cierre sin cobro devuelve `PENDIENTE_FACTURACION`, **no ingreso cero**; si hay cortesía sin cierre financiero devuelve `PENDIENTE_REGISTRO_SIN_COBRO`; si hay cierre sin cobro devuelve `SIN_COBRO`; si hay documento vigente devuelve `DOCUMENTADO` (en 007B incluirá saldo derivado). Un documento revertido sin reemplazo retorna `PENDIENTE_FACTURACION` con historial conservado. La respuesta jamás altera Obra.

### 5.4 Concurrencia 007A

- Usar `transaction.atomic`, orden de bloqueos **Presupuesto → Obra → documento/cierre → eventos** para toda escritura relacionada con Obra. No bloquear `Usuario` antes de Presupuesto; verificar actor usando rol persistido. No adquirir locks de Obras a través de las rutas de Usuarios 006.
- La lectura preliminar de `obra.presupuesto_id` no habilita escribir sin releer/bloquear la fila raíz; replicar la pauta de `apps.obras.services`.
- La BD debe impedir duplicar documento vigente por Obra o folio externo incluso en dos conexiones concurrentes. Controlar `IntegrityError` esperado para devolver `409` estable, sin capturar indiscriminadamente errores de integridad.
- Revertir y registrar uno nuevo deben serializarse por Obra. No sobrescribir documentos reversados ni modificar `CierreCostosObra`.

## 6. 007B — Pagos y seguimiento de cobranza

**Dependencia obligatoria:** 007A integrado en `main` con Backend CI verde. 007B no reescribe migraciones de 007A ni cambia política de importes o folios.

### 6.1 Modelos de pago

**`PagoDocumento`**:
- PK, FK `documento` PROTECT, `monto` `Decimal(38,2) > 0`, `fecha_pago` ISO civil no futura y no anterior a la fecha de emisión (anticipos no implementados), `medio` enum `TRANSFERENCIA` / `EFECTIVO` / `TARJETA` / `OTRO`, `referencia_respaldo` texto obligatorio, `observacion` opcional y `registrado_por`/timestamp de servidor.
- `activo` booleano de validez del registro (default true); `anulado_por`, `anulado_en`, `motivo_anulacion` y `referencia_reversion_externa` nulos mientras activo. Solo cambiar a inactivo mediante acción y justificación; el registro original y los importes históricos son inmutables. No hay DELETE.
- Guardar `clave_idempotencia` UUID obligatorio por pago, único en DB junto con huella de solicitud. Misma clave y mismo payload devuelve la respuesta original sin doble pago ni evento; misma clave con payload distinto devuelve 409. Cada operación de pago distinta usa una clave nueva. No basarse en doble clic del navegador.
- Se debe exigir respaldo verificable (referencia bancaria, recibo interno u otro soporte autorizado); `referencia_respaldo` no implica acceso a un banco. No guardar número de tarjeta, contraseña bancaria, CVV ni cuentas completas.

**`FinanzasEvento`** agrega tipos `PAGO_REGISTRADO` y `PAGO_ANULADO`, referencia FK al pago, actor, motivo, snapshot restringido, servidor. Cambios y eventos atómicos. Una anulación de pago no transfiere ni devuelve fondos físicamente: exigir `motivo` y `referencia_reversion_externa` antes de invalidar administrativamente el registro.

### 6.2 Cálculos de cobranza

Para `DocumentoCobro.estado == VIGENTE`:
- `abonado = SUM(PagoDocumento.monto WHERE activo=True)`, utilizando `Decimal` en PostgreSQL con precisión suficiente; ausencia de pagos significa `0.00` **solo cuando existe documento vigente**.
- `saldo = documento.monto_total - abonado`, invariante `0 <= abonado <= monto_total` comprobada **transaccionalmente** bajo lock del documento al crear/anular pago y con constraints DB pertinentes. No guardar saldo como campo editable ni usar `CierreCostosObra`.
- Estado **derivado**: `PAGADA` cuando saldo 0; `VENCIDA` cuando saldo positivo y fecha_vencimiento anterior a fecha local del servidor; `PARCIAL` cuando abonado positivo y saldo positivo aún no vencido; `PENDIENTE` cuando ningún abono y no vencida.
- Documentos revertidos no forman parte de la cartera vigente ni permiten pago, pero su historial sigue consultable. Los cierres sin cobro nunca crean pago ni saldo de cobranza.
- La vista de cartera incluye solo documentos vigentes; filtros por estado calculado, cliente, vencimiento, obra y fechas; paginación y conteo después de filtros, orden estable. La sumatoria debe evitar duplicación por joins; incluir totales del conjunto filtrado solo si pueden calcularse de forma eficiente y sin redondeos flotantes.
- No marcar `PAGADA` por emisión documental o validación de costos; solo por abonos activos suficientes. Los plazos son fecha de vencimiento **del documento externo**, no estimaciones del frontend.

### 6.3 Endpoints 007B

| Método | Ruta | Rol | Éxito |
| --- | --- | --- | --- |
| GET | `documentos/{id}/pagos/` | G/AF | 200 paginada |
| POST | `documentos/{id}/pagos/` | AF | 201 (o 200 repetición idempotente) |
| POST | `documentos/{id}/pagos/{pago_id}/anular/` | AF | 200 |
| GET | `documentos/{id}/pagos/{pago_id}/` | G/AF | 200 |
| GET | `documentos/{id}/pagos/historial/` | G/AF | 200 |
| GET | `cobranzas/` | G/AF | 200 paginada |
| GET | `cobranzas/resumen/` | G/AF | 200, agregados en CLP |
| GET | `documentos/{id}/` | G/AF | 200, ahora con cobranza calculada |

**POST pago**: `monto`, `fecha_pago`, `medio`, `referencia_respaldo`, `observacion` opcional; enviar `Idempotency-Key` UUID obligatorio en header. Exige documento vigente, no sin cobro, monto <= saldo **recalculado bajo bloqueo**, fecha válida. Pagos simultáneos no pueden sobrepasar total. El API fija actor y timestamps; no aceptar `activo` ni `saldo` del body.

**POST anular**: `motivo` y `referencia_reversion_externa` obligatorios; solo pago activo del documento de la URL. Segunda anulación 409, sin duplicar evento. No borrar pago histórico, alterar factura ni simular reembolso bancario.

**GET cobranzas/resumen**: conteos y montos de documentos vigentes: `monto_documentado_total`, `abonado_total`, `saldo_total`, `saldo_vencido`; no sumar documentos históricos revertidos ni cierres sin cobro como ingresos.

### 6.4 Concurrencia 007B

En escrituras: **Presupuesto → Obra → DocumentoCobro → PagoDocumento** (si aplica), y evento después. Recalcular saldos dentro de la transacción. Bloquear primero el mismo documento raíz para alta/anulación de pagos y reversión del documento; dos abonos o anulación versus alta/reversión jamás deben producir saldo negativo, documento revertido con pago activo ni evento inconsistente.

`Idempotency-Key` protege también contra reintentos tras timeout de respuesta. Implementar unicidad DB por clave y comparación del fingerprint de payload canónico; no ejecutar otra operación ni crear evento al repetir exactamente la clave.

## 7. Errores, validación y formato

- 200 GET/acciones exitosas, 201 creación, 401 falta/sesión inválida, 403 rol sin permiso, 404 PK inexistente o recurso ajeno al documento de la URL, 405 PUT/PATCH/DELETE no implementados, 400 entradas o filtros mal formados, 409 condiciones de negocio/duplicidad/concurrencia.
- Respuestas 409 con `code` estable: `obra_no_finalizada`, `cortesia_sin_cobro`, `documento_duplicado`, `documento_revertido`, `documento_ya_revertido`, `respaldo_reversion_requerido` (400 si campo faltante), `pagos_pendientes_de_resolver`, `sin_cobro_ya_registrado`, `monto_excede_saldo`, `pago_ya_anulado`, `idempotencia_conflictiva` y `monto_no_coincide` (400 para entrada inválida, 409 para inconsistencia con referencia persistida). Consistencia de elección y pruebas son obligatorias.
- Identificadores de ruta enteros positivos; rechazar bool y valores fuera de rango. Filtros desconocidos, repetidos, página no positiva y enum inválido → 400. Paginación 25, orden estable por (fecha,id), sin N+1 ni consulta financiera no autorizada.
- Fecha de vencimiento/emisión/pago nunca se deriva de hora enviada por el cliente; fecha civil del documento validada respecto de `timezone.localdate()` en Santiago. No inventar zonas horarias en payload.
- No filtrar información tributaria, referencia de pago, nombres de otros clientes ni costos a S/T mediante error, serializer, logs o OPTIONS.
- Actores vienen exclusivamente de `request.user`, revalidados desde BD; estados solo por servicios. Prohibir edición administrativa CRUD de documentos, pagos/eventos en Django Admin si eludiría controles de integridad; acciones internas con servicio transaccional común.

## 8. Arquitectura y migraciones

- Implementar en `backend/apps/finanzas/`: `models.py`, `services_documentos.py`, `serializers_documentos.py`, `permissions.py`, `views_documentos.py`, `urls.py` y `tests/`. 007B añade servicios, serializers, vistas y tests de pagos/cobranzas.
- Migraciones nuevas e incrementales de `finanzas`, con constraints e índices en PostgreSQL: documento por Obra/estado, folio/tipo, fechas/vencimiento, pagos por documento/actividad, idempotencia y eventos. No reescribir migraciones de `usuarios`, `comercial` ni `obras`.
- Registrar `/api/finanzas/` sin modificar `/api/auth/`, `/api/usuarios/`, `/api/clientes/`, `/api/presupuestos/` ni `/api/obras/`. Presupuesto, Obra y costos originales son de solo lectura desde Finanzas.
- Evitar llamar dentro de transacciones financieras a acciones de Obras que alteren estado. Consultar únicamente datos mínimos y usar un orden único de bloqueos compatible con 004A/004B.
- No MongoDB, colas, facturación electrónica real, proveedores de pago, almacenamiento de archivos, front, dashboards ni reportes exportables.

## 9. Plan mínimo de pruebas con PostgreSQL real

### 007A

1. AF registra un documento externo sobre Obra FINALIZADA/cierre de costos validado y Presupuesto APROBADO_CLIENTE; G puede leer, no escribir. Resto 403 incluso con flags de superusuario.
2. Obra PLANIFICADA/EN_PROCESO/SUSPENDIDA, sin cierre, origen no aprobado o PK inválida: rechazos consistentes, cero escritura/eventos.
3. Presupuesto neto calculado de ítems de varias líneas: coincide exactamente con `monto_neto` de documento; no se confunde con costo de cierre ni total con impuesto. Decimales string, límites de precisión y overflow.
4. Factura afecta/exenta, fecha emisión/vencimiento, folio externo único y respaldo obligatorio; no se genera DTE ni se calcula impuesto supuesto.
5. Dos registros concurrentes para misma Obra y dos para mismo folio: uno solo vigente; eventos correctos y rechazo 409 del otro.
6. Cortesía SIN_COBRO bloquea documento. AF registra cierre sin cobro sobre Obra finalizada; no ingreso ni pago ficticio, costos conservados. Doble registro rechazado.
7. Reversión exige evidencia externa, conserva documento original e historial; no permite segunda reversión; permite documento nuevo con folio distinto después; nunca modifica Presupuesto/Obra.
8. Clientes inactivos históricos elegibles; serializadores no exponen detalles de turnos/costos ni superuser bypass.
9. Paginación, filtros, errores, campos desconocidos, URLs, migración sobre PostgreSQL limpio/con datos anteriores, 550 pruebas previas sin regresión (conteo puede variar).

### 007B

1. Uno o varios pagos parciales y total; `saldo` exacto; estados PENDIENTE/PARCIAL/PAGADA/VENCIDA con reloj local del servidor.
2. Sobrepago, valor cero/negativo, tipo erróneo, importe en número JSON, fecha futura/anterior a emisión, sin respaldo: rechazo seguro.
3. `Idempotency-Key`: repetición idéntica no duplica pago/evento; payload distinto misma clave 409; simultaneidad de dos abonos mantiene `abonado <= total`.
4. Dos pagos competidores, reversión de documento contra pago y anulación contra alta, con conexiones PostgreSQL independientes (`TransactionTestCase`).
5. Reversión de documento con pago activo bloqueada; anulación de pago exige soporte externo, no simula reembolso, conserva historial; doble anulación bloqueada.
6. Documentos revertidos/cierre SIN_COBRO sin saldo de cobranza; documentos sin pago tienen saldo completo; nada convierte costos a ingresos.
7. Cartera: filtros, orden y agregados exactos sin duplicados, paginación después del filtro y permisos por cuatro roles.
8. Pruebas de compatibilidad con JWT revocado, usuario inactivo, permisos de G/AF/S/T y base histórica de Presupuestos/Obras.

**Validación obligatoria en cada incremento:**

```bash
docker compose exec -T backend python manage.py check
docker compose exec -T backend python manage.py makemigrations --check --dry-run
docker compose exec -T backend python manage.py migrate --noinput
docker compose exec -T backend python manage.py test --noinput
```

Además, migraciones reproducibles desde cero y con registros existentes, carreras reales sin `sleep`, revisión de cambios `git diff --check`, Backend CI verde y pruebas API con JWT/roles. Declarar número exacto de pruebas ejecutadas; no inventar datos ni usuarios nuevos en migraciones.

## 10. Exclusiones y extensiones futuras

No incluye: emisión fiscal/electrónica SII, conciliación bancaria automática, recaudación por pasarelas, anticipos, cuotas con interés, facturación parcial o múltiple simultánea por Obra, reajustes comerciales, ajustes/bonificaciones tributarias desde FYAG, nómina, compras, inventario, garantía comercial, cancelación o reapertura de Obras, rentabilidad formal, dashboard, alertas, PDF tributario, exportación Excel ni front.

Los documentos externos con montos diferentes del Presupuesto, notas de crédito con ajustes parciales, devoluciones y otros casos tributarios necesitan especificación adicional. **Nunca forzar coincidencia cambiando datos históricos ya aprobados.**

Los datos fiscales registrados son informativos; su validez y tratamiento legal dependen del documento real y revisión profesional. Este sistema no pretende certificar cumplimiento tributario.

## 11. Criterios de aceptación e integración

**007A se considera implementada** solo después de modelos, API, permisos, eventos, pruebas, migración, revisión técnica y Backend CI. **007B** no se inicia antes de fusionar 007A. Cada PR de código incluye resumen, contratos, decisiones de seguridad, migraciones, resultados reales y checklist.

Este PR **solo define documentación** y no habilita ningún endpoint. El workflow Backend CI actual se activa por `backend/**`, `compose.yaml`, `.env.example` o su propio YAML, no por `specs/**`; ausencia de CI en la PR documental no equivale a ejecución exitosa.

### Fuentes internas verificadas

- `specs/001-backend-structure.md`, `003a-gestion-clientes.md`, `003b-gestion-presupuestos.md`, `004-gestion-obras.md`, `004b-costos-finalizacion.md`, `006-backend-usuarios-roles.md`.
- `backend/apps/comercial/{models.py,calculos.py,services_presupuestos.py,permissions.py}`.
- `backend/apps/obras/{models.py,services_finalizacion.py,services_costos.py,permissions.py}`.
- `backend/apps/finanzas/`, `backend/config/{urls.py,settings.py}` y `.github/workflows/backend-ci.yml`.
