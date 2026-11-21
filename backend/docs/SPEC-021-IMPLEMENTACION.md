# SPEC-021 — Egresos y flujo registrado

FYAG registra desembolsos **ya realizados fuera del sistema**; no transfiere
dinero. No registrar cuentas bancarias completas ni usar anulación para simular
una devolución. La Obra es opcional e informativa: no genera ni modifica costos,
inventario, documentos, pagos recibidos o cierres.

## API y consumo

Contrato: [OpenAPI](openapi/SPEC-021-v1.json). Bajo `/api/finanzas/`:

| Método | Ruta | Acceso |
| --- | --- | --- |
| GET / POST | `egresos/` | AF y Gerencia leen; solo AF registra |
| GET | `egresos/{id}/` | AF / Gerencia |
| POST | `egresos/{id}/anular/` | AF |
| GET | `egresos/{id}/historial/` | AF / Gerencia |
| GET | `flujo-dinero/resumen/` | AF / Gerencia |

JWT versionado; cada acceso revalida rol, actividad y bloqueo operativo
persistidos. No hay bypass de superusuario. Respuestas `private, no-store`,
`Vary: Authorization`. GET no escribe. Campos desconocidos/administrados,
queries desconocidas, repetidas o vacías se rechazan. Listado e historial usan
páginas de 25; `page` es entero positivo canónico (página inexistente: 404).
No se permiten filtros de listado en detalle/historial/resumen.

- Montos JSON: strings decimales, sin float ni redondeo, positivos y máximo
  `999999999999999999999999999999999999.99`; salida con dos posiciones.
- Fecha de alta: civil `YYYY-MM-DD`, no futura en `America/Santiago`.
- Concepto/beneficiario: 200 caracteres; referencia de respaldo/corrección:
  500; observación/motivo: 2000. Textos normalizados mediante trim.
- Categorías: MATERIALES, TRANSPORTE, SERVICIOS, ARRIENDO, OTROS.
- Medios: TRANSFERENCIA, EFECTIVO, TARJETA, OTRO.
- `observacion` omitida equivale a `""`; `obra` omitida equivale a `null`.
- Listado: `categoria`, `medio`, `obra`, `activo=true|false`, `desde`, `hasta`,
  `page`; orden fecha de pago DESC, ID DESC. Sin `activo` incluye ambos estados.
- Fechas de filtro deben venir juntas; resumen las exige. Rango inclusivo de
  máximo 366 días. Filtrar períodos futuros es válido (no implica registrar pagos
  futuros). Importes agregados pueden superar el máximo de un movimiento.

## Transacciones e integridad

Alta y evento son atómicos. La unicidad PostgreSQL serializa UUID global dentro
de Egreso, independiente de UUID de pagos/inventario. La huella SHA-256 incluye
el payload validado y normalizado; mismo UUID/payload devuelve el alta original
(201 inicial, 200 replay; `Idempotency-Replayed: false|true`), incluso después
de anular. GET detalle devuelve el estado actual. Otra solicitud con ese UUID:
409 `idempotencia_conflictiva`. No reintentar una corrección con la misma clave.

Anulación bloquea únicamente Egreso; revalida autorización después de esperar,
actualiza estado y crea un solo evento. Segunda anulación: 409
`egreso_ya_anulado`. UUID perdedor se recupera después del rollback; solo se
traduce la constraint esperada `fin_egreso_idempotencia_unica`.

No se toman locks explícitos de Usuario, Presupuesto, Obra, Documento o Pago.
La FK informativa Obra toma el KEY SHARE nativo de PostgreSQL: puede esperar
un FOR UPDATE previo sobre Obra, pero no introduce una dependencia inversa
Egreso → raíz de Obras. No se requiere Obra finalizada.

El resumen calcula ambos SUM y la verificación de origen en **un SELECT**:
snapshot MVCC único aun dentro de READ COMMITTED exterior. No filtra pagos por
estado documental para ocultar inconsistencias. Reporta 409
`origen_inconsistente` si un pago activo del período tiene documento no vigente,
precede su emisión o el total activo del documento excede su importe.
Los SUM usan NUMERIC PostgreSQL; resta Decimal con precisión 80. El resultado
puede ser negativo y **no es utilidad, caja disponible ni saldo bancario**.

400: contrato/filtros/UUID inválidos; 401: sesión ausente/revocada/inactiva/
bloqueada; 403: rol no autorizado; 404: egreso/página no encontrado; 405: método
no admitido; 409: conflictos anteriores. Los errores de validación son mapas
de campos; autenticación/permisos usan `detail`; conflictos usan `code/detail`.

## Migración y comprobación

`finanzas.0003_egresos_flujo_dinero` añade únicamente tablas, índice y constraints
021. No transforma historia anterior. Si hay egresos, impide revertir esta
migración para no destruir su historial. Realizar backup y revisión operativa
antes de cualquier cambio de esquema en un entorno real; esta entrega no despliega.

Pruebas permanentes en `apps.finanzas.tests.test_egresos*` y
`test_flujo_dinero`: seis roles, seguridad persistida, validación, conservación
de historia, migración desde 0002 y carreras con locks PostgreSQL observados.
Las pruebas de snapshot bloquean el propio SELECT mediante advisory lock y
confirman altas/anulaciones de pago y egreso desde otra conexión antes de
liberarlo. El runner instala las migraciones desde esquema vacío.

```sh
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py migrate --noinput
python manage.py test apps.finanzas --noinput
python manage.py test --noinput
```

Usar PostgreSQL y las dependencias del Compose QA aislado (Mongo y ClamAV para
regresión completa). Los tests C2 requieren el laboratorio exclusivo previsto
por Usuarios, no habilitar ese modo en producción. El workflow actual corre en
PR/main: publicar una feature sin PR no acredita una ejecución de CI.

## Postman

Importar `postman/SPEC-021.postman_collection.json` y
`postman/FYAG-Beta.postman_environment.json`. Definir `base_url` (sin slash
final), tokens AF/Gerencia/rol denegado, fechas `desde/hasta/fecha_pago` y
`idempotency_key` UUID nuevo antes de ejecutar. No guardar tokens reales en Git.
Ejecutar en orden sobre QA: alta, replay, consultas, resumen, colisión,
anulación, replay posterior y doble anulación. La colección conserva `egreso_id`
y la respuesta original para comprobar replay; los ejemplos no ejecutan pagos.
