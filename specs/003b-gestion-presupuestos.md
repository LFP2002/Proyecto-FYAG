# SPEC-003B — Gestión de presupuestos

## 1. Estado, contexto y alcance

**Estado: especificación; implementación pendiente.** Este documento no implica
que existan modelos, migraciones ni endpoints de Presupuestos.

- Proyecto: FYAG, pyme chilena de servicios de frío y agroindustria.
- Módulo futuro: `backend/apps/comercial/`.
- Persistencia: PostgreSQL, usando la infraestructura Django/DRF existente.
- Dependencias: SPEC-002/002A (JWT y usuarios), SPEC-003A (Cliente), Backend CI.
- Objetivo: mantener la relación confiable **presupuesto aprobado → obra →
  costos reales → rentabilidad**.

El backend es la fuente de verdad. En este MVP todos los presupuestos requieren
aprobación de Gerencia, sin umbral monetario ni dependencia del monto.
`requiere_aprobacion_gerencia` se conserva como extensión futura para una política
delegada configurable, pero hoy lo administra exclusivamente el backend y siempre
vale `true`; no se recibe en POST/PATCH. La política configurable futura no se
implementa en este MVP, ni se introducen márgenes o reglas financieras.

Las decisiones de precisión, errores HTTP, revisión y anulación que se detallan
a continuación forman parte del contrato a implementar; no deben improvisarse
durante la codificación.

## 2. Modelos conceptuales

### 2.1 Presupuesto

| Campo | Definición prevista |
| --- | --- |
| `id` | `BigAutoField`, PK generada por Django. |
| `cliente` | FK obligatoria a `Cliente`, `on_delete=PROTECT`. |
| `descripcion` | `CharField(max_length=2000)`, obligatorio, string con `strip`, no vacío. |
| `estado` | `CharField(max_length=20)`, choices oficiales, default `BORRADOR`; administrado por servicios. |
| `requiere_aprobacion_gerencia` | `BooleanField`, no nullable, administrado por backend, default `true` y constraint que impide persistir `false`. |
| `presupuesto_origen` | FK a sí mismo, nullable/blank, `on_delete=PROTECT`; solo la acción de revisión puede establecerla. |
| `creado_por` | FK obligatoria a `settings.AUTH_USER_MODEL`, `on_delete=PROTECT`; siempre el usuario autenticado que crea el registro. |
| `creado_en` | `DateTimeField(auto_now_add=True)`. |
| `actualizado_en` | `DateTimeField(auto_now=True)`; se actualiza también ante cambios de ítems y transiciones. |

Propiedades de salida, **sin columnas editables**:

- `codigo`: `PRE-` seguido del ID decimal con al menos seis posiciones, por
  ejemplo ID 1 → `PRE-000001`. Un ID mayor a 999999 no se trunca. No es un
  correlativo tributario, puede tener saltos y no se genera contando filas.
- `moneda`: constante `CLP`; no hay selección de moneda en este MVP.
- `monto_neto`: suma calculada de subtotales de los ítems persistidos.

No almacenar nombre de cliente duplicado, monto manual, IVA ni total con IVA.
La relación es el ID real del Cliente. Congelar el presupuesto congela su FK,
no los atributos del registro Cliente: una actualización de contacto en Clientes
puede reflejarse en consultas posteriores. No se introduce un snapshot documental
tributario ni una copia de nombres en esta etapa.

### 2.2 PresupuestoItem

| Campo | Definición prevista |
| --- | --- |
| `id` | `BigAutoField`. |
| `presupuesto` | FK obligatoria a Presupuesto, `on_delete=PROTECT`; la fija la ruta, no el body. |
| `descripcion` | `CharField(max_length=2000)`, string obligatorio, `strip`, no vacío. |
| `cantidad` | `DecimalField(max_digits=12, decimal_places=3)`, finito y estrictamente mayor a cero. |
| `unidad` | `CharField(max_length=30)`, string obligatorio, `strip`, no vacío; libre, sin catálogo ni conversión automática de unidades. |
| `precio_unitario` | `DecimalField(max_digits=15, decimal_places=2)`, finito y mayor o igual a cero. |
| `orden` | Entero obligatorio entre 1 y 2147483647; único dentro del presupuesto. |

`subtotal` es una propiedad calculada, no un monto ingresado libremente.
Los ítems se consultan ordenados por `(orden, id)`.

- Crear, editar y eliminar ítems únicamente en `BORRADOR`.
- Puede haber huecos en `orden`. Eliminar una línea no renumera otras.
- Cambiar `orden` a uno ocupado se rechaza; no se intercambian posiciones
  silenciosamente. Para reordenar se puede usar una posición libre intermedia.
- El cliente debe enviar `orden` al crear. No se utiliza `count()+1`.
- El contenido y orden quedan congelados al salir de BORRADOR, también si se
  rechaza o anula posteriormente el presupuesto.
- Una línea gratuita es válida; no se aplica ningún catálogo de precios.

### 2.3 PresupuestoEvento

| Campo | Definición prevista |
| --- | --- |
| `id` | `BigAutoField`. |
| `presupuesto` | FK obligatoria a Presupuesto, `on_delete=PROTECT`. |
| `estado_anterior` | Choice oficial nullable únicamente para el evento inicial. |
| `estado_nuevo` | Choice oficial obligatorio. |
| `registrado_por` | FK a Usuario, `on_delete=PROTECT`, usuario interno autenticado que ejecuta la acción. |
| `motivo` | `CharField(max_length=2000)`, default `""`, no nullable; comentario normalizado con `strip`. |
| `creado_en` | `DateTimeField(auto_now_add=True)`. |

Historial append-only: no actualización ni eliminación mediante API o servicios
de dominio. Orden de lectura `(creado_en, id)`.

La creación produce exactamente un evento `NULL → BORRADOR`. Cada transición
exitosa produce exactamente un evento con el estado anterior real. Un PATCH de
contenido o modificación de ítems no genera eventos de estado. Una operación
fallida no genera eventos. Los usuarios no pueden elegir actor ni timestamps.

`motivo` es obligatorio, string no vacío tras trim, para rechazo de Gerencia,
rechazo del cliente y anulación. En otras transiciones es opcional y admite `""`.
La creación y el evento inicial de una revisión usan `motivo=""`.

La aprobación/rechazo del cliente representa una decisión comunicada por el
cliente y registrada por Administrativo/Finanzas. No implica login del cliente,
firma electrónica ni evidencia de envío de correo. El actor es siempre interno.

## 3. Dinero, precisión y cálculo

Todos los importes de esta SPEC son **netos, en CLP** y se calculan con `Decimal`.
Se conservan dos decimales monetarios aun trabajando en CLP, para permitir precios
unitarios fraccionarios; no se redondea automáticamente a pesos enteros.

Contrato preciso:

1. Cantidad: hasta 9 dígitos enteros y 3 decimales; mínimo `0.001`.
2. Precio unitario: hasta 13 dígitos enteros y 2 decimales; mínimo `0.00`.
3. Rechazar exceso de escala/precisión; no redondear silenciosamente entradas.
4. `producto = cantidad * precio_unitario`, usando un contexto Decimal local con
   precisión 50, suficiente para los límites de campos y orden definidos.
5. `subtotal = producto.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)`.
6. `monto_neto = sum(subtotales, Decimal("0.00"))`: redondeo por línea, no un
   segundo cálculo basado en sumar productos sin redondear.
7. Presupuesto sin líneas: neto `0.00`. Puede guardarse como BORRADOR, pero no salir
   de ese estado. Un total redondeado a `0.00` tampoco permite salir.

Ejemplos: `2.500 × 100.25 = 250.625` → subtotal `250.63`;
`0.001 × 0.01 = 0.00001` → subtotal `0.00`. Dos líneas cuyo producto sea
`0.005` dan `0.01 + 0.01 = 0.02`.

Entrada JSON de cantidad/precio: **strings decimales**, por ejemplo `"2.500"`
y `"100.25"`. Rechazar números JSON, floats Python, booleanos, NaN, Infinity,
notación científica, separadores de miles, coma decimal y signos no necesarios.
Se permite trim exterior; el formato es dígitos ASCII con punto decimal opcional
y dígitos a ambos lados si aparece punto. Validar finitud antes de comparar.
La capa de dominio acepta `Decimal` finitos, nunca convierte un float a Decimal.
Las respuestas serializan cantidad con tres decimales e importes con dos, como
strings; no usan JSON float. Sin pérdida de precisión en totales agregados SQL.

No persistir subtotal/neto como campos editables o caches independientes de ítems.
El neto congelado al aprobar será referencia de ingresos comerciales para
rentabilidad futura. IVA, facturación y documentos tributarios quedan en Finanzas.

## 4. Estados y máquina de estados

Choices exactos, sin alias:

- `BORRADOR`
- `PENDIENTE_GERENCIA`
- `APROBADO_GERENCIA`
- `RECHAZADO_GERENCIA`
- `ENVIADO_CLIENTE`
- `APROBADO_CLIENTE`
- `RECHAZADO_CLIENTE`
- `ANULADO`

Flujo comercial único obligatorio:

```text
BORRADOR → PENDIENTE_GERENCIA → APROBADO_GERENCIA → ENVIADO_CLIENTE
                         └→ RECHAZADO_GERENCIA         ├→ APROBADO_CLIENTE
                                                      └→ RECHAZADO_CLIENTE
```

### Tabla exhaustiva de transiciones

AF = `ADMINISTRATIVO_FINANZAS`; G = `GERENCIA`.

| Acción | Origen | Destino | Rol | Condiciones adicionales |
| --- | --- | --- | --- | --- |
| Crear | No existe | BORRADOR | AF | Cliente activo y cabecera válida; evento inicial. |
| enviar-gerencia | BORRADOR | PENDIENTE_GERENCIA | AF | Requisitos de salida de BORRADOR. |
| aprobar-gerencia | PENDIENTE_GERENCIA | APROBADO_GERENCIA | G | — |
| rechazar-gerencia | PENDIENTE_GERENCIA | RECHAZADO_GERENCIA | G | Motivo obligatorio. |
| enviar-cliente | APROBADO_GERENCIA | ENVIADO_CLIENTE | AF | Únicamente tras aprobación de Gerencia. |
| registrar-aprobacion-cliente | ENVIADO_CLIENTE | APROBADO_CLIENTE | AF | Decisión comunicada por el cliente. |
| registrar-rechazo-cliente | ENVIADO_CLIENTE | RECHAZADO_CLIENTE | AF | Motivo obligatorio. |
| anular | BORRADOR, PENDIENTE_GERENCIA, APROBADO_GERENCIA, ENVIADO_CLIENTE o APROBADO_CLIENTE | ANULADO | AF | Motivo obligatorio y no utilización operativa según integración futura. |

No existe ninguna otra transición. No se omiten etapas, no se vuelve a BORRADOR
y no se cambia `estado` mediante POST/PATCH genérico. Finanzas no puede cambiar
el booleano, ni siquiera enviando `true`; se rechaza en POST/PATCH.

**Decisión de cierre de anulación:** los rechazos son terminales para esa fila,
preservando explícitamente el resultado rechazado; no se anulan después. Una
propuesta distinta nace como revisión. `APROBADO_CLIENTE` puede anularse antes
de uso operativo. `ANULADO` continúa siendo terminal para su propia máquina de
estados, pero admite crear una revisión: esta crea otro BORRADOR, sin modificar
ni reactivar el origen. Crear una revisión no es una transición del origen.

Las acciones de transición no son idempotentes por reintento: una segunda petición
que ya no cumpla el estado de origen responde 409 y no crea otro evento. Esta
semántica difiere deliberadamente de activar/desactivar Cliente. No se implementan
claves de idempotencia en esta etapa. La lectura posterior permite conocer el
resultado cuando el consumidor perdió la primera respuesta.

## 5. Edición, cliente y condiciones de salida

Solo BORRADOR permite cambiar `cliente`, `descripcion` e ítems.
`requiere_aprobacion_gerencia` no es editable. `presupuesto_origen`, autor, ID y fechas
no se editan. Fuera de BORRADOR solo pueden cambiar estado y fecha por las
acciones autorizadas; el contenido comercial queda congelado incluso en rechazo.

Reglas de cliente:

- Al crear, asignar un cliente distinto mediante PATCH o crear una revisión,
  el cliente asignado debe existir y estar activo.
- Si PATCH envía `cliente`, se comprueba activo aunque sea el mismo ID.
- Si el cliente del BORRADOR fue desactivado, puede editarse otro contenido sin
  reasignarlo; el presupuesto no puede salir de BORRADOR hasta reactivarlo o
  asignar otro cliente activo.
- No se exige RUT: un Cliente SIN_IDENTIFICACION es válido para cotizar.
- Tras abandonar BORRADOR, una desactivación posterior del cliente no invalida
  el presupuesto ni bloquea las transiciones restantes por ese solo motivo.
- No cambiar el cliente histórico para sortear una desactivación.

Para enviar desde BORRADOR a Gerencia, comprobar
dentro de la transacción: cliente activo, descripción válida, al menos un ítem,
todas las líneas válidas y monto neto recalculado mayor que cero. Se admiten
líneas gratuitas si el total es positivo. Enviar significa registrar el hito
comercial, no efectuar un envío de correo en este MVP.

## 6. Revisiones

`crear-revision` pertenece exclusivamente a AF. Orígenes permitidos:
`RECHAZADO_GERENCIA`, `RECHAZADO_CLIENTE` y `ANULADO`. Otro estado responde 409.

No se permite crear revisión directamente desde `APROBADO_CLIENTE`. Si el cliente
solicita una modificación comercial de una propuesta aceptada antes de su uso
operativo, el flujo es `APROBADO_CLIENTE → ANULADO` y luego `crear-revision`.
La nueva propuesta conserva trazabilidad con la anterior sin alterar el registro
anulado. ANULADO sigue siendo terminal: la revisión crea una fila nueva, no una
transición ni reactivación de la fila origen.

Operación atómica:

1. Bloquear presupuesto origen y comprobar rol/estado.
2. Comprobar que su Cliente sigue activo; si no, rechazar sin crear filas.
3. Crear un nuevo BORRADOR copiando FK cliente y descripción, con booleano `true`
   fijado por backend, sin copiar el valor del origen.
4. Copiar ítems con nuevas PK, preservando contenido, precios, cantidades y orden.
5. Establecer `presupuesto_origen` al presupuesto rechazado o anulado inmediato.
6. Asignar nuevo ID/código, fechas y `creado_por=request.user` actual.
7. Crear únicamente un evento inicial `NULL → BORRADOR` para el nuevo presupuesto.

No copiar historial, estados, autor original ni fechas. El origen queda íntegro.
No reutilizar su ID ni modificar sus ítems. La revisión vuelve a pasar por todo
el flujo obligatorio de Gerencia y puede editarse por estar en BORRADOR.

No hay unicidad de `presupuesto_origen`: se permiten varias propuestas revisadas
a partir de un mismo origen rechazado o anulado, cada una con identidad propia. Repetir la acción
crea otra revisión (201); no se infiere idempotencia. La FK solo se establece al
crear un nuevo registro desde un origen existente, impidiendo ciclos por la vía
de aplicación; además se prohíbe autoreferencia estructural.

Puede implementarse tras las operaciones fundamentales, pero su contrato queda
definido aquí y no debe declararse disponible hasta tener sus pruebas.

## 7. Anulación y relación futura con Obras

No existe DELETE físico de Presupuesto. Anular conserva cabecera, ítems e historial
y agrega el evento con motivo. No existe una acción alternativa para borrar.

Un presupuesto ANULADO puede ser origen de una revisión que crea un nuevo
BORRADOR; su estado y contenido permanecen inmutables. Esto no habilita anular
presupuestos con utilización operativa: se mantiene el bloqueo futuro por Obras,
salvo operación compensatoria definida explícitamente en una SPEC posterior.

La condición «sin utilización operativa» deberá comprobar la asociación real con
Obras cuando esa SPEC exista. En este MVP todavía no existe tal relación: no se
crea un campo ficticio, string o booleano enviado por React para simularla.
Antes de habilitar la creación de Obras deberá integrarse el bloqueo de anulación
si ya hay una obra asociada. No se autoriza operación compensatoria implícita.

Solo `APROBADO_CLIENTE` habilitará crear una Obra. La SPEC de Obras determinará
la cardinalidad, sin asumir aquí una relación uno-a-uno ni varias obras por
presupuesto. También deberá coordinar creación de obra/anulación bloqueando el
mismo presupuesto para evitar carreras.

El monto neto aprobado será referencia comercial para comparar con costos reales
y calcular rentabilidad. No usar IVA como ingreso. No implementar ahora obras,
costos, horas reales, fórmulas operativas ni contabilidad.

## 8. Matriz de permisos

Usar los enums existentes de `Usuario.Rol`, sin duplicar una taxonomía de roles.

| Operación | ADMINISTRATIVO_FINANZAS | GERENCIA | SUPERVISOR_OBRAS / TECNICO |
| --- | --- | --- | --- |
| Listar, detalle, consultar ítems e historial | Sí | Sí | No |
| Crear, modificar BORRADOR y administrar sus ítems | Sí | No | No |
| Enviar a Gerencia | Sí | No | No |
| Aprobar/rechazar en Gerencia | No | Sí, solo PENDIENTE_GERENCIA | No |
| Enviar al cliente y registrar su decisión | Sí | No | No |
| Anular en estados permitidos | Sí | No | No |
| Crear revisión desde RECHAZADO_GERENCIA, RECHAZADO_CLIENTE o ANULADO | Sí | No | No |
| Borrar presupuesto o editar/borrar eventos | No | No | No |

Gerencia no crea ni modifica contenido comercial, aunque sea superusuario: no
hay bypass de rol en esta API. La autorización no se limita al creador: AF puede
gestionar los presupuestos comerciales según estado y G consultar todos.
La futura SPEC de Obras podrá mostrar a supervisores/técnicos únicamente la
información necesaria en sus recursos autorizados, sin abrir este módulo general.

## 9. Contrato HTTP conceptual

### 9.1 Rutas

| Método y ruta | Función | Éxito |
| --- | --- | --- |
| GET `/api/presupuestos/` | Listado de todos los estados, incluido ANULADO. | 200 |
| POST `/api/presupuestos/` | Crear cabecera BORRADOR, inicialmente sin ítems. | 201 |
| GET `/api/presupuestos/{id}/` | Cabecera, ítems y neto. | 200 |
| PATCH `/api/presupuestos/{id}/` | Modificar cabecera de BORRADOR. | 200 |
| POST `/api/presupuestos/{id}/items/` | Crear ítem en BORRADOR. | 201 |
| PATCH `/api/presupuestos/{id}/items/{item_id}/` | Modificar ítem de ese BORRADOR. | 200 |
| DELETE `/api/presupuestos/{id}/items/{item_id}/` | Eliminar ítem de BORRADOR. | 204 |
| GET `/api/presupuestos/{id}/historial/` | Eventos de estado, solo lectura. | 200 |
| POST `/api/presupuestos/{id}/enviar-gerencia/` | Acción de dominio. | 200 |
| POST `/api/presupuestos/{id}/aprobar-gerencia/` | Acción de dominio. | 200 |
| POST `/api/presupuestos/{id}/rechazar-gerencia/` | Acción de dominio con motivo. | 200 |
| POST `/api/presupuestos/{id}/enviar-cliente/` | Acción de dominio. | 200 |
| POST `/api/presupuestos/{id}/registrar-aprobacion-cliente/` | Registrar decisión comunicada. | 200 |
| POST `/api/presupuestos/{id}/registrar-rechazo-cliente/` | Registrar decisión con motivo. | 200 |
| POST `/api/presupuestos/{id}/anular/` | Anular con motivo. | 200 |
| POST `/api/presupuestos/{id}/crear-revision/` | Crear otro BORRADOR desde RECHAZADO_GERENCIA, RECHAZADO_CLIENTE o ANULADO y copiar líneas; no modifica el origen. | 201 |

No PUT en estos recursos ni DELETE de presupuesto. No endpoints para crear,
editar o eliminar eventos directamente. HEAD/OPTIONS estándar solo para rutas
y usuarios autorizados. Los ítems se consultan en el detalle; no se necesita
una segunda ruta GET de ítems en esta etapa.

### 9.2 Entrada y salida

Crear cabecera requiere exactamente estos campos de negocio:

```json
{
  "cliente": 1,
  "descripcion": "Instalación de sistema de frío"
}
```

`cliente` es la PK entera positiva de Cliente, nunca un nombre. No acepta
booleanos como IDs. `requiere_aprobacion_gerencia` es solo de salida, siempre `true`.
Descripción
y unidad son strings reales, no conversiones automáticas de números a texto.

POST de ítem requiere `descripcion`, `cantidad`, `unidad`, `precio_unitario`,
`orden`. PATCH de cabecera/ítem admite solo los campos editables de su recurso,
valida el estado final completo y no borra campos omitidos. No se aceptan ítems
anidados en POST/PATCH de cabecera: se usa su ruta específica.

```json
{
  "descripcion": "Montaje especializado",
  "cantidad": "2.500",
  "unidad": "hora",
  "precio_unitario": "100.25",
  "orden": 1
}
```

Campos de salida de cabecera: `id`, `codigo`, `cliente`, `descripcion`, `estado`,
`requiere_aprobacion_gerencia`, `presupuesto_origen`, `creado_por`, `creado_en`,
`actualizado_en`, `moneda`, `monto_neto`. Las relaciones se representan con IDs;
no incluir objetos Usuario ni datos sensibles. El detalle añade `items` con los
campos del ítem más `subtotal`. Las mutaciones de cabecera y acciones devuelven
el detalle final; las de ítem devuelven el ítem salvo DELETE (sin body).

Listado paginado: orden `(-creado_en, -id)`, page size 25 fijo, parámetro `page`;
respuesta DRF `{count, next, previous, results}` sin ítems anidados. Historial:
misma estructura paginada, orden `(creado_en, id)`, campos de evento documentados.
No filtros ni ordenación libre en este primer contrato. Las lecturas deben evitar
N+1 usando agregaciones, `select_related`/`prefetch_related` según corresponda.
Detalle y neto deben calcularse a partir del mismo conjunto de líneas leído, para
no devolver subtotales y total inconsistentes durante edición concurrente.

Rechazar campos desconocidos con 400 por campo. También rechazar explícitamente
campos administrados por servidor enviados en escrituras: `id`, `codigo`,
`estado`, `requiere_aprobacion_gerencia`, `creado_por`, fechas,
`presupuesto_origen`, `moneda`, `monto_neto`,
`subtotal` y la FK `presupuesto` del ítem. No cambiar PK por el body.

Acciones de transición aceptan solo `{ "motivo": "..." }` o `{}` si el motivo
es opcional; no admiten `estado`. `crear-revision` acepta `{}`: toda la copia se
determina desde el origen, sin overrides hasta el PATCH del nuevo BORRADOR.

### 9.3 Códigos de error y precedencia

- 400: campos inválidos/desconocidos, motivo ausente, Decimal inválido, orden
  duplicado, cliente inactivo, falta de ítems o neto cero al salir de BORRADOR.
- 401: sin JWT, JWT inválido, manipulado o expirado.
- 403: usuario autenticado sin rol para la operación, sin depender de un ID válido.
- 404: presupuesto inexistente para usuario autorizado; ítem inexistente o que no
  pertenece al presupuesto de la URL. Una FK cliente inexistente en el body es
  error de entrada 400 asociado a `cliente`. Página inexistente: 404 estándar DRF.
- 405: método no implementado en ruta existente para usuario autorizado.
- 409: estado actual incompatible, intento de editar contenido congelado,
  salto de aprobación o repetición de una transición;
  en el futuro, también anulación impedida por obra asociada.

Evaluar autenticación, permiso, existencia y luego estado/reglas. Una acción con
rol no autorizado no se convierte en 409 ni 404 por el estado del recurso.
Una ruta desconocida responde 404. Los errores de campo usan claves del campo;
los de estado usan `detail` y un código público estable como `estado_incompatible`.
No exponer SQL, trazas, nombres de constraints, hashes ni errores internos.

## 10. Servicios, transacciones y concurrencia

Arquitectura: modelos para persistencia/validaciones reutilizables; serializer
para contrato HTTP; permissions para rol; services para invariantes cruzadas,
transiciones y escrituras; views para transporte. No lógica compleja en views.

Toda escritura relevante usa `transaction.atomic()`. Para registros existentes,
obtener el Presupuesto con `select_for_update()` **antes** de evaluar estado,
modificar contenido/ítems, recalcular el total o crear revisión.

- No basar decisiones en la instancia leída previamente por la view.
- Crear/editar/eliminar ítem bloquea primero su Presupuesto; así una transición
  no puede congelarlo simultáneamente con una modificación de líneas.
- Actualizar solo los campos recibidos tras releer la fila, validando el estado
  final, para no sobrescribir cambios ajenos con instancias obsoletas.
- Salida de BORRADOR: bajo bloqueo, releer ítems persistidos y recalcular el neto
  Decimal. No confiar en un total del request ni en un agregado calculado antes.
- Transición y evento se escriben en la misma transacción. Si falla el evento,
  se revierte el estado; si falla la transición, no queda evento.
- Revisión bloquea el origen, copia cabecera/ítems y crea evento inicial en una
  sola transacción; cualquier error revierte todas sus filas nuevas.
- Creación inicial bloquea el Cliente seleccionado y verifica activo dentro de
  la transacción, crea cabecera y evento inicial juntos. No hay fila de presupuesto
  existente que bloquear antes de crearla.
- Al asignar cliente o salir de BORRADOR, bloquear también ese Cliente para
  serializar la comprobación de activo con la desactivación de SPEC-003A.
  Orden de bloqueo: presupuesto existente (origen en revisión), luego Cliente.
  No introducir operaciones inversas Cliente → presupuesto existente. Cuando se
  necesiten varios presupuestos, bloquear por PK ascendente.
- La desactivación posterior al commit no invalida una operación ya confirmada.

Cada acción obtiene el Presupuesto con `select_for_update()` y, después de
adquirir el bloqueo, relee el estado persistido y vuelve a evaluar la máquina de
estados. Si la acción sigue siendo válida desde ese estado, puede ejecutarse;
si ya no lo es, responde 409. No se exige que toda concurrencia produzca una
operación exitosa y otra fallida: se serializa conforme a las transiciones válidas.

Ejemplo A: aprobar-gerencia y rechazar-gerencia concurrentes desde
PENDIENTE_GERENCIA. Solo una confirma; la segunda encuentra un estado que ya no
es PENDIENTE_GERENCIA y responde 409. No se crean dos eventos de salida desde
el mismo estado.

Ejemplo B: registrar-aprobacion-cliente y anular concurrentes desde ENVIADO_CLIENTE:

- Si anular confirma primero (`ENVIADO_CLIENTE → ANULADO`), la aprobación
  posterior responde 409.
- Si la aprobación confirma primero (`ENVIADO_CLIENTE → APROBADO_CLIENTE`),
  anular puede ejecutar `APROBADO_CLIENTE → ANULADO` si sigue cumpliendo las
  reglas de dominio, incluida la futura restricción de utilización operativa.
  Ambas operaciones pueden tener éxito secuencialmente; cada evento refleja su
  estado anterior real. Esto es serialización válida, no una carrera incorrecta.

PostgreSQL es autoridad final para constraints/uniquidad. Detectar previamente
conflictos conocidos (p. ej. orden) para mensajes amigables y mapear únicamente
`IntegrityError` de constraints conocidos fuera del bloque atómico fallido.
No disfrazar errores inesperados como errores de usuario. Evitar `bulk_update`
o `QuerySet.update` en rutas de escritura que eludan servicios de congelación.

## 11. Integridad PostgreSQL propuesta

Los nombres definitivos podrán ajustarse a límites de Django/PostgreSQL al crear
migraciones; las invariantes siguientes son obligatorias.

### Presupuesto

- `estado` pertenece exactamente a los ocho choices.
- `descripcion != ""` e igualdad con `Trim(descripcion)`.
- `requiere_aprobacion_gerencia = True`.
- `presupuesto_origen IS NULL OR presupuesto_origen_id != id`.
- FK y NOT NULL protegen cliente, autor, estado y booleano; `PROTECT` en Django
  y las FK reales impiden referencias rotas al eliminar relacionados.

### PresupuestoItem

- Cantidad finita y `> 0`, precio unitario finito y `>= 0`.
- Columnas NUMERIC con precisión/escala explícitas; no REAL/DOUBLE PRECISION.
- Rechazar explícitamente `NaN` en NUMERIC, además de los comparadores: en
  PostgreSQL, `NaN > 0` puede ser verdadero. Los límites superiores finitos
  `cantidad <= 999999999.999` y `precio_unitario <= 9999999999999.99`, junto con
  los límites inferiores, excluyen NaN e infinitos y reflejan los límites de campo.
- Descripción y unidad no vacías e iguales a su `Trim`.
- `1 <= orden <= 2147483647`.
- `UniqueConstraint(fields=["presupuesto", "orden"])`.

### PresupuestoEvento

- Estado nuevo válido; anterior válido o NULL.
- Anterior NULL si y solo si nuevo BORRADOR: no hay transiciones de retorno.
- Unicidad condicional de `presupuesto` cuando `estado_anterior IS NULL` para
  impedir dos eventos iniciales; el servicio garantiza que exista uno.
- Si anterior no es NULL, debe ser distinto de nuevo.
- Motivo igual a su `Trim`; no vacío cuando nuevo es RECHAZADO_GERENCIA,
  RECHAZADO_CLIENTE o ANULADO. FK y NOT NULL para actor y presupuesto.

Una CheckConstraint no conoce el estado anterior de una fila ni puede validar
agregados de tablas relacionadas: la máquina de estados, congelación de ítems,
cliente activo, total positivo de salida y secuencia del historial son reglas de
servicio bajo transacción, no falsas garantías SQL. El historial es inmutable en
las interfaces de aplicación; no se promete impedir alteraciones manuales por un
administrador de base de datos ni se exige un trigger de auditoría en este MVP.
`Trim` SQL cubre espacios ordinarios; `strip()` Python cubre además otros blancos.

## 12. Seguridad y auditoría

Reutilizar JWT existente. Roles exclusivamente de `request.user.rol`; jamás de
body, query params, headers personalizados o estado React. Toda acción verifica
rol + estado actual + reglas de dominio. Ningún cliente externo se autentica.

PresupuestoEvento es trazabilidad de estados comercial. No registra cada cambio
de línea ni sustituye la futura auditoría global de `apps.auditoria`. No duplicar
un segundo sistema general de auditoría ni exponer historial editable.

## 13. Pruebas previstas y criterios de aceptación

Pruebas sobre PostgreSQL, nunca SQLite. Separar responsabilidades:

1. **Modelos:** campos, FKs protegidas, autores, timestamps, código estable y sin
   truncamiento; creación de borrador sin líneas; no persistencia de monto manual.
   Aprobación con default `True`, `editable=False` y rechazo de `False` al guardar.
2. **Constraints reales:** `IntegrityError` dentro de `transaction.atomic()` usando
   escrituras que omitan validación Python para choices, trim, aprobación obligatoria,
   autoreferencia, cantidades/precios, NaN, orden único, motivos y evento inicial.
3. **Decimal:** precisión máxima, exceso de escala, cero, negativos, floats,
   booleanos, NaN/Infinity y formatos inválidos; redondeo HALF_UP por línea, suma
   exacta, líneas gratuitas y totales que redondean a cero.
4. **Cliente:** activo al crear/asignar/salir; inactivo bloquea dichas operaciones;
   desactivación posterior no invalida histórico; SIN_IDENTIFICACION permitido.
5. **JWT:** sin token 401, JWT real válido, token expirado/manipulado; sin segundo
   mecanismo de autenticación.
6. **Cuatro roles:** matriz completa, incluidas acciones, ítems e historial; G no
   crea/edita ni anula; AF no aprueba/rechaza en Gerencia; rol inyectado no autoriza.
7. **Máquina completa:** cada transición permitida y cada combinación estado/acción
   prohibida; rechazo de `false` en modelo/DB y de cualquier valor del campo
   administrado en POST/PATCH; no atajos ni regreso a BORRADOR. Montos bajos y
   altos siguen el mismo flujo obligatorio sin umbral.
8. **Congelación:** PATCH de cabecera y CRUD de líneas solo BORRADOR, incluso si el
   presupuesto está rechazado/anulado; cambio directo de estado siempre rechazado.
9. **Salida:** descripción, cliente activo, al menos un ítem y neto positivo;
   cero en una línea permitido si el total es positivo.
10. **Motivos/eventos:** trim, límites, motivo requerido; un evento inicial y uno
    por transición; actor interno correcto; rollback conjunto; historial ordenado;
    no modificación/borrado de eventos ni duplicación por reintento de transición.
11. **Revisión:** nuevo código/ID, copia profunda de líneas, origen correcto,
    actor actual, siempre BORRADOR con aprobación requerida `true`, sin historial
    copiado; original intacto; origen inválido e
    inactivo rechazados; múltiples revisiones permitidas; rollback integral.
    Cubrir los tres orígenes permitidos (RECHAZADO_GERENCIA, RECHAZADO_CLIENTE,
    ANULADO), rechazo de revisión directa desde APROBADO_CLIENTE y flujo
    APROBADO_CLIENTE → ANULADO → nueva revisión BORRADOR. Verificar que crear
    revisión no cambia ni reactiva el origen anulado ni añade una transición a él.
12. **Concurrencia:** `TransactionTestCase` con conexiones independientes y
    sincronización controlada, no sleeps como prueba de exclusión. Cubrir edición
    de ítem vs salida, dos decisiones de Gerencia, decisión vs anulación, orden
    duplicado concurrente, asignación/salida vs desactivación de Cliente y revisión.
    Tras cada bloqueo, comprobar reevaluación contra el estado persistido. Para
    aprobar/rechazar en Gerencia, exigir un éxito y un 409. Para aprobación de
    cliente vs anulación, controlar ambos órdenes: anulación primero implica 409
    posterior de aprobación; aprobación primero permite también anular desde
    APROBADO_CLIENTE si se cumplen las reglas. En este segundo orden comprobar
    ambos éxitos y los eventos ENVIADO_CLIENTE → APROBADO_CLIENTE → ANULADO,
    sin exigir artificialmente que falle una transición todavía válida.
13. **HTTP:** 404 para inexistentes e ítems de otro presupuesto; rutas inválidas;
    PUT/DELETE de presupuesto 405; DELETE ítem solo en BORRADOR; campos desconocidos
    y administrados por servidor rechazados; PATCH parcial valida estado completo;
    paginación/orden y ausencia de datos sensibles/trazas.
14. **Regresión:** todas las pruebas existentes de Clientes y Auth deben continuar
    pasando, incluidas rutas de autenticación y constraints de identificación.

## 14. CI y secuencia de implementación futura

Backend CI ya existe en `main`. Toda implementación deberá superar, en orden:

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py migrate --noinput
python manage.py test
```

No mergear el PR si Backend CI falla. Las migraciones futuras deben reconstruir
una base PostgreSQL limpia sin edición del historial previo. El filtro actual
del workflow no ejecuta CI por un cambio exclusivamente en `specs/`; eso no
exime a la implementación posterior con cambios backend de superar los checks.

Orden recomendado: modelos/cálculo/constraints y tests → servicios/estados y
concurrencia → permisos/serializer/API → revisiones si se entregan en un segundo
incremento. Declarar implementadas solo las operaciones realmente verificadas.

## 15. Compatibilidad y diferencias frente al mock

Revisión realizada de `frontend/src/data/constants.js`,
`frontend/src/pages/Presupuestos.jsx` y `frontend/src/context/AppContext.jsx`:

- El mock define `UMBRAL = 5000000` y decide el paso por Gerencia por monto.
  **No es regla de backend**: todos requieren aprobación de Gerencia sin umbral.
- El mock ingresa `monto` libremente con `Number`; aquí se deriva de ítems Decimal.
- El mock relaciona clientes por nombre y permite un placeholder «Sin cliente»;
  aquí siempre existe una FK real a Cliente (sin identificación sí, sin cliente no).
- El mock genera códigos contando registros y modifica estados localmente;
  aquí el código deriva de PK estable y las acciones del backend gobiernan estados.
- Los aliases de roles del mock no son permisos reales; se usan enums de Usuario.
- El mock contiene una referencia singular a obra; no se traslada esa cardinalidad
  a esta SPEC. La decidirá explícitamente la SPEC de Obras.

SPEC-003A es compatible con cliente activo al crear y con SIN_IDENTIFICACION para
cotizar. Esta SPEC cierra la decisión de no exigir identificación tributaria en
cotización; la obligación tributaria se resolverá en Finanzas. Los permisos de
Clientes no se copian automáticamente: Gerencia gestiona Clientes, pero en
Presupuestos únicamente consulta y decide la aprobación de Gerencia.

No se modifica frontend ni ninguna especificación anterior en esta entrega.

## 16. Fuera de alcance

- Obras y su cardinalidad/operaciones compensatorias.
- Costos y horas reales, pagos, facturación e IVA tributario.
- Alertas e integración React.
- PDF, envío real de correo y firma electrónica.
- Portal de cliente y autenticación de clientes externos.
- Auditoría global y reglas tributarias de identificación.

Esta entrega crea exclusivamente la especificación. No implementa modelos,
migraciones, serializers, servicios, permisos, views ni rutas.
