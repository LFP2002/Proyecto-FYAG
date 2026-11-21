# SPEC-019B — Entregas y devoluciones vinculadas a Obras

## Alcance e identidades

FYAG mueve unidades físicas e imputa costos internos; **no transfiere dinero**.
No crea ni modifica Egreso, PagoDocumento, DocumentoCobro o flujo monetario.
No convierte gastos manuales históricos en consumos físicos ni deduplica por
texto. El Supervisor debe evitar registrar manualmente de nuevo un consumo ya
despachado por Bodega.

`OperacionMaterial` consolida los seis actos permitidos por §9.3: autorización
de entrega, entrega, autorización de devolución, recepción devuelta, valoración
de ingreso y regularización inicial. Es un libro inmutable con UUID, huella
SHA-256 de carga normalizada/acción/actor, cantidad/unidad, autor y fecha reales.
Sus FK identifican Obra, artículo, autorización, entrega original, ingreso y
gasto, según el acto. `MovimientoInventario.operacion` es OneToOne para SALIDA
y DEVOLUCION. Cada entrega tiene un único `GastoObra` MATERIAL con origen
`BODEGA_019B`; no se reutiliza un gasto de otra fuente.

Los actos con costo conservan precio aplicado y saldos/promedios anteriores y
posteriores. `EstadoValoracion` es una proyección SQL por artículo, con saldo
valorado/promedio y referencia histórica inmutable: saldo, último ID de
movimiento y fecha del corte. No existe una segunda fórmula de costos de Obra.

Las autorizaciones no reservan stock ni generan gastos. Sus remanentes se
derivan del libro: cantidad autorizada menos ejecuciones. Las autorizaciones de
retorno consumen el máximo retornable de su entrega, incluidas sus cantidades
pendientes: no es posible autorizar dos veces el mismo sobrante. Se admite
recepción parcial de cada autorización. No se publica edición/cancelación de
autorizaciones en este incremento.

## Precisión y valoración

- Cantidades NUMERIC(12,3), positivas, máximo `999999999.999`.
- Costo neto y promedio NUMERIC(15,2), máximo `9999999999999.99`.
- Entrada JSON exclusivamente string decimal, sin floats, exponentes,
  truncamiento ni exceso de escala; salida con tres/dos posiciones.
- El costo explícito cero es compatible con 004B y requiere el mismo respaldo
  de AF; nunca se asigna cero por omisión ni a existencias históricas.
- Cálculos Decimal con precisión 60 y `ROUND_HALF_UP` al centavo. PostgreSQL
  revalida con NUMERIC y `round(..., 2)`, equivalente para valores no negativos.
- Recepción valorada: `(saldo_valorado * promedio + cantidad * precio) /
  (saldo_valorado + cantidad)`. Si saldo previo es cero, inicia al precio nuevo.
- Entrega: congela promedio; no lo cambia para las unidades restantes. Al
  agotar saldo valorado, promedio vigente pasa a null.
- Devolución: suma cantidad al saldo valorado **al precio original del despacho**
  y recalcula promedio con la misma fórmula. El gasto conserva ese precio;
  su subtotal sigue siendo la propiedad 004B `(cantidad - devuelta) * precio`,
  redondeada HALF_UP. No se guardan subtotales alternativos.
- Se verifica representabilidad y subtotal antes de mover stock. Un valor
  positivo no puede desaparecer al redondearse a cero. Los errores de Bodega
  son genéricos, sin cantidades económicas, precios ni límites monetarios.

Este redondeo centesimal después de cada evento puede diferir de un libro
contable que acumule precisión ilimitada; es la política ratificada, no una
conciliación contable ni bancaria.

Cada recepción física 019A posterior al corte queda sin valorar hasta el acto
explícito de AF, con referencia de respaldo. Se valoriza por ID ascendente del
libro para ese artículo. Si existe stock histórico pendiente, primero se exige
regularización inicial (cantidad derivada del corte, costo, motivo y respaldo).
No inserta otro INGRESO ni cambia saldo físico. Si hay cualquier saldo físico
sin valorar, se bloquea **todo despacho**, no se escogen unidades arbitrarias.
Los retornos ya autorizados siguen permitidos con nuevos ingresos pendientes;
un artículo desactivado solo admite esos retornos y la valoración de su historia,
no nuevas autorizaciones, recepciones ordinarias o despachos.

## Locks, atomicidad y PostgreSQL

1. Advisory transaccional de UUID, namespace **1900**, compartido con ingresos
   019A; el hash firmado de 32 bits solo serializa, la UUID completa identifica.
2. En actos de Obra: **Presupuesto → Obra** (helper propietario 004B).
3. Autorización/entrega original, ordenadas por ID.
4. Artículo → existencia → estado de valoración.
5. Gasto/control de costos e historial.

Los ingresos 019A y valoraciones AF nunca adquieren después locks de Obras.
Catálogo conserva su namespace de código 1901. Las FK usan KEY SHARE nativo;
en actos vinculados sus raíces ya están bloqueadas. No se toman locks de Usuario.
No hay una dependencia artículo → Obra en rutas de ingreso/valoración.
Las carreras con finalización se serializan por las mismas raíces de 004B.

Los triggers nuevos reemplazan, sin editar 0001/0002, la validación de movimientos
y conciliación: `INGRESO + DEVOLUCION - SALIDA`. Se conservan no-mutar y saldo
confirmado al commit. Los triggers 019B también bloquean raíces antes del
artículo en escrituras directas, verifican estado/roles/unidad/remanentes,
calculan la proyección de valoración y comprueban los enlaces económicos.
Constraints diferidas exigen movimiento y evento 004B para cada ejecución y
correspondencia de `cantidad_devuelta`; un índice impide eventos duplicados.
Gasto/entrega y movimiento/operación son únicos. Se rechazan gastos huérfanos,
reasignación de vínculos, cruces de Obras y mutaciones de libros/eventos ligados.

Cada entrega/retorno llama una vez al helper de evento de gastos, que reutiliza
`services_costos.invalidar`. Versiones y validaciones previas se invalidan una
sola vez; la revalidación sigue siendo explícita del Supervisor. Los eventos
de gasto y las declaraciones de control causadas por Bodega conservan autor
Bodeguero real y origen `BODEGA_019B`. Los guards de servicios 004B rechazan
edición, anulación y devolución manual del gasto vinculado; gastos manuales
conservan sus reglas y su contrato de respuesta. El origen está identificado en
el modelo y en los snapshots del historial económico de la integración.

Toda escritura revalida sesión, actividad, rol y controles SPEC-018 persistidos,
tanto antes como después de esperas. Replay también exige autorización vigente.
Errores SQL inesperados se propagan; solo la constraint conocida
`inv_019b_integridad` se traduce a conflicto de negocio. Ningún fallo parcial
deja movimiento, promedio, gasto o evento confirmado.

## API, permisos y consumo

Contrato completo: [SPEC-019B-v1.json](openapi/SPEC-019B-v1.json).
Todas las rutas siguientes están bajo `/api/inventario/`:

| Ruta | POST | GET |
| --- | --- | --- |
| `autorizaciones-entrega/` | Supervisor | S/G/B, sin costos |
| `entregas/` | Bodeguero | S/G/B; B sin costos |
| `autorizaciones-devolucion/` | Supervisor | S/G/B, sin costos |
| `devoluciones/` | Bodeguero | S/G/B; B sin costos |
| `valorizaciones/` | Finanzas | AF/G |
| `regularizaciones-iniciales/` | Finanzas | AF/G |
| `estados-valorizacion/` | No | B/S/AF/G: solo artículo/estado |

Técnico y TI no reciben permisos. Staff/superuser/claims no elevan privilegios.
No se publican detalles de Obra ni campos económicos a Bodega, tampoco por
filtros, errores o movimientos 019A. AF no accede a las nuevas listas de Obras:
su lectura de precios se limita a valoración de inventario.

Todos los POST nuevos usan `clave_idempotencia` UUID en body, sin query params.
Unicidad global entre actos 019B e ingresos 019A, huella con actor real; carga
normalizada igual: 201 inicial, 200 replay con `Idempotency-Replayed: false|true`.
UUID con otra acción, actor o carga: 409. El replay de despacho sigue devolviendo
el acto original después de retornos; no incluye un gasto mutable anidado.

Cuerpos cerrados. IDs JSON enteros positivos BIGINT. Referencias: 150 caracteres;
motivos: 2000, trim y sin controles. En autorizaciones/ejecuciones pueden omitirse:
se registran textos administrativos de servidor; en valoración se exige respaldo,
y regularización exige además motivo explícito. No se aceptan actor, precio en
Bodega, unidad, fecha servidor, saldos, gasto o campos administrados.

GET nuevos: orden ID ASC, páginas de 25; filtros `articulo/page` y, en listas de
actos de Obra, `obra/autorizacion/entrega`. Rechazar desconocidos, repetidos,
vacíos y filtros de precios. Sin escrituras en GET; `private, no-store`,
`Vary: Authorization`. Los movimientos existentes ahora admiten filtro
`tipo=INGRESO|SALIDA|DEVOLUCION`, manteniendo los demás contratos 019A.

400: contrato inválido; 401: sesión ausente/no disponible; 403: rol no permitido;
404: referencia/página inexistente; 405: método no publicado; 409: estado, stock,
remanente, valoración pendiente/orden/rango o colisión UUID. Ver schemas de errores.

## Migraciones y operación

- `obras.0012_origen_gasto_bodega`: campo aditivo; filas anteriores quedan MANUAL.
- `inventario.0003_operaciones_material`: dos entidades, FK, índices/constraints
  y ampliación firmada del libro físico.
- `inventario.0004_integridad_materiales`: corte bajo lock de tablas, sin precio,
  actor ni movimiento ficticio; instalación de triggers y conciliación nueva.

El upgrade conserva filas previas de Obras, gastos, eventos, cierres, inventario,
pagos y egresos. No cambia migraciones históricas. Antes de un despliegue real,
prever backup y ventana para el corte transaccional. Reversión soportada solo
sin actos 019B: con historia, se bloquea antes de retirar protecciones/tablas.
No se ejecutó despliegue en esta entrega.

Postman: importar `postman/SPEC-019B.postman_collection.json` y reutilizar
`postman/FYAG-Beta.postman_environment.json`. Configurar localmente base_url,
tokens AF/G/T, tokens B/S, `obra_id` operativa y `articulo_historico_id` con saldo
anterior al corte aún no regularizado. Ejecutar en QA en orden. La colección
crea un artículo nuevo, ingresa, valora a dos precios, autoriza/despacha/devuelve,
regulariza historia y comprueba idempotencia y confidencialidad. No exportar
tokens reales al repositorio. El caso histórico requiere una fixture real de
upgrade, no se fabrica mediante una ruta productiva.

## Validación de la entrega

Pruebas permanentes `apps.inventario.tests.test_materiales*` y
`test_contrato_materiales`, más regresiones de Inventario/Obras. Cubren seis
roles, sesiones revocadas/inactivas/bloqueadas, proyecciones sin precios, límites,
promedio/retorno histórico, stock pendiente y regularización, eventos/guards SQL,
conservación de 021 y cierres, upgrade y diez carreras PostgreSQL observadas con
`pg_blocking_pids`, sin sleeps ni mocks de locks.

QA aislado usa PostgreSQL 18, MongoDB y ClamAV del Compose de premerge, sin
modificar `compose.yaml`. `check`: 0 problemas; `makemigrations --check --dry-run`:
sin diferencias. Migraciones de esquema vacío y upgrade desde 019A verificadas.
Suite dirigida Inventario/Obras: **286 pruebas OK**. Newman: **28 solicitudes,
95 aserciones, 0 fallos**. OpenAPI 3.1 y referencias válidos; **23 respuestas HTTP
de rutas nuevas** comprobadas contra sus schemas (otras cinco son rutas 019A).

Regresión backend completa sobre código final: **1167 pruebas OK en 301.117 s**,
sin fallos (PostgreSQL, MongoDB y ClamAV QA). El código ejecutado se contrastó
con un manifiesto externo antes de publicar; sin cambios en Finanzas/SPEC-021,
Usuarios, frontend ni migraciones anteriores. Solo se ajustaron dos pruebas
históricas de migraciones de Obras para consultar sus columnas históricas,
manteniendo la comparación exacta de datos y comprobando origen MANUAL.

CI queda pendiente del PR: el workflow actual solo se activa en PR/main. No se
crea PR, merge ni despliegue desde esta implementación.
