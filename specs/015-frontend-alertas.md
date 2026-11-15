# SPEC-015 — Integración frontend FYAG: Alertas

**Estado:** aprobación de redacción confirmada por el responsable en conversación; pendiente de integración documental en `main`. La aprobación del texto no autoriza por sí sola publicar código ni fusionar cambios. **Ámbito:** frontend React/Vite únicamente. **Backend:** SPEC-009 está implementada e integrada en `main` mediante PR #30. Esta SPEC define cómo consumirla desde la interfaz y no altera su contrato.

## 1. Contexto y objetivo

- `specs/009-alertas-backend.md` especifica los endpoints reales de Alertas, sus schemas, RBAC y errores. `backend/config/urls.py` monta la API bajo `/api/alertas/`; las vistas y serializers de `backend/apps/alertas/` implementan el contrato.
- `frontend/src/data/constants.js` ofrece Alertas en el menú a GERENCIA y SUPERVISOR_OBRAS. `frontend/src/app.jsx` todavía presenta `PendingIntegration` para el módulo.
- La pantalla captura el estado pendiente actual; no demuestra por sí misma un fallo de proxy ni implica que falten rutas backend.
- El cliente autenticado `useAuth().request`, el aislamiento `createScope` y el pager existentes se reutilizan. No introducir cliente HTTP, sesión, permisos ni almacenamiento alternativos.

**Objetivo:** sustituir el placeholder de Alertas para GERENCIA y SUPERVISOR_OBRAS por una bandeja real de su rol, con resumen, filtros contractuales, paginación, detalle e historial, y acuse motivado cuando `acciones_permitidas` indique `ATENDER`.

## 2. Alcance y exclusiones

Incluye:
- Carga de `GET /api/alertas/resumen/` y `GET /api/alertas/`.
- Filtros server-side exactos de SPEC-009, conservación de filtros al paginar y actualización explícita.
- Vista de detalle e historial paginado al seleccionar una alerta.
- Acuse motivado vía `POST /api/alertas/{id}/atender/`, con conciliación posterior de lista, resumen, detalle e historial aplicables.
- Estados de carga, vacío, error, obsoleto/sincronización desactualizada, sin permiso, conflicto y recuperación mediante relectura.

Queda fuera: cambios a backend, base de datos, migraciones, contratos o permisos; alertas nuevas; resolución manual, edición o eliminación; links que infieran pantallas o acciones de dominios aún no integrados; notificaciones externas; métricas o totales calculados por React; exportación; refresh/reconciliación desde la interfaz; datos mock; publicación, commit, push, PR y merge automáticos.

## 3. Roles, privacidad y datos

| Rol | Acceso a bandeja/resumen/detalle/historial/acuse |
|---|---|
| GERENCIA | Sí, únicamente sus alertas destinatarias y la proyección contractual del backend. |
| SUPERVISOR_OBRAS | Sí, únicamente sus alertas destinatarias; sin información financiera de documentos/cobranzas. |
| ADMINISTRATIVO_FINANZAS, TECNICO, ADMINISTRADOR_TI | No: no montar la pantalla ni enviar requests de Alertas. La API puede contestar 403 si se intenta acceso directo. |

El backend conserva autoridad sobre rol y recurso. La interfaz no toma rol desde querystring, flags Django ni datos editables, y nunca amplía permisos. No inferir usuario destinatario, saldo, estado de origen, gravedad ni elegibilidad a partir del contenido del recurso. Mostrar únicamente campos validados del schema de la respuesta, particularmente `titulo`, `descripcion` y `recurso_codigo` tal como los entrega el backend; nunca buscar ni mostrar folios, pagos, nombres de clientes, montos, costos, teléfonos, adjuntos ni descripciones libres del dominio origen. Para GERENCIA, una alerta de turno se limita al texto público de alerta: no consultar ni renderizar datos de turno. Para SUPERVISOR, no mostrar campos financieros aunque lleguen inesperadamente.

No registrar cuerpos, alertas, motivos, credenciales ni cabeceras en logs. El motivo de atención reside solamente en memoria mientras el formulario está montado y se borra al cerrar, cambiar identidad o cerrar sesión. No guardar JWT, alertas ni PII en Web Storage, IndexedDB o cache duradera.

## 4. Contratos HTTP de frontend

Todas las llamadas usan `useAuth().request` a rutas relativas `/api/...`, respetan refresh compartido 401, `credentials`, CSRF y el tratamiento `no-store` existente. Se validan estrictamente schemas de respuesta, valores enum, tipos y paginación. No seguir directamente URLs `next`/`previous`: derivar la página segura en el mismo path `/api/alertas/` y validar query permitida.

### 4.1 Resumen

`GET /api/alertas/resumen/`, sin query. Mostrar `por_estado`, `activas`, `por_tipo` y `sincronizacion` exactamente como agregados del backend. No sumar filas ni computar conteos en React. El conjunto de tipos expuestos debe ser el del rol; no construir tipos ajenos ni suponer una clave opcional como error. `RESUELTA` se etiqueta como histórico y no como alerta activa. Si `sincronizacion.desactualizada` es true, mostrar aviso de datos potencialmente atrasados sin prometer reconciliación inmediata ni ejecutar comando alguno.

### 4.2 Listado y filtros

`GET /api/alertas/?...` responde `{count,next,previous,results}` con 25 por página y orden backend.

Filtros permitidos exclusivamente:
- `estado`: omitirlo por defecto para consultar incidencias actuales; valores `PENDIENTE`, `ATENDIDA`, `RESUELTA`, `TODAS`.
- `tipo`: enum de catálogo devuelto para el rol.
- `recurso_tipo`: `PRESUPUESTO`, `OBRA`, `TURNO` o `DOCUMENTO`, sujeto a catálogo/rol y relación con `tipo`.
- `recurso_id`: entero decimal positivo y solo junto a `recurso_tipo`.
- `desde` y `hasta`: ambas fechas `YYYY-MM-DD`, rango máximo backend de 366 días inclusivos.
- `page`: entero decimal positivo.

No mandar parámetros vacíos, repetidos, valores por defecto, aliases ni rol destinatario. Validar pares de fechas y rango antes de llamar API; conservar filtros validados al pasar páginas; al cambiar filtro volver a página 1. No etiquetar filtros locales como búsqueda global. El estado sin filtro debe usar la semántica del API (solo PENDIENTE/ATENDIDA).

### 4.3 Detalle e historial

Al seleccionar fila, usar `GET /api/alertas/{id}/`; validar la misma proyección que el listado y descartar respuesta tardía al cambiar selección o sesión. El historial usa `GET /api/alertas/{id}/historial/?page=N`, schema de evento de SPEC-009 y pager independiente de la lista. No crear un panel de recurso origen ni enlazar a turnos, presupuestos o documentos por simple disponibilidad de su ID.

### 4.4 Acuse motivado

Solo mostrar «Atender» cuando la alerta indique `acciones_permitidas` exactamente conteniendo `ATENDER` y su estado contractual lo permita. Confirmar mediante formulario/modal accesible con `motivo` obligatorio tras trim, 1–2000 caracteres. Enviar únicamente `{ "motivo": "..." }` a `POST /api/alertas/{id}/atender/`; no incluir estado, actor, timestamp ni rol. Bloquear doble submit. Nunca declarar éxito ni cambiar estado optimistamente antes de HTTP 200 y relectura satisfactoria.

Un 200 exige reconsultar lista, resumen, alerta e historial según vista. Si el POST confirma pero falla la relectura, mostrar sincronización pendiente y bloquear otra escritura hasta reconsulta. No repetir automáticamente POST tras timeout, error de red, 409 o 5xx.

## 5. UX y arquitectura

- Montar la página en `frontend/src/app.jsx` solo para `mod === 'alertas'` y roles GERENCIA/SUPERVISOR_OBRAS, manteniendo las demás rutas y `PendingIntegration` sin cambios.
- Título «Alertas», tarjetas de resumen alimentadas por `/resumen/`, controles de filtro, tabla/lista responsive accesible con título, tipo, severidad, recurso público permitido, estado y fecha de creación; selección muestra detalle e historial. No se exige ni se presume un mock para completar la presentación.
- Los controles no disponibles para un rol se ocultan, pero la autorización real sigue en el backend. La navegación no debe transformar un ID de recurso en una capacidad de acceso no especificada.
- Reutilizar estilos Bootstrap/FYAG, `useCommercial` o un hook basado en `createScope` siguiendo el patrón más próximo. Cancelar GET al desmontar, cambio de selección, filtros o identidad; descartar respuestas tardías; prevenir requests redundantes.
- Diferenciar loading, error recuperable, vacío, 403, 404, stale/conflicto 409, API no disponible y resultado de acuse. Mensajes públicos: `alerta_ya_atendida`, `alerta_resuelta`, `alerta_desactualizada`; después de conflicto reconsultar y exigir nueva decisión.
- Labels visibles, navegación teclado, foco y `aria-live`/`role="alert"` para errores. Verificar anchos 320, 375, 768 y 1024 px sin overflow.

Archivos candidatos de implementación posterior (no incluidos en esta entrega documental): `frontend/src/pages/Alertas.jsx`, `frontend/src/alertas/api.js`, `frontend/src/alertas/domain.js`, modificación acotada `frontend/src/app.jsx`, pruebas `frontend/tests/alertas-*.test.js` y simulador aislado de backend frontend si es requerido. No editar `frontend/src/auth/client.js` salvo que una incompatibilidad comprobada y probada lo haga estrictamente necesario.

## 6. Errores, consistencia y recuperación

- 400: mostrar error de validación/filtro sin perder filtros ni motivo; no exponer HTML interno.
- 401: utilizar el refresh existente; si la sesión queda anónima, desmontar y limpiar la vista.
- 403: informar acceso denegado, limpiar contenido, no reintentar ni escalar rol.
- 404: alerta no disponible; no revelar si pertenece a otro rol.
- 405: discrepancia método/contrato; no sustituir método.
- 409: mapear solo los tres códigos estables, marcar la vista para conciliación y requerir GET explícito antes de nuevo acuse.
- 429: mostrar `Retry-After` si existe.
- Red/timeout/5xx en GET: conservar filtros, indicar que no se pudo actualizar y ofrecer relectura explícita. No presentar datos antiguos como vigentes sin aviso.
- Red/timeout/5xx en POST: resultado incierto; bloquear el reenvío hasta reconsultar. Un fallo del GET posterior a POST exitoso no deshace la escritura.

La bandeja comparte el estado de atención por rol, no por cuenta individual. La vista no sugerirá que atender como Gerencia atendió también la alerta paralela de Supervisor.

## 7. Pruebas y criterios de aceptación

Pruebas automatizadas frontend:
1. GERENCIA/SUPERVISOR consultan únicamente `/api/alertas/resumen/` y `/api/alertas/`; AF/T/TI no envían ninguna llamada, incluso al montar página directamente.
2. Permisos/proyecciones por rol; Supervisor nunca ve campos económicos; Gerencia no obtiene detalle de turnos; no se renderizan propiedades extra/PII.
3. Resumen estricto, lista/detalle/historial estrictos, enums, nullables, estructura de 25 elementos y paginación same-origin segura.
4. Filtros permitidos, pares de fechas, rangos y recurso_id con recurso_tipo; rechazo local de query vacía, desconocida, inválida o repetida; el estado inicial no manda `estado`.
5. Resumen agregado se muestra desde servidor y no se recalcula a partir de la página actual; aviso `desactualizada` no dispara reconciliación.
6. Acuse envía solo motivo trim, valida longitud, bloquea doble envío, respeta acciones permitidas, 200 relee recursos, 409 no repite POST ni finge éxito.
7. 400/401/403/404/405/409/429/5xx/red/timeout, sesión revocada, cambio usuario/rol y respuesta tardía limpian/recuperan estado correctamente.
8. Filtros persisten al paginar/refrescar; filtro cambia página a 1; historial y listado paginan independientemente.
9. Accesibilidad/responsive; sin mocks productivos, solicitudes a recursos origen, datos inventados, tokens o almacenamiento persistente.
10. Desde `frontend/`, ejecutar `npm ci` si se requieren preparar dependencias, `npm test` y `npm run build`. Informar pruebas E2E locales como no ejecutadas si no hubo ejecución real con cuenta autorizada.

**Aceptación:** la pantalla de Alertas consume únicamente contratos de SPEC-009 con AuthClient; entrega datos y conteos backend-only; atiende motivadamente solo las alertas elegibles; G/S ven solo su ámbito; los demás roles no envían requests; fallos y estados inciertos no simulan éxito; el resto del frontend y backend permanecen sin cambios fuera de alcance.

## 8. Riesgos y cuestiones de producto

- La bandeja representa la destinataria por rol y estados derivados, no una notificación personal ni un canal push; debe evitarse presentar nuevas funciones de notificación.
- Alertas puede resolverse automáticamente entre la carga y el acuse; el conflicto 409 es comportamiento normal que exige relectura.
- `sincronizacion.desactualizada` refleja el último ciclo completo registrado por backend; frontend no puede garantizar frescura adicional.
- Las acciones directas de navegación al origen no forman parte de este contrato; agregar deep links requeriría confirmar contrato y permisos de destino.

## 9. Secuencia documental y de implementación

1. Esta rama contiene únicamente esta SPEC de frontend, complementaria a SPEC-009 backend.
2. El responsable revisa y aprueba el texto de contrato en concreto; la aprobación general de redactar la SPEC no equivale a aprobación automática del contrato final.
3. Después de aprobación explícita del texto, un operador autorizado puede publicar la rama documental mediante PR sin código; no hacer commit/push/PR/merge automáticamente.
4. Tras integrar la SPEC en `main` con autorización, el usuario actualiza su copia local con `git switch main` y `git pull --ff-only origin main`.
5. Solo con SPEC aprobada e integrada y encargo de implementación, crear rama de implementación frontend desde `origin/main`, programar, ejecutar pruebas y entregar informe previo a cualquier publicación.
6. No modificar backend, infraestructura, `compose.yaml`, permisos globales, workflows ni archivos de entorno para resolver la pantalla.

## 10. Referencias

- `specs/009-alertas-backend.md` (API, catálogo, RBAC, errores, privacidad y sincronización).
- `specs/008-011-mapa-backend-pendiente.md` (estado integrado de SPEC-009 y separación de responsabilidades).
- `backend/apps/alertas/{urls.py,views.py,serializers.py,catalogo.py,permissions.py}` y `backend/config/urls.py`.
- `frontend/AGENTS.md`, `frontend/src/app.jsx`, `frontend/src/data/constants.js`, `frontend/src/auth/{AuthContext.jsx,client.js}`, `frontend/src/comercial/{ui.jsx,scope.js}`.

## 11. Seguimiento de implementación local (14-11-2026)

- El worktree local contiene `frontend/src/pages/Alertas.jsx`, montado para GERENCIA y SUPERVISOR_OBRAS. La UI consume resumen/listado, filtros, paginación, detalle/historial y atención motivada según las acciones permitidas por la API, reutilizando `useAuth().request`.
- `frontend/tests/integrations-domain.test.js` prueba consultas y matriz por rol; la suite completa local aprobó 159 pruebas y el build aprobó. No se ejecutó E2E de navegador contra cuentas reales ni Frontend CI.
- Implementación no publicada: sin commit, push, PR ni merge. Se conserva el estado de aprobación/integración documental indicado al inicio de esta SPEC; este registro no lo altera.
