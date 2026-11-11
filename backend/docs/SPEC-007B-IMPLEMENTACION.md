# SPEC-007B — Pagos y seguimiento de cobranzas

Entrega para revisión en `feature/backend-007b-pagos-cobranzas`, acumulativa sobre 007A integrada. No hay commit, push ni PR. La SPEC oficial no se modifica ni se declara integrada antes de revisión y CI.

**Registrar un pago documenta dinero recibido y comprobado fuera de FYAG. No transfiere dinero ni se conecta a bancos. Anular un registro no efectúa una devolución bancaria.** No se implementan SII, pasarelas, anticipos, intereses, facturación parcial múltiple, rentabilidad, frontend, MongoDB, dashboard ni reportes de otros módulos.

## 1. Archivos y alcance

Nuevos en `backend/apps/finanzas/`:

- `services_pagos.py`: registro idempotente, anulación, canonización/huella y bloqueo documental.
- `serializers_pagos.py`: entradas estrictas, lectura actual y respuesta original del alta.
- `consultas_cobranzas.py`: suma de pagos activos, saldo, estados derivados y anotaciones SQL sin joins multiplicadores.
- `views_pagos.py`: pagos, historial, cartera, filtros, paginación y agregados.
- `migrations/0002_pagos_cobranzas.py`: modelo de pagos, índices/constraints y ampliación de eventos.
- `tests/test_pagos.py`, `test_cobranzas.py`, `test_concurrencia_pagos.py`, `test_migracion_pagos.py`.

Modificados en `backend/apps/finanzas/`:

- `models.py`: `PagoDocumento`, tipos/referencia de eventos y lista permitida de snapshots.
- `services_documentos.py`: únicamente import de PagoDocumento y guard de pagos activos en reversión.
- `serializers_documentos.py`: resumen calculado de cobranza y referencia/snapshots de eventos de pago.
- `views_documentos.py`: queryset de documentos con anotaciones de cobranza para evitar N+1.
- `urls.py`: nuevas rutas explícitas antes del router de 007A.
- `tests/test_documentos.py`: se conserva la prueba de inmutabilidad/CRUD y se actualiza el antiguo placeholder que esperaba 404 en pagos/cobranzas, ahora habilitados por 007B; nombre del test actualizado. No se elimina ninguna regla documental de 007A.

Informe nuevo: `backend/docs/SPEC-007B-IMPLEMENTACION.md`.

No se modifican Comercial, Obras, Usuarios, configuración de autenticación ni migraciones anteriores. En particular, `finanzas.0001_facturacion_documental` queda intacta. No hay cambios fuera de Finanzas y este informe. `backend/scripts/` ya estaba sin seguimiento al iniciar y se preserva/excluye del ZIP.

## 2. Modelo e integridad

### PagoDocumento

- PK BigAutoField; FK PROTECT a DocumentoCobro; monto Decimal/NUMERIC(38,2) estrictamente positivo, hasta 36 enteros y dos decimales.
- Fecha civil ISO no futura en `America/Santiago`, no anterior a emisión documental. No se acepta timestamp/zona enviada por cliente.
- Medio TRANSFERENCIA, EFECTIVO, TARJETA u OTRO. Respaldo obligatorio hasta 500 caracteres; observación opcional hasta 2000, default vacío; textos normalizados con trim.
- Registrador PROTECT y fecha de servidor. Activo inicialmente true; anulado_por/en, motivo_anulacion y referencia_reversion_externa nulos hasta anulación.
- UUID de idempotencia global y obligatorio, con constraint `fin_pago_idempotencia_unica`. Huella SHA-256 de 64 caracteres hexadecimales.
- Constraints de monto/rango, medio, formato de huella, textos y coherencia completa activo/metadatos de anulación. Índices documento/activo y fecha_pago/ID.
- Sin saldo persistido ni campos de tarjeta/cuentas bancarias/credenciales. No introducir esos datos tampoco en textos libres: usar referencias documentales mínimas verificadas, no números completos ni secretos.
- Guardias heredados de RegistroInmutable contra edición, borrado y operaciones bulk. No se registra CRUD en Django Admin. Únicamente el servicio de anulación actualiza activo y metadatos, nunca monto ni identidad/origen.

### FinanzasEvento

Se agregan PAGO_REGISTRADO y PAGO_ANULADO con FK PROTECT al pago. La constraint exige exactamente una referencia pertinente:

- Evento documental → documento, sin pago ni cierre sin cobro.
- Evento sin cobro → cierre sin cobro, sin documento ni pago.
- Evento de pago → pago, sin documento ni cierre sin cobro; el documento se obtiene a través del pago.

Los eventos de pagos tienen snapshots limitados de documento/monto/fecha/medio/respaldo/observación/actividad y datos de anulación. No contienen UUID, huella, tokens, credenciales ni costos operativos. El serializer filtra defensivamente campos y tipos; boolean solo para activo e integer solo para IDs autorizados. Historial append-only mediante guardias ORM y API sin edición/borrado.

La migración `0002_pagos_cobranzas` crea la tabla vacía y amplía la constraint de eventos sin alterar sus filas anteriores. No inventa pagos ni ingresos a partir de documentos históricos. FK/constraints se aplican en PostgreSQL. La invariante agregada entre filas se protege por servicio bajo lock del documento; no se pretende implementar una CHECK con SUM entre tablas, que PostgreSQL no admite como constraint local. Los escritores externos/SQL deben respetar el mismo protocolo; un DBA puede eludir guardias ORM.

## 3. Transacciones y concurrencia

Orden invariable de filas bloqueadas: **Presupuesto → Obra → DocumentoCobro → PagoDocumento**, evento al final. Se reutiliza la raíz de 007A; la lectura preliminar se revalida tras bloquear. No se bloquea Usuario antes de Presupuesto, ni se llaman acciones mutadoras de Obras.

Registro y anulación son atómicos con su evento. Se revalida AF, actividad y versión desde BD al entrar y después de esperas por la raíz; la autenticación JWT global de SPEC-006 sigue rechazando access/refresh revocados. Los roles no se obtienen del body, flags Django ni claims de privilegio.

- Alta: después del lock documental se comprueba repetición de UUID, vigencia, ausencia de cierre sin cobro, fecha respecto de emisión y saldo recalculado con SUM de pagos activos. Monto > saldo → 409 sin escritura.
- Anulación: lock documental, luego pago acotado al documento de URL; solo activo. Verifica integridad del saldo actual, fija metadatos y evento. Un segundo intento → 409 sin evento adicional.
- Reversión documental: mismo lock de 007A sobre DocumentoCobro; si hay pagos activos → `409 pagos_pendientes_de_resolver`. No borra, anula automáticamente ni compensa pagos. Tras resolverlos administrativamente, puede revertirse con respaldo externo y se conserva todo el historial.
- Las carreras entre distintos UUID del mismo documento se serializan por su raíz, no por saldo leído previamente ni por controles del navegador.

### Idempotencia global y recuperación

1. Se valida UUID del header y contrato del body. El UUID admite mayúsculas/minúsculas con formato guionado de 36 caracteres; se normaliza a UUID de PostgreSQL.
2. La huella incluye **documento destino**, monto con dos decimales, fecha ISO, medio, respaldo y observación normalizados. JSON de claves ordenadas, separadores estables, SHA-256. Observación omitida equivale a cadena vacía; `100.1` equivale a `100.10`. El actor no redefine la operación: otro AF autorizado recupera el mismo registro/registrador original.
3. La búsqueda por UUID se hace **antes de validar saldo/vigencia actuales**, y se repite después de adquirir la raíz para solicitudes que todavía no encuentran un registro. Esto permite recuperar la operación tras quedar pagado el documento, anular el pago o revertir el documento después de resolverlo.
4. Mismo UUID y huella → pago original, HTTP 200, sin evento ni reactivación. Huella distinta (incluido otro documento) → 409 idempotencia_conflictiva.
5. Con raíces distintas, dos inserciones pueden competir en el índice UUID. Se captura **solo** `fin_pago_idempotencia_unica`, después del rollback completo del bloque atómico perdedor, y se recupera/compara el registro ganador. No se bloquea un pago de otra raíz ni se invierte el orden para resolver la colisión. Otros IntegrityError no se ocultan.
6. Primera creación → 201. Header de respuesta `Idempotency-Replayed: false` o `true`. No hay memoria de proceso como fuente de verdad ni caducidad que permita reutilizar una clave histórica.

**Cuerpo original del POST:** se reconstruye desde campos de alta inmutables, con activo=true y metadatos de anulación nulos, exactamente como se respondió al crear. No incluye saldo dinámico ni UUID/huella. Si el pago se anuló posteriormente, el reintento sigue recuperando ese cuerpo, **no** el estado actual ni una nueva operación. Consultar GET del pago para estado actual inactivo y metadatos de anulación. La prueba de pérdida de respuesta simula un timeout al serializar después de que el servicio confirmó el alta; reintentar con la misma clave recupera una sola fila/evento.

## 4. Cobranza calculada

Solo para documentos VIGENTES:

```text
abonado = SUM(monto WHERE activo = true), o Decimal("0.00") si no hay pagos
saldo = monto_total - abonado
0 <= abonado <= monto_total; saldo >= 0
```

La suma SQL usa NUMERIC y campos de salida Decimal(38,2). La resta de dominio usa contexto Decimal local de precisión 50; no se depende del contexto global por defecto ni de float. Entradas con precisión/magnitud excesiva se rechazan sin redondearlas. Los importes JSON siempre son strings de dos decimales.

Estados, en este orden de prioridad:

1. PAGADA si saldo cero, aunque la fecha documental haya vencido.
2. VENCIDA si saldo positivo y vencimiento anterior al día civil de Santiago.
3. PARCIAL si abonado positivo, saldo positivo y no vencida.
4. PENDIENTE si no hay abonos y no vencida. Vencimiento hoy todavía no significa vencida.

`DocumentoLecturaSerializer` agrega `cobranza = {moneda, abonado, saldo, estado}`. Para documento REVERTIDO devuelve `cobranza: null`; no se crea cartera para cierre SIN_COBRO ni un documento inexistente. El estado financiero de Obras conserva sus etiquetas 007A y, si hay documento vigente, su objeto documental incluye la nueva cobranza.

Una subconsulta agrupada por documento suma pagos activos sin multiplicar filas al consultar referencias de origen. Se anotan saldos/estados en SQL para filtrar **antes** de contar/paginar. Listados usan select_related/prefetch_related y pruebas de número acotado de consultas.

Resumen de cartera: suma únicamente documentos vigentes del mismo conjunto filtrado. Devuelve moneda CLP, `documentos`, `conteos` por estado, `monto_documentado_total`, `abonado_total`, `saldo_total`, `saldo_vencido`. Un conjunto vacío tiene conteo cero y sumatorias cero, no ingresos derivados de una cortesía. Si una sumatoria supera NUMERIC(38,2), devuelve 409 importe_fuera_rango en vez de truncar, redondear o convertir a float. Ningún cálculo usa CierreCostosObra.

## 5. API

Base `/api/finanzas/`. JWT Bearer válido en todas las rutas. G/AF leen; solo AF crea/anula; S/T no acceden, incluso con is_superuser/is_staff y también mediante OPTIONS. Sin PUT, PATCH ni DELETE genéricos.

| Método | Ruta | Éxito |
|---|---|---|
| GET | `documentos/{id}/pagos/` | 200, 25/página |
| POST | `documentos/{id}/pagos/` | 201 o 200 repetición |
| GET | `documentos/{id}/pagos/{pago_id}/` | 200, estado actual |
| POST | `documentos/{id}/pagos/{pago_id}/anular/` | 200 |
| GET | `documentos/{id}/pagos/historial/` | 200, 25/página |
| GET | `cobranzas/` | 200, 25/página |
| GET | `cobranzas/resumen/` | 200, agregados filtrados |
| GET | `documentos/{id}/` | 200, contrato 007A + cobranza |

Rutas explícitas de pagos preceden al router 007A; `pagos/historial/` precede a la captura de pago_id. No se cambian URLs de autenticación, Usuarios, Comercial ni Obras.

### Escrituras

POST pago, header obligatorio `Idempotency-Key: <UUID>`:

```json
{
  "monto": "100.13",
  "fecha_pago": "2026-11-10",
  "medio": "TRANSFERENCIA",
  "referencia_respaldo": "Referencia mínima del comprobante ya verificado",
  "observacion": "Observación opcional"
}
```

Ejemplo de formato, no autorización para inventar un pago. Ajustar monto/fecha/referencia al documento y comprobante de pruebas. No se aceptan activo, saldo, documento, actor, timestamps, UUID/huella en body, campos bancarios/tarjeta ni desconocidos. Nada produce transferencias.

POST anular:

```json
{
  "motivo": "Corrección administrativa acreditada",
  "referencia_reversion_externa": "Respaldo verificable de la corrección externa"
}
```

Ambos textos obligatorios. Se mantiene monto, documento, clave, huella, respaldo original, observación y registrador originales.

### Lectura, filtros y orden

- Pagos: ID, naturaleza administrativa, documento ID, monto/fecha/medio/respaldo/observación, registrador/timestamp, actividad y metadatos de anulación. No objetos de Usuario/Cliente, UUID/huella, costos, evidencias ni credenciales.
- Historial de pagos: tipos/actor ID/motivo/snapshots restringidos; referencia `pago`. La ruta de historial documental 007A continúa mostrando eventos documentales; no se mezclan referencias incompatibles.
- Pagos listados: filtros `activo=true|false`, `medio`, `fecha_pago_desde`, `fecha_pago_hasta`, `page`; orden `(-registrado_en,-id)`.
- Historial: solo page, orden `(creado_en,id)`.
- Cartera/resumen: filtros `estado` (PENDIENTE/PARCIAL/PAGADA/VENCIDA), `cliente`, `obra`, `fecha_vencimiento_desde`, `fecha_vencimiento_hasta`, `fecha_emision_desde`, `fecha_emision_hasta`, `page`. `estado` aquí es cobranza, no VIGENTE/REVERTIDO. Orden cartera `(fecha_vencimiento,id)`. Resumen no pagina ni limita sus totales al tamaño de página; page, si se envía, solo se valida.
- Desconocidos/repetidos, página no positiva, enum inválido, IDs fuera de rango y fechas/rangos inválidos → 400. Un número positivo válido inexistente o pago de otro documento → 404.

### Errores

400 validación; 401 sesión ausente/inactiva/revocada; 403 rol sin permiso; 404 recurso inexistente/ajeno; 405 métodos no implementados para AF autorizado. Conflictos 409 con `code` estable:

- `monto_excede_saldo`, `documento_revertido`, `sin_cobro_ya_registrado`.
- `idempotencia_conflictiva`, `pago_ya_anulado`, `pagos_pendientes_de_resolver`.
- `saldo_inconsistente` para una anomalía agregada persistida detectada antes de escribir; `importe_fuera_rango` para agregado fuera del rango admitido.
- Se conservan códigos documentales de 007A, incluido `origen_inconsistente`.

No se exponen payloads ajenos ni datos financieros a S/T a través de esos errores o metadatos.

## 6. Validaciones ejecutadas

Validaciones en Docker con Django **5.2.19** y PostgreSQL **18.6** (`connection.vendor=postgresql`, `pg_version=180006`). La suite completa incluye la regresión de 007A, Comercial, Obras y Usuarios; no se presenta una suite parcial como prueba de regresión íntegra.

| Comando (prefijo `docker compose exec -T backend`) | Resultado |
|---|---|
| `python manage.py check` | `System check identified no issues (0 silenced).` |
| `python manage.py makemigrations --check --dry-run` | `No changes detected` |
| `python manage.py migrate --noinput` | `Applying finanzas.0002_pagos_cobranzas... OK` |
| `python manage.py showmigrations finanzas` | 0001 y 0002 aplicadas `[X]` |
| `python manage.py test apps.finanzas --noinput` | **78 pruebas, 29.561 s, OK** |
| `python manage.py test --noinput` | **628 pruebas, 123.662 s, OK**; BD temporal creada desde cero y destruida al terminar |
| `git diff --check` (host) | Sin errores de whitespace; avisos de conversión LF/CRLF de Git en Windows |

Ejecuciones intermedias reales: regresión 007A de **37 pruebas, 12.899 s, OK**; primeras pruebas de pagos/cobranza **26 pruebas, 8.942 s, OK**; suite acumulativa **75 pruebas, 28.537 s, OK**. Luego se agregaron recuperación tras pérdida de respuesta, fecha Santiago con zona UTC y cierre sin cobro fuera de cartera.

Las advertencias de Simple JWT al emitir tokens para usuario inactivo corresponden a pruebas negativas existentes de Usuarios, no a errores de la suite ni a un login autorizado.

Cobertura nueva:

- Pago parcial, exacto total, sobrepago, cuatro estados, prioridad de PAGADA y vencimiento civil.
- Validación estricta de dinero, UUID, fechas, medio, respaldo, observación y campos de servidor; máximo NUMERIC bajo contexto Decimal reducido y overflow de sumas globales.
- Canonización, clave distinta para operación distinta, conflicto de payload/documento, repetición tras saldo cero/anulación/reversión y pérdida de respuesta posterior al commit.
- Anulación respaldada, segunda anulación, rollback de pago/evento/anulación, historial, inmutabilidad, Admin y constraints SQL.
- Roles G/AF/S/T, flags sin bypass, OPTIONS, JWT revocado, cuenta inactiva, IDs ajenos, paginación/filtros, orden, agregados sin duplicados y consultas acotadas.
- Migración limpia al crear BD de pruebas; downgrade/upgrade 0001 → 0002 con documento/eventos 007A históricos preservados y cero pagos inventados. También se mantienen las pruebas de migración previas.
- **11 carreras** PostgreSQL: sobrepago competidor; dos abonos que completan exacto; UUID igual/contenido igual; UUID igual/contenido distinto; UUID igual entre documentos; pago→reversión y reversión→pago; anulación→nuevo pago y nuevo pago→anulación; doble anulación; anulación→reversión. Conexiones independientes, Event, timeouts y bloqueo observado con pg_blocking_pids, sin sleeps.

No se ejecuta GitHub Actions sin push/PR, ni se afirma CI remoto verde. Postman y pruebas manuales quedan para la revisión posterior, no se presentan como ejecutadas.

## 7. Procedimiento manual y Postman reproducible

### Preparación segura

1. Levantar Docker habitual y aplicar migraciones con los comandos anteriores. Usar entorno aislado y cuentas de revisión de los cuatro roles, sin credenciales de producción. No modificar estados/costos por SQL para habilitar pruebas.
2. Obtener documentos VIGENTES desde 007A sobre Obras finalizadas, presupuestos aprobados y respaldos externos de prueba. Consultar su detalle y cobranza. Para SIN_COBRO usar el flujo autorizado de cortesía/finalización/cierre 007A, no una factura cero.
3. Variables Postman locales: `baseUrl`, `accessAF`, `accessG`, `accessS`, `accessT`, `documentoId`, `pagoId`, `paymentKey`, `originalPaymentResponse`. No exportar/sincronizar tokens, contraseñas, cookies ni referencias privadas con la colección/ZIP.
4. Login con el flujo existente: GET auth/csrf, cookie CSRF + header X-CSRFToken al POST login, conservar CSRF rotado para refresh/logout. Llamadas financieras con `Authorization: Bearer {{accessAF}}`; no autentican mediante cookie refresh.
5. Generar `paymentKey` **una sola vez por operación nueva** (por ejemplo UUID en la consola de Postman). No poner `{{$guid}}` directamente como header dinámico ni regenerarlo en cada reintento: eso sería otra operación y no probaría idempotencia.

### Secuencia de registro y recuperación

1. GET `/api/finanzas/documentos/{{documentoId}}/`: verificar saldo completo y PENDIENTE sin abonos; no confundir neto/costo/total documentado con ingresos.
2. POST `documentos/{{documentoId}}/pagos/`, header `Idempotency-Key: {{paymentKey}}`, body según ejemplo con pago de prueba comprobado y monto <= saldo. Esperar 201, `Idempotency-Replayed: false`, guardar ID y cuerpo original localmente.
3. Reenviar **mismo body y misma variable de clave**: 200, `Idempotency-Replayed: true`, mismo cuerpo/ID, un solo pago/evento. Probar formatos canónicos equivalentes de monto (`100.1`/`100.10`) y trim de textos sin cambiar su contenido significativo.
4. Misma clave y monto/medio/fecha/respaldo/observación distinto, o destino otro documento: 409 idempotencia_conflictiva y ninguna fila adicional.
5. Si se pierde una respuesta/timeout, no generar nueva clave: repetir la misma solicitud y recuperar la respuesta original. La prueba automatizada simula pérdida de respuesta después de confirmar la transacción.
6. Con clave nueva para otro abono real de prueba, completar el saldo: PAGADA. Nuevo pago sobre saldo cero: 409 monto_excede_saldo. Repetir la clave del abono que completó el saldo: 200, no sobrepago ni segundo evento.

### Anulación y reversión

1. Intentar revertir documento con pago activo usando el contrato 007A: 409 pagos_pendientes_de_resolver, sin alterar documento/pago.
2. POST `documentos/{{documentoId}}/pagos/{{pagoId}}/anular/` sin respaldo externo → 400. Con motivo y rectificación de prueba acreditada → 200, activo=false; saldo recalculado excluye ese pago. No se ejecuta devolución bancaria.
3. Repetir anulación → 409 pago_ya_anulado. GET detalle/historial conserva monto y datos originales, dos eventos por pago anulado.
4. Repetir el POST original de alta con su clave después de anular → 200 y **cuerpo original del alta**, mientras GET pago sigue inactivo. No usar el campo activo del cuerpo reproducido como estado actual; consultar GET.
5. Resolver administrativamente todos los pagos activos con respaldo. Revertir documento con evidencia externa real/de prueba → 200 REVERTIDO, `cobranza: null`, fuera de cartera. GET pagos/historial sigue disponible. Nueva clave para pagar ese documento → 409 documento_revertido; clave del pago histórico original recupera su operación sin crear otra.

### Estados, filtros y permisos

1. Preparar documentos de prueba con vencimiento pasado/hoy/futuro según respaldo externo. Pagar parcialmente uno vencido mantiene VENCIDA; completar total da PAGADA; parcialmente no vencido da PARCIAL. Las fechas deben contrastarse con Santiago.
2. GET cobranzas con filtros combinados y luego cobranzas/resumen con los mismos filtros. Comprobar conteos, suma documental, suma de pagos **activos**, saldo y saldo vencido. Documentos revertidos y cierres sin cobro no aparecen ni aportan ingresos ficticios.
3. Con más de 25 registros, verificar segunda página y orden estable. Parámetro desconocido/repetido, página cero, IDs boolean/texto, enum inválido o rango de fechas invertido → 400. Pago de otro documento → 404. PUT/PATCH/DELETE con AF → 405.
4. G puede consultar todos los endpoints de lectura, no POST pago/anular. S/T → 403 incluso OPTIONS y aunque tengan flags Django. Sin token o con token invalidado mediante cambio de identidad/rol de Usuarios → 401; nuevo login de rol sin permiso → 403. No dejar el entorno sin Gerencia activa.
5. No ejecutar pruebas de carrera alterando producción ni con sleeps. Las 11 pruebas TransactionTestCase verifican bloqueo real; Postman Runner paralelo por sí solo no demuestra orden ni ausencia de deadlocks.

## 8. ZIP y revisión

`revision-spec-007b.zip` contiene únicamente archivos nuevos/modificados de esta entrega y este informe, con rutas relativas al repositorio; es un paquete incremental sobre 007A, no un despliegue completo. Se excluyen `.env`, secretos, bases de datos, dependencias, cachés, pruebas locales/temporales, `.git`, frontend, entregas anteriores y scripts ajenos. Incluye los tests automatizados versionables del incremento, no datos privados ni artefactos locales de ejecución.

Revisar este ZIP antes de Postman. Commit, push, PR, Backend CI e integración requieren autorización posterior del usuario.
