# SPEC-004 — Gestión de Obras

## 1. Estado, contexto y alcance

**Estado: incremento 004A implementado e integrado en `main` mediante el PR #8
(7 de noviembre de 2026), con Backend CI aprobado.** El incremento 004B
(técnicos participantes, turnos, costos completos y finalización) está especificado
en `specs/004b-costos-finalizacion.md`, pero todavía no implementado. Las decisiones D1–D9 son del equipo, no una
aprobación formal externa de FYAG.

- Proyecto: FYAG, Proyecto Beta — Sistema de Gestión de Obras y Presupuestos.
- Módulo implementado para 004A: `backend/apps/obras/` (modelos, migraciones, servicios y API DRF).
- Persistencia: PostgreSQL; API: Django REST Framework; autenticación JWT existente.
- Dependencias: SPEC-001, SPEC-002A/002B, SPEC-003A y SPEC-003B implementadas.
- Objetivo: enlazar **presupuesto aceptado → ejecución operativa trazable → futura
  facturación y medición de costos/rentabilidad** sin mezclar sus estados.

### Incrementos definidos

- **004A — Base operativa (implementada en `main`):** categorías, creación de obras,
  asignación/reasignación de técnicos, planificación, inicio efectivo, edición
  de fichas, suspensión, reanudación, historial, permisos y bloqueo concurrente
  de anulación de Presupuestos utilizados. Creación y guard en Comercial se
  entregan juntos; no existen acciones `finalizar` ni `cancelar` en su API.
- **004B — Participantes, turnos, costos y finalización (especificada, pendiente):**
  incorpora técnicos participantes sin sustituir al responsable principal, turnos
  por obra con evidencia textual, materiales/gastos con costos manuales, revisión
  de completitud y habilitación de FINALIZADA solo tras implementar y probar
  esos controles. El contrato detallado está en `specs/004b-costos-finalizacion.md`;
  no debe asumirse implementado hasta contar con código, pruebas y CI.
- CANCELADA se conserva en el ciclo conceptual; su acción no se incluye en 004A
  ni se habilita automáticamente en 004B. Requiere una especificación posterior
  con reglas financieras reales de cancelación.

FINALIZADA permanece como estado conceptual, no como transición disponible en
004A. En 004B exige costos reales registrados y completitud validada; no hay
excepción ni flags del frontend para omitir el control. Ninguno de los incrementos
implementa Finanzas ni MongoDB.

### Naturaleza de las decisiones

- **Reglas respaldadas:** fuentes identificadas en §2 y contrato vigente de
  SPEC-003B (aprobación, origen aceptado y protección del presupuesto utilizado).
- **Diseño técnico adoptado:** capas Django/DRF, FK, constraints, bloqueos,
  serializers acotados e historial transaccional; se conserva la compatibilidad.
- **Decisiones de diseño del equipo:** D1–D9 (§15), adoptadas para este MVP sin
  atribuirlas al cliente. PLANIFICADA amplía los cuatro estados de las fuentes;
  la cardinalidad, fechas y proyecciones por rol son precisiones del diseño.
- **Definiciones posteriores:** detalle verificable de costos/completitud en 004B,
  cancelación con reglas financieras y circuito sin cobro. No se dan por resueltas.

Se mantiene íntegra la política comercial vigente: TODOS los presupuestos
requieren Gerencia; `requiere_aprobacion_gerencia` siempre `true`, administrado
por backend y rechazado en POST/PATCH. Solo `APROBADO_CLIENTE` habilita una obra.
Ninguna categoría constituye una excepción a esa regla.

## 2. Fuentes revisadas y resolución de diferencias

Documentos de referencia disponibles en la carpeta académica superior al repo
(no versionados aquí; los títulos y páginas permiten identificar las fuentes):

| Fuente | Evidencia relevante | Tratamiento en el diseño de 004A |
| --- | --- | --- |
| Proyecto 2 [Beta] - Sistema de Gestión de Obras y Presupuestos, pp. 2–4 | Ocho categorías, cuatro estados, ficha, supervisor operativo, técnico solo lectura; listas administrables. | Base funcional; no convertir los ejemplos de reglas en decisiones confirmadas. |
| Beta, p. 2 y p. 4 | Ejemplo «no cerrar si hay pagos pendientes»; ciclo explícito Obra Finalizada → Factura → Cuenta por cobrar → Pago → Cierre comercial. | Finalización operativa independiente de cobro (§7). |
| Beta, p. 4 | Ejemplos de no finalizar sin técnico y no cancelar con pagos asociados. | El equipo exige técnico al iniciar/reanudar; cancelación diferida (§7). |
| ANEXO B - Minuta de Levantamiento de Requerimientos (Kick-off), pp. 1–2 | Autonomía de mandos medios con trazabilidad; completar costos antes de Finalizada. | D8 conserva el requisito: 004A no finaliza; 004B debe validar costos, sin fingir cumplimiento actual. |
| ANEXO C - Especificaciones funcional del sistema de gestión y aplicación móvil, pp. 8–9 | Ficha de obra, fecha de creación editable, categorías y estados. | D4 distingue programación editable y timestamps inmutables; precisión del equipo, no equivalencia textual con la fuente. |
| ANEXO C, pp. 11, 14–17 | Materiales por obra, horas, auditoría y futuro ERP/móvil. | Puntos de extensión; no implementar inventario, móvil ni auditoría global ahora. |
| SPEC-003B, §§6–8, 10–11 | Presupuesto congelado, revisiones limitadas, anulación sin uso operativo, bloqueo concurrente. | Asociación inmutable y bloqueo común sobre Presupuesto (§8). |

Frontend revisado: `frontend/src/pages/Obras.jsx`, `TecnicoApp.jsx`,
`frontend/src/context/AppContext.jsx` y `frontend/src/data/constants.js`.

- El mock usa una referencia singular `p.obra` y lista aprobados sin obra: apoya
  la elección 1:0..1 del equipo, pero no prueba que sea una prohibición de FYAG.
- Permite crear sin técnico y solo lo exige al finalizar; este diseño permite
  ausencia únicamente en PLANIFICADA y exige técnico elegible al iniciar/reanudar.
- Técnicos son nombres hardcodeados; aquí son FK a `Usuario`, nunca nombres como ID.
- El selector de estados permite cambios arbitrarios; aquí habrá tabla exhaustiva.
- `applyEstado` bloquea cancelación por pagos no anulados, no finalización por deuda.
  El mock no define qué significa pago asociado, anticipo o factura anulada.
- `TecnicoApp` permite avances/bitácora; Beta y la instrucción actual exigen solo
  consulta. Avances, porcentajes y escritura móvil quedan fuera de este incremento.
- Ocultar importes en React no es seguridad: la respuesta backend debe excluirlos.
- Las categorías del mock son parciales; no constituyen el catálogo de dominio.

## 3. Arquitectura y convenciones

Seguir la estructura existente en Comercial:

- `models.py`: modelos, normalización, validación estructural, FK y constraints.
- `services.py`: escrituras atómicas, bloqueos, invariantes cruzadas y eventos.
- `serializers.py`: contratos explícitos de entrada/salida y rechazo de campos
  desconocidos/server-managed, incluidos los enviados con su valor correcto.
- `permissions.py`: matriz por acción usando `Usuario.Rol`, sin roles nuevos.
- `views.py`: transporte DRF, queryset autorizado, paginación y traducción de errores.
- `urls.py`: rutas `/api/`, plural y acciones con guiones, como Presupuestos.
- `exceptions.py`: errores de dominio independientes de DRF, siguiendo Comercial.
- `tests/`: modelos, constraints PostgreSQL, servicios, permisos/API y concurrencia.

Servicios reciben el actor interno, nunca roles desde el body. La capa de entrada
verifica rol y recurso; los servicios de Obras revalidan autorización de escritura
para no permitir que otro caller ejecute el ciclo operativo con un técnico.
No duplicar autenticación ni abrir los endpoints comerciales a nuevos roles.
Reutilizar patrones, sin refactorizar módulos ajenos para crear un framework común.

## 4. Cardinalidad, origen y trazabilidad

**D1 — Decisión del equipo:** un Presupuesto tiene cero o una Obra; cada Obra tiene
exactamente un Presupuesto. Una FK única (`OneToOneField`, `PROTECT`) expresa
esta relación, también cuando la obra está FINALIZADA o CANCELADA.

Motivo: evita duplicar el ingreso comercial al atribuir rentabilidad y coincide
con la selección «aprobados sin obra». Una relación 1:N requeriría definir reparto
del alcance y del monto, facturación parcial y costos; esas reglas no están dadas.
Varias visitas pueden pertenecer a la misma obra: no crean obras adicionales ni
duplican ingresos. El registro detallado de visitas no forma parte de 004A.

- Crear desde presupuesto persistido en `APROBADO_CLIENTE`, sin obra asociada.
- Presupuesto inmutable después de crear; no sustituirlo ni mover la obra a otro.
- Cliente derivado de `obra.presupuesto.cliente`, sin FK duplicada ni entrada
  `cliente`. Conserva identidad por la FK congelada del presupuesto y `PROTECT`.
- Nombre/contacto del Cliente son datos actuales, no un snapshot contractual.
- **D5 — Decisión del equipo:** no volver a exigir cliente activo para crear una obra desde
  una aceptación vigente: SPEC-003B indica que desactivarlo no invalida el histórico.
  Su desactivación tampoco bloquea iniciar, reanudar, suspender ni la futura
  finalización. La regla no habilita cancelar en 004A.
- Crear obra no cambia `APROBADO_CLIENTE` ni genera `PresupuestoEvento`: no es una
  transición comercial. Sí genera el evento inicial de Obra.
- Cancelar no libera el presupuesto ni permite otra obra con la misma FK.
- No crear revisiones de presupuesto usado mediante atajos: SPEC-003B no permite
  revisión directa desde APROBADO_CLIENTE y la anulación queda bloqueada por uso.
  Una sustitución comercial posterior requiere otra especificación explícita.
- D9: emergencias siguen el flujo comercial aprobado; su priorización operativa
  es futura, sin saltos de aprobación. Garantías gratuitas no se resuelven creando
  presupuestos ficticios: SPEC-003B exige neto positivo para salir de BORRADOR.
  004A no cubre ese caso; una SPEC posterior definirá un circuito sin cobro
  trazable al origen. La categoría Garantía no introduce una excepción comercial.

## 5. Modelos conceptuales

Las siguientes definiciones aplican D1/D2/D4: una obra por presupuesto,
planificación con técnico opcional y separación entre programación e inicio real.
Campos/choices terminales describen el ciclo completo: persistir su estructura
no autoriza transiciones ni endpoints terminales en 004A.

### 5.1 CategoriaServicio

| Campo | Definición del modelo 004A |
| --- | --- |
| `id` | BigAutoField. |
| `nombre` | CharField(100), string obligatorio, trim, no vacío; único sin distinguir mayúsculas mediante `Lower(nombre)`. Acentos se conservan. |
| `activo` | BooleanField, default true, administrado por acciones activar/desactivar. |
| `creado_por` | FK Usuario, PROTECT, actor autenticado; nullable exclusivamente para catálogo inicial de migración. |
| `creado_en`, `actualizado_en` | Timestamps automáticos. |

**D6 — Decisión del equipo:** GERENCIA administra categorías; supervisor las selecciona.
Sin eliminación física ni reutilización de nombres de categorías inactivas.
Desactivar impide nuevas asignaciones, no invalida obras existentes.
Renombrar corrige la etiqueta global, no el significado; para otro significado,
crear otra categoría y desactivar la anterior. IDs y eventos preservan identidad.

Catálogo inicial por migración de datos: Proyecto, Mantención, Climatización,
Proyecto eléctrico, Emergencia, Garantía, Venta de repuestos y Mejoras.
Para estas filas de sistema, `creado_por` será nullable y solo la migración podrá
dejarlo null; no inventar un usuario GERENCIA ni fijar PKs de usuarios.
En la API siempre se asigna el actor. No codificar estas categorías como choices.

### 5.2 Obra

| Campo | Definición del modelo 004A |
| --- | --- |
| `id` | BigAutoField. |
| `presupuesto` | OneToOneField a Presupuesto, no nullable, PROTECT, related_name `obra`. Inmutable por aplicación. |
| `categoria_servicio` | FK CategoriaServicio, PROTECT, obligatoria. Representa el tipo de servicio. |
| `descripcion` | CharField(2000), string operativo obligatorio, trim, no vacío. No se copia automáticamente del texto comercial. |
| `tecnico_responsable` | FK settings.AUTH_USER_MODEL, PROTECT, null/blank permitidos únicamente en PLANIFICADA; asignación no nula a usuario activo con rol TECNICO. |
| `fecha_programada` | DateField nullable/blank, opcional y editable antes de terminal; admite futuro, no representa inicio efectivo. |
| `iniciado_en` | DateTimeField nullable, solo backend al ejecutar iniciar; inmutable después, no se reinicia al reanudar. |
| `estado` | CharField(12), choices PLANIFICADA, EN_PROCESO, FINALIZADA, SUSPENDIDA, CANCELADA; default PLANIFICADA, administrado por servicios. |
| `finalizado_en` | DateTimeField nullable, solo backend al finalizar. |
| `cancelado_en` | DateTimeField nullable, solo backend al cancelar. |
| `creado_por` | FK Usuario, PROTECT, supervisor autenticado que crea. |
| `creado_en`, `actualizado_en` | Automáticos; creado_en inmutable. Solo actualizado_en cambia también por cambio de técnico y transición. |

Propiedades de salida: `codigo` = `OB-` + PK con al menos seis dígitos,
`cliente` y `cliente_nombre` derivados, `presupuesto_codigo`. No contar filas para
generar códigos; no son correlativos tributarios. No almacenar monto, margen,
saldo, avance, indicadores ficticios ni campos financieros en este modelo.

### 5.3 ObraEvento y CategoriaServicioEvento

Historial relacional append-only, distinto de la futura auditoría global.

| Campo de ObraEvento | Definición del modelo 004A |
| --- | --- |
| `id`, `obra` | BigAutoField y FK Obra PROTECT. |
| `tipo` | CREACION, CAMBIO_ESTADO, CAMBIO_TECNICO, EDICION. |
| `estado_anterior`, `estado_nuevo` | Choices de Obra; anterior null solo en CREACION; nuevo obligatorio. |
| `datos_anteriores`, `datos_nuevos` | JSONField PostgreSQL con claves permitidas de ficha; IDs, fechas ISO y strings, nunca montos ni objetos Usuario completos. |
| `registrado_por`, `creado_en` | FK Usuario PROTECT, actor del servicio; timestamp automático. |
| `motivo` | CharField(2000), trim, default vacío. Obligatorio excepto CREACION sin técnico; con técnico inicial requiere motivo de asignación. |

CREACION registra PLANIFICADA, ficha inicial en `datos_nuevos` y `{}` en anteriores;
si incluye técnico, el mismo evento registra asignación, actor y motivo, sin segundo
evento artificial. Transición contiene estados y timestamps cambiados, incluido
`iniciado_en` al iniciar. CAMBIO_TECNICO contiene FK anterior/nueva (pueden ser null
solo en PLANIFICADA); EDICION solo los campos efectivamente cambiados. En cambios
sin transición, estado anterior y nuevo son iguales. No copiar textos comerciales.

CategoriaServicioEvento: FK categoría PROTECT, tipo CREACION/EDICION/ACTIVACION/
DESACTIVACION, datos anteriores/nuevos limitados a nombre/activo, actor, motivo
y timestamp; motivo obligatorio salvo CREACION de categoría. Las filas iniciales del catálogo no simulan
eventos de usuario; su origen se documenta por la migración.

Un evento por operación efectiva, en la misma transacción; fallo no deja eventos.
Orden `(creado_en, id)`. Sin POST/PATCH/DELETE de eventos ni escritura directa
en Django Admin que eluda servicios. No se promete inmutabilidad frente a un DBA.

## 6. Asignación, edición y fechas

**D2 — Decisión del equipo (vigente para el principal en 004A):** técnico
responsable principal opcional solo en PLANIFICADA. Crear no inicia ejecución.
La SPEC-004B amplía el acceso operativo con técnicos participantes adicionales;
no elimina el responsable principal ni altera la relación 1:1 Presupuesto–Obra. Ausencia = null, nunca «Sin asignar», nombre o supervisor.
Un técnico puede ser responsable de varias obras; no inventar cupos ni calendario.

- Asignación/reasignación por SUPERVISOR_OBRAS en PLANIFICADA, EN_PROCESO o
  SUSPENDIDA, con motivo, actor e historial. Desasignar solo en PLANIFICADA.
- Nueva FK no nula activa y rol TECNICO; mismo valor (incluso null → null)
  responde 409 `sin_cambios`, sin evento. No hay equipo multi-técnico.
- Preservar responsable anterior en historial. El técnico anterior pierde acceso
  tras confirmar la reasignación; el nuevo obtiene acceso. No heredar acceso
  por haber sido responsable en el pasado.
- Desactivar un usuario o cambiar su rol no borra su responsabilidad histórica ni
  reasigna automáticamente obras. No es posible imponer rol/actividad con una FK.
- Iniciar/reanudar requieren técnico no nulo, activo y rol TECNICO; la futura
  finalización conserva esa validación. Suspender permite gestionar una baja.
  No se habilita cancelar en 004A.

PATCH de ficha permite solo `descripcion`, `categoria_servicio`, `fecha_programada`
y `motivo` obligatorio si hay cambio, en PLANIFICADA/EN_PROCESO/SUSPENDIDA. El técnico
se cambia mediante acción dedicada. No-op válido responde 200 sin cambiar fecha
ni crear evento. No se admiten cambios en FINALIZADA/CANCELADA.
Categoría explícita se valida activa incluso si se envía la misma; editar otro
campo no exige reactivar la categoría histórica.

**D4 — Decisión del equipo:** `creado_en` inmutable; `fecha_programada` opcional,
editable con motivo/historial, admite pasado/hoy/futuro o null. `iniciado_en`
se fija con hora del servidor al iniciar y no cambia al suspender/reanudar.
No admite entrada del consumidor ni backdating. La programación no dispara
transiciones ni obliga a esperar esa fecha para iniciar. Timestamps terminales
futuros usan hora del servidor, nunca la fecha programada.

### Justificación conjunta D1/D2/D4

Las mantenciones programadas requieren reservar una obra antes de conocer el
técnico o comenzar en terreno. PLANIFICADA representa ese intervalo sin ejecución
ficticia. Una obra reúne las visitas del presupuesto sin duplicar ingresos.
Esta ampliación y las fechas separadas son diseño del equipo, no citas ni acuerdos
externos de FYAG sobre los cuatro estados originales.

## 7. Máquina de estados y significado del cierre

**D3 — Máquina de estados adoptada por el equipo.**
En 004A se incluyen crear, iniciar, suspender y reanudar; la columna delimita
el incremento, no declara rutas ya implementadas:

| Acción | Origen | Destino | Condiciones | Incremento |
| --- | --- | --- | --- | --- |
| Crear | No existe | PLANIFICADA | Presupuesto APROBADO_CLIENTE sin obra, categoría activa, ficha válida; técnico opcional y elegible si se informa, con motivo. | 004A |
| iniciar | PLANIFICADA | EN_PROCESO | Motivo, técnico no nulo y elegible; fijar iniciado_en. | 004A |
| suspender | EN_PROCESO | SUSPENDIDA | Motivo obligatorio. | 004A |
| reanudar | SUSPENDIDA | EN_PROCESO | Motivo obligatorio, técnico elegible. | 004A |
| finalizar | EN_PROCESO | FINALIZADA | Motivo/resumen operativo, técnico elegible y costos completos verificables; D8. | 004B, no disponible en 004A |
| cancelar | Por especificar | CANCELADA | Conceptual; orígenes y reglas financieras pendientes de otra SPEC. | Fuera de 004A, sin habilitación automática en 004B |

Todas ejecutadas por SUPERVISOR_OBRAS. No existen otras transiciones ni PATCH de
estado. SUSPENDIDA debe reanudarse antes de finalizar. FINALIZADA y CANCELADA son
terminales; no reapertura ni cancelación después de finalizar en este incremento.
La suspensión permite retomar; cancelar es abandonar definitivamente la ejecución.
Repetir una transición responde 409 y no crea otro evento. No hay idempotency keys.

Cancelar conserva obra, presupuesto, técnico, fechas e historial. No significa
anular factura, devolver dinero, liberar el presupuesto ni borrar costos futuros.
Si se necesita corregir una cancelación accidental, se requiere un procedimiento
de rectificación acordado; no insertar una obra duplicada para sortear unicidad.

### Finalización operativa frente a cierre comercial

FINALIZADA significa ejecución terminada, declarada por el supervisor. No significa
facturada, pagada, rentable ni cerrada comercialmente. El ciclo Beta p. 4 es:

```text
EN_PROCESO → FINALIZADA → [Facturación → Cuenta por cobrar → Pago → Cierre comercial]
                          ámbito futuro de Finanzas, no estados de Obra
```

La frase «no cerrar si hay pagos pendientes» se interpreta como cierre comercial,
no como requisito de FINALIZADA. Exigir pago antes de finalizar bloquearía la
facturación que nace después: no se introduce esa dependencia circular.
No se consulta cobranza para finalizar ni se crea `pagado` o `cerrada` ficticio.

El ejemplo «no cancelar con pagos asociados» es distinto: antes de integrar
Finanzas habrá que definir pagos efectivos, anticipos, anulados y documentos
vigentes, y comprobarlos bajo bloqueo de Obra. Hoy no existen tales entidades
backend: la transición sigue siendo conceptual, no se ofrece cancelación en 004A
ni se afirma que exista control financiero. No aceptar `tiene_pagos` desde el consumidor.
Especificar reglas financieras antes de implementar cancelación; toda reversión será
explícita y nunca consecuencia automática de cancelar.

### Costos completos: requisito conservado y entrega parcial

La minuta B p. 2 exige costos completos antes de FINALIZADA. No equivale a cobro
completo. Registrar una suma positiva tampoco prueba que estén completos.
**D8 conserva el requisito del Anexo B sin excepciones.** 004A no finaliza ni
declara cumplido el cierre completo. 004B exige costos reales registrados y
completitud validada con criterios verificables por especificar antes de habilitar
la acción. Una suma positiva, checkbox o flag del frontend no sustituyen evidencia.
Dividir incrementos no certifica cumplimiento actual ni aprobación externa.

## 8. Presupuesto utilizado y coordinación implementada con Comercial

La integración entre `crear_obra` (Obras) y `anular_presupuesto` (Comercial)
**está implementada conjuntamente en 004A**, integrada en `main`
mediante el PR #8. Se considera uso operativo la existencia de una Obra
desde `PLANIFICADA` y en cualquier estado posterior, incluidos los terminales
futuros. Una Obra cancelada no libera su Presupuesto.

El servicio `anular_presupuesto` rechaza con **HTTP 409** y código público
`presupuesto_utilizado` cuando existe una Obra asociada. No altera el estado
comercial ni crea `PresupuestoEvento` por ese intento. El guard consulta la
relación persistida mediante `Obra.objects.filter(presupuesto_id=...).exists()`;
no acepta banderas editables de frontend para simular utilización.

Crear y anular bloquean primero el **mismo Presupuesto** mediante
`select_for_update()` dentro de una transacción. Tras obtener el bloqueo
revalidan estado y asociación:

1. Si anular confirma primero, crear relee ANULADO y falla sin generar una Obra.
2. Si crear confirma primero, anular detecta la Obra y responde 409.
3. Dos creaciones concurrentes dejan exactamente una Obra; la segunda falla
   con `presupuesto_utilizado`, y la unicidad DB respalda esa decisión.

Esta coordinación está cubierta por pruebas de concurrencia PostgreSQL de 004A.
No se cambian los restantes estados, permisos, revisiones ni aprobaciones de
SPEC-003B. Su §7 documenta ahora la regla efectivamente integrada.

La FK protege la existencia del Presupuesto, pero no garantiza por sí sola que
esté `APROBADO_CLIENTE`: esta invariante cruzada permanece en el servicio
transaccional, no en una CHECK con JOIN.

## 9. Permisos por rol, recurso y campos

Roles EXACTOS de `Usuario.Rol`; abreviaturas solo para esta tabla:
G = GERENCIA, AF = ADMINISTRATIVO_FINANZAS, S = SUPERVISOR_OBRAS, T = TECNICO.
**D6:** separación de funciones adoptada por el equipo, sin bypass operativo por
superusuario. Es una precisión de diseño respecto del acceso total citado en Beta.

| Operación | G | AF | S | T |
| --- | --- | --- | --- | --- |
| Listar/detalle de obras | Todas | Todas, proyección mínima | Todas | Solo responsable actual |
| Crear/editar/reasignar/transicionar | No | No | Sí, según estado | No |
| Historial operativo completo | Sí | No | Sí | No |
| Seleccionar presupuestos disponibles/técnicos | No | No | Sí | No |
| Consultar categorías | Todas | No | Todas | No catálogo global; etiqueta en su obra |
| Crear/renombrar/activar/desactivar categorías e historial | Sí | No | No | No |
| Borrar obras/categorías/eventos | No | No | No | No |

AF consulta en 004A una proyección mínima para coordinación (§10.2), sin historial,
escrituras, candidatos ni catálogo global. La categoría se identifica en su ficha.

Técnico: filtrar queryset por `tecnico_responsable_id=request.user.pk` ANTES de
paginar, contar y resolver detalle. Obra ajena = 404 idéntico a inexistente.
Incluye sus obras terminales para trazabilidad (diferencia con el mock, D6).
No basta con permiso de objeto en retrieve: listado, count y filtros también
deben estar acotados. Verificación por PK, no por nombre, email ni parámetro `rol`.

La ficha operativa de todos los roles excluye monto de presupuesto, precios,
ítems comerciales, costos, margen, pagos, saldos, datos bancarios y credenciales.
No anidar serializers de Presupuesto/Cliente/Usuario completos. ID/código de
presupuesto solo identifica el origen y no concede acceso al endpoint comercial.
Supervisor y técnico siguen sin acceso general a `/api/presupuestos/` o Clientes.
Las descripciones operativas se redactan sin información financiera; no copiar
automáticamente campos libres comerciales que pudieran contener precios.
Historial restringido a G/S; motivos no son un canal de notas financieras.

## 10. Contrato HTTP implementado para 004A

### 10.1 Rutas

La tabla corresponde a las rutas **implementadas en 004A**, conforme a las
decisiones del equipo (§15). Las rutas terminales se detallan por separado:
no se registran en 004A ni se anuncian en su esquema u OPTIONS.

| Método y ruta | Entrada/función | Éxito |
| --- | --- | --- |
| GET `/api/obras/` | Lista autorizada. | 200 |
| POST `/api/obras/` | Crear ficha desde presupuesto. | 201 |
| GET `/api/obras/{id}/` | Ficha operativa. | 200 |
| PATCH `/api/obras/{id}/` | Campos editables + motivo. | 200 |
| POST `/api/obras/{id}/cambiar-tecnico/` | `tecnico_responsable`, `motivo`. | 200 |
| POST `/api/obras/{id}/iniciar/` | `motivo`; fija iniciado_en. | 200 |
| POST `/api/obras/{id}/suspender/` | `motivo`. | 200 |
| POST `/api/obras/{id}/reanudar/` | `motivo`. | 200 |
| GET `/api/obras/{id}/historial/` | Eventos paginados, G/S. | 200 |
| GET `/api/obras/presupuestos-disponibles/` | S: APROBADO_CLIENTE sin obra. | 200 |
| GET `/api/obras/tecnicos-disponibles/` | S: usuarios activos rol TECNICO. | 200 |
| GET/POST `/api/categorias-servicio/` | Consultar/crear catálogo. | 200/201 |
| GET/PATCH `/api/categorias-servicio/{id}/` | Detalle/renombrar con motivo. | 200 |
| POST `/api/categorias-servicio/{id}/activar/` o `/desactivar/` | `motivo`. | 200 |
| GET `/api/categorias-servicio/{id}/historial/` | G: historial de catálogo. | 200 |

Rutas del ciclo posterior (no disponibles en 004A):

| Ruta conceptual | Entrega y condición |
| --- | --- |
| POST `/api/obras/{id}/finalizar/` | 004B, tras implementar y probar costos completos conforme D8; contrato especificado en SPEC-004B; implementación y pruebas pendientes. |
| POST `/api/obras/{id}/cancelar/` | Otra SPEC con reglas financieras; no se habilita automáticamente con 004B. |

En 004A esas rutas no están registradas (404); POST/PATCH de `estado` continúa
rechazado (400). Tampoco habrá servicio público que permita finalizar sin API.
SPEC-004B especifica rutas de participantes, turnos, gastos y costos, así como
permisos y contratos propios; no están implementados en 004A y no se agregan
campos monetarios a la salida operativa de Obra.

Sin PUT ni DELETE. HEAD/OPTIONS estándar con los mismos permisos de lectura.
Activar/desactivar ya en ese valor = 200 sin evento ni cambio de fecha, como
Clientes. PATCH nombre idéntico = 200 sin evento; cambios efectivos exigen motivo.

### 10.2 Entradas y salidas

POST requiere `presupuesto`, `categoria_servicio`, `descripcion`. Opcionales:
`tecnico_responsable` y `fecha_programada` (omitidos equivalen a null). `motivo`
obligatorio si se asigna técnico inicial; opcional en otro caso. Ejemplo:

```json
{
  "presupuesto": 1,
  "categoria_servicio": 2,
  "descripcion": "Mantención de unidad de frío en sala técnica",
  "tecnico_responsable": 7,
  "fecha_programada": "2026-11-20",
  "motivo": "Asignación inicial para mantención programada"
}
```

IDs enteros JSON positivos hasta el límite BigAutoField; rechazar bool, float,
strings y null salvo técnico según §6. Texto real, trim antes de longitud y obligatoriedad. Fecha string
ISO `YYYY-MM-DD`, calendario válido, sin hora. Validar estado final del PATCH,
sin borrar campos omitidos; fecha_programada admite null explícito para retirarla.
Objetos/listas anidados no admitidos. Cambiar técnico exige ambos campos; null
solo en PLANIFICADA. Iniciar/suspender/reanudar reciben únicamente `motivo`.

Server-managed en Obra: `id`, `codigo`, `cliente`, `cliente_nombre`,
`presupuesto_codigo`, `estado`, `iniciado_en`, `finalizado_en`, `cancelado_en`, `creado_por`,
`creado_en`, `actualizado_en`. `presupuesto` solo en POST; técnico solo en POST
y acción específica. Rechazar 400 todos los campos desconocidos, montos e
intentos de controlar `requiere_aprobacion_gerencia`, incluso con `true`.

Salida de ficha/listado G/S/T: `id`, `codigo`, `presupuesto`, `presupuesto_codigo`,
`cliente`, `cliente_nombre`, `categoria_servicio`, `categoria_nombre`,
`descripcion`, `tecnico_responsable`, `tecnico_nombre`, `fecha_programada`, `iniciado_en`, `estado`,
`finalizado_en`, `cancelado_en`, `creado_por`, `creado_en`, `actualizado_en`.
Nombres de usuario: `get_full_name()` o username si vacío, nunca fallback a email.
Relaciones en enteros, sin URLs que otorguen acceso a recursos generales.
Mutaciones devuelven la misma ficha final. Historial en ruta separada.

Serializer explícito AF para listado/detalle: SOLO `id`, `codigo`, `presupuesto`,
`presupuesto_codigo`, `cliente`, `cliente_nombre`, `categoria_servicio`,
`categoria_nombre`, `tecnico_responsable`, `tecnico_nombre`, `fecha_programada`,
`iniciado_en`, `estado`, `finalizado_en`. Excluye descripción libre, actores,
motivos, historial y campos adicionales de la ficha G/S/T. Técnico/nombre son null
si no hay asignación. Selección de serializer por rol del usuario autenticado,
nunca por parámetro; listas, detalle, esquema y OPTIONS respetan esa proyección.
Serializers de entrada separados por creación, ficha y acciones; no reutilizar
el de salida para permitir campos administrados por backend.

Presupuestos disponibles devuelve SOLO `id`, `codigo`, `cliente`, `cliente_nombre`;
no descripción comercial, ítems, monto ni historial. Crear exige una descripción
operativa nueva. Técnicos disponibles: solo `id`, `nombre`. Son proyecciones de
Obras, no ampliaciones de permisos comerciales ni una API general de usuarios.
La lista es orientativa: creación revalida bajo bloqueo.

Categoría: POST `{nombre}`; PATCH `{nombre, motivo}`; salida `id`, `nombre`,
`activo`, `creado_por`, `creado_en`, `actualizado_en`. Historial devuelve los campos
de evento descritos en §5.3; no incluir secretos ni información financiera.

Paginación DRF `{count,next,previous,results}`, 25 fijo. Obras por defecto
`(-creado_en,-id)`; filtros opcionales `estado`, `tecnico_responsable`, `cliente`,
`categoria_servicio`, `fecha_programada_desde`, `fecha_programada_hasta` (inclusivos;
excluyen fechas null cuando se aplica un límite).
Validar tipos, rango de fechas y choices; FK válida sin coincidencias da lista vacía.
Filtro de otro técnico nunca amplía el queryset de T. Orden permitido:
`creado_en`, `-creado_en`, `fecha_programada`, `-fecha_programada`, con ID del mismo
sentido como desempate y fechas null al final. AF usa estos mismos filtros/orden.
Sin orden/filtros por datos monetarios.
Catálogo por `(nombre,id)`, filtro `activo=true/false`, default todos para G/S;
presupuestos disponibles por `(-creado_en,-id)` y técnicos por PK ascendente.
Historial por `(creado_en,id)`. Parámetros de filtro/orden inválidos = 400.
Usar `select_related` y consultas acotadas; no N+1 ni cargar todos los eventos.

### 10.3 Errores y precedencia

- 400: entrada inválida/desconocida, FK en body inexistente, categoría inactiva,
  técnico ausente al iniciar o no elegible, null prohibido fuera de PLANIFICADA,
  fecha inválida, nombre de categoría duplicado, motivo vacío cuando obligatorio.
- 401: sin JWT válido/usuario no autenticable, siguiendo Auth existente.
- 403: rol sin permiso de acción, antes de revelar existencia del recurso.
- 404: recurso inexistente o fuera del queryset autorizado; página inexistente.
- 405: método no soportado para usuario autorizado.
- 409: `estado_incompatible`, `presupuesto_utilizado`, `sin_cambios` en reasignación;
  futuro bloqueo de cancelación por compromiso financiero tendrá código propio.

Orden: autenticación → permiso → existencia/recurso autorizado → contrato de
entrada → reglas de estado y dominio bajo bloqueo. Errores de campo por clave;
conflictos `{detail, code}`. No filtrar nombres de constraints ni errores SQL.
Traducir únicamente IntegrityError conocidos fuera del atomic fallido.

## 11. Transacciones y concurrencia

El orden de bloqueos aplica desde 004A. Los escenarios con finalizar corresponden
a 004B; cancelar requiere otra especificación financiera. No habilitan esas acciones
en 004A. Para este incremento se prueban además suspensión/reanudación concurrentes
y reasignación/edición frente a ellas, releyendo el estado después del bloqueo.

Toda escritura de dominio y su evento usan `transaction.atomic()`. Releer filas
persistidas después de `select_for_update()`, no confiar en objetos de la view.

Orden común: Presupuesto → Obra (si existe) → CategoriaServicio (si se valida)
→ Usuario técnico (si se valida). Varias filas del mismo tipo por PK ascendente.
Creación bloquea Presupuesto, categoría y técnico solo si se informa; no existe
Obra aún. Iniciar bloquea Obra y su técnico actual después del Presupuesto. Transiciones
pueden bloquear presupuesto y luego obra uniformemente, evitando inversión de
orden con Comercial. Para descubrir el presupuesto se puede leer su ID antes,
pero revalidar asociación tras el bloqueo: no confiar en una FK mutable del caller.

- Creación/anulación/duplicidad: serialización según §8 y unicidad definitiva DB.
- Iniciar/iniciar: un éxito y un 409, un solo timestamp/evento de inicio.
- Iniciar/asignar/desasignar: releer estado y técnico bajo lock. Si desasignar gana,
  iniciar falla por ausencia; si iniciar gana, desasignar falla fuera de PLANIFICADA.
  Una reasignación válida puede preceder o seguir al inicio con eventos ordenados.
- Dos decisiones terminales: una gana; la otra encuentra estado terminal y falla.
- Suspender vs finalizar: cualquiera que gane hace incompatible la segunda.
- Reasignar vs finalizar: si reasignar gana, se finaliza con nuevo responsable;
  si finalizar gana, reasignar falla. Ambos éxitos secuenciales pueden ser válidos.
- PATCH vs transición: si PATCH confirma primero, la transición usa ficha nueva;
  si la terminal confirma primero, PATCH falla sin evento.
- Desactivar categoría vs asignarla: bloqueo de categoría serializa su elegibilidad;
  desactivación posterior al commit no invalida la obra ya creada.
- Desactivar/cambiar rol de técnico vs asignar/iniciar/reanudar/finalizar: bloquear usuario;
  el update concurrente serializa con este lock. Baja posterior no borra historia.
  Futuros servicios de usuarios no deben adquirir locks en orden inverso.
- Lecturas de T se filtran con FK actual en la consulta. Una respuesta ya obtenida
  antes de reasignar no puede retirarse; peticiones posteriores al commit no deben
  conservar permisos mediante caché ni prefetch de otra solicitud.

No señales para orquestar transiciones. No escrituras vía bulk/update en servicios
que eludan invariantes. Admin futuro solo lectura para obra/eventos salvo acciones
que invoquen servicios. La DB no implementa por sí sola toda la máquina de estados.

## 12. Integridad PostgreSQL y migraciones de 004A

- FK reales y PROTECT: presupuesto, categoría, responsable, actores y eventos.
- Unicidad no condicional de `Obra.presupuesto`, incluso canceladas/finalizadas.
- CHECK estado pertenece exactamente a los cinco choices, incluida PLANIFICADA.
- Descripción/nombre no vacíos e iguales a `Trim`; normalizar también con strip.
- `Lower(nombre)` único globalmente, incluidas categorías inactivas.
- Presupuesto y categoría NOT NULL. CHECK: técnico no null o estado PLANIFICADA.
  Fecha programada nullable, sin restricción contra fechas futuras.
- PLANIFICADA exige iniciado_en null; EN_PROCESO/SUSPENDIDA/FINALIZADA lo exigen
  no null. CANCELADA conceptual no fija aún si hubo inicio, pero conserva técnico
  no null por D2; sus futuros orígenes deberán respetarlo o revisar explícitamente
  el diseño. Ninguna ruta actual puede producir CANCELADA.
- iniciado_en, si existe, >= creado_en; finalizado_en >= iniciado_en cuando exista.
  Inmutabilidad del inicio y del origen se garantiza por servicios, no solo CHECK.
- FINALIZADA si y solo si finalizado_en no null; CANCELADA si y solo si
  cancelado_en no null. En estados no terminales ambos null.
- Timestamps terminales no anteriores a creado_en (CHECK misma fila).
- Eventos: tipo/estados válidos, motivo normalizado y obligatorio salvo creación
  sin técnico (motivo inicial condicionado validado por modelo/servicio);
  anterior null solo para CREACION, creación nueva PLANIFICADA, unicidad condicional
   de evento CREACION por obra; CAMBIO_ESTADO anterior distinto de nuevo y par
   habilitado en §7 (004A: iniciar/suspender/reanudar; ampliar en 004B para finalizar,
  nunca admitir pares de cancelación aún indefinidos); otros tipos con estados iguales.
  JSON con esquema validado por modelo
  y servicio, no prometer una FK para IDs guardados en JSON.
- Índices de FK y para consultas `(tecnico_responsable, estado)` e historial
  `(obra, creado_en, id)`; revisar planes antes de añadir índices especulativos.

Estado del presupuesto, rol/actividad del técnico, actividad de categoría,
inmutabilidad de fechas técnicas y secuencia/eventos completos son reglas de aplicación bajo
transacción, no CHECK con JOIN ni con el reloj del servidor. `save()` validará
estructura mediante full_clean, como Presupuestos; bulk SQL solo tiene garantías
de constraints. No afirmar que full_clean sustituye locks o permisos.

En 004A se generaron y aplicaron localmente las migraciones `obras.0001_initial`,
`obras.0002_catalogo_inicial`, `obras.0003_alter_*` (validación de JSON vacío)
y `obras.0004_remove_obraevento_*` (constraint de eventos de creación).
La dependencia parte de la última migración de Comercial y del Usuario swappable.
No editar migraciones históricas, crear obras retroactivas ni fabricar eventos.
El catálogo inicial se carga por migración de datos con modelos históricos y
alias de conexión; la reversa evita borrar categorías usadas.
La ejecución local confirmó `migrate --noinput` y ausencia de drift con
`makemigrations --check --dry-run`. Backend CI del PR #8 aprobó la integración
de 004A en `main`. Las migraciones de 004B serán nuevas, posteriores a `0004`.

## 13. Pruebas automatizadas y criterios de aceptación

Las pruebas locales se ejecutaron con Django/PostgreSQL, sin sustituir SQLite.
**Resultado local reportado: 44 pruebas de `apps.obras` y 332 pruebas del backend
completo, todas `OK`**, con `manage.py check` correcto y sin migraciones
pendientes. Ese resultado no sustituye el check de GitHub Actions ni constituye
aprobación formal externa del cliente.

**Alcance de la cobertura:** la suite actual incluye modelos, servicios,
API/roles, integridad de eventos y carreras reales crear/anular en ambos órdenes,
además de dos creaciones concurrentes. La lista siguiente conserva criterios
de aceptación del MVP y de regresión, pero **no afirma que cada escenario
enumerado ya tenga un test independiente**. La validación CI y cualquier
cobertura adicional se completarán durante revisión del PR.

Las carreras con `finalizar` y el punto 15 pertenecen a 004B; las que involucran
`cancelar`, a una futura SPEC financiera. En 004A no existen rutas ni servicios
para esas acciones; se rechaza `estado` inyectado y la creación de Obra y el
bloqueo de anulación son una única entrega.

1. Modelos: campos/defaults, código estable, fechas, FK protegidas, cliente derivado,
   categorías iniciales, cero duplicación de montos o nombres como claves.
2. Constraints reales mediante bulk_create/update y SQL: FK, NOT NULL, unicidad
   presupuesto incluso terminal, choices, trim, timestamps coherentes y eventos.
3. Crear desde cada estado de Presupuesto: solo APROBADO_CLIENTE; no cambios ni
   eventos comerciales, un evento inicial PLANIFICADA; categoría válida, técnico
   omitido/null o elegible con motivo. iniciado_en null incluso con programación pasada.
4. Cliente desactivado después de aceptación según D5; cliente de obra no editable.
5. Matriz completa de estados × acciones, repeticiones 409, terminales congelados,
   sin saltos ni reapertura. Iniciar exige técnico elegible, fija un solo iniciado_en;
   reanudar no lo cambia. Suspensión conserva ficha y responsable.
6. Reasignar: técnico activo/rol correcto, motivo, antes/después, misma FK 409,
   desasignar solo PLANIFICADA, prohibido en otros estados/terminales;
   pérdida/ganancia de acceso, también en planificación.
7. Fecha operativa: pasado/hoy/futuro, formato, límites de día local, correcciones
   con historial, null/omisión, futuro permitido, inicio independiente de programación,
   rechazo de timestamps inyectados y antiguo campo fecha_inicio.
8. Permisos cuatro roles con JWT real y superusuario: cada método/acción, sin
   bypass de rol; falsificación por body/query/header rechazada.
9. T: listado/count/paginación/detalle solo propios, obra ajena 404, intentos de
   filtros ampliados, terminales propios según D6; ningún acceso a historial global,
   Usuarios, Clientes o Presupuestos ni modificación de su propia obra.
10. Proyecciones con lista exacta de campos: ausencia de importes, ítems, correos,
    credenciales y datos bancarios, también en candidatos, errores y OPTIONS.
    AF lista/detalle con conjunto mínimo exacto, sin descripción ni historial;
    denegar escrituras, catálogo y candidatos incluso siendo superusuario.
11. Catálogo: administración G, duplicados case-insensitive, trim, activación
    idempotente, baja sin destruir histórico, asignación inactiva 400 y renombres.
12. Historial: actor interno, datos anteriores reales, orden/paginación, eventos
    iniciales únicos, no-op sin evento, rollback completo si falla evento.
13. Anular presupuesto usado en cada estado de Obra: 409 sin PresupuestoEvento;
    presupuesto sin obra mantiene reglas previas; cancelar obra no libera uso.
14. Concurrencia con TransactionTestCase, conexiones independientes y sincronización
    controlada: crear/crear, crear/anular en ambos órdenes, finalizar/cancelar,
    reasignar/finalizar, PATCH/finalizar, categoría baja/asignación y usuario
    baja/asignación, iniciar/iniciar, iniciar/asignar/desasignar y baja/iniciar/reanudar.
    Comprobar eventos y ausencia de filas parciales; no sleeps
    como prueba de exclusión. Admitir ambos éxitos cuando son secuencias válidas.
15. **004B:** finalizar no exige factura ni pago. Probar materiales/horas y costos
    reales según contrato aprobado; completitud verificable y rechazo si falta
    evidencia, rollback, permisos y carrera registro/corrección de costos frente
    a finalizar bajo bloqueo de Obra. Costos completos y cobranza son condiciones
    diferentes. Rechazar flags del frontend y finalización sin costos registrados
    o sin completitud validada; no aprobar automáticamente por suma positiva.
16. HTTP: 400/401/403/404/405/409, precedencia, desconocidos/server-managed, PATCH
    parcial, métodos prohibidos, orden/filtros/paginación y ausencia de N+1.
17. Migraciones en base limpia/existente, catálogo sin usuario inventado, no drift.
18. Regresión completa Auth/Clientes/Presupuestos, incluida aprobación obligatoria
    por Gerencia y sus pruebas de Decimal, concurrencia, revisiones e historial.

## 14. Integraciones futuras y límites

La PK Obra será referencia estable para materiales, horas y costos reales.
Registrar esos movimientos como entidades independientes con actor/fecha y
correcciones trazables; no como sobrescritura de un total en Obra.
El responsable actual no reemplaza al técnico que realizó horas históricas.
Material despachado, utilizado y devuelto no son necesariamente el mismo costo:
SPEC-004B define valorización, devoluciones y controles contra doble contabilización;
su implementación aún está pendiente.

Rentabilidad futura usará neto aprobado CLP de Presupuesto y costos reales
definidos, con Decimal y política de redondeo explícita; no IVA como ingreso ni
porcentajes/umbrales del mock. La decisión 1:0..1 evita repetir el neto por obra.
No mostrar rentabilidad cero cuando no se han cargado costos: ausencia no es cero.

Al incorporar costos: implementar la completitud/cierre y el guard de finalizar
ya especificados en SPEC-004B, coordinados con el bloqueo de Obra. Antes de incorporar facturas/pagos:
definir bloqueo de cancelar, compensaciones y cierre comercial en Finanzas,
también bajo ese lock. No introducir ahora tablas financieras, MongoDB, flags
temporales de integración, mocks productivos ni callbacks que siempre aprueben.

Fuera de 004A, especificados en 004B: participantes técnicos, turnos por Obra,
evidencia textual y fotos opcionales, materiales y gastos, costos reales,
revisión del Supervisor, completitud verificable y habilitación de finalizar.
La SPEC-004B ya define valorización, correcciones, evidencia y quién valida;
no están implementados y su ausencia no equivale a cero costos.

Fuera de ambos incrementos: inventario y stock,
facturas/pagos/cobranza, márgenes, auditoría global/MongoDB, adjuntos generales
(distintos de las fotos opcionales de turno 004B), avances y bitácora móvil general,
PDF/Excel, dashboard, alertas, notificaciones, reapertura, sustitución de
presupuesto usado y política de aprobación configurable.
Las necesidades del Beta completo se desarrollarán en otras SPEC, no se declaran
eliminadas por acotar este incremento.

D9: emergencias mantienen las aprobaciones comerciales vigentes; priorización
operativa futura. Garantías gratuitas requieren una SPEC de circuito sin cobro,
trazable a la obra/presupuesto de origen; 004A no las cubre mediante presupuestos
ficticios ni excepciones al neto positivo. Cancelación requiere reglas financieras
reales en otra SPEC, sin guard ficticio ni activación automática en 004B.

## 15. Decisiones de diseño adoptadas para el MVP

D1–D9 son decisiones técnicas del equipo **reflejadas en el 004A implementado**,
no acuerdos formalmente aprobados por FYAG. Las fuentes se identifican en §2;
sus ampliaciones no se presentan como requisitos originales.

| ID | Decisión adoptada | Fundamento y alcance |
| --- | --- | --- |
| D1 | OneToOneField Presupuesto–Obra, incluso terminal. Varias visitas en una obra. | Precisión del equipo: evita duplicar ingresos y conserva origen. |
| D2 | Técnico nullable solo PLANIFICADA; elegible para iniciar/reanudar. Toda asignación con actor, motivo e historial. | Ampliación para planificación de terreno; sin desasignar durante ejecución. |
| D3 | Crear PLANIFICADA; iniciar EN_PROCESO; suspender SUSPENDIDA; reanudar EN_PROCESO. | PLANIFICADA amplía los cuatro estados originales. FINALIZADA en 004B; CANCELADA conceptual. |
| D4 | creado_en inmutable; fecha_programada opcional/editable/futura; iniciado_en al inicio real. | Precisión del equipo que separa planificación de ejecución y auditoría. |
| D5 | Cliente inactivo no invalida presupuesto aprobado ni bloquea ejecución. | Decisión coherente con preservación histórica de SPEC-003B. |
| D6 | G lee todo/administra categorías; S opera; AF proyección mínima; T solo asignación actual. Sin datos financieros ni bypass por superusuario. | Matriz adoptada por el equipo; controles en backend. |
| D7 | Finalización independiente de factura/pago. Sin cancelar ni simular controles financieros en 004A. | Conserva ciclo Beta y evita dependencia circular. |
| D8 | FINALIZADA exige costos reales registrados y completitud validada en 004B. | Conserva exigencia Anexo B; sin finalizar en 004A ni flags que omitan control. |
| D9 | Emergencias con flujo aprobado; garantías gratuitas sin presupuestos ficticios. | Priorización futura; circuito sin cobro trazable al origen en otra SPEC. |

La SPEC-004B precisa la valorización manual, la evidencia de turnos y la
validación de completitud con decisiones B1–B8. Su implementación sigue pendiente.
También quedan fuera la cancelación con compromisos financieros y el circuito
tributario de gratuidades. No son alternativas pendientes a D1–D9 ni habilitan
esas funcionalidades en 004A.

## 16. Estado de entrega y validación para integración

El incremento **004A está implementado e integrado en `main` a través del
Pull Request #8, con Backend CI verde**. Se realizaron:

1. Modelos, constraints y migraciones de categorías, obras e historiales.
2. Servicios transaccionales para creación, edición, cambio de técnico, inicio,
   suspensión, reanudación y administración de categorías.
3. Integración inseparable con el guard de anulación en Comercial, mediante
   bloqueo común del Presupuesto y pruebas de concurrencia en PostgreSQL.
4. Serializers de entrada y salida, permisos por rol/recurso, proyección mínima
   para Finanzas, filtros, paginación y rutas HTTP de 004A.
5. Pruebas locales: 44 de Obras, 266 de Comercial y 332 del proyecto completo,
   todas correctas. `manage.py check` y `makemigrations --check --dry-run`
   reportaron cero errores y cero cambios pendientes.

**Integración confirmada:** PR #8 fusionado el 7 de noviembre de 2026 tras
Backend CI verde. La cobertura local de referencia para 004A fue de 332 tests.
La entrega posterior de 004B necesita su propia validación CI; no está incluida
en esa aprobación histórica.

**Pendiente de implementación:** aplicar `specs/004b-costos-finalizacion.md`
por entregas, con migraciones y pruebas para participantes, turnos y evidencias,
materiales/gastos, completitud y `finalizar`. La gratuidad documentada en 004B
no equivale a facturación real. Cancelación de Obras y circuito tributario de
garantías/cortesías requieren especificaciones posteriores.

Comandos de validación utilizados/previstos en Docker:

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py migrate --noinput
python manage.py test apps.obras
python manage.py test apps.comercial
python manage.py test
```

El workflow `.github/workflows/backend-ci.yml` se activa con cambios de backend
en Pull Requests hacia `main`; para 004A ya finalizó en verde en el PR #8.
Esta actualización es **solo documental**: no cambia modelos, migraciones,
servicios, endpoints ni tests. 004B requiere nuevas ejecuciones y un PR propio.
