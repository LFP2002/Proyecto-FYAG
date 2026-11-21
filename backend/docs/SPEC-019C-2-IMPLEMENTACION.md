# SPEC-019C-2 — Mermas de Bodega y Obras

Base: `main` `9dc08097599649ae386c0c2a9024f5c161d73647`.
Rama: `feature/backend-019c2-mermas-bodega-obras`. Sin cambios en SPEC,
frontend, Finanzas, Obras, Usuarios o migraciones históricas. Sin PR, merge o
despliegue. Esta entrega no agrega compras, archivos, notificaciones o ERP.

## Persistencia y estados

`Merma` comparte almacenamiento con ámbitos inequívocos BODEGA/OBRA y constraints
de origen: MB sin Obra/entrega/actividad; MO con Obra/entrega derivadas, sin corte
físico ni operación nueva. Cantidad NUMERIC(12,3), unidad histórica, tipo, motivo,
referencia, actividad, informante/fecha servidor, UUID y huella de creación.
MB guarda el último movimiento físico observado. Solo MB APROBADA puede tener
operación OneToOne. `OperacionMaterial.merma_bodega` identifica el origen físico
en sentido inverso; todos los actos anteriores mantienen null.

`MermaEvento` es append-only: una CREACION y máximo una APROBACION/RECHAZO.
La inserción del evento proyecta estado, decisor, fecha, motivo y operación en
`Merma`. Originales y eventos no se editan/eliminan; decisión completa, sin
cantidad parcial, cancelación, reapertura o reclasificación como devolución.
Rechazar y volver a informar es el procedimiento para corregir cantidades.

Tipos MB: DANO, VENCIMIENTO, EXTRAVIO, DIFERENCIA_CONTEO, OTRA.
Tipos MO: CORTE_NO_REUTILIZABLE, DANO_EN_OBRA, EXTRAVIO_EN_OBRA, OTRA.
El motivo debe describir pérdida/no reutilización; no se intenta inferir
semánticamente la explicación del texto libre. MB requiere referencia interna;
MO actividad y referencia opcional. Sin adjuntos nuevos.

## MB: baja física y pérdida histórica

Bodeguero informa artículo activo; guarda unidad y último movimiento bajo lock,
sin reservar ni bajar stock. AF aprueba solo cuando el artículo sigue activo,
la unidad corresponde, existe stock suficiente, el saldo está completamente
valorizado y existe promedio. Compara el último movimiento con el corte original:
si cambió, `409 corte_desactualizado`, sin usar ciegamente recepciones posteriores.
Una valoración sin movimiento no invalida corte: se usa el promedio oficial
vigente releyéndolo bajo lock. Rechazar no depende del corte/stock/valoración o
actividad actuales del artículo.

Aprobación en una transacción: Op MERMA → Movimiento MERMA → evento/proyección.
La Op congela costo unitario, saldo valorado anterior/posterior y promedio
anterior/posterior. El trigger de Op actualiza valoración; el AFTER físico
heredado aplica el saldo desde el movimiento. No existe segunda resta en Python.
Promedio restante igual al anterior; null al agotar. Cantidad positiva y resta
exacta. Conciliación al commit: `INGRESO + DEVOLUCION - SALIDA - MERMA`.

La pérdida se calcula con Decimal, precisión local 60, HALF_UP a centavo, a
partir de cantidad y precio históricos inmutables. No se redondea un positivo
a cero; precio oficial cero sí es legítimo. El total calculado no crea otra
tabla contable. AF queda como actor de Op/movimiento y evento; la observación
física identifica ID de merma y Bodeguero informante. El motivo completo de
decisión permanece en evento (sin truncar al agregar prefijos).

No genera GastoObra, eventos de costos, Egreso ni PagoDocumento. Es pérdida
interna de existencias, no dinero pagado. B nunca recibe campos de costo/importe.
AF/G reciben precio congelado e `importe_perdida` si aprobada; null antes o al
rechazar, sin exponer estimaciones cambiantes como pérdida confirmada.

## MO: clasificación, no nuevo costo ni movimiento

Técnico participante activo informa exclusivamente con ID de ENTREGA 019B real.
Obra/artículo/unidad se derivan de esa entrega; cliente no decide estas relaciones.
Obra EN_PROCESO/SUSPENDIDA, cantidad hasta la entregada. Pendiente no reserva
clasificación ni devolución. Al aprobar se releen informante activo/participante,
entrega, gasto BODEGA_019B vigente y cantidades disponibles bajo raíz de entrega.
Rechazar permite informante desasignado, pero solo en Obra operativa.

Solo se escriben `Merma` y `MermaEvento`: no Op nueva, movimiento, saldo,
valoración, gasto, evento económico, control/cierre, pago o egreso. El costo
original de despacho no cambia por clasificar. S/G ven costo histórico de la
entrega e `importe_informativo_no_aditivo`; T no recibe ninguno. Ese importe no
se suma a agregados de Obra ni flujo de dinero. Las unidades no devueltas y no
clasificadas no se presentan como necesariamente usadas.

Ejemplo vinculante, 6 m a precio histórico 100:

- Devolver 2 reutilizables: stock recupera 2, gasto neto = 4 × 100.
- Aprobar MO 2 inutilizables: stock no cambia otra vez, gasto neto = 6 × 100;
  importe informativo MO = 200, no se agrega de nuevo.

La historia permanece accesible por su autor después de desasignación o cierre.
Pendiente no impide finalizar; finalizada no permite aprobar ni rechazar y no
reabre el cierre retrospectivamente.

## Retornos 019B y compatibilidad C1

Por entrega se impone `MO aprobadas + devoluciones físicas recibidas <= entregada`.
La aprobación MO y ambos caminos 019B bloquean la entrega original; PostgreSQL
verifica también INSERT directo antes del validador 019B/artículo/gasto.

Nueva autorización de devolución: cantidad hasta `entregada - MO aprobadas -
todas las cantidades previamente autorizadas`, incluidas las ya recibidas.
Recepción: cantidad hasta el remanente de autorización y `entregada - MO aprobadas
- todas las devoluciones recibidas`. Aplica incluso a autorizaciones anteriores a
MO. La cantidad autorizada histórica nunca se reduce, borra ni anula.

GET `autorizaciones-devolucion/` añade solo `cantidad_recibible_efectiva`:

`max(0, min(autorizada - recibida_de_esa_autorizacion,
            entregada - MO_aprobadas - recibidas_totales))`.

Se calcula con subqueries correlacionadas en un SELECT, sin N+1 ni lecturas
parciales entre agregados. POST/replay conserva serializer original 019B.
Un 409 controlado rechaza exceso antes de efectos; SQL vuelve a comprobarlo.
`cantidad_devuelta` del gasto sigue siendo exclusivamente devolución física.
Despacho, valoración, autorización C1 y UUID originales se conservan sin otro
motor. El catálogo físico 019A/B admite MERMA de Bodega sin costos públicos.

## API y seguridad

Prefijo `/api/inventario/`, trailing slash:

| Ruta | Métodos | Lectura | Crear | Decidir |
| --- | --- | --- | --- | --- |
| `mermas-bodega/` | GET/POST | B/AF/G | B | — |
| `mermas-bodega/{id}/` | GET | B/AF/G | — | — |
| `mermas-bodega/{id}/decidir/` | POST | — | — | AF |
| `mermas-obra/` | GET/POST | T propias; S/G | T participante | — |
| `mermas-obra/{id}/` | GET | T propia; S/G | — | — |
| `mermas-obra/{id}/decidir/` | POST | — | — | S |

Sin acceso cruzado B/MO, AF/MO o S/MB; TI no accede. Gerencia solo lectura.
Scope T aplicado en SQL antes de obtener/paginar; ajena e inexistente mismo 404.
Sin stock/costo/gasto en proyección T; B sin economía aun en historial/errores.

POST MB: articulo/cantidad/tipo/motivo/referencia_respaldo/clave_idempotencia.
POST MO: entrega/cantidad/tipo/motivo/actividad/clave_idempotencia, referencia
opcional. Decidir: decision APROBAR|RECHAZAR/motivo/clave_idempotencia.
Bodies cerrados. No acepta actor, precio, fecha, estado, cantidad parcial o gasto.
IDs positivos BIGINT; strings Decimal hasta 999999999.999, tres posiciones máximo;
sin float/exponentes/truncamiento. Motivo/actividad 2000, referencia 150; trim,
sin controles Unicode. Las referencias opcionales vacías se preservan vacías.

GET: ID ASC, páginas de 25; filtros estrictos page/articulo/estado/tipo y para
MO obra/entrega. No filtros de otros actores/economía. Detalle/POST sin queries.
GET no escribe. Cache private, no-store y Vary Authorization, también en errores.
400 datos/filtros; 401 sesión; 403 rol; 404 scope/referencia/página;
405 método; 409 estado/idempotencia. Conflictos `code/detail`, sin SQL interno.

Roles, actividad, sesion_version, credencial personal y bloqueos se releen de
persistencia, también tras esperas y antes de confirmar. Sin privilegios por
staff, superuser o claims JWT. Se reutilizan los controles 018/018C efectivos,
sin desactivar seguridad para QA.

## Idempotencia y orden de locks

UUID canónica por creación/decisión. Ambos ámbitos/acciones comparten dominio
C2 en eventos; huella SHA-256 incluye ámbito/acción/actor/payload normalizado.
Misma clave y carga normalizada: replay sin efectos, 200 y header
`Idempotency-Replayed: true`. Primera creación 201, decisión 200, header false.
Replay creación conserva imagen PENDIENTE aunque GET ya muestre decisión.
Otra carga/actor/acción: 409 idempotencia_conflictiva. Una segunda decisión con
otra clave: 409 merma_ya_decidida. Recurso fuera del ámbito: 404.

- C2 adquiere UUID advisory namespace **1904** antes de recursos.
- MB aprobación genera UUID física independiente en namespace **1900** (dominio
  019A/B), antes de artículo; nunca reutiliza UUID creación/decisión.
- MB: artículo → existencia → valoración → merma. Sin locks de Obras.
- MO: Presupuesto → Obra → entrega original → merma/participante. Sin locks
  explícitos de artículo, valoración, gasto o controles de costos.
- Retornos 019B: UUID1900 → raíces → padres ID ASC (entrega precede a su
  autorización de devolución) → artículo → saldos → gasto/control.

No advisory nuevo tras recursos, ni artículo → Obra ni merma → entrega entre
circuitos. Las FK mantienen KEY SHARE nativos. Creación/decisión revalida sesión
después de esperas. El hash firmado de 32 bits solo serializa advisory; la UUID
completa y huella determinan identidad. B/C1 no adquieren namespace1904 en sentido
inverso. Los callers internos deben respetar orden global, sin componer servicios
desde locks de recursos ya adquiridos en sentido inverso.

## Migraciones y operación

- `0007_mermas`: tablas, enlaces nullable y ampliación controlada de tipos y
  constraints; no backfill de mermas/precios/actores.
- `0008_integridad_mermas`: originales/eventos inmutables, proyección SQL,
  comprobación diferida de creación/decisión/efecto MB y ausencia de Op MO,
  conciliación firmada y guard de devoluciones. Valida un movimiento físico
  exacto por Op MB. Los validadores anteriores permanecen para tipos antiguos;
  MERMA usa validadores específicos sin exigir Obra o actor B para una baja AF.

No modifica 0001–0006 ni migraciones de Obras. Upgrade conserva historia C1,
ingresos, entregas, devoluciones, gastos y proyecciones exactamente. Pruebas
heredadas también contrastan preservación financiera. Reversión sin historia
C2 restaura validadores anteriores; con cualquier merma se bloquea antes de
retirar validación/tablas. Nunca usar rollback destructivo con libro existente;
planificar backup y ventana de migración antes de un eventual despliegue.

## QA, contratos y pendientes

QA PostgreSQL/Mongo/ClamAV exclusivo `fyag-spec019c2-20261121`; sin bases de
usuarios ni datos reales. Pruebas permanentes `test_mermas*` y
`test_contrato_mermas.py`: ejemplo 6 m, stock/valoración/corte, devoluciones
antiguas/nuevas/parciales, replays, seis roles, SQL directo, upgrade, locks y
concurrencia con conexiones independientes y `pg_blocking_pids` observado.

Contratos verificables: `openapi/SPEC-019C-2-v1.json`; actualización compatible
GET retorno en `SPEC-019B-v1.json` y tipos físicos en `SPEC-019A-v1.json`.
Postman: `postman/SPEC-019C-2.postman_collection.json`, compatible con el
environment FYAG-Beta existente. Tokens/IDs locales vacíos; UUID/IDs de negocio
capturados al ejecutar. Sin Vault, IDs fijos ni credenciales. Ejecutar en orden
con artículo valorizado y entrega de 6 en Obra operativa con Técnico participante.
No depende de resultados manuales de compañeros.

Newman: **27 solicitudes, 92 aserciones, 0 fallos**. OpenAPI C2/B validado 3.1,
con **27 respuestas HTTP y 12 cuerpos válidos** conformes a sus esquemas.
Check sin problemas y makemigrations sin drift; migraciones limpias/upgrade OK.
OpenAPI 019A/C1 también válido; respuesta física MERMA contrastada con schema
019A, sin costos de Bodega. Suite dirigida Inventario/Obras/Finanzas/Usuarios:
**745 pruebas OK, 207.261 s**. Regresión completa final: **1269 pruebas OK,
356.735 s**, incluido el fixture literal Manguera QA en metros.
Se añadieron **61 pruebas permanentes**, incluidas **25 carreras PostgreSQL con
bloqueo observado**, más verificación del orden real de advisory locks MB.
Cubren ambas direcciones de MB/ingreso-despacho, valoración vigente, doble MB/MO,
MO/recepción-autorización, finalización, desasignación y revocación de sesión,
rol o actividad durante espera. Sin deadlocks, efectos duplicados o saldos
inconsistentes observados. Los conteos se restringen a fixtures propios.

Sin contradicciones funcionales materiales para corregir la SPEC. Costos MO
informativos no equivalen a nuevo gasto ni egreso real; pendientes no reservan
stock ni retornos. CI del futuro PR queda pendiente, no se declara aprobado.
