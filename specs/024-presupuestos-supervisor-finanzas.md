# SPEC-024 — Elaboración de presupuestos por Supervisor y Finanzas (backend FYAG)

> **Contrato funcional ratificado para la Beta local.** Base comprobada: `main` `148e2120499c9221dd476f179b124024582f97fa`, con SPEC-020A/B y SPEC-023A/B integradas. **Alcance exclusivo: backend y documentación técnica**. Sin cambios en `frontend/`, sin nube y sin ampliar Bodega. Este contrato modifica puntualmente la matriz de **Presupuestos** de SPEC-020A; conserva intacta la política de **Clientes** y las atribuciones de Gerencia.

## 1. Objetivo

El **Supervisor de Obras** puede confeccionar presupuestos propios como `BORRADOR`, gestionar sus ítems y enviarlos a **Administrativo/Finanzas** para revisión. **Administrativo/Finanzas** también puede crear presupuestos desde cero y mantiene en exclusiva la aprobación o rechazo interno, envío al cliente, registro de respuesta del cliente, anulaciones y las decisiones comerciales. **Gerencia** sigue en modo de consulta y alertas selectivas, sin facultad de aprobación.

Presupuestos son propuestas comerciales. Bodega complementa la **ejecución real de Obras** según SPEC-019B/C: no enlazar ítems del presupuesto a artículos de stock, no consultar disponibilidad al cotizar, no generar faltantes negativos, compras, reservas, entregas ni gastos automáticos a partir del presupuesto. Servicios, mano de obra y materiales continúan siendo líneas comerciales libres con `descripcion`, `cantidad`, `unidad`, `precio_unitario` y `orden`.

## 2. Estado real verificado y riesgo de seguridad

- `apps.comercial.permissions.PuedeOperarPresupuestos` solo permite a Gerencia y Administrativo/Finanzas entrar en el módulo y reserva toda escritura a Finanzas.
- `apps.comercial.permissions.revalidar_escritura` es compartido por servicios de **Clientes** y servicios de **Presupuestos**; actualmente exige exclusivamente `ADMINISTRATIVO_FINANZAS`. **NO ampliar este helper global a Supervisor**: eso concedería escrituras indebidas sobre Clientes.
- `apps.comercial.services_presupuestos` usa ese helper en `_usuario_interno`, ediciones, ítems, creación, `_transicionar` y creación de revisiones. Refactorizar con una **autorización exclusiva del dominio presupuestario**, diferenciando `elaborar`, `enviar_revision` y `decision_finanzas`, revalidando rol/sesión desde PostgreSQL; mantener **sin cambios** el helper AF-only para Clientes.
- `Presupuesto.creado_por` ya guarda al creador; `PresupuestoEvento` registra transiciones. `BORRADOR`, `PENDIENTE_FINANZAS`, `APROBADO_FINANZAS`, `RECHAZADO_FINANZAS` y `politica_aprobacion=FINANZAS` ya existen. No reescribir historia, migraciones ni inventar una nueva política de aprobación.
- `PresupuestoViewSet.get_queryset` actualmente lista todos los presupuestos para roles admitidos; al dar acceso a Supervisor **debe introducirse aislamiento por autor en SQL**. `get_object`, histórico, modificación de ítems y acciones deben usar la misma proyección scoped, sin cargar el recurso ajeno antes de autorizarlo.
- `GET /api/clientes/` sigue vedado a Supervisor por SPEC-020. Para poder elegir un cliente sin abrir datos personales se define abajo un **selector mínimo propio del contexto presupuestario**.

## 3. Matriz de permisos ratificada

| Acción | Supervisor Obras | Administrativo/Finanzas | Gerencia | Técnico/Bodeguero/TI |
| --- | --- | --- | --- | --- |
| Consultar presupuestos e historial | Solo creados por él | Todos | Todos, lectura autorizada | Sin nuevos accesos |
| Crear nuevo BORRADOR | Sí | Sí | No | No |
| Modificar cabecera/ítems del BORRADOR | Solo propios | Cualquier borrador | No | No |
| Enviar BORRADOR a Finanzas | Solo propios | Cualquier borrador | No | No |
| Aprobar/rechazar revisión interna | No | **Exclusivo** | No | No |
| Enviar presupuesto al cliente | No | **Exclusivo** | No | No |
| Registrar aceptación/rechazo del cliente | No | **Exclusivo** | No | No |
| Anular presupuesto | No | **Exclusivo** | No | No |
| Crear revisión de presupuesto RECHAZADO_FINANZAS | Solo propio, nuevo BORRADOR propio | Sí | No | No |
| Otras revisiones (rechazo cliente/gerencial legado/anulación) | No | Sí, conforme reglas actuales | No | No |
| Seleccionar cliente activo (ID/nombre) | Sí, mínima proyección | Sí | No requiere ampliación | No |
| CRUD completo de Clientes | **No** | **Sí** | Solo GET actual | No |

Notas:
1. El Supervisor conserva consulta de sus presupuestos **en cualquier estado**, incluso tras aprobación, rechazo y aceptación del cliente, pero ya no los edita después de pasar a `PENDIENTE_FINANZAS`. Un Supervisor **no ve ni modifica** presupuestos creados por otros supervisores o por Finanzas; Finanzas sí puede acceder y operar sobre todos. No conceder acceso comercial nuevo al Técnico, Bodeguero ni TI por ser superusuario.
2. Finanzas puede corregir borradores propios o de Supervisor **antes de que se envíen a revisión**. `PENDIENTE_FINANZAS` permanece congelado para ediciones de ítems/cabecera: no modificar silenciosamente cifras aprobables. Cuando Finanzas rechaza, el autor Supervisor puede crear una nueva revisión vinculada al original, preservando ambos historiales y sin reabrir el registro rechazado. El rechazo exige motivo.
3. Una revisión realizada por Supervisor de un rechazo financiero crea un presupuesto **nuevo** cuyo `creado_por` es el Supervisor, `presupuesto_origen` es el original, y `politica_aprobacion=FINANZAS`; copia cabecera e ítems de modo controlado usando el servicio existente y genera su propio evento `NULL -> BORRADOR`. No inventar autoaprobación ni modificar/eliminar el original.
4. Gerencia conserva únicamente lectura y sus alertas críticas/seleccionadas de SPEC-020B. No recibe alerta operacional nueva de `PENDIENTE_FINANZAS`; Finanzas sigue siendo la responsable del tipo existente. Rutas `enviar-gerencia`, `aprobar-gerencia`, `rechazar-gerencia` permanecen 403 uniforme para todos.

## 4. Flujo y validaciones

```text
SUPERVISOR o FINANZAS: crear -> BORRADOR
     | editar cabecera e ítems (Supervisor: solo propio; Finanzas: todos)
     | enviar-finanzas (Supervisor: solo propio; Finanzas: todos)
     v
PENDIENTE_FINANZAS  [contenido congelado]
     | aprobar-finanzas (solo AF) -> APROBADO_FINANZAS
     | rechazar-finanzas (solo AF, motivo obligatorio) -> RECHAZADO_FINANZAS
     |   -> crear-revision (Supervisor: solo propio; AF: todos) -> nuevo BORRADOR
     v
APROBADO_FINANZAS -> enviar-cliente (solo AF) -> ENVIADO_CLIENTE
     -> registrar-aprobacion-cliente / registrar-rechazo-cliente (solo AF)
     -> APROBADO_CLIENTE permite crear Obra según contratos vigentes
```

- Finanzas puede confeccionar y aprobar un presupuesto creado por el mismo usuario AF: **no exigir otra persona revisora** ni introducir autorización por montos; esta es la política ya vigente de SPEC-020A.
- Para pasar de `BORRADOR` a `PENDIENTE_FINANZAS`, preservar `_validar_salida`: cliente activo, al menos un ítem válido y monto neto positivo. No cambiar Decimal, precios, totales, impuestos, idempotencia de transiciones ni protecciones de Obras.
- Después de envío, no permitir cambios de cliente, descripción ni ítems por ningún rol hasta las transiciones autorizadas. Revisiones nunca reescriben presupuesto/eventos originales.
- `PresupuestoEvento.registrado_por` representa al actor real de cada transición. `Presupuesto.creado_por` conserva su autoría; el historial actual de eventos **no constituye auditoría completa de cada edición de ítems**. No declarar que se registran ediciones individuales salvo agregar expresamente un mecanismo auditado y probado en un alcance ulterior.
- Respetar contrato vigente de historiales `GERENCIA_LEGADA` con salida por Finanzas; no forzar la nueva ruta de envío sobre históricos, ni cambiar estados históricos.
- No crear Obras ni afectar Bodega al aprobar/enviar presupuestos; las Obras siguen requiriendo `APROBADO_CLIENTE`.

## 5. API HTTP y selección mínima de cliente

Mantener rutas y cuerpos de SPEC-003B/020A con slash final:

| Método/ruta | Cambio 024 |
| --- | --- |
| `GET /api/presupuestos/` | Añade Supervisor, filtrado `creado_por=request.user` **en SQL**; AF y Gerencia mantienen consulta actual |
| `GET /api/presupuestos/{id}/` | Supervisor solo propio, terceros = 404 indistinguible de inexistente |
| `GET /api/presupuestos/{id}/historial/` | Mismo scope de Supervisor; eventos de estado reales |
| `POST /api/presupuestos/` | Permite Supervisor o AF, crea BORRADOR; `creado_por` siempre servidor |
| `PATCH /api/presupuestos/{id}/` | Supervisor propio BORRADOR / AF cualquier BORRADOR |
| `POST /api/presupuestos/{id}/items/` | Supervisor propio BORRADOR / AF cualquier BORRADOR |
| `PATCH/DELETE /api/presupuestos/{id}/items/{item_id}/` | Scope dueño antes de consultar ítem; solo BORRADOR |
| `POST /api/presupuestos/{id}/enviar-finanzas/` | Supervisor propio o AF, solo BORRADOR; crea evento y notificación financiera vigente |
| `POST /api/presupuestos/{id}/crear-revision/` | AF: reglas actuales; Supervisor: propio `RECHAZADO_FINANZAS` exclusivamente |
| `POST .../aprobar-finanzas/, rechazar-finanzas/, enviar-cliente/, registrar-*-cliente/, anular/` | Solo AF, sin ampliar |
| `GET /api/presupuestos/clientes-elegibles/?buscar=&page=` | Nuevo selector **solo lectura**, Supervisor/AF; 25 por página; clientes activos: `id,nombre_legal,tipo_cliente` únicamente |

El selector restringido no reemplaza ni amplía `GET /api/clientes/`: excluir RUT, correo, teléfono, nombres de contacto, identificaciones extranjeras y datos sensibles. Filtrado por nombre, orden estable; parámetros estrictos; solo clientes activos; 401/403/400 consistentes, sin filtración de recuentos de clientes inactivos. No aceptar creación o modificación de clientes desde este endpoint. Se permite al Supervisor proporcionar un ID de cliente elegible en el cuerpo de creación o edición de su borrador. El servicio comprueba cliente activo bajo bloqueo, también al enviar.

**Control de acceso:** 401 para sesión inválida; 403 para rol sin capacidad; 404 para recurso de otro Supervisor o inexistente; 409 para estado incompatible; 400 para validación de campos. No exponer datos de recurso ajeno mediante serializer/errores antes de scoped lookup. Replays de acciones existentes no deben saltarse autoridad.

## 6. Diseño de autorización y transacciones

1. Mantener `revalidar_escritura` de Clientes **estrictamente AF-only**. Nunca sustituirlo por un helper que admita Supervisor. Crear un guard presupuestario específico que relea rol, `is_active`, `sesion_version`, credencial/estado operativo (018/C2) y autoría persistida cuando aplique. No confiar en claim `rol`, flags `is_superuser/is_staff` ni ID/rol enviado en JSON.
2. Separar guards de **confección** (S sobre propios/AF sobre todos), **envío** (S sobre propios/AF sobre todos), **decisión comercial** (AF únicamente) y **consulta** (S propios, AF/G según su lectura actual). Usar en `Permission`, `get_queryset` y **servicios transaccionales**, no exclusivamente en la vista React o en el ViewSet.
3. Revalidar tras adquirir `select_for_update`, antes de guardar y antes de transicionar; proteger de modificación concurrente de creador/rol/sesión mientras se espera. Preservar el lock order actual y reglas de `Presupuesto -> Cliente` vs `Cliente -> Presupuesto`; no introducir nuevos advisory locks sin necesidad.
4. Para acciones financieras (aprobar, rechazar, envío cliente, decisión cliente, anulación, revisión no autorizada al S), el helper AF-only debe prevalecer incluso si el objeto fue creado por Supervisor. Revisión con datos copiados produce nuevas PKs de items y evento propio.
5. Preservar aislamiento por ID en detail, historial, edición, ítems y revisiones. No implementar `list` global + filtro Python. Evitar N+1; mantener paginación de 25.
6. Conservación de comportamientos API sin cambios: AF y Gerencia siguen leyendo listas/detalles, AF sigue escribiendo, rutas gerenciales legadas siguen denegadas; cualquier modificación necesaria de tests antiguos de roles debe actualizar expectativas por **SPEC-024**, sin debilitar negativas históricas de Clientes, Finanzas, Alertas, Obras, Inventario o credenciales.

## 7. No alcance explícito

**No implementar**: enlace FK entre `PresupuestoItem` y `ArticuloInventario`; consulta de stock al confeccionar; faltantes negativos; catálogo de precios; costo/promedio de Bodega aplicado a precio de venta; compras automáticas; reserva/descuento de stock por cotización; copiado de cantidades presupuestadas a `GastoObra`; asignación automática de materiales a Obras; aprobación por Gerencia; dashboard/mensajería; nuevos roles; edición reactiva de frontend; cloud.

Los ingresos, entregas, devoluciones y gastos derivados de Bodega **siguen exclusivamente en las operaciones reales de Obras** (SPEC-019B/C). Los presupuestos representan lo vendido/cotizado; los gastos registran lo ejecutado. No duplicar movimientos, no alterar valorización histórica.

## 8. Pruebas y aceptación

**Casos obligatorios (Django/API/servicios):**
- Matriz completa de seis roles para cada acción, métodos PUT/DELETE/OPTIONS, sin JWT, JWT expirado, usuario inactivo, versión revocada, credenciales/bloqueos persistidos C2; `is_staff/is_superuser` y token con `rol` falsificado no conceden permisos.
- S crea BORRADOR, añade/modifica/borra ítems, actualiza cabecera, consulta propio y envía a Finanzas; AF recibe alerta vigente y puede aprobar/rechazar, enviar al cliente y registrar su decisión; S ve la evolución sin poder decidir.
- AF crea, edita, envía y aprueba su propio presupuesto sin segundo aprobador; AF también puede editar borrador ajeno antes del envío.
- S no consulta/edit/crea ítem/envía/revisa presupuestos de AF u otro S: 404; AF y G conservan lectura, G nunca escribe; acciones AF exclusivas permanecen 403 al S incluso sobre presupuesto propio.
- En `PENDIENTE_FINANZAS` no se edita contenido ni por S ni por AF; simultaneidad entre agregar ítem y enviar se serializa por Presupuesto, con final coherente. Revocación de sesión/rol bajo lock no confirma cambios ni eventos.
- Rechazo financiero con motivo, revisión por S del propio presupuesto rechazado, FK al original y nuevo autor S, originales e historiales intactos. Intentar revisión por S de `RECHAZADO_CLIENTE`, `ANULADO` o legado se rechaza; AF mantiene sus caminos históricos.
- Selector mínimo de clientes activos: S y AF leen únicamente ID/nombre/tipo, sin PII; G, T, TI y B denegados; `GET /api/clientes/` sigue vedado al S y CRUD Clientes sigue AF-only a nivel API **y servicios**.
- Prohibición de mutar estados/políticas/autor desde body, Decimal exacto, ítems libres, montos positivos, cliente activo, no ítems: validaciones iguales a 003B. Sin registros ni movimientos de Bodega/Gasto/Obra producidos por cotización.
- Migración limpia y upgrade conservador. **Preferencia: ninguna migración nueva** si basta con permisos/consultas/servicios/serializers, sin modificar las anteriores. Backend Django check, makemigrations check, pruebas comerciales+Usuarios+Obras+Alertas+Inventario+Chat y regresión completa; CI GitHub posterior.
- OpenAPI nueva o extensión versionada para permisos/selector, Postman con roles reales y negativas, informe de cambio bajo `backend/docs/SPEC-024-IMPLEMENTACION.md`; sin secretos ni credenciales reales.
- E2E QA API: S crea -> editar ítems -> enviar -> AF aprobar/rechazar -> enviar cliente -> registrar aprobación -> S consulta historial y AF/G consultan. Verificar CORS/OPTIONS según endpoint nuevo.

**Criterio de cierre:** CI del PR de implementación verde, pruebas locales aisladas y control de ausencia de cambios en `frontend/`, `specs/`, servicios de Clientes salvo si fuera inevitable para conservar su autorización, Bodega, Finanzas, Chat, Dashboard o infraestructura cloud. Evitar modificación de helpers compartidos para ampliar inadvertidamente roles.

## 9. Flujo de entrega y límites de ejecución

1. PR documental de esta SPEC separado del código; tras integrar contrato, implementar sobre rama `feature/backend-024-presupuestos-supervisor-finanzas`.
2. OpenCode implementa **solo backend**, agrega pruebas/OpenAPI/Postman y publica commit/push en su rama, no PR/merge. ChatGPT realiza revisión técnica, abre PR y comprueba CI antes de proponer/fusionar implementación según autorización.
3. Mantener `main` intacto durante desarrollo, no forzar push, no eliminar datos ni volúmenes del proyecto. QA aislado. Frontend sigue bajo responsabilidad de compañeros; su adaptación posterior debe consumir permisos/selector publicados.
