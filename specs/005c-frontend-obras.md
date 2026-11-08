# SPEC-005C — Integración del frontend: Gestión real de Obras

**Estado:** especificada, pendiente de implementación. **Fecha de definición:** 8 de noviembre de 2026. **Rama prevista:** `feature/frontend-005c-obras`, creada desde `main` después del PR #15.

**Naturaleza:** contrato de integración de React con las API de Obras ya implementadas en Django. Esta SPEC **no añade reglas al dominio**, no crea endpoints ni autoriza cambios en el backend. Para cualquier discrepancia prevalecen las SPEC-004/004B, los serializers, permisos y servicios realmente integrados en `main`: informar la discrepancia y no inventar una solución en React.

## 1. Contexto y decisión de alcance

- SPEC-005A integra autenticación real JWT/CSRF y sesión en memoria; PR #14 integrado.
- SPEC-005B integra Clientes y Presupuestos reales, con formularios, edición en línea, pruebas y Frontend CI; PR #15 integrado el 8-11-2026. El cliente HTTP común está en `frontend/src/auth/client.js`, y los patrones de aislamiento y reconsulta en `frontend/src/comercial/`.
- Backend Obras: SPEC-004A (PR #8) y 004B-1 a 004B-5 (PR #9 a #13) implementados, con migración `0011_cierre_costos_finalizacion.py` y suite previa de 508 pruebas del backend.
- `frontend/src/app.jsx` conserva Obras como `PendingIntegration`; el antiguo `frontend/src/pages/Obras.jsx` y `TecnicoApp.jsx` son prototipos de estados/acciones distintos del contrato Django. **No montarlos tal cual.** Reutilizar únicamente diseño o componentes presentacionales seguros después de verificar sus dependencias.
- Módulos Finanzas, Reportes, Dashboard, Alertas y administración de usuarios siguen sin integración real. **No** presentar cifras del mock como datos persistidos.

### Objetivo de producto

Ofrecer a Gerencia, Supervisor, Administrativo/Finanzas y Técnico la experiencia operativa autorizada sobre una misma fuente de verdad (PostgreSQL): creación y seguimiento de obras, participantes, turnos, evidencia privada, gastos, control y validación de costos, cortesía y finalización **operativa**. No es facturación ni cierre comercial.

### División de entregas para control de cambios

La SPEC completa cubre **005C-1, 005C-2 y 005C-3**; implementarlas en PR independientes y acumulativos. No ejecutar los tres bloques juntos antes de revisar el primero.

1. **005C-1 — Fichas y operación de Obras:** listado, detalle, filtros, categorías, presupuestos disponibles, técnicos disponibles, creación/edición, cambios de estado y técnico, participantes, historiales operativos y proyección restringida de AF. Vista de Técnico solo lectura de sus obras, pendiente de activar turnos en 005C-2.
2. **005C-2 — Turnos y evidencia privada:** inicio/cierre/subsanación por técnico; revisión, corrección y cierre administrativo por supervisor; listado e imágenes protegidas, acceso y descargas seguras.
3. **005C-3 — Gastos, control y cierre:** materiales/otros gastos, devoluciones, anulaciones, control de rubros, validación y versiones, resúmenes, cortesía y finalización; históricos económicos por rol.

Cada subentrega debe tener pruebas frontend, build, revisión técnica, PR y Frontend CI en verde. La presente SPEC se mantiene como marco integral; avances parciales no autorizan declarar 005C completa.

## 2. Principios técnicos y seguridad

1. Reutilizar **la misma instancia** `authClient` de 005A mediante `useAuth().request`, con token Bearer y refresh existente. No crear cliente `fetch` sin autenticación para consumir Obras.
2. Reutilizar/adaptar prudentemente `createScope` de 005B, incluyendo cancelación en desmontaje/cambio de sesión, protección frente a respuestas tardías, bloqueo de doble escritura, timeout y estado de reconsulta tras resultado incierto. **No repetir POST/PATCH/DELETE automáticamente** por fallas de red, timeout o 5xx; una operación pudo persistirse aunque se perdiera la respuesta.
3. En 401 usar renovación existente; en 403 conservar la denegación, sin cambiar rol ni simular acceso. Un 404 de objeto fuera de alcance no debe filtrar datos de otras obras.
4. Cargar datos bajo **identidad + rol + recurso**; limpiar vistas, formularios, fotos y respuestas pendientes cuando cambia el usuario o se cierra sesión. No persistir JWT, evidencia o costos en `localStorage`, `sessionStorage` ni cachés de larga vida.
5. No enviar en los cuerpos campos administrados por servidor: IDs propios, `estado`, timestamps, actor, costos calculados, banderas de completitud, versiones, `subtotal`, `finalizado_en` o datos de otro usuario técnico.
6. Solo presentar importes y detalles permitidos por la proyección real de cada rol. No deducir un costo/hora de la remuneración ni un costo real del presupuesto. El código y descripción comercial no deben copiarse a la ficha operativa.
7. Todos los identificadores en JSON deben ser **enteros positivos**; fechas `YYYY-MM-DD`; duraciones ajustadas como enteros positivos; cantidades y valores monetarios **strings decimales con punto y precisión exacta**, sin calcular netos con `Number` ni alterar redondeos.
8. Respetar paginación nativa DRF, páginas de 25 y estructuras `{count,next,previous,results}`. No confundir un filtro local de página con un filtro global del servidor. Respetar los parámetros efectivamente soportados.
9. No utilizar `window.location`, `<img src="/api/...">`, enlaces directos ni `window.open` para recursos de evidencia privados, pues requieren cabecera Bearer; ver §7.
10. **Diseño visual aprobado:** React + Bootstrap 5 + CSS propio FYAG, **Bootstrap Icons oficiales para todos los iconos nuevos** (SVG inline o fuente oficial si ya estuviera instalada). No introducir otra biblioteca de íconos, no agregar tutoriales técnicos permanentes, conservar etiquetas, estados vacíos, confirmaciones y mensajes de error contextuales.
11. La autorización es siempre del backend. Los controles condicionales mejoran la UX, pero jamás reemplazan permisos ni guards transaccionales de Django.
12. No hacer cambios al backend ni crear tablas/migraciones para salvar una limitación de presentación. Documentar obstáculos de contratos antes de cambiar el alcance.

## 3. Matriz de permisos por rol (contrato actual de `permissions.py`)

| Recurso/acción | GERENCIA (G) | SUPERVISOR_OBRAS (S) | ADMINISTRATIVO_FINANZAS (AF) | TECNICO (T) |
| --- | --- | --- | --- | --- |
| Listado/detalle de Obras | Lectura operativa | Lectura operativa | **Lectura mínima** | Solo membresía activa |
| Crear/editar Obra, cambiar responsable, transiciones incluida FINALIZADA | No | Sí | No | No |
| Presupuestos disponibles y técnicos disponibles | No | Sí | No | No |
| Categorías de servicio | Gestiona y lee | Solo lee | No | No |
| Historial operativo de Obra | Lee | Lee | No | No |
| Participantes/lista e historial | Lee | Lee y asigna/desasigna | No | No |
| Turnos y evidencia | Lee | Lee y revisa/corrige/cierra administrativamente | No | Solo turnos **propios** y fotos permitidas |
| Inicio/cierre/subsanación de turnos | No | No | No | Solo su turno propio |
| Gastos e historial económico | Lee | Lee y escribe | No | No |
| Control de rubros | Lee | Lee y modifica | No | No |
| Validar costos y registrar cortesía | No | Sí | No | No |
| Resumen de costos | Completo | Completo | **Resumen mínimo** | No |
| Finalizar Obra | No | Sí | No | No |

No existe bypass por `is_superuser`. AF no ve descripción libre de la obra, auditoría, turnos, tarifas ni fotos; **su ficha de Obra no es igual a la de G/S**. El técnico solo visualiza obras con una membresía `ObraParticipante.activo=True` y sus propios turnos. No mostrar costo/hora ni importes al técnico.

## 4. API operativa — 005C-1

Todas las rutas comienzan en `/api/` y exigen JWT. Un `SimpleRouter` registra `obras` y `categorias-servicio`; las acciones `@action` llevan `/` al final. No inventar ruta de cancelación/reapertura ni un recurso de progreso en porcentaje.

### 4.1 Listado y ficha

| Método | Ruta | Rol | Respuesta/semántica |
| --- | --- | --- | --- |
| GET | `/api/obras/` | G/S/AF/T | Listado paginado de 25; T limitado por membresía activa; AF proyección mínima. |
| GET | `/api/obras/{id}/` | G/S/AF/T con recurso permitido | Detalle autorizado. |
| GET | `/api/obras/mis-obras/` | T | Listado paginado de sus obras autorizadas, con los filtros permitidos de Obras. |
| GET | `/api/obras/{id}/historial/` | G/S | Historial paginado, sin cifras económicas. |
| GET | `/api/obras/presupuestos-disponibles/` | S | Presupuestos `APROBADO_CLIENTE` sin Obra; lista paginada. |
| GET | `/api/obras/tecnicos-disponibles/` | S | Usuarios activos con rol T; lista paginada. |

Filtros **de servidor** permitidos para `/obras/` y `/mis-obras/`: `estado` (enum real), `tecnico_responsable` (ID), `cliente` (ID), `categoria_servicio` (ID), `fecha_programada_desde`, `fecha_programada_hasta` (ISO), `ordering` solo `creado_en`, `-creado_en`, `fecha_programada`, `-fecha_programada`; `page` una sola vez. No enviar parámetros vacíos, repetidos, aliases o campos de filtrado no soportados. Si se muestra un filtro, indicar realmente qué hace y conservar paginación/estado.

Estados exactos: `PLANIFICADA`, `EN_PROCESO`, `SUSPENDIDA`, `FINALIZADA`, `CANCELADA`. `CANCELADA` puede aparecer en lecturas históricas pero **no existe endpoint para cancelarla** en esta entrega.

Proyección `ObraLecturaSerializer` para G/S/T: `id`, `codigo`, `presupuesto`, `presupuesto_codigo`, `cliente`, `cliente_nombre`, `categoria_servicio`, `categoria_nombre`, `descripcion`, `tecnico_responsable`, `tecnico_nombre`, `fecha_programada`, `iniciado_en`, `estado`, `finalizado_en`, `cancelado_en`, `creado_por`, `creado_en`, `actualizado_en`. AF recibe `ObraFinanzasSerializer` con datos mínimos (sin `descripcion`, eventos ni datos de auditoría detallados). Ninguna ficha contiene montos comerciales ni costos reales.

### 4.2 Altas y mutaciones

| Método | Ruta | Cuerpo | Regla |
| --- | --- | --- | --- |
| POST | `/api/obras/` | `presupuesto` (ID), `categoria_servicio` (ID), `descripcion`, `tecnico_responsable` (ID o null, opcional), `fecha_programada` (ISO o null, opcional), `motivo` opcional | S; nace `PLANIFICADA`; presupuesto aprobado por cliente y sin Obra. |
| PATCH | `/api/obras/{id}/` | Subconjunto de `categoria_servicio`, `descripcion`, `fecha_programada`, `motivo` | S, solo campos editables y estados permitidos. |
| POST | `/api/obras/{id}/cambiar-tecnico/` | `{"tecnico_responsable": 7, "motivo": "..."}`; ID puede ser null solo cuando las reglas lo permitan | S; motivo y guardias de membresía/estado. |
| POST | `/api/obras/{id}/iniciar/` | `{"motivo": "..."}` | S; `PLANIFICADA → EN_PROCESO`, responsable elegible. |
| POST | `/api/obras/{id}/suspender/` | `{"motivo": "..."}` | S; `EN_PROCESO → SUSPENDIDA`, sin turnos abiertos. |
| POST | `/api/obras/{id}/reanudar/` | `{"motivo": "..."}` | S; `SUSPENDIDA → EN_PROCESO`, responsable elegible. |

No aceptar cambios directos a `estado`, `tecnico_responsable` mediante PATCH genérico, presupuesto origen o timestamps. Las transiciones solo se ejecutan mediante acciones dedicadas. No iniciar una Obra sin técnico principal elegible. Todo motivo obligatorio se valida antes de enviar; Django sigue decidiendo elegibilidad bajo bloqueo.

### 4.3 Participantes

| Método | Ruta | Rol/contrato |
| --- | --- | --- |
| GET | `/api/obras/{id}/participantes/?page=N` | G/S, todas las membresías, histórico incluido. Filtro servidor `activo=true|false` opcional. |
| POST | `/api/obras/{id}/participantes/` | S, `{"tecnico": 7, "motivo": "..."}`. Alta 201 o reactivación 200. |
| POST | `/api/obras/{id}/participantes/{participante_id}/desasignar/` | S, `{"motivo": "..."}`. No desasignar principal actual ni técnicos con turnos incompatibles. |
| GET | `/api/obras/{id}/participantes/historial/?page=N` | G/S, eventos paginados. |

Usar ID estable de participante y técnico, no nombre como PK. Mostrar `activo`, `es_responsable`, `origen_registro`, marcas y actor cuando el rol puede leerlos. Los técnicos pueden integrar múltiples obras; no mostrar como participantes activos a los históricos sin etiqueta.

### 4.4 Categorías de servicio

- `GET /api/categorias-servicio/` y `GET /api/categorias-servicio/{id}/`: G/S, listas paginadas; opcional `activo=true|false`.
- `POST /api/categorias-servicio/`: **G**, `{ "nombre": "..." }`.
- `PATCH /api/categorias-servicio/{id}/`: **G**, `{ "nombre": "...", "motivo": "..." }` conforme serializer.
- `POST /api/categorias-servicio/{id}/activar/` y `/desactivar/`: **G**, objeto con `motivo` opcional; registrar cambios efectivos.
- `GET /api/categorias-servicio/{id}/historial/`: **G**, paginado.

En creación de Obra presentar únicamente categorías elegibles activas; gestionar categorías en un apartado de Gerencia, no confundir con acceso del Supervisor para seleccionar.

## 5. Turnos y evidencia — 005C-2

### 5.1 Rutas exactas

| Método | Ruta | Rol | Datos |
| --- | --- | --- | --- |
| GET | `/api/obras/{id}/turnos/?page=N` | G/S/T | Lista de 25, T filtrado a sus turnos. |
| POST | `/api/obras/{id}/turnos/iniciar/` | T propio | JSON `{}`; timestamps fijados por servidor. |
| POST | `/api/obras/{id}/turnos/{turno_id}/finalizar/` | T propietario | JSON `{"descripcion_trabajo":"..."}` o multipart con `descripcion_trabajo` y `fotos[]` opcionales. |
| POST | `/api/obras/{id}/turnos/{turno_id}/subsanar/` | T propietario | Descripción opcional y fotos opcionales, según serializer, solo si OBSERVADO. |
| POST | `/api/obras/{id}/turnos/{turno_id}/revisar/` | S | `decision` = `VALIDAR` o `OBSERVAR`; `motivo` y `costo_hora_neto` string cuando corresponda. |
| POST | `/api/obras/{id}/turnos/{turno_id}/corregir/` | S | `motivo` obligatorio y cambios permitidos (`descripcion_trabajo`, `duracion_ajustada_segundos` entero/null, `costo_hora_neto` string). |
| POST | `/api/obras/{id}/turnos/{turno_id}/cerrar-administrativamente/` | S | `motivo`, `descripcion_trabajo` y `duracion_ajustada_segundos` entero/null opcional. |
| GET | `/api/obras/{id}/turnos/{turno_id}/fotos/{foto_id}/` | G/S/T autorizado | Binario privado autenticado; no usar enlace público. |

Turno usa **`turno_id`** como identificador, no `id`. Su estado de revisión es `ABIERTO`, `PENDIENTE_REVISION`, `OBSERVADO` o `VALIDADO`. T muestra datos operativos, descripción y observación limitada; **nunca tarifas ni costo por turno**. G/S reciben proyección ampliada `TurnoSupervisorSerializer` con costo/hora, costo de mano de obra, revisión y motivo.

### 5.2 Reglas y UX

- T puede iniciar un turno solo si es miembro activo, Obra `EN_PROCESO`, usuario activo, y no tiene otro turno `ABIERTO` en ninguna Obra. No inventar reloj de inicio/duración del cliente; mostrar el tiempo del servidor, y si se muestra transcurso local, rotularlo como orientativo.
- Al cerrar, descripción de trabajo obligatoria; fotografías opcionales. No enviar `tecnico`, `iniciado_en`, `terminado_en`, horas ni tarifa. T puede subsanar un `OBSERVADO`, no editar tiempos ni decidir su revisión.
- S puede observar/validar; la tarifa es **costo horario interno ingresado manualmente por S**. Las correcciones motivadas vuelven el turno a revisión pendiente y pueden invalidar costos antes validados.
- El cierre administrativo se atribuye a S y no al técnico. Sin duración ajustada verificada, no permitir presentar el tiempo bruto como costo de trabajo; el backend bloqueará VALIDAR hasta tenerla.
- SUSPENDIDA y FINALIZADA restringen escrituras; puede haber turnos históricos cerrados. No ofrecer un botón de cierre de Obra cuando todavía haya turnos pendientes o abiertos.
- No subir archivos por error en un formulario de solo texto; `FormData` debe conservar exactamente el campo multipart `fotos[]`, **sin definir manualmente Content-Type**, para que el navegador genere el boundary. Para cierre sin fotos se admite JSON.

### 5.3 Fotografías privadas: requisito de seguridad crítico

`FotoTurnoSerializer.fotos[].descarga` entrega una ruta del mismo origen. `foto_turno` devuelve `FileResponse` binario con `Content-Disposition: attachment`, `Cache-Control: private, no-store`, `nosniff` y requiere autenticación Bearer.

El método `authClient.request()` existente interpreta respuestas como JSON. Para descargar evidencia, **ampliar de forma mínima y retrocompatible el cliente autenticado** (o incorporar un método en su mismo módulo/closure) que soporte `Blob`/respuesta binaria y `FormData`, sin leer refresh desde JavaScript, sin revelar el access token y sin alterar la política CSRF/refresh. La renovación 401 debe ser la misma y el reintento máximo uno; no ejecutar `response.json()` sobre bytes. Reutilizar `AbortSignal`/timeout, impedir redirecciones, validar rutas `/api/` same-origin.

La descarga puede emplear un Blob URL efímero generado después del GET autenticado, revocarlo tras uso y limpiar recursos al desmontar/logout. **No** usar URL de fotos directamente en `<img src>`, `<a href>` o `window.open`, ni copiar tokens en parámetros URL; una cookie de refresh con `Path=/api/auth/` no autentica esa ruta. No persistir fotos en storage ni caché global. Si no se implementa visualizador seguro, implementar descarga autenticada y dejar la previsualización fuera de alcance, sin exponer imágenes.

Límites backend: JPEG/PNG/WebP, máximo 5 imágenes por turno, 5 MiB cada una y 12 millones de píxeles; el backend valida contenido y elimina metadatos. La UI puede anticipar restricciones pero no sustituirlas.

## 6. Materiales, gastos y costos — 005C-3

### 6.1 Materiales y gastos en un apartado único

| Método | Ruta | Contrato |
| --- | --- | --- |
| GET | `/api/obras/{id}/gastos/?page=N` | G/S, paginado de 25, incluye vigentes y anulados. |
| POST | `/api/obras/{id}/gastos/` | S, `tipo`, `descripcion`, `unidad`, `cantidad` string, `costo_unitario_neto` string, `fecha_gasto`, `referencia_respaldo`/`observacion` opcionales. |
| PATCH | `/api/obras/{id}/gastos/{gasto_id}/` | S, campos editables y `motivo` de corrección efectiva. |
| POST | `/api/obras/{id}/gastos/{gasto_id}/devolver/` | S, `cantidad` string, `fecha_devolucion` ISO y `motivo`. Solo tipo MATERIAL vigente; no superar cantidad disponible. |
| POST | `/api/obras/{id}/gastos/{gasto_id}/anular/` | S, `{"motivo":"..."}`; baja lógica, sin DELETE. |
| GET | `/api/obras/{id}/costos/historial/?page=N` | G/S, historial económico completo paginado. |

Tipos exactos: `MATERIAL`, `TRANSPORTE`, `ARRIENDO_EQUIPO`, `SERVICIO_EXTERNO`, `OTRO`. El frontend comparte el selector de unidades existente de 005B (más «Otra») para `unidad` de gasto, pero no confunde la unidad con el tipo. Mostrar cantidades `cantidad_devuelta`, `vigente`, subtotal de backend y costos netos CLP con precisión de strings. **No** interpretar devolución como reembolso monetario ni como inventario. No ofrecer eliminar físicamente registros.

### 6.2 Control de costos, versiones y validación

- `GET /api/obras/{id}/costos/control/`: G/S, lectura de control real o proyección virtual. **No provoca creación de control**.
- `PATCH /api/obras/{id}/costos/control/`: S, puede declarar `materiales_estado` y `otros_estado` (`CON_REGISTROS`, `NO_APLICA`), respectivas justificaciones y `motivo` requerido para cambios efectivos. `PENDIENTE` es estado inicial/derivado por invalidación, **no opción manual de escritura**.
- `GET /api/obras/{id}/costos/resumen/`: G/S respuesta completa con totales, versiones, estados, justificaciones y cortesía; AF respuesta mínima con totales por rubro, `costos_validados` y `cortesia_sin_cobro`, sin tarifas ni identidad técnica. T no accede.
- `POST /api/obras/{id}/costos/validar/`: S, solo `{ "motivo": "..." }`. El servidor comprueba responsable, turnos, gastos, rubros, importe positivo, control persistido, integridad y coherencia actual. La UI muestra pendientes reportados por backend sin enviar flags de validación falsos.
- `POST /api/obras/{id}/cortesia-sin-cobro/`: S, `{ "justificacion": "..." }`; rectificación de autorización anterior requiere además `motivo` nuevo y no vacío. La cortesía **no reduce el costo real** ni factura $0, ni cambia el presupuesto aprobado.

`ControlCostosObra.version_actual` y `version_validada` son de **solo lectura**. Tras cualquier escritura de gastos/turnos/declaraciones/participantes/cortesía que afecte completitud, reconsultar control y resumen; una validación anterior puede quedar obsoleta. `costos_validados` es derivado del backend, jamás un checkbox que React establezca a voluntad.

### 6.3 Finalización operativa de Obra

`POST /api/obras/{id}/finalizar/`: solo **S**, JSON exclusivamente `{ "motivo": "..." }`, motivo obligatorio. Disponible únicamente en `EN_PROCESO`, con responsable elegible, todos los turnos y rubros completos, validación de costos **vigente** y costo real positivo. No cambiar estado localmente antes de respuesta 200; tras éxito reconsultar ficha, resumen e historiales permitidos.

Un 409 (`costos incompletos`, validación desactualizada, estado incompatible, finalización duplicada) **no debe generar un segundo POST automático**. Mostrar el bloqueo y ofrecer reconsulta. `FINALIZADA` es terminal e inmutable para operaciones; mantener consultas permitidas. No existe UI de cancelar/reabrir; no exponer `CierreCostosObra` como si existiera un endpoint de detalle, porque el backend no registra uno para este bloque. La fotografía de costos existe en la base y el resumen autorizado sigue disponible.

La obra terminada **no equivale a facturada/pagada**, y el frontend no debe calcular rentabilidad, deuda ni cambiar el monto comercial.

## 7. Diseño y experiencia de usuario FYAG

- Respetar el diseño ya acordado en SPEC-005B: Bootstrap 5, CSS personalizado y **Bootstrap Icons como única familia de íconos para iconos nuevos**, usando SVG oficiales. Estilos consistentes con Clientes y Presupuestos, sin bibliotecas adicionales.
- Pantalla Obras: barra con título, «Nueva obra» solo S; filtros reales a la derecha, botón de actualizar de Bootstrap Icons (`arrow-counterclockwise`) y tabla con código, cliente, categoría, responsable, estado, fecha y acción «Ver obra». Responsive y accesible.
- Ficha con cabecera operativa y **pestañas por función**: «Resumen/Estado», «Técnicos» (S/G), «Turnos» (G/S/T propio), «Materiales y gastos» (G/S), «Costos» (G/S, AF solo resumen mínimo) e «Historial» donde corresponda. No renderizar pestañas prohibidas ni utilizar una sola ficha exhaustiva para todos los roles.
- T: experiencia móvil con «Mis obras», «Mis turnos», iniciar/cerrar/subsanar y evidencia; sin ver nombres de técnicos ajenos si no lo permite la API, ni tarifas, totales o permisos económicos.
- G: lectura integral permitida de operación, técnicos, turnos y costos; además administración de catálogo de categorías de servicio. No ofrecer aprobar por segunda vez costos ni finalizar obras.
- AF: lectura de ficha mínima y resumen financiero autorizado, sin descripción libre, fotos ni historial operativo/económico detallado; no extrapolar permisos de Comercial a Obras.
- S: flujo de gestión completa, con motivo en acciones delicadas, confirmación de finalización/cortesía/baja; mensajes de validación breves junto a campos, sin tutoriales permanentes. Mostrar pendientes desde `409.pendientes` de manera legible sin afirmar haber validado algo que no validó Django.
- Para campos monetarios usar CLP, unidades y fechas claras; impedir que una presentación con separadores de miles cambie el valor enviado a API. No sumar montos de presupuestos y gastos como métrica financiera nueva.
- Tablas largas: paginación auténtica de 25, acciones con estados de carga/disabled y tablas navegables en móvil. Mantener teclado, `aria-label`, labels de formularios y mensajes de error por campo.
- No mostrar «progreso %», «alertas de rentabilidad», «pagado», «facturado», «cancelar obra» ni «avance de obra» derivados del prototipo si Django no tiene fuente de datos/API para ello.
- Si se construye una funcionalidad progresivamente, mostrar **Pendiente de integración** solo en la subsección todavía no conectada; no fingir datos ni bloquear indiscriminadamente partes ya implementadas.

## 8. Reconciliación, errores y coherencia

- El backend es la fuente de verdad de estados, versiones, totales, timestamps, membresías y permisos. No mantener instantáneamente cambios optimistas de estado terminal.
- **401**: reutilizar el refresh 005A; **403**: acceso denegado; **404**: no existe/no autorizado; **405**: acción no habilitada; **400**: campo o archivo inválido; **409**: estado/guard/concurrencia; **429**: abuso/espera. Los errores HTTP no deben exponer HTML interno, stack traces, SQL ni cabeceras privadas.
- Después de un write exitoso leer la ficha/colección/valores relacionados que pudieron invalidarse, mediante consultas seguras. Si una reconsulta falla, no conservar silenciosamente una vista que aparenta estar sincronizada: mostrar estado de sincronización pendiente y permitir reintento de lectura.
- Timeout/error de red tras write: resultado incierto; bloquear reenvío hasta reconsultar y reconciliar. Un reintento manual sin verificar puede duplicar eventos o turnos. Conservar formulario cuando sea pertinente, pero impedir duplicación accidental.
- Al cambiar Obra, usuario o rol, descartar o abortar consultas viejas y revocar cualquier Blob URL de evidencia en memoria. No mezclar fotos/historial/recursos de una Obra con otra.
- Las respuestas paginadas de diferentes endpoints deben guardarse por clave de recurso (obra + endpoint + página + filtro) y no reutilizar colecciones incompatibles. Considerar lista vacía y páginas fuera de rango.
- No inferir un turno abierto de un mensaje local si backend podría haberlo cerrado mediante Supervisor; releer datos actuales antes de acciones irreversibles.

## 9. Pruebas y criterios de aceptación

### 9.1 005C-1 — Operación y participantes

1. G/S/AF/T ven proyecciones distintas; AF no puede leer descripción libre, historial o participantes; T solo membresías activas.
2. Listas de obras y catálogo de categorías usan paginación y filtros del servidor, sin parámetros inventados.
3. S crea Obra desde presupuesto `APROBADO_CLIENTE` no utilizado y categoría activa; fecha, ID y responsable son coherentes. Rechazo del presupuesto utilizado no crea ficha fantasma.
4. S edita únicamente campos permitidos; cambia responsable y transiciona inicio, suspensión, reanudación con motivo; no ofrece cancelar ni finalizar sin haber implementado 005C-3.
5. Participantes históricos y actuales se distinguen, principal no se desasigna, 409 aparece ante conflictos; G solo observa.
6. G administra categorías y S consulta; AF/T no tienen pestaña de catálogo.
7. Tras logout/cambio de Obra no aparecen datos ni acciones tardías del usuario anterior.

### 9.2 005C-2 — Turnos y fotografías

8. T inicia turno propio y no puede iniciar segundo turno abierto simultáneo. Servidor decide timestamps.
9. T finaliza con descripción sin fotos (JSON), y con fotos (multipart `fotos[]`); puede subsanar OBSERVADO, pero no revisar ni editar tarifas.
10. S observa, valida, corrige y cierra administrativamente; cierre administrativo sin duración acreditada impide revisión VALIDAR hasta corrección.
11. G/S pueden acceder a evidencias autorizadas; AF no; T solo fotos de turnos propios. Descarga binaria autenticada; no solicitud anónima accidental, token no aparece en URL y Blob URL se revoca al salir.
12. Archivo inválido o excesivo produce mensaje claro y no simula subida exitosa; no superar los límites de 5 archivos, 5 MiB y 12 MP.

### 9.3 005C-3 — Control de costos y cierre

13. S registra/corrige/anula gastos y devoluciones; G consulta; AF/T no ven rutas detalladas. Los importes siguen siendo strings decimales.
14. S puede declarar rubros y validar costos completos; control/versión no se actualizan desde React. Un 409 por costos incompletos presenta los pendientes emitidos por Django.
15. Cualquier corrección económica posterior invalida la validación vigente; UI reconsulta y no permite afirmar que sigue validado.
16. Cortesía no pone costos en cero ni modifica Presupuesto; rectificación requiere motivo.
17. Finalización 200 deja Obra FINALIZADA; repetición 409; sin botones de editar/anular/reabrir en estado terminal; consulta económica sigue autorizada.
18. AF ve **solo** resumen mínimo, nunca costos por técnico, fotos o motivos de cortesía.

### 9.4 Regresión transversal y CI

19. Mantener todas las pruebas de autenticación 005A y Comercial 005B; sin pérdida de cobertura. Cualquier aumento de número de tests debe provenir de ejecución real, no de estimación.
20. Pruebas unitarias/integración UI con respuestas HTTP controladas para permisos, filtrados, errores, cancelación, doble envío y reconsulta; evidencia con Blob/FormData simulados sin usar tokens de prueba reales.
21. Prueba manual E2E con cuentas de G/S/AF/T sobre Django real y PostgreSQL; probar persistencia tras F5 y cambio de sesión. Distinguir ejecución manual de tests automatizados.
22. En `frontend/`: `npm ci`, `npm test`, `npm run build`, `npm audit --omit=dev` (y `npm audit` cuando proceda). En backend Docker: `python manage.py check`, `makemigrations --check --dry-run`, `python manage.py test` para comprobar ausencia de regresiones. Frontend CI debe aprobar cada PR.
23. Si cambia `frontend/src/auth/client.js`, probar la regresión completa 005A, incluyendo renovación concurrente, logout y CSRF; no sacrificar la seguridad por facilitar fotos.

## 10. Fuera de alcance

- Backend nuevo, migraciones, cambios a reglas de negocio, creación de usuarios o nuevas rutas REST.
- Cancelación, reapertura o rectificación post-finalización de Obra.
- Facturas, pagos, cobranzas, IVA, estado de pago, rentabilidad o stock.
- Firma electrónica, geolocalización, control horario global, validación automática de ejecución y notificaciones.
- Avance porcentual no implementado en backend, alertas derivadas de montos del mock, MongoDB, PDF/Excel y reportes generales.
- Imagen pública o evidencia servida desde CDN sin autenticación; no almacenar fotos ni tokens fuera de memoria permitida.
- Despliegue a producción, políticas de retención y endurecimiento del servidor de archivos fuera de lo ya implementado en backend.

## 11. Entrega y controles de revisión

- **Primero** integrar esta SPEC en la rama 005C con una actualización documental independiente para SPEC-005B. Los commits de documentación no incluyen código.
- **Después** implementar 005C-1 sin 005C-2/3. Dejar avisos de sección pendientes donde no haya conexión; no crear mocks. Entregar ZIP con los archivos frontend modificados, listado de pruebas y limitaciones; revisión técnica antes del commit.
- Para 005C-2 y 005C-3, crear nuevas ramas/PR tras el merge del subincremento anterior; preservar el alcance de esta SPEC completa y agregar notas documentales de integración por bloque.
- Prohibido hacer commit/push/PR por OpenCode hasta revisión humana del código y prueba E2E.
- Cada PR se describe con resumen, cambios, validaciones realmente ejecutadas, alcance excluido, checklist de CI/merge pendiente. No marcar aprobado un workflow que no haya corrido.
- Tras el último merge, actualizar el estado global de SPEC-005C a **implementada e integrada**, referenciando los PR y CI de cada bloque.

## 12. Referencias verificadas

- [SPEC-004](https://github.com/LFP2002/Proyecto-FYAG/blob/main/specs/004-gestion-obras.md), [SPEC-004B](https://github.com/LFP2002/Proyecto-FYAG/blob/main/specs/004b-costos-finalizacion.md): decisiones D1–D9 y B1–B9 y límites.
- [Obras: views](https://github.com/LFP2002/Proyecto-FYAG/blob/main/backend/apps/obras/views.py), [turnos](https://github.com/LFP2002/Proyecto-FYAG/blob/main/backend/apps/obras/views_turnos.py), [gastos](https://github.com/LFP2002/Proyecto-FYAG/blob/main/backend/apps/obras/views_gastos.py), [costos](https://github.com/LFP2002/Proyecto-FYAG/blob/main/backend/apps/obras/views_costos.py), [permisos](https://github.com/LFP2002/Proyecto-FYAG/blob/main/backend/apps/obras/permissions.py), [serializers](https://github.com/LFP2002/Proyecto-FYAG/tree/main/backend/apps/obras).
- [AuthClient 005A](https://github.com/LFP2002/Proyecto-FYAG/blob/main/frontend/src/auth/client.js) y [Comercial 005B](https://github.com/LFP2002/Proyecto-FYAG/tree/main/frontend/src/comercial).
- [PR #13](https://github.com/LFP2002/Proyecto-FYAG/pull/13): finalización backend; [PR #14](https://github.com/LFP2002/Proyecto-FYAG/pull/14): frontend sesión; [PR #15](https://github.com/LFP2002/Proyecto-FYAG/pull/15): frontend comercial.

**Nota histórica:** los encabezados de algunas SPEC-004/004B describen etapas anteriores como pendientes, aunque las API de esos bloques están integradas. Su texto es marco histórico; la disponibilidad real de rutas se verificó en `backend/apps/obras/` en `main` al redactar 005C.
