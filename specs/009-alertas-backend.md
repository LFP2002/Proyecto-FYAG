# SPEC-009 — Alertas operativas y financieras: detección, atención y reconciliación (backend)

**Estado: IMPLEMENTADA E INTEGRADA EN `main` mediante PR #30.** Los endpoints, modelos, migraciones, control de acceso y reconciliación automática se encuentran implementados en `backend/apps/alertas/`, con rutas registradas en `backend/config/urls.py`. Este documento conserva el contrato funcional aprobado; las evidencias de integración se registran en el apartado 14.

## 1. Contexto confirmado y precedencia

Proyecto-FYAG utiliza Django 5/DRF, PostgreSQL, JWT con sesion_version y roles persistidos. Existen APIs reales de Clientes/Presupuestos (SPEC-003), Obras/Turnos/Costos (SPEC-004/004B), Finanzas/Cobranzas (SPEC-007), Usuarios y RBAC exclusivo de TI (SPEC-006B/006C), y auditoría global de solo lectura (SPEC-008).

La autoridad sobre el estado de cada entidad corresponde al módulo propietario. Alertas es un **modelo derivado de observaciones**, no un mecanismo para actualizar las entidades de origen, no un nuevo motor contable y no una alternativa a sus endpoints existentes. Sus escrituras se limitan a los registros propios de Alerta y AlertaEvento.

**Precedencia:** prevalecen los invariantes de datos, permisos y cálculos de los dominios propietarios y el control JWT/CSRF/CORS vigente. Los resultados de un prototipo React nunca son fuente de verdad. Toda contradicción material debe elevarse para revisión antes de cambiar el contrato.

## 2. Objetivo, entregables y catálogo cerrado v1

Exponer una bandeja de alertas por rol, con condición verificable, deduplicación, historial, acuse motivado y resolución automática. Entregar endpoints estables, migraciones nuevas en apps.alertas, reconciliador ejecutándose de forma efectiva, tests Django/PostgreSQL, documentación OpenAPI y guía operativa. **No implementar frontend**.

| Tipo estable | Condición actual que activa | Origen exacto | Destinatarios | Severidad fija |
|---|---|---|---|---|
| PRESUPUESTO_PENDIENTE_GERENCIA | Presupuesto.estado = PENDIENTE_GERENCIA | comercial.Presupuesto | GERENCIA | MEDIA |
| OBRA_SUSPENDIDA | Obra.estado = SUSPENDIDA | obras.Obra | GERENCIA y SUPERVISOR_OBRAS | ALTA |
| TURNO_PENDIENTE_REVISION | TurnoObra.estado_revision = PENDIENTE_REVISION | obras.TurnoObra | SUPERVISOR_OBRAS | MEDIA |
| COBRANZA_VENCIDA | DocumentoCobro.estado = VIGENTE, saldo > 0 y fecha_vencimiento < hoy civil Santiago | finanzas.DocumentoCobro mediante finanzas.consultas_cobranzas.con_cobranza | GERENCIA | ALTA |

Vencida significa que el cálculo **oficial** retorna estado_cobranza_calculado = VENCIDA, no cualquier documento con fecha anterior: pago total, documento revertido y saldo no positivo lo excluyen. No usar float, no sumar pagos dos veces y no inventar IVA. El tipo de Turno se activa también al entrar a PENDIENTE_REVISION desde una subsanación o corrección, no únicamente en el primer cierre.

**Exclusión expresa:** no existe avance porcentual persistido ni validado de Obra; por tanto, no se implementa alerta de desviación costo-versus-avance, umbrales de 10 puntos, rentabilidad proyectada, severidad inferida de dinero, SMS, email, push, Kafka, Celery u otro servicio no justificado para este alcance. Futuras alertas exigen ampliación explícita de SPEC.

## 3. Matriz RBAC y semántica de destinatarios

| Rol persistido activo | Consultar / atender | Ámbito visible |
|---|---|---|
| GERENCIA | Sí | Sus alertas de presupuestos, obras suspendidas y cobranza vencida |
| SUPERVISOR_OBRAS | Sí | Sus alertas de obras suspendidas y turnos pendientes |
| ADMINISTRATIVO_FINANZAS | No (403) | Conserva sus endpoints reales de cobranza, no hereda la bandeja |
| TECNICO | No (403) | Conserva sus endpoints operativos de Obras |
| ADMINISTRADOR_TI | No (403) | Exclusividad de administración de Usuarios; sin alertas de negocio |

La bandeja corresponde al **rol destinatario**, no a una cuenta individual. Dos personas activas del mismo rol comparten el estado de atención de la alerta de ese rol. Distintos roles mantienen acuses independientes: una obra suspendida genera **dos registros**, uno para GERENCIA y otro para SUPERVISOR_OBRAS; atender el aviso de un rol NO atiende el del otro. La resolución de la causa sí debe resolver ambos.

El servidor valida rol persistido, is_active y sesión versionada, sin elevación por is_staff/is_superuser, claims o componentes React. Todos los GET, POST y metadatos OPTIONS aplican el ámbito del rol; un ID que pertenece a otro rol es indistinguible de uno inexistente (404). No revelar saldos, folios, pagos, documentos ni costos a Supervisor; no revelar detalles de Turnos a Gerencia más allá de la alerta de OBRA_SUSPENDIDA.

## 4. Modelos, restricciones e historial de eventos

### 4.1 Alerta (modelo nuevo)

Campos mínimos: id BigAutoField; tipo del catálogo; rol_destinatario (GERENCIA/SUPERVISOR_OBRAS); recurso_tipo (PRESUPUESTO/OBRA/TURNO/DOCUMENTO); recurso_id entero positivo BigInteger; generacion entero positivo; estado PENDIENTE/ATENDIDA/RESUELTA; severidad derivada del catálogo **no editable**; creado_en; atendida_por FK a Usuario nullable; atendida_en nullable; motivo_atencion nullable; resuelta_en nullable; ultima_comprobacion_en. Prohibidos snapshots de precios, correos, tokens, descripciones libres y datos duplicados del negocio en Alerta.

Correspondencia cerrada tipo↔recurso_tipo y tipo↔rol_destinatario; CheckConstraints y validación de servidor. UniqueConstraint para (tipo, recurso_tipo, recurso_id, rol_destinatario, generacion) y **unicidad parcial de alerta no resuelta** por (tipo, recurso_tipo, recurso_id, rol_destinatario) cuando estado está en PENDIENTE o ATENDIDA. Una causa no produce más de una alerta abierta para el mismo rol.

La generación arranca en 1 por combinación de tipo, recurso y rol, y aumenta de manera monotónica al reactivarse una condición que ya había quedado RESUELTA. No reabrir ni borrar un episodio histórico ni reiniciar su número. Reintentos y dos workers simultáneos no pueden crear dos generaciones activas. Resolver la concurrencia con bloqueos PostgreSQL de granularidad por clave y constraints, respetando el orden de locks de los servicios existentes. No usar un mutex global que serialice todos los recursos del sistema.

Estados y transiciones:
- Primera detección: inexistente → PENDIENTE; registrar CREACION.
- Reconocimiento motivado autorizado: PENDIENTE → ATENDIDA; registrar ATENCION; no cambia origen.
- Origen deja de cumplir la regla: PENDIENTE o ATENDIDA → RESUELTA; registrar RESOLUCION por el sistema; no inventar usuario operador; conservar fecha/actor/motivo de atención anteriores.
- Nueva ocurrencia posterior: crear una nueva Alerta PENDIENTE con generacion + 1 y nueva CREACION. La anterior permanece RESUELTA.
- Reconciliar una condición activa ya registrada no modifica la generación ni el historial; se permite actualizar únicamente ultima_comprobacion_en con frecuencia controlada.

### 4.2 AlertaEvento (modelo nuevo e histórico)

Registro append-only: id, alerta FK con PROTECT, tipo (CREACION/ATENCION/RESOLUCION), estado_anterior nullable, estado_nuevo, actor nullable (null para sistema), motivo (vacío para eventos automáticos, no vacío para atención), registrado_en (hora servidor). No se acepta input HTTP para crear o modificar eventos. Restringir update/delete vía servicios y modelos como las auditorías existentes, y no crear APIs de edición/borrado. El evento RESOLUCION se registra independientemente para los dos roles en alertas compartidas.

### 4.3 Coherencia de campo y representación

Estado PENDIENTE exige atendida_por/atendida_en/motivo_atencion null y resuelta_en null. Estado ATENDIDA exige los tres campos de atención y resuelta_en null. Estado RESUELTA exige resuelta_en y puede conservar campos de atención (si se atendió antes); validar CheckConstraint, timestamps y transiciones. No se expone la columna generacion como parámetro editable. La severidad, titulo y descripcion son derivados del tipo, con texto fijo de servidor y sin datos sensibles.

## 5. Detección, activación y resolución automática

No se permiten efectos laterales en GET. La creación/resolución es responsabilidad del servicio de proyección de alertas:

1. **Notificación rápida postcommit:** integrar puntos mínimos de señalización después de una mutación de negocio exitosa, sin cambiar sus reglas. Priorizar transiciones reales (Presupuesto enviado/retirado de Gerencia, Obra suspendida/reanudada, Turno cerrado/subsanado/revisado/corregido, documento registrado/revertido y pago registrado/anulado). Usar transaction.on_commit o patrón equivalente seguro y no ejecutar consultas de alertas antes del commit de negocio. Un fallo de señalización nunca debe revertir un pago confirmado ni una operación original.
2. **Reconciliación obligatoria:** comando de gestión idempotente y seguro para ejecutar un ciclo completo de fuentes, detectando alertas faltantes y resolviendo las obsoletas, incluso tras reinicio o fallo de callback. Por ejemplo, python manage.py reconciliar_alertas --once, o nombre documentado equivalente. Usar filtros/consultas incrementales y agregaciones: no cargar toda la base a memoria; no modificar el dominio.
3. **Programación efectiva sin usuario conectado:** ejecutar un ciclo al inicio del proceso reconciliador y posteriormente cada 60 segundos como configuración por defecto de desarrollo. Proveer servicio/proceso separado del web server para Docker Compose; en despliegue real debe haber scheduler/worker externo equivalente, con reinicio supervisado y prevención de carreras. No depender de que alguien abra /api/alertas/ o ejecute manualmente el comando. No instalar Celery/Redis ni agregar dependencias sin justificación técnica.
4. **Cambio de día civil:** la comparación de fecha_vencimiento usa hoy_santiago() de Finanzas y la misma consulta con_cobranza. El proceso programado debe detectar vencimientos nuevos tras medianoche America/Santiago incluso con transiciones de 23/25 horas (DST). No usar UTC date ni sumar segundos para avanzar días civiles.
5. **Observabilidad:** persistir timestamp de la última reconciliación completa exitosa (tabla de estado propio del módulo, sin secretos). GET /api/alertas/resumen/ incluirá sincronizacion.ultima_correcta_en nullable y sincronizacion.desactualizada boolean. Considerar desactualizada cuando no existe ejecución exitosa o su edad supera 180 segundos bajo cadencia 60s. El endpoint de resumen **solo lee**, nunca ejecuta reconciliación.
6. **Consistencia eventual declarada:** si una incidencia aparece y desaparece enteramente entre reconciliaciones y se pierde la señalización postcommit, puede no producir episodio histórico, pues el estado actual no da evidencia suficiente de su aparición. No prometer captura de cada transición breve sin un outbox duradero de dominios; registrar el límite operacional y probar recuperación al siguiente ciclo para incidencias vigentes.

Priorizar no añadir bloqueos ni importaciones circulares en los servicios originales; si las notificaciones postcommit requieren cambiar archivos de Comercial/Obras/Finanzas, documentar exactamente los archivos y demostrar regresión. El reconciliador siempre es el mecanismo de recuperación: los callbacks no reemplazan el scheduler.

## 6. Contrato REST público v1

Rutas nuevas (slash final obligatorio):

| Método | Ruta | Descripción |
|---|---|---|
| GET | /api/alertas/ | Bandeja paginada del rol actual |
| GET | /api/alertas/resumen/ | Conteos agregados y salud de reconciliación |
| GET | /api/alertas/{id}/ | Detalle autorizado |
| GET | /api/alertas/{id}/historial/ | Historial de la alerta, paginado |
| POST | /api/alertas/{id}/atender/ | Reconocimiento motivado, sin modificar origen |

Los métodos de escritura restantes (PUT/PATCH/DELETE, y POST sobre rutas distintas de atender) deben retornar 405 a perfiles que tienen acceso. No agregar endpoints CRUD generales, POST de resolución, método para forzar estado ni exposición pública de reconciliación administrativa.

### 6.1 GET /api/alertas/

Paginación DRF exacta: count, next, previous, results; 25 elementos por página, orden creado_en DESC, id DESC. Filtrar por rol_destinatario **antes** de contar, paginar o consultar detalle. Query aceptada: estado (PENDIENTE/ATENDIDA/RESUELTA/TODAS), tipo del catálogo, recurso_tipo del catálogo, recurso_id entero positivo (requiere recurso_tipo), desde y hasta YYYY-MM-DD en Santiago (ambas juntas, rango máximo 366 días inclusivos), page entero decimal positivo. Parámetros no reconocidos, repetidos, incoherentes, valores vacíos o extremos → 400. Fecha aplica a creado_en; desde inclusive y hasta inclusive con frontera SQL exclusiva al inicio del día siguiente.

Sin estado: listar **solo incidencias actuales**, es decir PENDIENTE y ATENDIDA. estado=TODAS incluye registros resueltos históricos; estado=RESUELTA los filtra expresamente. Sin fechas: no restringir temporalmente incidencias activas; mantener acceso histórico paginado por petición explícita. No aceptar por query un rol_destinatario arbitrario: se deduce del principal.

### 6.2 GET /api/alertas/resumen/

No acepta filtros ni page. JSON 200 contractual de ejemplo sintético:

~~~json
{
  "generado_en": "2026-11-12T15:30:00-03:00",
  "zona_horaria": "America/Santiago",
  "por_estado": {"PENDIENTE": 2, "ATENDIDA": 1, "RESUELTA": 4},
  "activas": 3,
  "por_tipo": {
    "PRESUPUESTO_PENDIENTE_GERENCIA": {"PENDIENTE": 1, "ATENDIDA": 0, "RESUELTA": 1},
    "OBRA_SUSPENDIDA": {"PENDIENTE": 1, "ATENDIDA": 1, "RESUELTA": 1},
    "COBRANZA_VENCIDA": {"PENDIENTE": 0, "ATENDIDA": 0, "RESUELTA": 2}
  },
  "sincronizacion": {"ultima_correcta_en": "2026-11-12T15:29:00-03:00", "desactualizada": false}
}
~~~

por_tipo incluye solo tipos destinados al rol, todos sus estados con ceros cuando no haya filas. por_estado.RESUELTA es conteo histórico, no una incidencia actual. El ejemplo muestra estructura, no datos reales. Para Supervisor, por_tipo incluye únicamente OBRA_SUSPENDIDA y TURNO_PENDIENTE_REVISION. No revelar contadores de otro rol.

### 6.3 GET /api/alertas/{id}/ y resultados del listado

El listado y el detalle comparten una proyección idéntica, sin importes ni datos privados. Ejemplo sintético:

~~~json
{
  "id": 18,
  "tipo": "TURNO_PENDIENTE_REVISION",
  "estado": "PENDIENTE",
  "severidad": "MEDIA",
  "rol_destinatario": "SUPERVISOR_OBRAS",
  "recurso_tipo": "TURNO",
  "recurso_id": 83,
  "recurso_codigo": null,
  "obra": 12,
  "titulo": "Turno pendiente de revisión",
  "descripcion": "El turno requiere revisión del Supervisor.",
  "creado_en": "2026-11-12T14:10:00-03:00",
  "atendida_por": null,
  "atendida_en": null,
  "motivo_atencion": null,
  "resuelta_en": null,
  "acciones_permitidas": ["ATENDER"]
}
~~~

Todos los campos tienen tipos estables. recurso_codigo es string o null, generado por backend desde un identificador permitido (código de presupuesto/obra, folio si el rol lo permite); obra es PK de Obra o null. Para alertas de obra suspendida, obra coincide con recurso_id; para Turno, obra se obtiene del modelo TurnoObra; para documento, se permite Obra como contexto exclusivamente a Gerencia; para Presupuesto sin Obra, null. No incluir IDs de pago, nombres de clientes, correos, precios, costos, teléfonos, documentos privados ni descripción libre de origen. Las acciones_permitidas resultan del estado y del rol en servidor: ["ATENDER"] solo PENDIENTE y condición vigente; de otro modo [].

### 6.4 POST /api/alertas/{id}/atender/

Body exacto JSON con un único campo, motivo string tras trim, longitud 1–2000, sin campos desconocidos ni datos de actor/estado/fecha. Requiere JWT válido y rol destinatario. En una transacción PostgreSQL: bloquear registro de alerta, revalidar condición de origen actual y estado PENDIENTE, guardar actor real, fecha del servidor y motivo, crear exactamente un AlertaEvento ATENCION. Responder 200 con la misma proyección de detalle y estado ATENDIDA. **Nunca** modificar el recurso propietario.

Conflictos estables con HTTP 409 y JSON code/detail:
- alerta_ya_atendida: la alerta está ATENDIDA.
- alerta_resuelta: está RESUELTA.
- alerta_desactualizada: figura abierta, pero la condición de origen ya no se verifica al atender; la reconciliación posterior la resolverá.

Un doble POST concurrente produce un único evento de atención y una respuesta 200/409 según quién ganó. No reintentar automáticamente acciones no idempotentes en el frontend.

### 6.5 GET /api/alertas/{id}/historial/

Paginación DRF de 25 por page, filtro obligatorio por rol y por alerta antes de consultar. Orden registrado_en DESC, id DESC. Schema de evento:

~~~json
{
  "id": 54,
  "alerta": 18,
  "tipo": "ATENCION",
  "estado_anterior": "PENDIENTE",
  "estado_nuevo": "ATENDIDA",
  "actor": 7,
  "motivo": "Revisión coordinada con el equipo.",
  "registrado_en": "2026-11-12T15:10:00-03:00"
}
~~~

Actor null cuando el evento lo crea el sistema. Sin snapshots de datos de negocio. No exponer el historial si la alerta no pertenece al rol.

## 7. Validación de errores y códigos HTTP

- 200 GET válido; 200 POST de atención válida.
- 400 filtros/JSON/motivo inválidos, parámetros duplicados, paginación inválida o rango >366 días.
- 401 ausencia, caducidad o revocación del JWT, usuario inactivo.
- 403 rol sin acceso al módulo, incluso OPTIONS (en el marco del permiso DRF).
- 404 alerta inexistente o perteneciente a otro rol, en detalle, atención e historial, sin filtración de existencia.
- 405 método no permitido a un actor autorizado.
- 409 conflictos de atención con code estable: alerta_ya_atendida, alerta_resuelta, alerta_desactualizada.
- 500 error interno genérico sin SQL, tokens, credenciales, datos de documentos ni tracebacks en cuerpo; logs saneados con correlación.

GET/HEAD/OPTIONS no crean alertas, actualizan flags ni ejecutan reconciliación. Respuestas autenticadas de Alertas: Cache-Control private, no-store. Mantener JWT versionado, CSRF y CORS existentes sin nuevos orígenes confiables.

## 8. Concurrencia, invariantes transaccionales y rendimiento

- Operaciones por recurso/rol con select_for_update y/o advisory locks **por clave**, respetando lock order propietario; ninguna carrera crea dos alertas activas con igual clave.
- UniqueConstraints parciales y totales en PostgreSQL; resolver colisiones con rollback y recuperación, no ignorarlas silenciosamente.
- La atención comprueba estado bajo lock y condicion actual sin transferir bloqueos hacia dominios en orden incompatible. Si no es posible revalidar sin riesgo de deadlock, detener implementación y documentar la alternativa antes de modificar el contrato.
- En reconciliación, el estado del recurso es fuente de verdad; la transición se revalida antes de resolver. Un pago registrado y después anulado puede reactivar COBRANZA_VENCIDA con nueva generación; un documento revertido lo resuelve; un turno observado resuelve el pendiente y su subsanación puede originar otro.
- La reconciliación debe ser idempotente ante reintentos, caída del proceso, dos workers y reinicios; eventos append-only, sin duplicación de CREACION/ATENCION/RESOLUCION.
- Paginación estable, filtros e índices efectivos; evitar N+1 al construir el campo obra/recurso_codigo. Agregaciones de resumen solo del rol autorizado.
- Cadencia, latencia, número de filas y plan SQL se medirán realmente; no afirmar que un proceso está desplegado por haber escrito un comando. El estado desactualizada hace visible la falta de reconciliación.

## 9. Arquitectura, migraciones y operación

Implementación contenida en apps.alertas: models, migrations, services, serializers, permissions, views, urls, tests y management/commands/reconciliar_alertas.py. Agregar include a backend/config/urls.py. Las modificaciones mínimas en servicios de Comercial/Obras/Finanzas para eventos postcommit deben justificarse y contar con pruebas de regresión por dominio. Evitar señales Django implícitas si no ofrecen transacciones y trazabilidad apropiadas.

Añadir un proceso de reconciliación en Compose o un mecanismo de scheduler equivalente, separado del servidor web y habilitado para el entorno de desarrollo **al ejecutar docker compose up -d --build**, con intervalo documentado y parada limpia. Un comando que solo funciona cuando un operador lo ejecuta manualmente NO satisface la detección automática. Documentar instalación/ejecución equivalente para producción, recuperación y observabilidad sin inventar despliegue remoto.

La migración incremental de alertas debe funcionar en base vacía y en base con Presupuestos/Obras/Finanzas existentes. Efectuar reconciliación inicial segura tras aplicar migraciones, sin alterar datos históricos. No editar migraciones ya integradas de otras apps ni reescribir operaciones de negocio existentes.

## 10. Matriz mínima de pruebas PostgreSQL y aceptación

1. Matriz exacta de los cuatro tipos; ninguna alerta sin fuente verificable, severidad fuera del catálogo ni porcentaje de avance.
2. Presupuesto pendiente → alerta G; aprobación/rechazo → RESUELTA; otros estados nunca la activan.
3. Obra suspendida → dos alertas distintas G/S; atender una no afecta otra; reanudar resuelve ambas; segunda suspensión genera nueva generación y conserva historial.
4. Turno ABIERTO → PENDIENTE_REVISION (cierre) → OBSERVADO/VALIDADO (resolver); OBSERVADO → PENDIENTE_REVISION por subsanación crea nuevo episodio.
5. Documento vigente y vencido con saldo pendiente → alerta G. Documento pagado totalmente/revertido → resuelta; anulación posterior de pago puede reactivarla; día anterior/al vencimiento no activa; utilizar exclusivamente con_cobranza.
6. Cruce de medianoche y DST America/Santiago; reconcilia sin usuario conectado; scheduler activo, salud stale/healthy, reinicio y recuperaciones.
7. Dos reconciliadores concurrentes, señalización postcommit simultánea, fallo de callback y recuperación: una sola alerta abierta y un evento por transición; no hay writes en GET.
8. Acceso por rol: G/S por su ámbito, AF/T/TI 403; JWT revocado/usuario inactivo 401; flags Django no escalan; alerta de otro rol 404 en detalle, historial y POST.
9. Body estricto, motivo vacío/con espacios >2000, campos extra, filtro duplicado, fecha invertida/rango largo, page inválida, recurso_id sin tipo, estado/tipo incorrectos → 400.
10. Atención PENDIENTE → 200 con único evento; doble petición concurrente → 200+409; ATENDIDA → alerta_ya_atendida; RESUELTA → alerta_resuelta; causa no vigente aún sin reconciliar → alerta_desactualizada.
11. Respuesta exacta y nullables de todas las rutas, sort, página 25, conteos de rol, historial append-only, generacion creciente y no fuga de montos, PII ni datos ajenos.
12. Validar migraciones desde PostgreSQL limpio con migraciones previas, manage.py check, makemigrations --check --dry-run, suite apps.alertas y suite completa, EXPLAIN/consulta bounded si es necesario; CI de backend en verde.
13. Integración HTTP/contrato con suite Postman completa para el usuario; validar además que el frontend pueda consumirlo con Bearer sin modificaciones posteriores del backend. Postman no sustituye pruebas de concurrencia real ni el scheduler.

## 11. Fuera de alcance y extensiones posteriores

No se implementan UI React, notificaciones externas, modificación administrativa de alertas, cálculo de utilidad proyectada, control porcentual de avance, creación de documentos o pagos desde Alertas, ni nuevas políticas de acceso a otros módulos. Las futuras alertas requerirán SPEC incremental. No prometer cobertura absoluta de incidentes fugaces fuera de las transiciones realmente notificadas o del estado observado por reconciliación.

## 12. Entrega e integración

1. ChatGPT mantiene esta SPEC versionada y entrega en el chat un **prompt detallado**, sin crear archivos de instrucciones para OpenCode.
2. OpenCode implementa en rama feature/backend-009-alertas desde main actualizado, sin modificar frontend, documenta cualquier incompatibilidad antes de cambiar contrato, ejecuta pruebas reales y entrega informe técnico detallado **antes de commit/push**.
3. Tras revisar ese informe, OpenCode realiza commits descriptivos, push y PR con motivación, decisiones de arquitectura, migraciones, impacto, verificación y rollback.
4. ChatGPT revisa el PR y GitHub Actions, además de la separación de responsabilidades y seguridad. Entrega una suite Postman completa importable cuando el código esté listo; el usuario la ejecuta y comunica passed/failed.
5. Corregir y revalidar si procede. Merge solo después de autorización explícita. Actualizar estado de SPEC-009 a implementada/integrada únicamente después de pruebas aprobadas y merge verificado.
6. Cada publicación de SPEC se notifica para que el usuario traiga los cambios a su PC. Este documento es especificación, no código ejecutable.

## 13. Fuentes internas verificadas

- backend/apps/alertas/ (implementación integrada), backend/config/{settings.py,urls.py}, compose.yaml.
- backend/apps/comercial/{models.py,services_presupuestos.py}.
- backend/apps/obras/{models.py,services.py,services_turnos.py}.
- backend/apps/finanzas/{models.py,consultas_cobranzas.py,services_documentos.py,services_pagos.py,validaciones.py}.
- backend/apps/usuarios/{models.py,authentication.py}; SPEC-006B/006C.
- specs/003b-gestion-presupuestos.md, specs/004-gestion-obras.md, specs/004b-costos-finalizacion.md, specs/007-finanzas-cobranzas.md, specs/008-auditoria-global-api.md.

## 14. Estado de implementación y validación de integración

- **PR de contrato:** [#28](https://github.com/LFP2002/Proyecto-FYAG/pull/28), integrado en `main`.
- **PR de implementación:** [#30](https://github.com/LFP2002/Proyecto-FYAG/pull/30), fusionado con commit `01d801490a471622924ee2444db17da1b42fe377`.
- **API implementada:** `GET /api/alertas/`, `GET /api/alertas/resumen/`, `GET /api/alertas/{id}/`, `GET /api/alertas/{id}/historial/` y `POST /api/alertas/{id}/atender/`.
- **Persistencia y operación:** dos nuevas migraciones, eventos de atención, restricciones PostgreSQL, callbacks postcommit y proceso reconciliador independiente habilitado desde Docker Compose.
- **Pruebas locales declaradas por OpenCode:** 48 pruebas de Alertas y 721 pruebas Django/PostgreSQL completas, 0 fallidas.
- **GitHub Actions:** workflow Backend CI del SHA `dab472ebb1cbd092cb88540dae269059a3919ef7` finalizado en `success`, comprobado antes del merge.
- **Postman:** el responsable confirmó **201 pruebas aprobadas y 0 fallidas** en el recorrido automático de SPEC-009. Los cuatro escenarios manuales opcionales, que requerían datos existentes de Obras, Turnos y Cobranzas, **no se ejecutaron**; su lógica dispone de pruebas Django automatizadas, pero no deben declararse comprobados manualmente.
- **Riesgos documentados:** consistencia eventual del reconciliador ante incidencias fugaces y posible desplazamiento de paginación numérica por escrituras concurrentes. No se declara una garantía de historial completo sin outbox.
- **Frontend:** la implementación de interfaces queda fuera de SPEC-009 y corresponde al equipo frontend sobre sus propias especificaciones; backend contractualmente disponible en `main`.

Este apartado registra hechos de integración, sin reemplazar el detalle de `backend/docs/SPEC-009-IMPLEMENTACION.md` ni alterar contratos, rutas o permisos.
