# SPEC-021 — Registro de egresos y flujo de dinero (FYAG Beta)

> **Estado: CONTRATO DOCUMENTAL RATIFICADO PARA IMPLEMENTACIÓN.** 21-11-2026.
> **Producto:** FYAG Beta, seguimiento económico de una pyme de servicios.
> **Base técnica verificada:** `main` SHA `3d1351773dcb5dcbb90838fda194785ac9d11498`. SPEC-007A/007B, 010, 011, 019A y 020A/B integradas. SPEC-019B permanece como propuesta en PR #56.
> **Alcance previsto:** backend Django REST Framework, PostgreSQL, API, OpenAPI y pruebas. Esta integración documental no incluye código ejecutable, migraciones ni frontend. La implementación requiere una rama y PR propios; un merge documental no equivale a despliegue ni a validación productiva.

## 1. Problema de negocio

FYAG ya permite registrar facturas externas y los **pagos efectivamente recibidos de clientes** (`finanzas.PagoDocumento`), así como los **costos de ejecución de Obras** (`obras.GastoObra` y sus cierres). **No existe en el backend un registro equivalente de dinero realmente pagado por la empresa a terceros.**

La distinción es obligatoria:

- **Cobro recibido:** registro de dinero que ingresó, respaldado por `PagoDocumento` activo; no corresponde al total facturado.
- **Egreso pagado:** registro de dinero que efectivamente salió, respaldado por nuevo `Egreso` activo; no corresponde al gasto presupuestado ni a una obligación pendiente.
- **Costo de Obra:** uso de recursos para ejecutar un trabajo, sea o no pagado en esa misma fecha. No se puede sumar otra vez como salida de dinero si ya existe un Egreso asociado.
- **Inventario:** entradas y salidas de materiales físicos; ninguna representa por sí misma dinero que entra o sale. Una salida de Bodega podrá atribuir un costo a la Obra sin generar un segundo egreso.

**La finalidad es mostrar el flujo de dinero registrado**, no utilidad contable, conciliación bancaria, saldo bancario real, emisión tributaria ni contabilidad de partida doble.

## 2. Objetivo mínimo de SPEC-021

Habilitar a Administrativo/Finanzas para:

1. Registrar un **pago efectivamente realizado** a un tercero, con monto, fecha, concepto, categoría, medio y referencia de respaldo.
2. Consultar y filtrar egresos, con vínculo **opcional y meramente informativo** a una Obra si tiene relación directa.
3. Anular administrativamente un registro equivocado con causa y evidencia de corrección, conservando el original y su historial.
4. Consultar el resumen de un período: **cobros recibidos, pagos realizados y diferencia**. Presentar la diferencia como **flujo neto registrado**, no como ganancia ni saldo disponible en banco.

**Importante:** registrar el pago en FYAG **no ejecuta una transferencia**; solo deja constancia de un desembolso ocurrido fuera del sistema.

### Ejemplo conceptual

- Cobros de clientes efectivamente registrados en noviembre: CLP 100.000.
- Egresos efectivamente pagados y registrados en noviembre: CLP 80.000.
- Flujo neto registrado del período: **CLP +20.000**.

No significa utilidad de CLP 20.000: pueden existir costos devengados, obligaciones impagas, impuestos y otros movimientos fuera de FYAG.

## 3. Límite de alcance para no convertir FYAG en ERP

**Incluye:** una tabla de egresos registrados, historial de alta/anulación, permisos, listados paginados, filtros, operaciones idempotentes, resumen neto por fechas, API versionada y pruebas reales.

**No incluye:**
- Proveedores como entidad, órdenes de compra, cuentas por pagar, cuotas, pagos programados o aprobación multinivel.
- Banca integrada, conciliación de cuentas, saldo inicial de caja/banco, presupuesto de tesorería, caja chica, multiempresa, multimoneda o transferencias entre cuentas propias.
- Emisión o validación de DTE/boletas/facturas, cálculo automático de IVA, contabilidad tributaria ni deducción de impuestos.
- Nómina de remuneraciones, información salarial individual, reembolsos a proveedores, inversiones/aportes de capital o ingresos extraordinarios que no correspondan a cobros de clientes.
- Descargas de respaldos externos desde enlaces no confiables, adjuntos nuevos, notificaciones, alertas y vistas React.
- Generación automática de `Egreso` al crear `GastoObra`, un ingreso de inventario, una factura o una autorización de Bodega.

Un futuro incremento podrá ampliar estos casos **solo con una SPEC específica**.

## 4. Modelo y datos (propuesta)

### 4.1 `Egreso`

Entidad en `apps.finanzas`, con nueva migración posterior a `finanzas.0002_pagos_cobranzas`.

| Campo | Semántica |
| --- | --- |
| `id` | PK de servidor |
| `monto` | **Importe total efectivamente pagado, CLP**, `Decimal` positivo con 2 decimales; no guardar neto/IVA inventados |
| `fecha_pago` | Fecha civil real `YYYY-MM-DD`, no futura, zona America/Santiago |
| `categoria` | Clasificación sencilla: `MATERIALES`, `TRANSPORTE`, `SERVICIOS`, `ARRIENDO`, `OTROS`; sin interpretar automáticamente estados tributarios |
| `concepto` | Descripción breve de lo pagado |
| `beneficiario` | Nombre comercial/descripción breve del tercero; **no** guardar datos bancarios completos |
| `medio` | `TRANSFERENCIA`, `EFECTIVO`, `TARJETA`, `OTRO` (mismo vocabulario que pagos recibidos) |
| `referencia_respaldo` | Identificador de comprobante externo obligatorio; texto, no documento tributario creado por FYAG |
| `observacion` | Opcional, longitud limitada |
| `obra` | FK a Obra nullable; **referencia informativa**, no validación/cierre de costos ni nueva escritura en Obras |
| `registrado_por`, `registrado_en` | Usuario AF real y fecha de servidor |
| `clave_idempotencia`, `huella_solicitud` | UUID único + hash de payload, para repetición segura |
| `activo` | `True` para registro válido, `False` si fue anulado administrativamente |
| `anulado_por`, `anulado_en`, `motivo_anulacion`, `referencia_correccion` | Solo si está anulado; conservar el registro original |

**No permitir edición monetaria de un egreso ya registrado.** Si hay error de monto, fecha, categoría, referencia o vinculación, se anula el registro equivocado y se crea uno nuevo con otra clave, sin borrar el hecho histórico.

La anulación indica una **corrección administrativa de un registro**, no que un banco haya devuelto el dinero. Si la empresa realmente recibió una devolución de fondos, necesita un flujo financiero distinto; no simularla desactivando un egreso correcto.

**`EgresoEvento`**: historial append-only con `CREACION` y `ANULACION`, autor real, fecha servidor y motivo, referenciado a egreso. No dar acceso público a editar/eliminar eventos.

**Sin cambios obligatorios en `PagoDocumento`, `DocumentoCobro`, `GastoObra`, `MovimientoInventario` ni `CierreCostosObra`.** Relaciones y auditoría deben preservarse.

### 4.2 Invariantes de PostgreSQL

- `monto > 0`, finito, `NUMERIC`, precisión compatible con `finanzas.validaciones.importe`; input/output JSON siempre string decimal de dos posiciones.
- Categoría y medio de catálogo cerrado; campo concepto/beneficiario/referencia normalizado y no vacío; límites establecidos de texto.
- `clave_idempotencia` única y huella de payload verificable; actor y sello temporal del servidor.
- Coherencia total entre `activo` y columnas de anulación; no reactivar administrativamente un egreso anulado.
- FK Obra con `PROTECT`, sin lectura transversal de detalles de Obras a Bodeguero, Técnico o TI.
- Registro histórico inmutable salvo transición controlada de anulación, con servicio transaccional y evento en una operación atómica.
- Protecciones PostgreSQL para integridad de estados y unicidad; los servicios no son un sustituto de constraints.

## 5. Permisos y confidencialidad

| Operación | Administrativo/Finanzas | Gerencia | Supervisor | Bodeguero | Técnico | Administrador TI |
| --- | --- | --- | --- | --- | --- | --- |
| Listar/ver egresos y su historial | Sí | Sí | No | No | No | No |
| Registrar egreso | **Sí** | No | No | No | No | No |
| Anular egreso con motivo y respaldo | **Sí** | No | No | No | No | No |
| Consultar resumen de cobros/egresos | Sí | Sí | No | No | No | No |

Revalidar `rol`, `is_active`, sesión versionada y bloqueo operativo a partir del usuario persistido en cada acceso, sin elevación por `is_staff`, `is_superuser` ni claims JWT. Separar permisos de lectura y escritura. No añadir ninguna facultad financiera a los otros roles.

No aceptar `actor`, `activo`, sello de servidor, `saldo` ni campos administrados por el backend en requests.

## 6. API propuesta

Conservar `/api/finanzas/` y rutas existentes; sin romper contratos de cobros.

| Método | Ruta | Función |
| --- | --- | --- |
| GET | `/api/finanzas/egresos/` | Listado paginado y filtrado, sin totales monetarios ad hoc |
| POST | `/api/finanzas/egresos/` | Registrar egreso con header `Idempotency-Key: <UUID>` |
| GET | `/api/finanzas/egresos/{id}/` | Detalle de egreso autorizado |
| POST | `/api/finanzas/egresos/{id}/anular/` | Anulación con `motivo` y `referencia_correccion` |
| GET | `/api/finanzas/egresos/{id}/historial/` | Eventos paginados |
| GET | `/api/finanzas/flujo-dinero/resumen/` | Cobros/egresos efectivamente registrados en período |

**POST egreso:** `monto`, `fecha_pago`, `categoria`, `concepto`, `beneficiario`, `medio`, `referencia_respaldo`, `observacion` opcional, `obra` opcional/null; `Idempotency-Key` UUID obligatorio y de unicidad global para egresos. Misma clave/payload retorna el alta original sin duplicar registro, **incluso después de una anulación**: el replay reconstruye la respuesta de creación original y `GET detalle` presenta el estado actual. Misma clave con payload diferente → 409, no 500. Distinguir alta 201 de repetición 200 mediante encabezado `Idempotency-Replayed` como en SPEC-007B.

**POST anulación:** solo `motivo` y `referencia_correccion` obligatorios; segunda anulación → 409. Revisión y evento en una transacción. La cancelación administrativa exige referencia de rectificación, no una devolución bancaria simulada.

**GET listado:** filtros por `categoria`, `medio`, `obra`, `activo`, `desde` y `hasta` (fechas del pago, dos juntas, máximo 366 días), `page`; orden por fecha de pago DESC, ID DESC y paginación nativa DRF de 25. Rechazar query desconocida/repetida, campos vacíos, IDs inválidos y fechas imposibles.

**GET resumen:** `desde` y `hasta` obligatorios, rango civil inclusivo en Santiago, máximo 366 días, sin agrupación inventada por documento o por factura; no hay paginación. Entrega ejemplo:

```json
{
  "periodo": {"desde": "2026-11-01", "hasta": "2026-11-30"},
  "moneda": "CLP",
  "ingresos_recibidos": "100000.00",
  "egresos_pagados": "80000.00",
  "flujo_neto_registrado": "20000.00",
  "naturaleza": "REGISTROS_ADMINISTRATIVOS_NO_CONCILIADOS"
}
```

**Definiciones exactas de agregados:**

- `ingresos_recibidos = SUM(PagoDocumento.monto)` de pagos **activos** cuya `fecha_pago` cae en el rango, incluso si el documento ya está revertido solo si tal estado es válido según invariantes de SPEC-007; los datos inconsistentes deben reportar 409, no ocultarse.
- `egresos_pagados = SUM(Egreso.monto)` de egresos **activos** cuya `fecha_pago` cae en el mismo rango.
- `flujo_neto_registrado = ingresos_recibidos - egresos_pagados`; **puede ser negativo**.
- La lectura suma cobros efectivamente registrados, **no** `DocumentoCobro.monto_total`, saldos de cobranza ni pagos presupuestados.
- No sumar por segunda vez los costos de Obras ni consumos físicos de Bodega. Usar `Decimal` con precisión suficiente y responder importes como strings de dos decimales.

El resumen es una **foto administrativa a la fecha de consulta** y se recalcula cuando se anula un registro. No representa saldos de cuentas ni un libro de caja por asiento con cierre irreversible.

Responder 400/401/403/404/405/409 de acuerdo con SPEC-007. `Cache-Control: private, no-store` y `Vary: Authorization` para respuestas autenticadas.

## 7. Seguridad, concurrencia y pruebas

- Reutilizar validadores y convenciones existentes de Finanzas: `Decimal` estricto, fechas civiles America/Santiago, errores controlados, campos cerrados, referencia externa, idempotencia con huella y usuario persistido.
- Alta de egreso/evento atómica. Dos POST simultáneos con la misma UUID y contenido igual deben producir exactamente un egreso y su evento, con respuesta idempotente. Si difieren, 409. Sin transacciones distribuidas ni dependencia de herramientas bancarias.
- Anulación concurrente: un 200 y un 409, evento único. No borrar ni editar historia. Si una lectura y anulación coinciden, evitar datos corruptos sin prometer lectura de estado futuro.
- Resumen del período con **un único snapshot PostgreSQL verificable**, evitando mezclar pagos recibidos y egresos de cortes transaccionales distintos. No asumir que `transaction.atomic()` bajo el aislamiento predeterminado `READ COMMITTED` estabiliza dos agregados sucesivos. Usar una única sentencia SQL para ambos agregados o aislamiento de lectura apropiado y probado. No realizar escrituras en GET.
- Integridad: reversión administrativa de un pago recibido existente continúa aplicando SPEC-007; una anulación de egreso no debe afectar `PagoDocumento`, `GastoObra`, inventario ni costos cerrados.
- Seis roles; usuario inactivo, sesión revocada/bloqueada y claims manipulados; prueba de referencia de Obra inexistente/no permitida; consulta de historial por ID ajeno.
- Migración desde BD existente y desde cero, validación de `check` y `makemigrations --check --dry-run`, carreras PostgreSQL reales, suite regresiva completa, CI GitHub y Postman esencial. Sin datos de prueba en producción ni secretos en repo.
- Documentar OpenAPI nueva `SPEC-021-v1.json`, con schemas de respuestas y errores. No tocar `frontend/`.

## 8. Decisiones de diseño ratificadas para el contrato Beta

Se adoptan estas políticas sencillas para este incremento, coherentes con FYAG Beta:

1. **Fuente de registro:** Administrativo/Finanzas registra únicamente pagos ya realizados, con referencia de comprobante externo; Gerencia solo supervisa.
2. **Importe:** total **efectivamente desembolsado en CLP**, sin suponer IVA; no registrar pagos por cobrar ni documentos no pagados como egresos.
3. **Clasificación:** categorías cerradas mínimas `MATERIALES/TRANSPORTE/SERVICIOS/ARRIENDO/OTROS`; no crear maestros de proveedores ni contabilidad.
4. **Relación con Obra:** opcional e informativa. Un pago puede relacionarse con una Obra sin crear, editar o validar automáticamente su costo.
5. **Resumen:** incluir solo pagos de clientes activos y egresos activos por fecha del pago, sin confundirlo con utilidad ni saldo bancario; ingresos extraordinarios quedan fuera del MVP.
6. **Corrección:** anulación motivada del registro equivocado y nueva alta correcta; no usar anulación para simular reembolso físico.

Estas políticas definen el **contrato autorizado para implementación**, no capacidades que ya estén habilitadas en el backend. Cualquier ampliación funcional debe documentarse antes de incorporarla.

## 9. Orden de trabajo FYAG

1. Integrar esta SPEC documental revisada en `main` sin cambios de código, migraciones ni frontend.
2. Crear rama de implementación desde `main` actualizado, implementar servicios/migración/API/OpenAPI/Postman y pruebas localmente con OpenCode.
3. Auditar diff, publicar PR de implementación y ejecutar CI. El responsable ha delegado la autorización general de merge al revisor técnico **solo si** contrato, pruebas, seguridad, migraciones, regresión y CI quedan aprobados; no fusionar con pendientes materiales.
4. Entregar las nuevas rutas al equipo de frontend, además de las correcciones ya identificadas en SPEC-020.
5. Luego retomar SPEC-019B simplificada (entregas/devoluciones) y, solo si aporta valor al objetivo Beta, SPEC-019C.

**No usar SPEC-021 como excusa para activar dinero ficticio en Bodega, crear DTE, modificar créditos de clientes ni implementar un libro contable completo.**

## Seguimiento del frontend local — 25-11-2026

- Se añadió localmente `frontend/src/pages/Egresos.jsx` para consultar y registrar egresos mediante las rutas existentes, con filtros, paginación, detalle e historial; no realiza transferencias ni deriva egresos de movimientos de inventario o costos de Obras.
- El alcance implementado es solo frontend y sus contratos disponibles. No se cambió backend, no se ejecutó QA financiero real ni se declara publicación.

## Rediseño de la interfaz de Finanzas — 26-11-2026

- Listado a ancho completo, búsqueda global por concepto, beneficiario o código OB completo, filtros plegables, importes CLP exactos y estados legibles. GET /egresos/ admite buscar (máximo 100 caracteres no vacíos) y resumen=true (total y cantidad de activos en el conjunto filtrado, no en la página). Se excluyen anulados del agregado; sin resumen se conserva la respuesta anterior. Listado y agregado son lecturas separadas, no un cierre contable inmutable.
- Formulario de pago externo realizado, con obra opcional seleccionada por nombre/código mediante la consulta AF existente de Obras. Se conserva la asociación informativa, sin afectar stock ni costos. Detalle con historial y anulación bajo demanda; motivo, referencia y confirmación obligatorios. Alta idempotente, congelación de payload/UUID ante incertidumbre y relectura del estado vigente; anulación incierta exige reconsulta.
- Flujo de dinero en pestaña independiente, con período explícito y agregados existentes, no representa saldo bancario ni conciliación. Sin barras de progreso. Gerencia y permisos originales conservados.
- OpenAPI y pruebas dirigidas actualizados; ejecución local y revisión visual pendientes. Sin merge.

### Visualización del flujo de dinero

- Tras consultar un período válido, Finanzas presenta dos gráficos de igual escala interna por gráfico, en columnas paralelas en escritorio y apiladas en pantallas estrechas: comparación de ingresos/egresos desde cero y puente de ingresos menos egresos hasta el flujo neto firmado. El puente conserva el eje cero, conectores entre etapas y resultado positivo, negativo o equilibrado.
- Los importes exactos y las etiquetas accesibles se obtienen de los agregados ya validados; únicamente las coordenadas gráficas se aproximan. Sin nuevas dependencias, peticiones, contratos ni modificaciones de permisos. No se interpreta el resultado como saldo bancario.
- Estado inicial con icono, instrucción y explicación breve; si ambos importes son cero, estado sin movimientos en lugar de gráficos vacíos. No se muestran datos de un período anterior bajo fechas recién aplicadas.
- Pruebas dirigidas de geometría, precisión, estados inicial y vacío y resultado financiero añadidas. Ejecución local y validación visual pendientes.
