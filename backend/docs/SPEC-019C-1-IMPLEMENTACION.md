# SPEC-019C-1 — Solicitudes de materiales

Implementación desde `main` `23bd1b304c34d7cd743251761eba29ba452a5cfe`.
La SPEC ratificada permanece intacta; no incluye 019C-2, merma, compras,
proveedores, adjuntos, frontend ni funcionalidades financieras.

## Modelo e historia

`SolicitudMaterialObra` conserva Obra, solicitante real, artículo, unidad
histórica, cantidad original NUMERIC(12,3), justificación, UUID/huella y fecha
servidor. Su original no admite modificación o eliminación. Comienza PENDIENTE.

`SolicitudMaterialEvento` es append-only, con CREACION y una única APROBACION o
RECHAZO, actor y fecha propios, motivo, UUID/huella, cantidad y autorización
cuando corresponde. El trigger de inserción del evento proyecta la decisión en
la solicitud: estado, cantidad aprobada, motivo, Supervisor, fecha y autorización.
No hay edición pública ni segunda decisión. El detalle incluye el historial;
no se añadió otro endpoint de eventos.

APROBADA exige cantidad positiva hasta la solicitada y autorización OneToOne.
RECHAZADA no tiene cantidad aprobada ni autorización. PENDIENTE no tiene columnas
de decisión pobladas. `OperacionMaterial.solicitud_material` es nullable/OneToOne:
los actos 019B previos conservan null; las autorizaciones generadas desde 019C-1
se vinculan en ambos sentidos con su solicitud. No se publica esta relación en
los serializers históricos de Bodega.

Solicitar y decidir **no reservan ni mueven stock**, no comprueban precios,
no crean gastos, pagos o egresos, ni invalidan costos de Obra. Una solicitud
pendiente tampoco impide finalizar. La historia sigue visible para su autor
tras desasignación, desactivación del artículo o finalización de Obra.

## API real y RBAC

Contrato: [OpenAPI SPEC-019C-1-v1](openapi/SPEC-019C-1-v1.json).
Prefijo `/api/inventario/`, trailing slash obligatorio:

| Método y ruta | Técnico | Supervisor | Gerencia | B / AF / TI |
| --- | --- | --- | --- | --- |
| GET `articulos-solicitables/` | Sí | Sí | Sí | No |
| GET `solicitudes-materiales/` | Solo propias | Todas | Lectura | No |
| POST `solicitudes-materiales/` | Participante activo | No | No | No |
| GET `solicitudes-materiales/{id}/` | Solo propia | Sí | Lectura | No |
| POST `solicitudes-materiales/{id}/decidir/` | No | Sí | No | No |

El catálogo expone **solo id/codigo/nombre/unidad** de artículos activos. No
requiere stock ni valoración. Acepta `buscar` (codigo/nombre, máximo 150) y `page`.
Las solicitudes aceptan filtros `obra`, `articulo`, `estado` y `page`; ID ASC,
páginas de 25. Los filtros son cerrados, sin vacíos/repetidos. El scope de Técnico
se aplica en SQL antes de buscar o paginar; ajena/inexistente devuelven el mismo
404. No existe filtro de otro solicitante. Detalle y POST no admiten queries.

Creación: body cerrado `obra`, `articulo`, `cantidad`, `justificacion`,
`clave_idempotencia`. Decisión: `decision=APROBAR|RECHAZAR`, `motivo`,
`clave_idempotencia`; `cantidad_aprobada` obligatoria solo al aprobar, prohibida
incluso como null al rechazar. No se aceptan actor, fecha, estado, unidad,
precio, costo o autorización ajena.

IDs: enteros positivos BIGINT. Cantidades: strings positivos con hasta 9
enteros y 3 decimales, máximo `999999999.999`; salida con tres posiciones. Sin
floats, exponentes, signos ni truncamiento. Justificación/motivo: máximo 2000,
trim, no vacíos ni controles ASCII/Unicode. Actor y sellos temporales son del
servidor. No se amplió el rango ni la fórmula de costos 004B/019B.

La cuenta persistida debe estar activa, con rol autorizado, misma versión de
sesión, credencial personal y bloqueo operativo compatible con SPEC-018/018C.
Esto se revalida en servicios y tras esperas por locks. No se confía en claims,
flags staff/superuser ni objetos de Usuario desactualizados. No se añadieron
permisos del Técnico a catálogo general, existencias, movimientos, valoración,
gastos o Finanzas. Todas las proyecciones 019C-1 carecen de información económica.

GET no escribe; respuestas nuevas: `Cache-Control: private, no-store`,
`Vary: Authorization`, incluidos errores. 400: esquema/filtro inválido;
401: sesión no disponible; 403: rol sin permiso; 404: referencia inaccesible,
solicitud ajena o página inexistente; 405: método no publicado; 409: conflicto.
Los conflictos usan `code/detail`, sin mensajes SQL ni importes internos.

## Decisión e integración con 019B

Crear exige participante activo, Obra EN_PROCESO/SUSPENDIDA y artículo activo.
Una Obra ajena al Técnico responde 404. Antes de aprobar se releen bajo lock:
estado de Obra/solicitud, participación activa y rol/actividad del solicitante,
artículo y unidad histórica. Unidad cambiada después de solicitar: 409, no se
reinterpreta silenciosamente la cantidad original. Rechazar puede resolver una
solicitud cuyo Técnico fue desasignado o cuyo artículo se desactivó, pero sigue
requiriendo Obra operativa y Supervisor válido.

Se extrajeron únicamente `_huella` y `_autorizar_entrega_bloqueada` de 019B.
El servicio público 019B usa el mismo núcleo. La aprobación lo invoca dentro
de su transacción con raíces/artículo ya bloqueados y UUID independiente. El
núcleo no adquiere nuevos advisory locks; conserva validación de permisos y los
triggers 019B. No se duplicó el despacho ni se modificaron contratos antiguos.

Bodega consulta la autorización normal y despacha mediante `entregas/` 019B.
Siguen aplicándose remanentes, despachos parciales, stock suficiente, valoración
completa, promedio vigente congelado, UUID de ejecución y un único GastoObra por
despacho. La aprobación no garantiza disponibilidad. El Supervisor nunca aparece
como Técnico solicitante; el Bodeguero sigue siendo ejecutor físico del gasto.

## Idempotencia, locks e integridad

UUID en body. Creación y decisiones comparten dominio de unicidad en el libro
de eventos **019C-1**. La huella SHA-256 incluye acción, actor real, referencia y
payload normalizado. No es el dominio de UUID de ejecuciones físicas 019B.

- Crear: 201 inicial; replay idéntico 200 con imagen original PENDIENTE, incluso
  después de decidir. GET presenta estado actual.
- Decidir: 200 inicial y replay; repetir UUID/actor/carga retorna la misma
  decisión y autorización, sin invocar de nuevo el núcleo 019B.
- `Idempotency-Replayed: false|true` distingue ambos casos.
- UUID con otra carga/acción/actor: 409 `idempotencia_conflictiva`.
- Otra clave contra solicitud ya decidida: 409 `solicitud_ya_decidida`.
- Cantidad aprobada superior a la original: 409 `cantidad_aprobada_excesiva`.
- Estado, participación, unidad o artículo incompatibles: 409 `estado_incompatible`.

Orden efectivo:

1. UUID 019C-1: advisory transaccional namespace **1903**, hash firmado de 32
   bits solo para serializar; comparación de UUID completa/huella en el libro.
2. Si es aprobación nueva, generar y bloquear UUID 019B en namespace **1900**,
   diferente de la UUID de creación y decisión. Siempre antes de raíces. Un
   replay sale antes de generar autorización; no adquiere nuevos efectos.
3. Presupuesto → Obra, mediante `_obra_bloqueada` propietario.
4. Solicitud → participante → artículo → estado requerido por núcleo 019B.

No hay advisory lock nuevo tras adquirir raíces/artículo. 019B no adquiere el
namespace 1903, por lo que no hay dependencia inversa B → C1. Cada operación
adquiere una clave por namespace. Los ingresos 019A siguen sin tomar locks de
Obras. Desasignación y finalización se serializan en las mismas raíces 004B.
Callers internos deben respetar este orden, sin componer servicios públicos
desde locks de recursos adquiridos en sentido inverso.

PostgreSQL impone estados/cantidades, textos/huellas y unicidad de eventos y
vínculos. Triggers protegen originales y eventos, verifican actor/origen y
proyectan la decisión. Triggers diferidos exigen creación auditada y concordancia
exacta entre decisión, proyección y autorización; impiden autorizaciones C1
huérfanas o reutilizar una autorización ajena. El trigger enlazado de Op corre
antes del trigger 019B para tomar raíz/solicitud/participante antes del artículo
también en INSERT SQL directo. Una autorización normal 019B con enlace null no
recibe restricciones C1 nuevas.

Fallos en evento/autorización revierten todo. Solo constraints conocidas
`inv_sol_integridad`/`inv_019b_integridad` se traducen a conflicto controlado;
IntegrityError inesperados no se ocultan. No se toman locks explícitos de Usuario;
las FK conservan sus KEY SHARE nativos y la sesión se relee después de esperas.

## Migraciones y verificación

- `inventario.0005_solicitudes_materiales`: dos entidades, constraints y FK
  nullable nueva en OperacionMaterial. Filas 019B previas conservan enlace null.
- `inventario.0006_integridad_solicitudes`: triggers de original/evento,
  proyección y confirmación diferida. No modifica migraciones anteriores.

No hay backfill de solicitudes, actores, precios o movimientos ficticios. El
upgrade prueba conservación exacta de artículos, saldos, valoraciones, movimientos,
autorizaciones, gastos, eventos, participantes, controles, cierres, documentos,
pagos y egresos anteriores. Una reversión con solicitudes existentes se bloquea
para preservar su historia. Antes de un despliegue real corresponde revisar
backup/ventana; esta entrega no despliega ni borra bases existentes.

QA exclusivo con PostgreSQL 18, MongoDB y ClamAV, proyecto Compose independiente.
Resultados sobre código final:

| Validación | Resultado |
| --- | --- |
| `manage.py check` | 0 problemas |
| `makemigrations --check --dry-run` | Sin diferencias |
| Migración limpia y upgrade desde 019B/021 | OK |
| Inventario + Obras | 327 pruebas OK |
| Backend completo | 1208 pruebas OK, 327.685 s |
| Carreras C1 con `pg_blocking_pids` observado | 13 aprobadas |
| Visibilidad antes/después de commit | 1 aprobada |
| Orden real de advisory locks frente a raíces | 1 aprobado |
| Newman | 30 solicitudes, 110 aserciones, 0 fallos |
| OpenAPI 3.1 y referencias | Válidos |
| Contraste HTTP/OpenAPI | 25 respuestas nuevas + 8 cuerpos válidos conformes |

Las 41 pruebas nuevas cubren creación/decisión, límites/errores, seis roles,
scope/historial, credenciales y bloqueos persistidos, SQL impropio, rollback,
finalización/desasignación, UUID iguales/distintos, sesiones revocadas durante
esperas y despacho real 019B con gasto único. No dependen de IDs de fixtures ni
conteos globales de solicitudes. Las suites heredadas se conservan intactas.

## Postman y restricciones

Colección: `postman/SPEC-019C-1.postman_collection.json`. Reutiliza el environment
existente `postman/FYAG-Beta.postman_environment.json`; no lo duplica. Variables
legibles de colección: `token_tecnico`, `token_otro_tecnico`, `token_supervisor`,
`token_bodega`, `token_ti`, `obra_id`, `articulo_id` y cantidades. Se reutilizan
`base_url`, `token_af`, `token_gerencia` del environment. Tokens/IDs reales solo
en valores locales, nunca en Git; no se usa Vault. Requiere Obra operativa,
participación activa, artículo activo y stock valorizado para el despacho.
Captura UUID/solicitud/autorización de las respuestas sin IDs fijos. Ejecutar en
orden sobre QA. Los resultados manuales de compañeros no son condición para
continuar el desarrollo; Newman ya se ejecutó en QA aislado.

No se detectaron contradicciones materiales que requieran modificar la SPEC.
No hay edición/cancelación de solicitudes ni revisión de decisiones confirmadas,
reservas o avisos automáticos. Aprobar no reabre Obras ni habilita despachos en
estados finales. CI queda **pendiente del PR** (workflow PR/main); no se declara
aprobado ni se crea PR, merge o despliegue desde esta implementación.
