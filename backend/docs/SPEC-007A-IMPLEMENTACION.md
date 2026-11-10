# SPEC-007A — Facturación documental: entrega para revisión

Rama: `feature/backend-007a-facturacion`. Alcance exclusivo 007A, backend Django/DRF/PostgreSQL. Sin commit, push ni PR. No se cambia el estado de la SPEC oficial ni se declara integrada antes de revisión y CI.

**FYAG registra administrativamente documentos ya emitidos fuera del sistema. No emite, valida, anula legalmente ni simula DTE ante el SII. Ninguna operación mueve dinero.** No hay pagos, cobranzas, saldos, PDF tributarios, archivos adjuntos, descargas remotas ni integración bancaria.

## Archivos

Nuevos bajo `backend/apps/finanzas/`:

- `validaciones.py`: límites NUMERIC(38,2), suma Decimal con precisión local 50 y fecha civil de Santiago.
- `serializers_documentos.py`: contratos estrictos, proyección financiera y snapshots filtrados.
- `services_documentos.py`: registro externo, reversión y cierre sin cobro bajo transacción.
- `views_documentos.py`: endpoints, filtros, paginación y estado financiero.
- `migrations/0001_facturacion_documental.py`: tablas, FKs, constraints e índice de emisión.
- `tests/base.py`: fixtures; una finalización real mediante servicios existentes y fixtures históricos adicionales explícitos.
- `tests/test_documentos.py`: permisos, contratos, importes, fechas, historial, cortesía, rollback, consultas y constraints.
- `tests/test_concurrencia.py`: carreras PostgreSQL con conexiones independientes.
- `tests/test_migracion.py`: instalación sobre datos históricos existentes.

Modificados:

- `backend/apps/finanzas/models.py`, `permissions.py`, `urls.py`, `admin.py`.
- `backend/config/urls.py`: únicamente inclusión de `/api/finanzas/`.
- Este informe: `backend/docs/SPEC-007A-IMPLEMENTACION.md`.

No se modifica código de Comercial, Obras o Usuarios, migraciones previas, autenticación, SPEC, frontend, MongoDB, `database/` ni `backend/scripts/`. El directorio de scripts ya estaba sin seguimiento al iniciar y queda fuera de la entrega.

## Modelos e integridad

### DocumentoCobro

- FK PROTECT a Obra. Presupuesto y Cliente derivados, sin FKs duplicadas ni entrada editable.
- Tipos `FACTURA_AFECTA` / `FACTURA_EXENTA`; folio externo ASCII de hasta 100 dígitos. Se conserva exactamente, sin trim, conversión a número ni adición/eliminación de ceros iniciales. Los ceros solo se conservan si figuran en el documento externo; su cotejo es humano.
- Emisión/vencimiento civiles ISO, emisión no futura según `America/Santiago`, vencimiento no anterior a emisión.
- Neto, impuesto, total: Decimal/NUMERIC(38,2), máximo 36 enteros y dos decimales, no negativos; total positivo e igual a neto + impuesto. Exenta exige impuesto cero; afecta positivo sin tasa fija asumida.
- El neto debe coincidir exactamente con la suma de subtotales de ítems aprobados, usando el cálculo comercial existente. Nunca se toma del costo interno de cierre.
- Estado VIGENTE/REVERTIDO y metadatos de registro/reversión de servidor; identidad, importes y datos externos originales inmutables.
- Unicidad permanente `(tipo_documento, folio_externo)`, incluso tras reversión; índice único parcial de Obra en estado VIGENTE.
- Constraints SQL de tipos, folio, fechas, rangos, suma, impuesto y coherencia completa de metadatos de reversión. FK protegidas y sin CRUD en Admin.

### CierreSinCobro

- OneToOne PROTECT con Obra, FK PROTECT a cortesía de esa misma Obra, actor AF, timestamp y motivo obligatorio.
- Exige finalización, origen aprobado, cierre de costos y cortesía SIN_COBRO existente. La autorización histórica corresponde al servicio de Obras; no se invalida porque el Supervisor cambie de rol posteriormente.
- Rechaza cualquier documento histórico, vigente o revertido. No genera importe cero, ingreso, pago ni altera precios, costos o cortesía.
- Inmutable, sin edición ni eliminación. Impide registro documental posterior.

### FinanzasEvento

- Tipos `DOCUMENTO_REGISTRADO`, `DOCUMENTO_REVERTIDO`, `SIN_COBRO_REGISTRADO`.
- Constraint de exactamente una referencia pertinente: documento para los dos primeros, cierre sin cobro para el último. Actor PROTECT, motivo, snapshots por lista permitida, fecha de servidor.
- Snapshots sin objetos anidados, credenciales ni detalles operativos. Serializer con filtrado defensivo.
- Guardias de modelo/queryset contra save de registros existentes, update, delete y bulk. Toda mutación/evento es atómica.
- La reversión actualiza únicamente estado y metadatos desde el servicio, con lock y validación; no hay PATCH libre. Los guardias ORM no sustituyen permisos SQL: un DBA puede eludirlos con SQL directo, igual que en otros históricos del backend.

Migración nueva: `finanzas.0001_facturacion_documental`, dependiente de `obras.0011_cierre_costos_finalizacion` y usuario swappable. No crea cuentas, documentos ni eventos ficticios y no migra costos a ingresos.

## API y permisos

Todos los endpoints requieren Bearer JWT válido; se conservan revocación de SPEC-006, roles, cookies y CSRF existentes. El permiso relee actividad y rol en PostgreSQL y no admite elevación por flags/grupos/claims.

| Método | Ruta bajo `/api/finanzas/` | Rol | Éxito |
|---|---|---|---|
| GET | `documentos/` | G/AF | 200, paginada |
| POST | `documentos/` | AF | 201 |
| GET | `documentos/{id}/` | G/AF | 200 |
| POST | `documentos/{id}/revertir/` | AF | 200 |
| GET | `documentos/{id}/historial/` | G/AF | 200, paginada |
| GET | `obras-elegibles/` | AF | 200, paginada |
| POST | `obras/{obra_id}/registrar-sin-cobro/` | AF | 201 |
| GET | `obras/{obra_id}/estado-financiero/` | G/AF | 200 |

G no escribe. S/T reciben 403 incluso con `is_superuser`/`is_staff`, también en OPTIONS. Anónimo, sesión revocada o cuenta inactiva reciben 401. No se crean rutas de 007B. PUT/PATCH/DELETE no están implementados (405 para AF autorizado).

### Entradas

POST documento, todos obligatorios:

```json
{
  "obra": 123,
  "tipo_documento": "FACTURA_AFECTA",
  "folio_externo": "123456",
  "fecha_emision": "2026-11-10",
  "fecha_vencimiento": "2026-12-10",
  "monto_neto": "2080.22",
  "monto_impuesto": "100.13",
  "monto_total": "2180.35",
  "referencia_respaldo": "Ubicación interna de documento externo verificado"
}
```

**Ejemplo ficticio de formato, no instrucción para inventar un documento.** Sustituir ID, fechas, folio e importes por los del respaldo real de un entorno de pruebas. El impuesto ilustrado no asume 19%. Neto debe coincidir con el origen aprobado; no se cambia el presupuesto para acomodarlo.

POST reversión: `motivo` (hasta 2000) y `referencia_rectificacion_externa` (hasta 500), ambos no vacíos. POST sin cobro: únicamente `motivo_registro` (hasta 2000). Texto normalizado con trim salvo folio, que exige valor exacto sin espacios.

Se rechazan campos desconocidos o administrados (`estado`, `actor`, `registrado_por`, timestamps, presupuesto, cliente, moneda, saldo, pagos, etc.). El ID de Obra en JSON es entero positivo real, no string/boolean/float. Dinero: exclusivamente strings decimales no negativos, sin exponentes, coma, separadores, NaN/Infinity ni más de dos decimales. No se redondean entradas inválidas. Fechas: exactamente `YYYY-MM-DD`.

### Lecturas

- Documento incluye `naturaleza=REGISTRO_ADMINISTRATIVO_DOCUMENTO_EXTERNO`, `origen`, datos externos, importes con dos decimales, estado y metadatos de registro/reversión. Actores solo por ID, no objetos de Usuario.
- `origen`: ID/código Obra y Presupuesto, identificación mínima del Cliente (ID, nombre legal, tipo/número/país/tipo extranjero), moneda CLP, neto aprobado, finalización y cortesía solo ID/tipo.
- Sin contactos completos del Cliente, costos, turnos, tarifas, evidencias privadas ni justificación operativa de cortesía.
- Historial documental en su ruta paginada; evento del cierre sin cobro incluido en `cierre_sin_cobro.eventos` del estado financiero, accesible a G/AF.
- Estado financiero: `PENDIENTE_FACTURACION`, `PENDIENTE_REGISTRO_SIN_COBRO`, `SIN_COBRO` o `DOCUMENTADO`. Incluye documento vigente/cierre cuando existen. Sin montos ficticios, campos de cobro ni saldo. Una reversión sin reemplazo vuelve a pendiente, conservando el historial documental.
- Listado documental fijo 25, orden `(-registrado_en,-id)`. Filtros permitidos: `estado`, `tipo_documento`, `obra`, `cliente`, `fecha_emision_desde`, `fecha_emision_hasta`, `page`. Rechaza desconocidos, repetidos, IDs inválidos, fechas o rangos inválidos y página no positiva.
- Elegibles: finalizadas, origen aprobado y cierre de costos, sin cortesía, cierre sin cobro ni documento vigente; acepta solo page, orden `(-finalizado_en,-id)`. Una Obra con documento revertido puede reaparecer para re-registro con otro folio.
- Uso de select_related/prefetch_related y EXISTS; pruebas de consultas acotadas en páginas de 25.

### Errores

400 para entradas/filtros/IDs fuera de contrato, incluido respaldo ausente de reversión; 404 recurso numérico válido inexistente; 409 con `code` estable:

- `obra_no_finalizada`, `presupuesto_no_aprobado`, `cierre_costos_requerido`.
- `cortesia_sin_cobro`, `cortesia_requerida`, `sin_cobro_ya_registrado`.
- `documento_duplicado`, `documento_ya_revertido`, `monto_no_coincide`.
- `origen_inconsistente`: protección ante alteración externa de FK durante la espera por lock.

`monto_no_coincide` es 409 para discrepancia con presupuesto persistido; formato/suma/precisión inválidos son 400. Doble reversión o cierre devuelve 409 sin evento duplicado. Solo se traducen IntegrityError de unicidades conocidas; los inesperados se propagan y revierten la transacción.

## Concurrencia y decisiones

1. `transaction.atomic`, raíz Presupuesto → Obra, después documento/cierre y evento. La lectura preliminar del presupuesto se revalida después de bloquear. Finanzas nunca llama mutaciones de Obras ni bloquea Usuario antes de la raíz.
2. Actor releído al entrar y después de esperar por Obra; se comprueba versión frente al objeto autenticado. Sin locks de Usuario ni mutex de Usuarios 006.
3. Unicidad por Obra y folio en PostgreSQL, además del chequeo controlado. Folios entre Obras distintas compiten en el índice único; conflicto conocido se traduce después del rollback.
4. Reversión y re-registro se serializan por la misma Obra. Reversión no borra ni altera el respaldo/importes originales; requiere rectificación externa comprobada por AF, no certificada por FYAG.
5. No hay modelo de pagos en 007A. Al incorporar 007B deberá añadirse el guard de pagos activos en la reversión bajo el lock del documento; no se anticipan tablas ni saldos ahora.
6. Reglas tributarias MVP no equivalen a criterio contable profesional. FYAG no comprueba en SII autenticidad, receptor, folio ni rectificación; AF debe cotejarlos fuera de la aplicación. Una referencia es texto, nunca URL pública automática ni descarga remota.
7. Para nuevos escritores SQL/ORM externos debe respetarse este protocolo. La inmutabilidad y elegibilidad entre tablas se garantizan por servicios y permisos de aplicación; las constraints cubren las invariantes locales y unicidades.

## Verificación

Entorno comprobado: Django **5.2.19**, PostgreSQL **18.6** (`connection.vendor=postgresql`, `pg_version=180006`). Pruebas sin SQLite, sleeps ni migraciones antiguas reescritas.

Comandos ejecutados con prefijo `docker compose exec -T backend`:

| Comando | Resultado |
|---|---|
| `python manage.py check` | `System check identified no issues (0 silenced).` |
| `python manage.py makemigrations --check --dry-run` | `No changes detected` |
| `python manage.py migrate --noinput` | Primera aplicación: `Applying finanzas.0001_facturacion_documental... OK`; segunda ejecución: `No migrations to apply.` |
| `python manage.py test apps.finanzas --noinput` | **37 pruebas, 12.317 s, OK** |
| `python manage.py test --noinput` | **587 pruebas, 97.512 s, OK** sobre el código final; base temporal creada desde cero y destruida al terminar. Primera regresión previa: 587 pruebas, 96.962 s, OK. |
| `python manage.py showmigrations finanzas` | `[X] 0001_facturacion_documental` |
| `git diff --check` (host) | Sin errores de whitespace; avisos LF/CRLF de Git en Windows |

La primera ejecución específica de 26 pruebas detectó una fixture de estados con inicio nulo al volver a EN_PROCESO; se corrigió la fixture, sin modificar reglas de Obras. Después pasó la suite específica de **32 pruebas en 9.765 s** y luego la ampliación a 37. Las advertencias de emisión de tokens para usuario inactivo de la suite global corresponden a tests negativos existentes de Usuarios, no a un login autorizado ni a fallos.

Las pruebas cubren finalización real de Obras, precio de múltiples ítems distinto al costo interno, afecta/exenta, fecha Santiago aun con zona activa UTC, permisos de cuatro roles, JWT revocado, cliente inactivo histórico, límites monetarios, folios, filtros/URLs, paginación, privacidad, rollback, constraints SQL y migración con historia preservada.

Carreras: documentos sobre misma Obra, mismo folio/tipo entre Obras distintas, doble reversión, reversión seguida de nuevo registro y doble cierre sin cobro. Conexiones independientes (`TransactionTestCase`), barreras Event, timeouts y espera observada mediante `pg_blocking_pids`.

No se ejecuta GitHub Actions porque no hay push/PR; no se afirma CI remoto verde. Pruebas manuales/Postman posteriores a revisión, no presentadas como ejecutadas.

## Procedimiento manual / futura suite Postman

1. Levantar el entorno habitual con PostgreSQL; aplicar `docker compose exec -T backend python manage.py migrate --noinput`. Usar cuentas propias del entorno de revisión para G/AF/S/T. No crear cuentas ni documentos fiscales ficticios en migraciones.
2. Login con el flujo existente: GET `/api/auth/csrf/`, POST login con cookie CSRF y `X-CSRFToken`. Guardar access en variable local no compartida; conservar cookie HttpOnly y CSRF rotado para refresh/logout. No incluir secretos en colección, ZIP, capturas o logs.
3. AF: GET `/api/finanzas/obras-elegibles/`; elegir Obra finalizada con respaldo externo verificado y neto aprobado. Si no existen datos elegibles, prepararlos mediante los flujos autorizados de Comercial/Obras, no SQL de alteración de costos/estados.
4. GET estado financiero: pendiente, sin saldo ni ingreso cero. POST documento con su respaldo exacto → 201, naturaleza administrativa y VIGENTE. Confirmar neto/identidad de origen, importes dos decimales, evento y ausencia de detalles operativos. La Obra y los costos no deben cambiar.
5. Repetir sobre misma Obra o mismo folio/tipo en otra → 409 documento_duplicado. Probar neto diferente (total aritméticamente válido) → 409 monto_no_coincide; suma errónea, números JSON, exponentes, precisión extra, fecha futura o campo servidor → 400.
6. G puede listar/ver/historial/estado, pero no registrar/revertir/sin cobro ni consultar elegibles. S/T → 403 incluso OPTIONS. Sin access → 401. Cambiar rol de AF mediante Usuarios y comprobar que el access antiguo obtiene 401, nuevo login con rol sin permiso obtiene 403.
7. Reversión sin referencia externa → 400. Solo después de rectificación externa realmente acreditada: POST revertir con motivo/referencia → 200 REVERTIDO; mismo total y folio, dos eventos. Repetir → 409. Estado vuelve a pendiente; folio viejo no reutilizable. Nuevo respaldo con otro folio permite nuevo registro vigente.
8. Otra Obra con cortesía autorizada por Supervisor y finalizada: facturar → 409 cortesia_sin_cobro; estado pendiente registro sin cobro. POST registrar-sin-cobro con motivo → 201 SIN_COBRO y evento visible a G/AF. No cambia precio/costo, no crea documento ni pago. Repetir o intentar facturar después → 409. Si ya existía documento histórico, el cierre debe rechazarse.
9. Probar filtros combinados, repetidos/desconocidos, página cero y segunda página; orden estable y 25 por página. Probar PUT/PATCH/DELETE con AF → 405. `/api/finanzas/cobranzas/` y rutas de pagos → 404 (007B no implementado).
10. Revisar código y contratos antes de construir/aprobar la colección Postman. Los casos negativos de cortesía con documento previo y las carreras están automatizados con fixtures/conexiones controladas; no forzar esas inconsistencias manualmente en producción.

## Paquete

`revision-spec-007a.zip`: entrega incremental con archivos nuevos/modificados de este trabajo y este informe, rutas relativas al repositorio. Excluye `.env`, secretos, DB, dependencias, cachés, frontend, `.git`, entregas anteriores y scripts ajenos. No es un despliegue completo: aplicar sobre la rama base revisada.
