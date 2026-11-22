# SPEC-024 — Presupuestos de Supervisor y Finanzas

Base obligatoria: `main@4843e2a00623adbeca2cc00f4e19d68e89878311`.
Rama: `feature/backend-024-presupuestos-supervisor-finanzas`.
Alcance: backend Comercial, pruebas y contratos. Sin esquema nuevo ni dependencias
nuevas; sin frontend, Bodega, Chat, cambios JWT/credenciales ni adaptación cloud.

## Arquitectura y separación de dominios

`permissions_presupuestos.py` concentra guards presupuestarios separados para
lectura, selector, elaboración, envío a revisión, decisiones AF y revisiones.
`PuedeOperarPresupuestos` decide la capacidad antes de localizar recursos o
interpretar cuerpos; los servicios vuelven a autorizar bajo transacción.

**El helper `permissions.revalidar_escritura` conserva exactamente su cuerpo
AF-only** y `services.py` de Clientes no cambia. Sus referencias continúan en
guardar/activar/desactivar clientes; Presupuestos ya no lo importa. No derivar
facultades de Clientes de la nueva capacidad presupuestaria.

Se releen desde PostgreSQL rol, actividad, versión de sesión, hash de contraseña,
credencial PERSONAL y estado operativo según la política C2 vigente. No se
confía en rol del JWT, valores mutables del objeto actor ni staff/superuser.
Los controles JWT existentes se reutilizan sin cambiar Usuarios.

## Matriz efectiva

| Operación | Supervisor | Administrativo/Finanzas | Gerencia | Técnico/Bodeguero/TI |
|---|---|---|---|---|
| Listar/detalle/historial | Solo propios, cualquier estado | Todos | Todos | 403 |
| Crear BORRADOR | Sí | Sí | 403 | 403 |
| Cabecera/ítems BORRADOR | Solo propios | Cualquiera | 403 | 403 |
| Enviar a Finanzas | Solo propios | Cualquiera | 403 | 403 |
| Aprobar/rechazar, envío/respuesta cliente, anular | 403 | Según estado histórico | 403 | 403 |
| Revisar RECHAZADO_FINANZAS | Solo propio | Sí | 403 | 403 |
| Revisar rechazo cliente/gerencial legado o ANULADO | 409 en propio | Reglas actuales | 403 | 403 |
| Selector mínimo de clientes | Sí | Sí | 403 | 403 |
| Clientes generales | 403 | CRUD existente | Solo lectura existente | 403 |

Las rutas gerenciales retiradas permanecen 403 para todos los roles, antes de
recurso y cuerpo, también al consultar sus capacidades. No se cambia la selección
de alertas de Gerencia ni se crea aprobación doble por dos empleados AF.

## API y scopes

Rutas y cuerpos previos de 003B/020A conservados, con slash final:

- `GET/POST /api/presupuestos/`: consulta scoped y creación S/AF.
- `GET/PATCH /api/presupuestos/{id}/`: S propio / AF todos; escritura BORRADOR.
- `POST .../{id}/items/`, `PATCH/DELETE .../{id}/items/{item_id}/`: mismo scope.
- `GET .../{id}/historial/`: mismo scope, eventos reales ordenados por fecha/ID.
- `POST .../{id}/enviar-finanzas/`: S propietario o AF.
- `POST .../{id}/crear-revision/`: S solo rechazo financiero propio; AF conserva
  todos sus orígenes históricos válidos.
- Decisiones posteriores siguen exclusivamente AF. PUT/DELETE de presupuesto
  continúan sin handler (405 para rol admitido); no hay DELETE físico.

`presupuestos_visibles` aplica `filter(creado_por_id=actual.pk)` en SQL para S,
antes de buscar presupuesto, ítem, historial o procesar body. También lo usan los
servicios con `select_for_update`, sin confiar en la instancia del caller. Se
revalida el creador de la fila tras esperar el lock. Los recursos de AF u otro S
son indistinguibles de inexistentes: 404, incluidos cuerpos malformados. AF/G
mantienen sus consultas. Listas conservan 25 elementos y prefetch de líneas.

Precedencia: 401 sesión inválida; 403 sin capacidad; 404 ajeno/inexistente; 409
estado incompatible; 400 validación. Las decisiones AF responden 403 al S
incluso sobre presupuesto propio o ID inexistente. Campos administrados (autor,
estado, política, origen, fechas, montos) continúan rechazados.

### Selector nuevo

`GET /api/presupuestos/clientes-elegibles/?buscar=nombre&page=1`

Solo S/AF, incluidos HEAD/OPTIONS. No tiene escritura. Respuesta paginada DRF:
`count,next,previous,results`; solo clientes activos, orden `(nombre_legal,id)`,
25 por página. `buscar` es substring de nombre, case-insensitive, trim, no vacío,
máximo 200 caracteres; queries desconocidas/repetidas o página no positiva
responden 400, página fuera de rango 404. No se filtran recuentos de inactivos.

Cada resultado contiene **exclusivamente** `id,nombre_legal,tipo_cliente`.
La consulta usa `values` con esas columnas, sin cargar ni serializar RUT,
identificación, contacto, teléfono o correo. No modifica `/api/clientes/`.
Al asignar el ID en crear/PATCH y al enviar, el servicio comprueba cliente
activo bajo bloqueo; el selector no constituye autorización de escritura.

## Estados, revisiones e integridad

Flujo nuevo:
`BORRADOR -> PENDIENTE_FINANZAS -> APROBADO_FINANZAS -> ENVIADO_CLIENTE -> APROBADO_CLIENTE`.
Rechazo desde pendiente: `RECHAZADO_FINANZAS` con motivo obligatorio.
No se añaden estados ni se modifica la política `FINANZAS`.

Salida de BORRADOR conserva validación de cliente activo, descripción, al menos
una línea válida y monto neto positivo. Cantidad/precio siguen Decimal exacto;
HALF_UP por línea, subtotal/neto calculados, nunca floats ni stock de Bodega.
**PENDIENTE_FINANZAS no puede editarse ni por AF.** Reintentar una transición ya
realizada responde 409, sin segundo evento: no se introducen claves idempotentes.

Supervisor puede revisar solo su propio RECHAZADO_FINANZAS. La operación existente
copia cabecera/ítems con nuevas PK, vincula `presupuesto_origen`, crea BORRADOR
FINANZAS con autor real y un evento inicial `NULL -> BORRADOR`. No copia historial
ni modifica origen, autores o fechas anteriores. Se permiten múltiples revisiones
independientes de un origen, incluso concurrentes, conforme a 003B: repetir no es
idempotente. AF conserva revisión desde los rechazos y ANULADO previos.

Los históricos GERENCIA_LEGADA conservan política, estados y eventos originales;
AF mantiene su camino de decisión y envío. No se reinterpreta historia como si
hubiera sido creada/revisada por el Supervisor.

## Concurrencia y revocación

Se conserva el orden `Presupuesto existente -> Cliente si corresponde` y el lock
de presupuesto que serializa ítems, envío, revisión y decisiones. Crear comienza
por Cliente porque aún no existe presupuesto. No se introducen advisory locks.

Cada escritura revalida actor antes y después de esperar el recurso, y al finalizar
la operación, antes de salir de la transacción. El cierre transaccional adquiere
locks `Usuario (NO KEY UPDATE) -> SeguridadCredencial -> EstadoAcceso`, relee
seguridad y compara rol persistido inicial/final. Cualquier revocación o cambio
de rol observado revierte cabecera, ítems, eventos y callbacks, incluso si el ítem
ya se había escrito dentro de la transacción. Los servicios de Usuarios mantienen
su orden Usuario -> credencial -> acceso; no se modifican ni adquieren recursos
comerciales. NO KEY UPDATE evita inversión con KEY SHARE de FKs al actor.

Una revocación que llega después de estos locks espera al commit: la escritura
precede a la revocación en el orden serializado, no es una sesión revocada que
consiga confirmar posteriormente. No se promete atomicidad entre transacciones
externas que eludan deliberadamente los protocolos de dominio/seguridad.

Pruebas permanentes usan conexiones PostgreSQL independientes y observación de
`pg_blocking_pids`, no sleeps como demostración de exclusión: edición/envío en
ambos órdenes, AF aprobar/rechazar, revocaciones mientras espera, cambio de autor,
dos revisiones y revocación después de guardar una línea aún no confirmada.

## Alertas, Obras y Bodega

Se reutilizan callbacks postcommit existentes. Enviar por S crea la incidencia
financiera para AF; G no recibe alerta operacional nueva. La decisión AF extingue
la causa y resuelve mediante la proyección vigente, sin alterar Alertas.

Obras conserva requisito APROBADO_CLIENTE, unicidad por presupuesto y guard de
anulación `presupuesto_utilizado` para obra de cualquier estado. Cotizar, aprobar
o registrar respuesta cliente **no crea automáticamente** Obra ni GastoObra.
Los tests comparan recuentos de todos los modelos Inventario y Obras/gastos antes
y después del flujo; la suite histórica vuelve a verificar sus protecciones.

PresupuestoItem permanece independiente de ArticuloInventario. Sin consultas de
stock, compras, reservas, entregas, valorización o gastos automáticos.

## Consumo React y contratos

React queda intacto. Usar JWT habitual, el selector mínimo para elegir ID de
cliente y el scope del servidor; no intentar habilitar Clientes generales al S.
No mandar autor/estado/política/monto calculado. Enviar decimales como strings.
Tras enviar, mostrar solo lectura al S; rechazo financiero habilita crear otra
revisión, no reabrir/editar el origen. No confundir edición con evento de estado:
el historial **no audita cada edición de ítems**.

OpenAPI versionado: `openapi/SPEC-024-v1.json`, contrato completo vigente del
dominio presupuestario. Postman: `postman/SPEC-024.postman_collection.json`,
ejecución secuencial con tokens S/AF/G y datos exclusivamente QA. Variables
externas: `base_url`, `cliente_id`, `supervisor_id`, `token_supervisor`, `token_af`,
`token_gerencia`. No exportar el environment con JWT a Git. Colección prueba
selector, Clientes denegado, scope, CRUD de líneas, rechazo/revisión, aprobación,
envío/respuesta cliente, historia, Gerencia solo lectura y rutas retiradas.

## Laboratorio y validación

Se usa `compose.premerge-qa.yaml` standalone sin modificar infraestructura
versionada, proyecto exclusivo `fyag-spec024-20261121`, secretos y override fuera
del repositorio. DB `fyag_spec018c_c2_qa`/test equivalente habilita pruebas C2
aisladas sin activar esa política sobre datos reales. PostgreSQL, Mongo, Redis y
ClamAV son exclusivos del proyecto, sin volúmenes persistentes preexistentes.
Snapshot de IDs Docker y volúmenes previo a cualquier operación QA.

Comandos reproducibles dentro del backend QA:

```text
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py migrate --noinput
python manage.py test apps.comercial --noinput --verbosity 1
python manage.py test --noinput --verbosity 1
```

Migración limpia sobre PostgreSQL vacío, upgrade sin plan de migraciones y
comparación de filas históricas forman parte de la validación. No hay nuevas
migraciones: el upgrade de código no debe reescribir presupuestos/eventos/items.
Los tests históricos solo adaptan expectativas contradichas expresamente por
024: S puede crear y leer lista scoped; recursos AF devuelven 404, no 403;
intentar inyectar rol en una creación ahora autorizada sigue fallando con 400.
No se retiran negativas de Clientes o decisiones exclusivas de AF/G.

### Resultados locales

Entorno: Python 3.13.18, Django 5.2.19, DRF 3.18.3, psycopg 3.3.9,
PostgreSQL 18; Newman 6.2.1 sobre Node 22 para E2E. Sin nuevas dependencias runtime.

| Verificación | Resultado |
|---|---|
| Django check final | Sin incidencias |
| makemigrations --check --dry-run | Sin drift |
| Migración limpia | Todas las migraciones existentes OK |
| Upgrade conservador | Sin plan adicional; filas históricas íntegramente iguales |
| Suite Comercial completa | 297 pruebas OK, 47,970 s |
| Casos específicos 024 (API, concurrencia, upgrade) | 20 pruebas OK, 4,862 s |
| Regresión completa backend | 1370 pruebas OK, 420,800 s |
| Postman por HTTP real/Daphne, dos ejecuciones | 32 requests / 46 aserciones OK en cada ejecución |
| OpenAPI | Documento 3.1 válido; 18 respuestas HTTP reales validadas con JSON Schema y formatos |
| Clientes | Helper y permiso comparados con AST de main: idénticos; servicios/vistas sin cambios |
| Secretos | Ningún secreto efímero QA ni JWT del environment en archivos nuevos/modificados |
| Limpieza QA | Proyecto exclusivo retirado; environment, JWT, secretos y reporte privado eliminados |
| Instalación preexistente | 7 contenedores activos con sus mismos IDs; lista de 38 volúmenes idéntica al snapshot inicial |

La regresión incluye Usuarios, Obras, Alertas, Inventario/Bodega y Chat sin
modificar su código ni sus pruebas. Los siete casos nuevos de concurrencia
incluyen diez escenarios al expandir las cuatro variantes de revocación.
El fallo inicial de una expectativa histórica (S antes no podía crear) se
adaptó a 400 por campos de rol inyectados; permanece una operación denegada,
no una aceptación de claims manipulados.

### Archivos de la entrega

- `apps/comercial/permissions_presupuestos.py` (nuevo).
- `apps/comercial/permissions.py` (solo permiso presupuestario).
- `apps/comercial/services_presupuestos.py`, `views_presupuestos.py`,
  `serializers_presupuestos.py`.
- `apps/comercial/tests/test_024.py`, `test_024_concurrencia.py`,
  `test_024_upgrade.py` (nuevos).
- `apps/comercial/tests/test_020a.py`, `test_presupuesto_api.py` (expectativas 024).
- Este documento, OpenAPI SPEC-024 y colección Postman SPEC-024.

### Límites y riesgos residuales

- La autoaprobación AF está permitida por contrato; no se ha implantado doble
  aprobación ni autorización por montos.
- El historial traza estados, no cada edición comercial; no constituye auditoría
  integral de contenido.
- Crear revisiones no es idempotente y puede producir varias propuestas válidas;
  React debe evitar reintentos ciegos tras perder una respuesta y consultar primero.
- Las reglas C2 se respetan según su habilitación vigente; no se activa la política
  de bloqueo del laboratorio sobre ambientes institucionales.
- La validación se hizo exclusivamente en QA aislado; no se migra ni reinicia la
  instalación preexistente. Su puesta en marcha requiere el procedimiento operativo
  autorizado posterior. No hay despliegue cloud ni aprobación de CI en esta entrega.

Las verificaciones locales no sustituyen la revisión técnica ni CI del futuro PR.
