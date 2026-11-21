# SPEC-019A — contrato REST y consumo backend

Implementación efectiva para revisión; **matriz propuesta, sin autorización de
merge/despliegue**. [OpenAPI 3.1](openapi/SPEC-019A-v1.json).
No hay valorización, salidas, devoluciones, mermas, solicitudes ni integración con
gastos/Obras. Una entrada física **no** constituye factura, compra ni gasto.

## Roles y transporte

Nuevo rol persistido `BODEGUERO` (sexto): TI puede crearlo, filtrarlo y asignarlo
mediante servicios 006B/018 existentes; alta sigue inactiva, temporal y primer
cambio obligatorio. Cambio a/desde Bodeguero incrementa versión y revoca sesiones.
Los campos `rol` de administración y `role` en login/me pueden contener ese valor.
Los OpenAPI históricos A/C2 conservan su evidencia; el enum actualizado se publica
en `Rol019A` del complemento 019A.

| Acción | Bodega | Gerencia | Supervisor | Finanzas | Técnico | TI |
| --- | --- | --- | --- | --- | --- | --- |
| GET catálogo/existencias/movimientos | Sí | Sí | Sí | Sí | No | No |
| POST artículo/ingreso, PATCH artículo | Sí | No | No | No | No | No |
| Administrar usuarios | No | No | No | No | No | Sí, sin cambios |

`is_staff`, `is_superuser`, grupos y claims de rol no conceden permisos. Se releen
rol, actividad, versión, credencial PERSONAL y acceso persistidos. Estados ausentes
o incoherentes deniegan; no se reconstruyen por lecturas. C2 conserva su gate QA
apagado por defecto y todas sus guardas, sin activación productiva en 019A.

API con trailing slash, JSON UTF-8 y `Authorization: Bearer <access>` vigente.
Inventario no autentica mediante refresh-cookie/sesión Django; no introduce una
mutación autenticada solo por cookie. CSRF/cookies/CORS de login/refresh/primer
cambio/logout conservan contratos 018; no relajar TLS ni origins. Sin secretos en
URLs, logs, referencias o motivos. Referencia/motivo son texto operativo visible
a los cuatro roles lectores: no incluir información sensible ni datos personales.

## Operaciones implementadas

| Método / ruta | Entrada y salida |
| --- | --- |
| GET `/api/inventario/articulos/` | Página 25, orden id. `buscar` código/nombre (icontains literal), `activo=true|false`; ambos opcionales, incluye inactivos por defecto. |
| POST `/api/inventario/articulos/` | `{codigo,nombre,unidad,descripcion?,activo?}`; 201 artículo y existencia cero atómicos. activo default true. No movimiento ficticio de apertura. |
| GET `/api/inventario/articulos/{id}/` | 200 artículo, sin saldo editable ni precio. |
| PATCH `/api/inventario/articulos/{id}/` | Solo campos de catálogo anteriores; 200. Código/unidad solo cambian sin movimientos; si no 409. `activo=false` impide entradas nuevas. No-op (incluido `{}`) no cambia actor/fecha. |
| GET `/api/inventario/existencias/` | Página 25, orden articulo_id. Filtro exacto `articulo`. Sin POST/PATCH/DELETE ni creación implícita. |
| GET `/api/inventario/movimientos/` | Página 25, orden creado_en,id; `articulo`, `tipo=INGRESO`, `desde`, `hasta` opcionales. Fechas ISO civiles inclusivas America/Santiago, desde <= hasta. Sin escritura directa pública. |
| POST `/api/inventario/ingresos/` | `{articulo,cantidad,clave_idempotencia,referencia?,motivo?}`; 201 nuevo movimiento o 200 replay. |

IDs de body: enteros JSON positivos dentro de BIGINT, no bool ni strings. IDs de
URL/query: dígitos ASCII, positivos, sin ceros iniciales, dentro de BIGINT.
No `PUT` ni borrado físico. Métodos no publicados: 405; rutas inexistentes: 404.
Paginación `{count,next,previous,results}`, `page` positiva; tamaño fijo 25, no
page_size/ordering del cliente. Query desconocida, repetida o vacía: 400. Página
inexistente: 404. POST no acepta filtros; `page` se tolera sin efecto por el
validador común, como parámetro reservado de paginación.

### Artículo

```json
{"codigo":"tubo-cobre-10","nombre":"Tubo de cobre","unidad":"metro","descripcion":"Diámetro nominal 10","activo":true}
```

Código: hasta 50 caracteres, trim/minúsculas, ASCII
`[a-z0-9][a-z0-9._-]{0,49}`, unicidad global. Nombre hasta 150, descripción hasta
2000 (vacía válida); unidad hasta 30, trim/minúsculas, no vacía. No inventar
conversiones ni catálogo de unidades; distinguir unidades físicas correctamente
antes del primer ingreso. Texto no admite controles ASCII. `activo` debe ser bool
JSON real. Descripción default `""`. Campos desconocidos, precio, cantidad, saldo,
timestamps/actor del cliente: 400. Código duplicado normalizado: 400.

Respuesta artículo:

```json
{"id":12,"codigo":"tubo-cobre-10","nombre":"Tubo de cobre","descripcion":"Diámetro nominal 10","unidad":"metro","activo":true,"creado_por":8,"actualizado_por":8,"creado_en":"2026-11-20T18:00:00-03:00","actualizado_en":"2026-11-20T18:00:00-03:00"}
```

IDs/fechas del ejemplo son ilustrativos, no fixtures reales ni datos de despliegue.
Catálogo conserva actor/fecha de alta y última modificación efectiva, no ofrece
en 019A una API de versiones históricas de cada nombre/descripción. El libro de
movimientos sí conserva cada ingreso inmutable.

### Entrada idempotente

```json
{"articulo":12,"cantidad":"2.500","clave_idempotencia":"f2ed42da-29ef-4c37-b600-04f2b3521573","referencia":"Recepción física QA","motivo":"Ingreso de material verificado"}
```

Cantidad **solo string decimal**: de `"0.001"` a `"999999999.999"`, hasta 9 dígitos
enteros y 3 fraccionarios, punto, sin espacios/exponentes/comas. Nada de floats,
booleanos, negativos, cero, NaN/Infinity o redondeo de escala excesiva. Todos los
saldos/cantidades de salida son strings con **exactamente 3 decimales**.
Referencia opcional hasta 150, motivo opcional hasta 2000; ambos default vacío y
trim. Su obligatoriedad contextual y respaldo documental quedan para revisión
funcional, sin inventar compra/factura en esta fase.

```json
{"id":31,"articulo":12,"tipo":"INGRESO","clave_idempotencia":"f2ed42da-29ef-4c37-b600-04f2b3521573","cantidad":"2.500","saldo_anterior":"0.000","saldo_posterior":"2.500","referencia":"Recepción física QA","motivo":"Ingreso de material verificado","actor":8,"creado_en":"2026-11-20T18:02:00-03:00"}
```

- Generar UUID con guiones (36 caracteres) **antes** de enviar; conservarla para
  reconciliar la misma intención, no generar otra en retry por pérdida de respuesta.
- Clave global por operación, persistida sin expiración automática; mismo actor,
  artículo, cantidad decimal normalizada, referencia/motivo recortados → mismo ID,
  body y fecha original, sin segunda suma. `"2.5"` y `"2.500"` son equivalentes.
- 201 con `Idempotency-Replayed: false`; replay 200 con header `true`. Estado/rol
  actuales se comprueban también para replay; no se revela a otro actor.
- `saldo_anterior`/`saldo_posterior` son snapshots del movimiento, no prometen el
  saldo actual al hacer replay si hubo más entradas; releer existencias para la
  pantalla de disponibilidad y no sobrescribirlas con un snapshot histórico.
- Clave usada con distinto artículo, cantidad, actor, referencia o motivo → 409
  `idempotencia_conflictiva`. No reutilizar UUID para otra operación legítima.
- Replay auténtico se permite aun si el artículo fue desactivado después: **no es
  un nuevo ingreso**. Clave nueva sobre inactivo → 409 `articulo_inactivo`.
- Falta de existencia → 409 `existencia_no_disponible`, sin reparación automática.
  Desborde de saldo → 409 `saldo_fuera_rango`; código/unidad históricos → 409
  `identidad_inmutable`. Forma `{code,detail}`. No exponer detalles SQL al cliente.
- 400 esquema/campos, 401 sesión inválida, 403 rol denegado antes de datos,
  404 artículo no disponible, 409 invariantes. Red/5xx no confirma éxito ni fallo
  del commit: reconciliar con **la misma clave**, nunca una nueva.

## Integración React y límites

No se modificó frontend. El equipo React deberá agregar el enum/etiqueta Bodeguero,
su navegación exclusiva y la matriz candidata de inventario, sin concederle
otros módulos. Cantidades como strings, sin aritmética JS float para saldos;
mostrar datos confirmados por backend, no sobrescribir saldo ni usar flags cliente
de autorización. Desactivar conserva histórico; 409 requiere mostrar/reconciliar,
no borrar movimientos. Código/unidad quedan bloqueados tras el primer ingreso.

Las decisiones 019B/019C (consumo, costo, Obra, aprobación, merma, rectificaciones)
requieren contrato nuevo. No hay ajuste negativo ni edición de movimiento.
Postman esencial y environment serán preparados posteriormente según instrucción
del responsable; **no creados ni ejecutados en esta entrega**, no condicionan la
siguiente SPEC. CI, revisión de permisos y ratificación funcional preceden al merge;
no existe SHA publicado nuevo porque no se autorizaron commit/push/PR.
