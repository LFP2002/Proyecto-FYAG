# SPEC-005B — Integración del frontend: Clientes y Presupuestos reales

**Estado:** **implementada e integrada en `main` mediante [PR #15](https://github.com/LFP2002/Proyecto-FYAG/pull/15) (8 de noviembre de 2026)**. Frontend CI `React / Vite` finalizó correctamente tanto en el PR como después del merge. Esta SPEC documenta el contrato de integración frontend ya entregado; no altera las reglas de negocio de Comercial.

**Nota de lectura:** las secciones siguientes conservan la formulación original de requisitos y pasos de implementación como evidencia del alcance acordado. Las menciones históricas a tareas «pendientes», al prototipo anterior y a la rama prevista **no describen el estado actual**. Para el estado real de entrega, consultar el registro de cierre del final.

**Precedencia:** `specs/003a-gestion-clientes.md` y `specs/003b-gestion-presupuestos.md` son autoridad de negocio; `specs/002b-hardening-autenticacion.md` y `specs/005a-frontend-autenticacion.md` gobiernan sesión y seguridad. Si esta SPEC contradice una API real vigente, **no** inventar contratos ni alterar silenciosamente el backend: documentar discrepancia y detener esa operación concreta para revisión.

## 1. Contexto verificado en `main`

- SPEC-005A está integrada mediante [PR #14](https://github.com/LFP2002/Proyecto-FYAG/pull/14), con Frontend CI aprobado. React 18 + Vite 6 utiliza login JWT/CSRF real y roles de Django.
- `frontend/src/auth/client.js` exporta `authClient`, cuyo `request(path, options)` añade access Bearer, conserva el same-origin, coordina refresh al recibir 401 y no renueva por 403. `AuthContext.jsx` expone `useAuth().request` y `useAuth().user`.
- `frontend/src/app.jsx` muestra `PendingIntegration` para todos los módulos no conectados. `AppContext.jsx` administra únicamente navegación; no tiene datos comerciales. Los viejos `pages/Clientes.jsx` y `pages/Presupuestos.jsx` contienen lógica de prototipo incompatible con 003A/003B y **no deben montarse sin reescritura**.
- Las API de Django se encuentran bajo `/api/clientes/` y `/api/presupuestos/` mediante `SimpleRouter` de DRF, registradas en `backend/config/urls.py`.
- `apps.comercial` ya implementa validaciones en modelos/serializers, servicios transaccionales, integridad PostgreSQL, permisos por rol, historial y revisión de presupuestos. No duplicar esas invariantes como autoridad en React.
- El frontend contiene elementos heredados del mock (`UMBRAL = 5000000`, campos `ciudad`, presupuesto `monto` editable, estados ligados a nombres, columna `obra` simulada, `presAction` y logs locales): **no utilizarlos** en los flujos reales.

## 2. Objetivo y entregables

Conectar de extremo a extremo las pantallas de **Clientes** y **Presupuestos** con el backend real, respetando campos, permisos, estados, serialización, paginación, historiales, errores y transacciones existentes. Mostrar datos persistidos; nunca fingir éxito o cambiar un estado comercial solo en memoria.

Entregar:
1. Cliente HTTP específico de Comercial, construido sobre `useAuth().request` / `authClient.request`, sin segundo almacenamiento de tokens ni segundo mecanismo de refresh.
2. Página Clientes: listado, detalle, creación, edición parcial, activación y desactivación, con los campos de 003A.
3. Página Presupuestos: listado paginado, detalle e ítems, edición de BORRADOR, flujos de estado por rol, historial y creación de revisiones.
4. Mensajes y estados de carga, vacío, error, sin permisos y reintento seguro, sin datos falsos.
5. Pruebas automatizadas de contratos API, permisos visuales, manejo de sesión, formularios y regresión, más CI verde.
6. Documentación de arranque/uso actualizada y reporte de límites de integración.

## 3. Seguridad y arquitectura obligatorias

- Conservar exactamente la sesión 005A: JWT access **solo en memoria**, refresh **solo HttpOnly**, CSRF para los endpoints de autenticación según 002B; los endpoints comerciales usan `Authorization: Bearer` conforme a la autenticación DRF. No debilitar cookies, SameSite, CSRF ni autorización backend.
- Reutilizar `useAuth().request` (`request(path, { method, body, signal })`) y `/api/` same-origin. No llamar `fetch()` directamente a rutas protegidas si el efecto evade la gestión de expiración/identidad. No usar URLs absolutas a orígenes externos ni credenciales/tokens en parámetros de URL.
- Usar `useAuth().user.role`, no un campo editable ni un selector visual. Si llega 401 y el cliente de sesión no puede renovar, el contexto de autenticación gobierna el retorno al login. El 403 indica falta de permisos y **no** debe iniciar una renovación ni ocultarse con un cambio de rol.
- Mantener el estado de formularios y listas aislado por `user.id` y `user.role`: al logout/cambio de cuenta, desmontaje o pérdida de sesión, limpiar formularios, datos y errores sensibles; impedir que una respuesta tardía vuelva a poblar la interfaz. Preferir `AbortController` y comprobaciones de validez de la sesión antes de aplicar resultados.
- No duplicar la persistencia de sesión en Redux/localStorage/sessionStorage/IndexedDB. Los datos comerciales tampoco se guardan allí como fuente de verdad.
- Un formulario con escritura deshabilita el envío mientras hay una operación pendiente. No realizar reintento automático de POST/PATCH/DELETE después de errores de red/timeout: el servidor podría haber confirmado la operación. Consultar el estado actual antes de decidir reintento explícito.
- Actualizar la vista con el **recurso devuelto por la API** y/o una lectura posterior, nunca deducir el nuevo `estado`, IDs, montos, fechas o autor. Manejar edición concurrente con los conflictos existentes; no prometer detección de cambios concurrentes que el backend no expone.
- Mantener `PendingIntegration` para Obras (005C), Finanzas, Alertas, Dashboard, Reportes y Usuarios; no habilitar pantallas antiguas con simulación de escritura. Conservar la experiencia móvil de Técnico como pendiente de integración.
- Los datos de Cliente son personales/comerciales: no registrarlos íntegramente en consola, telemetría ni trazas. Nunca mostrar errores SQL, stacks o respuesta HTML cruda del servidor.

## 4. Matriz de autorizaciones

Roles literales: `GERENCIA` (G), `ADMINISTRATIVO_FINANZAS` (AF), `SUPERVISOR_OBRAS` (S), `TECNICO` (T).

| Operación | G | AF | S | T |
| --- | --- | --- | --- | --- |
| Clientes: listar, ver, crear, PATCH, activar/desactivar | Sí | Sí | No | No |
| Presupuestos: listar, ver, historial | Sí | Sí | No | No |
| Presupuestos: crear, PATCH cabecera/ítems, enviar Gerencia/cliente, registrar decisión cliente, anular, revisar | No | Sí | No | No |
| Presupuestos: aprobar/rechazar Gerencia | Sí | No | No | No |

- Mostrar Clientes también en menú de G, pues su acceso **sí** existe en el backend (en 005A la navegación podía ocultarlo). AF ve Clientes y Presupuestos; G ve ambos en lectura, más operaciones permitidas. S y T no ven ambos módulos y reciben 403 si fuerzan el acceso a la API.
- No aplicar umbral de CLP 5.000.000 ni salto de aprobación. **Todos** los presupuestos requieren aprobación de Gerencia, sin importar monto, según SPEC-003B. El booleano `requiere_aprobacion_gerencia` lo fija Django en `true` y nunca es editable.
- No usar `is_superuser` como autorización alternativa. El frontend solo adapta controles; el backend sigue decidiendo.

## 5. Clientes — API y datos exactos (003A)

### 5.1 Rutas y semántica

| Método | Ruta | Éxito | Observación |
| --- | --- | --- | --- |
| GET | `/api/clientes/` | 200 | **Array** simple, ordenado por `nombre_legal`, `id`; incluye inactivos. **No paginado**. |
| POST | `/api/clientes/` | 201 | Nuevo cliente, `activo=true` por servidor. |
| GET | `/api/clientes/{id}/` | 200 | Recurso. |
| PATCH | `/api/clientes/{id}/` | 200 | Actualización **parcial**; el servidor conserva campos omitidos. |
| POST | `/api/clientes/{id}/activar/` | 200 | Idempotente, devuelve cliente activo. |
| POST | `/api/clientes/{id}/desactivar/` | 200 | Idempotente, devuelve cliente inactivo. |

No hay PUT ni DELETE; para rol autorizado responden 405. No existe búsqueda/filtro en API de Clientes en esta etapa. Un buscador local es opcional si se identifica explícitamente como filtro del listado recibido y no se inventa consulta remota.

### 5.2 Contrato de Cliente

| Campo | Tipo | Escritura | Regla |
| --- | --- | --- | --- |
| `id` | entero | No | PK real, clave UI y vínculo con Presupuesto. |
| `tipo_cliente` | `PERSONA` / `EMPRESA` | Sí | Obligatorio al crear. |
| `tipo_identificacion` | `RUT` / `DOCUMENTO_EXTRANJERO` / `SIN_IDENTIFICACION` | Sí | Obligatorio al crear. |
| `numero_identificacion` | string o null | Condicional | RUT válido o número extranjero; null en SIN_IDENTIFICACION. |
| `pais_identificacion` | string o null | Condicional | ISO-like de 2 letras mayúsculas para extranjero; null en otros tipos. |
| `tipo_documento_extranjero` | string o null | Condicional | Obligatorio en extranjero; null en otros tipos. |
| `nombre_legal` | string | Sí | Obligatorio, trim; razón social o nombre legal. |
| `nombre_contacto` | string | Opcional | Contacto principal. |
| `correo` | string | Opcional | Email válido y normalizado por servidor. |
| `telefono` | string | Opcional | Teléfono. |
| `activo` | booleano | No | Cambiar solo mediante `/activar/` y `/desactivar/`. |
| `creado_en`, `actualizado_en` | fecha ISO | No | Generados por servidor. |

No existe el campo `ciudad` en Cliente: **retirar de la interfaz y requests**. No se puede crear un Cliente sin correo **y** sin teléfono. En `SIN_IDENTIFICACION`, enviar explícitamente los tres campos de identificación como `null`; nunca números ficticios. Para cambiar un cliente existente a `SIN_IDENTIFICACION` por PATCH, enviar también esos tres null en la misma solicitud; no depender de limpiezas implícitas.

- `RUT`: aceptar ingreso legible y mostrar error de módulo 11 desde servidor; persistencia normalizada sin puntos y con guion. `pais_identificacion` y `tipo_documento_extranjero` deben ser null.
- `DOCUMENTO_EXTRANJERO`: solicitar país (2 letras ASCII), tipo de documento y número; servidor normaliza en mayúsculas, conserva separadores del número. No usar módulo 11 en este caso.
- `SIN_IDENTIFICACION`: ocultar/deshabilitar número, país y tipo de documento, y enviarlos como null.
- Mostrar cliente inactivo sin ocultar su historial; permitir editar o reactivar. Al seleccionar cliente para nuevo presupuesto, **ofrecer solo clientes activos**; un cliente sin RUT sigue siendo elegible para cotizar.
- Errores de duplicidad (RUT o identificación extranjera) y campos inválidos llegan como 400 por campo. No crear identificaciones alternativas para eludir unicidad.
- No enviar `activo`, fechas o ID en POST/PATCH; el servidor no acepta `activo` y los campos de solo lectura no deben incluirse en payload.

### 5.3 Experiencia visual mínima

- Listado con nombre legal, identificación (cuando corresponda), contacto y estado activo/inactivo; detalle con todos los campos autorizados.
- Formulario de alta/edición con `tipo_cliente`, `tipo_identificacion` dinámico y validación orientativa, sin reemplazar el backend.
- Confirmación antes de desactivar; botón de reactivar visible según estado. Conservar la selección y mostrar errores específicos por campo.
- Usar ID real como `key`; nunca relacionar por nombre. No mostrar contadores de Obras ni Presupuestos inventados (la API actual no devuelve esos agregados).

## 6. Presupuestos — API y datos exactos (003B)

### 6.1 Listado y detalle

- `GET /api/presupuestos/`: 200 `{count, next, previous, results}`; **paginación de 25**, `?page=N` y orden `-creado_en, -id`. Cada fila incluye `id`, `codigo`, `cliente` (ID), `descripcion`, `estado`, `requiere_aprobacion_gerencia`, `presupuesto_origen`, `creado_por`, `creado_en`, `actualizado_en`, `moneda` (`CLP`) y `monto_neto` (string decimal de dos posiciones). No incluye `items` ni `obra`.
- `GET /api/presupuestos/{id}/`: 200, misma cabecera más `items`, cada uno con `id`, `presupuesto`, `descripcion`, `cantidad` (string decimal con 3 posiciones), `unidad`, `precio_unitario` (string decimal con 2 posiciones), `orden` (entero), `subtotal` (string decimal con 2 posiciones).
- `GET /api/presupuestos/{id}/historial/`: 200 paginado, 25 eventos por página `{count, next, previous, results}` en orden `creado_en, id`. Cada evento incluye `id`, `presupuesto`, `estado_anterior`, `estado_nuevo`, `registrado_por`, `motivo`, `creado_en`.
- No existen filtros/ordenamiento remoto libre. Al mostrar filtros de estados, aplicar solo a la página cargada y etiquetarlo claramente, o cargar las páginas necesarias para obtener un resultado global; **no presentar contadores parciales como globales**.
- Para el nombre del cliente, resolver `presupuesto.cliente` contra Clientes por **ID**, con carga controlada (G/AF tienen permiso), o mostrar el ID cuando aún no se haya cargado. No usar la etiqueta como clave de unión.
- No hay relación `obra` dentro del serializer de Presupuesto. Quitar la columna simulada «Obra» o marcarla como pendiente de integración de Obras (005C) sin datos ficticios.

### 6.2 Cabecera y líneas: CRUD permitido

| Método | Ruta | Éxito | Cuerpo |
| --- | --- | --- | --- |
| POST | `/api/presupuestos/` | 201 | `{ "cliente": 1, "descripcion": "Instalación de frío" }` |
| PATCH | `/api/presupuestos/{id}/` | 200 | Solo `cliente` y/o `descripcion` cuando `BORRADOR`. |
| POST | `/api/presupuestos/{id}/items/` | 201 | Ítem con todos los campos obligatorios. |
| PATCH | `/api/presupuestos/{id}/items/{item_id}/` | 200 | Campos del ítem, parcial, solo `BORRADOR`. |
| DELETE | `/api/presupuestos/{id}/items/{item_id}/` | 204 | Sin cuerpo; solo `BORRADOR`. |

Ejemplo exacto para POST de un ítem:

```json
{
  "descripcion": "Montaje especializado",
  "cantidad": "2.500",
  "unidad": "hora",
  "precio_unitario": "100.25",
  "orden": 1
}
```

- Crear Presupuesto genera un **BORRADOR sin ítems**. Los ítems se guardan mediante llamadas separadas. Un modal/página de edición puede ofrecer un flujo guiado, pero **no** enviar ítems anidados en el POST de cabecera ni asumir que las dos escrituras son una transacción única. Si una falla, mostrar claramente qué se guardó y qué quedó pendiente.
- Cabecera editable exclusivamente en `BORRADOR`. Crear/cambiar cliente exige Cliente activo; no se exige RUT. Orden de ítems positivo y único dentro del Presupuesto.
- `cantidad` debe enviarse como **string** decimal positivo (precisión máxima 12 dígitos, 3 decimales, mínimo `0.001`); `precio_unitario` como **string** decimal no negativo (máximo 15 dígitos, 2 decimales). No enviarlos como numbers JSON; `orden` es **entero JSON**, no string ni booleano.
- No calcular ni persistir `monto_neto`, `subtotal`, `IVA`, `descuento`, `requiere_aprobacion_gerencia` ni `estado` desde la interfaz. El servidor calcula subtotal/neto con `Decimal` y regla de redondeo de 003B. Valores cero en una línea permitidos; el **total** debe superar cero antes de enviar a Gerencia.
- Para mostrar CLP, conservar los decimales **como strings**. No calcular totales mediante `Number()`, `parseFloat()`, floats JS ni dividir/multiplicar montos para decidir reglas. Aplicar formato local solo como presentación, sin usar el valor formateado de vuelta en el request.
- No existe DELETE físico de presupuesto. No hay endpoint `GET /items/` independiente: los ítems se leen del detalle.

### 6.3 Transiciones comerciales (solo rutas expresas)

| Estado actual | Acción POST | Destino | Rol | Motivo |
| --- | --- | --- | --- | --- |
| `BORRADOR` | `enviar-gerencia/` | `PENDIENTE_GERENCIA` | AF | Opcional |
| `PENDIENTE_GERENCIA` | `aprobar-gerencia/` | `APROBADO_GERENCIA` | G | Opcional |
| `PENDIENTE_GERENCIA` | `rechazar-gerencia/` | `RECHAZADO_GERENCIA` | G | **Obligatorio** |
| `APROBADO_GERENCIA` | `enviar-cliente/` | `ENVIADO_CLIENTE` | AF | Opcional |
| `ENVIADO_CLIENTE` | `registrar-aprobacion-cliente/` | `APROBADO_CLIENTE` | AF | Opcional |
| `ENVIADO_CLIENTE` | `registrar-rechazo-cliente/` | `RECHAZADO_CLIENTE` | AF | **Obligatorio** |
| `BORRADOR`, `PENDIENTE_GERENCIA`, `APROBADO_GERENCIA`, `ENVIADO_CLIENTE`, `APROBADO_CLIENTE` | `anular/` | `ANULADO` | AF | **Obligatorio** |

Todos los endpoints usan `/api/presupuestos/{id}/{accion}/`. Cuerpo exacto `{ "motivo": "texto" }`; cuando es opcional también se admite `{}`. No enviar un `estado` elegido por el navegador. Los cambios de estado devuelven **detalle actualizado** 200. Una transición duplicada o incompatible responde 409 y nunca debe mostrarse como exitosa.

Reglas innegociables:
1. **Siempre** `BORRADOR → PENDIENTE_GERENCIA → APROBADO_GERENCIA → ENVIADO_CLIENTE`; ni montos bajos ni urgencia permiten saltar Gerencia.
2. Enviar a Gerencia requiere Cliente activo, al menos un ítem y `monto_neto > 0`, calculado por backend.
3. Rechazos (`RECHAZADO_GERENCIA` / `RECHAZADO_CLIENTE`) y `ANULADO` son estados terminales del registro original. No corregirlos cambiando localmente de estado.
4. Anular `APROBADO_CLIENTE` **solo si no existe Obra asociada** (y demás estados permitidos). Si hay una Obra, 409 con `code: presupuesto_utilizado`, incluso si esa Obra está finalizada. No inventar un flag de «tiene obra» ni asumir que el frontend conoce esa relación.
5. Registrar aprobación del cliente es una anotación hecha por AF, no un login del cliente. No enviar correo real en `enviar-cliente`: es solo un evento/hito comercial en 003B.
6. Ocultar acciones no permitidas por rol o estado; mostrar confirmaciones para rechazar/anular y respetar siempre un posible 403 o 409 remoto por cambios concurrentes.

### 6.4 Revisiones e historial

- `POST /api/presupuestos/{id}/crear-revision/` por AF con **cuerpo `{}`**, devuelve 201 con **nuevo** Presupuesto `BORRADOR`, `presupuesto_origen = id anterior` y copia de ítems. Origen permitido: `RECHAZADO_GERENCIA`, `RECHAZADO_CLIENTE`, `ANULADO`.
- No habilitar revisión directa desde `APROBADO_CLIENTE`: si se requiere modificar una propuesta aceptada y no usada, la vía de negocio es anulación válida + revisión; el frontend no debe automatizar ambas en una sola acción.
- Crear revisión no es idempotente: dos envíos válidos producen dos revisiones distintas. Bloquear doble clic y exigir confirmación.
- Historial se consulta por su API paginada, no por un registro local inventado; el usuario ve estado anterior, nuevo estado, motivo, actor ID y fecha. No crear nombres de actor no devueltos por API.

### 6.5 Experiencia visual mínima

- Listado de presupuestos con código real `PRE-000001`, Cliente asociado por ID, descripción, `monto_neto` neto CLP, estado y acciones según G/AF. Paginación real y estado de página.
- Detalle con cabecera, ítems ordenados, neto, historial paginado y enlace a origen de revisión cuando corresponda.
- AF puede crear borrador, editar cabecera, incorporar/editar/eliminar líneas y ejecutar transiciones habilitadas; G solo lee y resuelve `PENDIENTE_GERENCIA`.
- Aprobaciones/rechazos/anulaciones con confirmación clara y campo de motivo cuando es obligatorio; ausencia de `motivo` y estados cambiantes se muestran con errores del backend, no se fabrican soluciones automáticas.
- La «rentabilidad», el IVA tributario, la facturación, el estado de pago, el margen contra costos reales y los indicadores por umbral del mock **no** forman parte de 005B.

## 7. Manejo de respuestas y errores

| Estado | Conducta frontend |
| --- | --- |
| 200, 201 | Mostrar recurso real; invalidar/actualizar listado y detalle después de escrituras. |
| 204 | DELETE de ítem sin body; reconsultar detalle y total. |
| 400 | Visualizar errores por campo, `non_field_errors` y mensajes de negocio sin perder datos del formulario. |
| 401 | Delegar en el cliente 005A para único refresh/reintento o volver a login si la sesión terminó. |
| 403 | Indicar falta de permiso sin modificar datos ni refrescar credenciales en bucle. |
| 404 | Recurso desaparecido/no encontrado o página inválida; ofrecer volver al listado. |
| 405 | Tratar como discrepancia entre UI y contrato; no sustituir método. |
| 409 | Mostrar `detail`/`code` público cuando corresponda; reconsultar estado real y permitir nueva decisión, sin repetir automáticamente la escritura. |
| 429 | Mostrar límite de solicitudes y `Retry-After` si existe. |
| 5xx / red / timeout | No declarar éxito; permitir relectura para verificar si la operación quedó aplicada. |

**Adaptación limitada del cliente HTTP:** el `ApiError` de 005A expone `status`, mensaje genérico y `retryAfter`, pero su `http()` no conserva el JSON de errores del backend. Para 005B se permite extenderlo **retrocompatiblemente** con un campo saneado (p. ej. `details`/`fieldErrors`/`code`) para mostrar errores 400/409 útiles, sin afectar refresh, logout, protecciones `epoch` ni los tests anteriores. Nunca renderizar HTML como contenido ejecutable ni imprimir tokens. No ocultar `400`/`409` detrás de «Error inesperado».

No bloquear indefinidamente la UI cuando un request falla; mostrar loading, empty y estados de error distintos. Mantener respuesta accesible con `role="alert"` cuando corresponda; formularios con `label`, foco coherente, teclado y confirmaciones. Mostrar fechas de servidor según configuración local `es-CL`, sin modificar ISO persistido.

## 8. Integración del árbol React y migración desde el mock

- `app.jsx`: dentro del layout autenticado, mostrar `Clientes` si `mod === 'clientes'` y rol autorizado; mostrar `Presupuestos` si `mod === 'presupuestos'` y rol autorizado; conservar `PendingIntegration` para los demás. Técnico sigue en flujo 005A sin nuevos datos de Obras.
- `context/AppContext.jsx`: conservar solo navegación; la lógica comercial va a servicios API y estado de componentes o contextos comerciales independientes. No reintroducir las funciones demo (`saveCli`, `savePre`, `presAction`, etc.).
- `pages/Clientes.jsx` y `pages/Presupuestos.jsx`: **reescribir** para usar contratos reales; las páginas del prototipo no consumen estas API y contienen reglas contradictorias.
- `data/constants.js`: eliminar o dejar sin uso en producción las reglas de `UMBRAL`, `presupuesto.monto`, `pago` y alias de roles de mock; reutilizar `PRE_E` solo como etiquetas de los estados reales 003B.
- No inventar un endpoint `api/usuarios/`, cliente «Sin cliente», cliente por nombre, montos editables directos, estados «Facturado/Pagado» de presupuesto, `Obra` en serializer comercial o actividad de pagos simulada.
- Mantener la estética FYAG (tablas, chips, sidebar, formularios) y reutilizar componentes existentes cuando sean compatibles; priorizar precisión de negocio y accesibilidad sobre pixel-perfect del mock.

## 9. Criterios de aceptación y pruebas obligatorias

**Pruebas automatizadas (frontend, Node test runner u otra herramienta justificada):**

1. `Clientes GET` recibe array sin paginación, muestra inactivos y respeta orden; no confundir con `{results}`.
2. Clientes CREATE/PATCH envía solo campos permitidos y muestra RUT/identificación extranjera/SIN_IDENTIFICACION; transición PATCH a SIN_IDENTIFICACION incluye tres `null`.
3. Cliente inactivo se puede reactivar/modificar, pero no elegir para un nuevo presupuesto; falta correo+teléfono y duplicados producen errores visibles.
4. `POST activar/desactivar` se ejecuta como acción real y no como `PATCH activo` ni eliminación.
5. Presupuestos GET paginado 25; detalle con ítems; historial paginado; navegación por `next/previous` segura, siempre same-origin y bajo API. No se aceptan URL externas devueltas como `next`.
6. Solo AF crea Presupuesto con `{cliente: int, descripcion: string}`; nunca montos, booleans ni líneas anidadas.
7. Ítem: cantidad/precio JSON string decimal, orden JSON int, CRUD correcto, subtotal y monto neto siempre de Django; confirmar 204 en borrado.
8. Umbral falso del mock no afecta flujo: monto de cualquier tamaño pasa por Gerencia. G aprueba/rechaza; AF no puede aprobar Gerencia.
9. Transiciones válidas e inválidas, motivo obligatorio, rechazos/anulación terminales, revisión crea nuevo ID, historial remoto; 409 y `presupuesto_utilizado` se reflejan sin éxito ficticio.
10. 401 con renovación compartida y un solo reintento, 403 sin escalada, 400 por campos, 404/405, 409, 429, 5xx y red: feedback y recuperación correctos.
11. Respuestas tardías de otra sesión, logout o navegación no vuelven a mostrar datos de usuarios anteriores; no leaks de token/cookie.
12. S/T no reciben ni pueden solicitar módulos comerciales mediante UI; G/AF ven solo acciones autorizadas. No usar `is_superuser` como bypass.
13. Módulos aún pendientes siguen en `PendingIntegration`; ninguna escritura demo se ejecuta desde pantallas montadas.
14. `npm ci`, `npm test` y `npm run build` correctos, con CI de Frontend verde. `python manage.py check`, migraciones sin cambios y suite completa del backend sin regresión cuando se valide la entrega.

**Prueba manual E2E con dos cuentas de rol real (sin credenciales en repositorio):**

- AF: login, nuevo cliente, nuevo BORRADOR, añadir ítem, enviar Gerencia; verificar en BD/API o recargando que persiste.
- G: login, ver ese presupuesto pendiente, aprobar; intentar crear presupuesto o editar ítems debe estar bloqueado por UI y responder 403 por API.
- AF: volver, enviar a cliente, registrar aceptación, inspeccionar historial. Verificar conflicto de anulación cuando ese presupuesto sea utilizado por Obras **solo en datos de prueba preparados**, nunca inventar una Obra desde 005B.
- Recargar con `F5`, renovar sesión y cerrar sesión; datos del usuario anterior no se muestran al iniciar con otro.
- Si el usuario no dispone de alguna cuenta de rol, documentar exactamente qué no pudo comprobarse; **no inventar resultados**.

**Invariantes:** al finalizar cada operación exitosa los datos reflejan el backend; no hay escrituras ficticias, saltos de Gerencia, importes simulados, claves por nombre ni acceso a módulos de roles sin permiso.

## 10. Fuera de alcance

- Modificaciones de API, permisos, migraciones o lógica en Django Comercial u Obras (salvo corrección puntualmente justificada y autorizada por el equipo antes de implementarla).
- Creación de usuarios, recuperación de contraseña, cambios de roles y funciones de administración de usuarios.
- Integración de Obras, técnicos, turnos, evidencias, materiales, costes y cierre 005C.
- Finanzas, facturación, IVA, cobros/pagos, descuentos, documentos tributarios y portal de cliente.
- PDFs, Excel, correo real, firmas, inventario, MongoDB, reportes, dashboard, alertas, auditoría global y producción.
- Búsqueda server-side o filtros/paginación extra inexistentes en 003A/003B.

## 11. Entrega y secuencia de trabajo

1. En una rama creada desde `main` con PR #14 integrado, incorporar **únicamente** este Markdown y, si se desea, la actualización de estado de 005A en un **commit de documentación**. No cambiar la SPEC durante la implementación por comodidad.
2. OpenCode lee ambas SPEC y los contratos completos de `apps.comercial`, identifica diferencias, implementa **solo frontend** y pruebas; no hace commits, push ni PR sin revisión.
3. Revisar código, contratos y pruebas localmente; completar pruebas manuales E2E con roles reales y corregir hallazgos.
4. Crear commit(s) de código, push, abrir PR 005B, comprobar Frontend CI en verde; Backend CI puede no ejecutarse si no cambió `backend/**` por diseño. No afirmar aprobación de un job que no se disparó.
5. Tras el merge, actualizar estado de SPEC-005B en una revisión documental separada y continuar con SPEC-005C.

## 12. Fuentes exactas revisadas

- [SPEC-003A](https://github.com/LFP2002/Proyecto-FYAG/blob/main/specs/003a-gestion-clientes.md): contrato y permisos de Cliente.
- [SPEC-003B](https://github.com/LFP2002/Proyecto-FYAG/blob/main/specs/003b-gestion-presupuestos.md): flujo comercial, contratos y revisiones.
- [Código Comercial](https://github.com/LFP2002/Proyecto-FYAG/tree/main/backend/apps/comercial): `urls.py`, `views.py`, `views_presupuestos.py`, serializers, permisos, modelos y servicios.
- [AuthClient](https://github.com/LFP2002/Proyecto-FYAG/blob/main/frontend/src/auth/client.js) y [AuthContext](https://github.com/LFP2002/Proyecto-FYAG/blob/main/frontend/src/auth/AuthContext.jsx): reutilización de sesión SPEC-005A.
- [PR #14](https://github.com/LFP2002/Proyecto-FYAG/pull/14) y `.github/workflows/frontend-ci.yml`: integración y CI confirmados.

## 13. Registro de cierre de implementación (8-11-2026)

- **Integración:** [PR #15 — `feat(frontend): integrar clientes y presupuestos reales 005B`](https://github.com/LFP2002/Proyecto-FYAG/pull/15), fusionado en `main` el 8-11-2026, con Frontend CI en verde.
- **Funcionalidad integrada:** CRUD autorizado de Clientes; presupuestos e ítems reales; aprobación obligatoria de Gerencia; historial, rechazos, revisiones y anulación conforme al backend; selector de unidades y edición en línea.
- **Interfaz:** barra de herramientas compacta, filtros de estado, controles de actualización y estilo Bootstrap 5/CSS FYAG; estándar acordado de Bootstrap Icons para nuevos íconos.
- **Verificación:** la implementación fue revisada y el usuario completó pruebas manuales exitosas de flujo G/AF en navegador. Las pruebas de CI constan en GitHub. No atribuir a este registro resultados de una suite no ejecutada en este commit documental.
- **Límites vigentes:** Obras, Finanzas, Dashboard, Alertas, Reportes y Usuarios no quedaron integrados como resultado de 005B. El filtrado por estado de Presupuestos opera sobre la página cargada (25 registros), no como filtro global de servidor.
- **Continuidad:** [SPEC-005C](005c-frontend-obras.md) define la integración de Gestión de Obras en bloques revisables.
