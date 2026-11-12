# SPEC-009 — Informe técnico de implementación y operación

## 1. Estado, base y alcance

Implementación en `feature/backend-009-alertas`, creada desde `origin/main` **dbcde3e** (merge del PR documental #28). Se leyó íntegramente `specs/009-alertas-backend.md` ya integrada. No se modifica esa SPEC ni frontend. El informe inicial se entregó sin commit/push/PR; después de su revisión favorable el responsable autorizó la publicación, **sin merge a main**. Ver actualización de integración en la sección 11.

API de alertas derivadas, exclusivamente con las cuatro reglas aprobadas:

| Tipo | Fuente de verdad | Destinatario | Severidad |
|---|---|---|---|
| PRESUPUESTO_PENDIENTE_GERENCIA | Presupuesto.estado=PENDIENTE_GERENCIA | Gerencia | MEDIA |
| OBRA_SUSPENDIDA | Obra.estado=SUSPENDIDA | Gerencia y Supervisor, registros independientes | ALTA |
| TURNO_PENDIENTE_REVISION | TurnoObra.estado_revision=PENDIENTE_REVISION | Supervisor | MEDIA |
| COBRANZA_VENCIDA | Documento vigente, saldo_calculado>0, estado_cobranza_calculado=VENCIDA, usando con_cobranza | Gerencia | ALTA |

No se implementan avance porcentual, costo-versus-avance, mensajería externa, nueva contabilidad, Redis/Celery ni interfaces React. Los ejemplos de documentación y fixtures son sintéticos y están identificados como tales; los endpoints solo leen registros persistidos reales.

## 2. Arquitectura y archivos

### Dentro de `backend/apps/alertas/`

| Archivo | Responsabilidad | Cambio |
|---|---|---|
| catalogo.py | Reglas cerradas: recurso, roles, severidad y textos fijos | Nuevo |
| models.py | Alerta, AlertaEvento, EstadoReconciliacion e integridad SQL/ORM | Sustituye esqueleto |
| migrations/0001_initial.py | Tablas nuevas, índices y constraints | Nuevo |
| migrations/0002_endurecer_transicion_evento.py | Impide NULL como estado anterior de atención/resolución | Nuevo |
| consultas.py | Condiciones oficiales y contexto público por lotes, sin writes | Nuevo |
| reloj.py | Hora de observación real de PostgreSQL | Nuevo |
| services.py | Locks, proyección, reconciliación, callbacks, atención y conflictos | Sustituye esqueleto |
| permissions.py | Revalidación de actividad, sesión y rol persistido | Sustituye esqueleto |
| serializers.py | Query/body estrictos, fechas civiles y proyecciones públicas | Sustituye esqueleto |
| parsers.py | JSON estricto, incluidas claves repetidas y constantes no JSON | Nuevo |
| views.py | HTTP, paginación, agregado de resumen, no-store y errores saneados | Sustituye esqueleto |
| urls.py | Cinco rutas REST | Sustituye esqueleto |
| management/__init__.py y management/commands/__init__.py | Paquetes del comando | Nuevos |
| management/commands/reconciliar_alertas.py | Ciclo individual y proceso periódico con parada limpia | Nuevo |
| tests/base.py | Fixtures sobre servicios/modelos reales, solo BD de tests | Nuevo |
| tests/test_servicios.py | Reglas, episodios, pagos, callbacks, reloj y comando | Nuevo |
| tests/test_api.py | Contrato, RBAC, validación, privacidad, GET puro y consultas | Nuevo |
| tests/test_concurrencia.py | Conexiones PostgreSQL independientes, carreras y locks | Nuevo |
| tests/test_migraciones.py | Instalación incremental con datos de negocio existentes | Nuevo |

### Fuera de Alertas

- `backend/apps/comercial/services_presupuestos.py`: notificar la PK al finalizar una transición de estado.
- `backend/apps/obras/services.py`: notificar cambios de estado de Obra desde el punto de registro de su evento.
- `backend/apps/obras/services_turnos.py`: notificar el Turno desde su registro de evento, cubriendo cierre, cierre administrativo, observación, validación, subsanación y corrección.
- `backend/apps/finanzas/services_documentos.py`: el punto común `evento()` notifica Documento directo o el documento del Pago; cubre también `services_pagos` **sin modificar ese archivo**. Cierre sin cobro no crea una cobranza ficticia.
- `backend/config/urls.py`: include `/api/alertas/`.
- `backend/config/settings.py`: intervalo de reconciliación configurable.
- `compose.yaml`: migraciones de arranque, healthcheck PostgreSQL y reconciliador separado.
- `.env.example`: intervalo opcional documentado.
- `backend/docs/openapi/SPEC-009-v1.json`: contrato OpenAPI 3.1.0, versión API 1.0.0.
- `backend/docs/SPEC-009-IMPLEMENTACION.md`: este informe.

No se cambian modelos de dominios propietarios, migraciones históricas, dependencias Python, políticas JWT/CSRF/CORS, endpoints anteriores ni las ocho fuentes de Auditoría global. El historial de Alertas permanece en su endpoint propio; no se añade implícitamente una novena fuente a SPEC-008.

## 3. Persistencia y ciclo de vida

**Alerta:** BigAutoField, tipo, rol_destinatario, recurso_tipo/recurso_id, generacion, estado, creado_en, atendida_por/en, motivo_atencion, resuelta_en y ultima_comprobacion_en. Severidad es propiedad derivada del catálogo, no columna editable; titulo y descripcion también se derivan. No se persiste contexto sensible, precios ni descripciones del negocio.

**AlertaEvento:** FK PROTECT a Alerta, tipo CREACION/ATENCION/RESOLUCION, estado anterior/nuevo, actor nullable, motivo y registrado_en. Las operaciones automáticas usan actor=null y motivo vacío. Una atención requiere actor y motivo. ORM bloquea update/delete/bulk_update/bulk_create; las instancias persistidas no admiten save/delete públicos. No hay endpoints de edición o borrado ni registro editable en admin. Esto sigue el patrón de inmutabilidad de Finanzas; no se afirma protección frente a un administrador de BD con SQL arbitrario.

**EstadoReconciliacion:** singleton id=1 con ultima_correcta_en nullable. Solo se crea/actualiza al completar un ciclo íntegro. GET no crea el singleton si falta.

Constraints:

- Correspondencia cerrada tipo/recurso/rol.
- recurso_id y generacion estrictamente positivos.
- Única generación por tipo/recurso/rol/número de episodio.
- Única alerta PENDIENTE o ATENDIDA por tipo/recurso/rol.
- PENDIENTE sin metadatos de atención o resolución.
- ATENDIDA con actor, fecha y motivo coherentes, sin resolución.
- RESUELTA con fecha coherente; conserva atención completa o ninguna, nunca parcial.
- Comprobación no anterior a creación.
- Un evento de cada transición como máximo por episodio, con estados/actor/motivo coherentes. La segunda migración endurece explícitamente NULL SQL para estados anteriores.

Flujo: condición detectada → nueva generación PENDIENTE + CREACION; acuse motivado → ATENDIDA + ATENCION; condición deja de cumplirse → RESUELTA + RESOLUCION; reaparición observada después → nueva generación incremental, sin reabrir el registro anterior.

Gerencia y Supervisor tienen alertas distintas de una Obra suspendida. Personas del mismo rol comparten el acuse; distintos roles no. La resolución de esa causa proyecta ambos roles en la misma transacción por recurso.

## 4. Concurrencia y límites de consistencia

Orden interno: advisory lock transaccional de PostgreSQL por `(tipo,recurso_id)` → filas Alerta por rol ordenado. La clave es un digest estable de 64 bits con namespace propio; una colisión extremadamente improbable solo serializaría dos claves, nunca las confundiría. Se serializan los roles del mismo recurso para resolverlos juntos, **no** todos los recursos del sistema.

La generación se obtiene bajo ese lock; los constraints respaldan la integridad. Una colisión SQL imprevista no se ignora ni se transforma en un éxito: la transacción se revierte; el comando falla el ciclo o la callback registra un error saneado, y el siguiente ciclo reevalúa la condición. Los escritores normales utilizan el mismo protocolo y no dependen de capturar colisiones como mecanismo ordinario de deduplicación.

Atender relee principal antes y después de esperar, localiza dentro de su rol, bloquea la alerta, comprueba estado y condición, registra atención/evento y confirma atómicamente. Una segunda petición produce 409 con un único evento histórico. Reconciliación y atención usan el mismo lock.

**No se adquieren locks de los propietarios después de bloquear Alertas.** Presupuesto/Obra/Documento/Pago y Turno se consultan mediante MVCC después de adquirir el lock propio. Así no se invierte el orden existente Presupuesto→Obra→Documento→Pago o Presupuesto→Obra→Turno. Una prueba mantiene los locks financieros mientras se atiende y luego confirma un pago total: la atención no bloquea al pago y el callback posterior resuelve la alerta conservando el acuse.

La condición es la última versión confirmada visible al SELECT, no una reserva sobre el origen hasta el commit. Una mutación concurrente posterior puede volver obsoleta la proyección inmediatamente; su callback o el ciclo periódico la corrige. No se promete atomicidad conjunta entre atención y modificación de un dominio propietario.

Las transiciones y salud se fechan con `clock_timestamp()` de PostgreSQL, después de esperar los locks, no con CURRENT_TIMESTAMP de inicio de transacción. Es la hora de observación del servidor de datos, no una fecha histórica inferida del negocio. Esto evita también que fixtures antiguas que adelantan y retroceden el reloj Python invaliden la cronología de Alertas. Los servidores deben mantener NTP; un retroceso real del reloj de BD puede impedir temporalmente una transición por los constraints, quedando visible como fallo recuperable.

Sin outbox duradero, una condición que aparece y desaparece entre ciclos y cuya callback se pierde puede no tener episodio histórico. Se declara este límite; no se reconstruyen incidentes sin evidencia. La API de lectura muestra contexto/acciones como observación actual, no como garantía para una escritura posterior: atender siempre revalida.

## 5. Detección automática, recuperación y despliegue efectivo

Las notificaciones se registran explícitamente con `transaction.on_commit`; capturan solo tipo y PK, no instancias con snapshots ni usuarios del negocio. La callback tiene su propia transacción y atrapa excepciones con correlación/clase, sin SQL, mensaje de excepción ni traceback. Un pago ya confirmado no se revierte ni se devuelve como fallido por un error de Alertas. Las importaciones locales evitan ciclos entre servicios.

El ciclo completo recorre candidatos activos por PK en lotes de hasta **500**, con marca máxima por recorrido; después revisa las alertas abiertas para resolver causas que dejaron de ser candidatas, incluso si el origen ya no existe. Revalida cada recurso bajo lock. No materializa históricos completos. Puede observar dos veces una clave activa en un ciclo; es idempotente y el contador examinados mide comprobaciones, no recursos distintos.

`ultima_comprobacion_en` solo se refresca para una condición activa ya conocida si transcurrieron al menos 60 segundos; no se crean eventos por esa comprobación. Un ciclo parcialmente fallido conserva las transiciones ya confirmadas, pero **no** avanza ultima_correcta_en. Un reintento recupera sin duplicarlas.

Comandos:

```sh
docker compose up -d --build
docker compose exec -T backend python manage.py reconciliar_alertas --once
docker compose logs --timestamps alertas_reconciliador
docker compose restart alertas_reconciliador
```

Compose incorpora:

1. PostgreSQL con healthcheck `pg_isready`.
2. Servicio `migraciones` que ejecuta migrate --noinput y debe terminar con código 0.
3. Web y `alertas_reconciliador` dependientes de esa aplicación exitosa.
4. Reconciliador independiente con init, restart unless-stopped y 30 s de parada limpia. Ciclo inicial inmediato y siguientes cada 60 s de inicio a inicio, sin solapamiento en un proceso. Si un ciclo dura más del intervalo, el siguiente comienza al terminar; no hay garantía de terminar en 60 s con cualquier volumen.

`FYAG_ALERTAS_INTERVALO_SEGUNDOS`: default **60**, válido 1–3600; opción `--interval` equivalente para ejecución directa. `--once` no inicia un bucle. El proceso continuo conserva el último éxito si falla, registra correlación y vuelve a intentar; SIGTERM/SIGINT detienen la espera y dejan terminar el ciclo actual. Si se supera el grace period, Docker puede interrumpirlo: transacciones cortas y reintentos garantizan recuperación, no una parada instantánea de ciclos arbitrariamente largos.

Salud pública: ultima_correcta_en nullable; desactualizada=true si no hay éxito o tiene **más de 180 s**, incluso si se configura un intervalo distinto. Las callbacks rápidas no simulan un ciclo completo ni actualizan ese indicador.

### Evidencia local real

- Se ejecutó `docker compose up -d --build`: imágenes construidas, PostgreSQL healthy, migraciones aplicadas y worker iniciado sin petición HTTP ni usuario conectado.
- Logs del worker: ciclos exitosos a **19:09:32Z, 19:10:32Z y 19:11:32Z** del 12-11-2026, cadencia observada de aproximadamente 60 s.
- Base local sin condiciones activas durante esa comprobación: examinados=0, transiciones=0. Duraciones observadas 0.044727 s, 0.020211 s y 0.016924 s; **no son benchmarks con volumen**.
- Comando individual real: éxito, 0.028065 s, sin condiciones activas.
- Parada con `docker compose stop alertas_reconciliador`: inspección **exit=0, oom=false**; posteriormente se inició de nuevo. Tras reinicio, nuevos éxitos a 19:12:24Z, 19:13:24Z, 19:14:24Z y 19:15:24Z, sin intervención HTTP.
- Lectura real posterior de EstadoReconciliacion: ultima_correcta_en=2026-11-12T19:15:24.208999+00:00 y desactualizada=False.
- Las condiciones de los cuatro tipos, vencimientos y carreras se ejercitan en PostgreSQL temporal de tests, no se añaden fixtures a la BD de desarrollo para justificar estos logs.

Producción: aplicar migraciones como paso controlado de despliegue antes de iniciar web/worker, ejecutar el mismo comando con supervisor externo (systemd, servicio de contenedores o scheduler equivalente), reinicio, logs saneados y monitoreo de desactualizada. No se ha desplegado ni probado una infraestructura productiva remota. MongoDB preexistente queda intacto, pero Alertas no lo utiliza ni depende de él.

## 6. Contrato REST y seguridad

| Método | Ruta | Contrato |
|---|---|---|
| GET | /api/alertas/ | count/next/previous/results, página fija 25, creado_en DESC/id DESC |
| GET | /api/alertas/resumen/ | generado_en, zona_horaria, por_estado, activas, por_tipo, sincronizacion |
| GET | /api/alertas/{id}/ | Misma proyección del listado |
| GET | /api/alertas/{id}/historial/ | Página fija 25, registrado_en DESC/id DESC |
| POST | /api/alertas/{id}/atender/ | JSON exacto motivo string, trim, 1–2000; devuelve detalle actualizado |

Listado acepta solo estado/tipo/recurso_tipo/recurso_id/desde/hasta/page. Estado omitido: PENDIENTE+ATENDIDA; TODAS incluye histórico. recurso_id exige recurso_tipo. Fechas juntas, formato YYYY-MM-DD, máximo 366 días inclusivos, Santiago; SQL usa inicio civil del día siguiente y no suma 86400 s. Historial solo page; detalle, resumen y atención sin query. No existe parámetro rol arbitrario ni limit/page_size.

Page e IDs son decimales positivos hasta BigInt firmado; inválidos o page fuera de rango producen 400, incluido last. Se rechazan duplicados de query, JSON con claves repetidas, datos no objeto, tipos coercibles de motivo, claves extra, NaN y JSON malformado. Content-Type de atención debe ser application/json (otros: 415).

Proyección Alerta: id, tipo, estado, severidad, rol_destinatario, recurso_tipo, recurso_id, recurso_codigo, obra, titulo, descripcion, creado_en, atendida_por, atendida_en, motivo_atencion, resuelta_en, acciones_permitidas. No se expone generacion como entrada ni parámetro editable.

- Código de presupuesto/obra con el formato real del dominio (`PRE-000001`, `OB-000001`); documento: folio externo solo para Gerencia; turno: null.
- Contexto obra por relación real; presupuesto sin Obra: null. Contexto ausente: null, no nombres ni relaciones inventadas.
- Textos del servidor fijos; nada de descripciones libres de origen, importes, cliente, evidencia o datos bancarios.
- Acciones [ATENDER] solo PENDIENTE con condición vigente; en otro caso [].
- Historial: id, alerta, tipo, estado_anterior, estado_nuevo, actor, motivo, registrado_en. Sistema actor=null; sin snapshots.
- Fechas JSON con offset de America/Santiago; timestamps nulos como null, no cadenas vacías.

La autenticación sigue usando VersionedJWTAuthentication existente. Revalidación de is_active/rol/sesion_version persistidos en todas las rutas; también después de cualquier espera de atención. Sin bypass por is_staff, is_superuser, grupos o claims. Permisos G/S solamente. AF/T/TI reciben 403, también OPTIONS. Detalle, historial, atención y OPTIONS con ID ajeno devuelven 404 indistinguible del inexistente.

Todos los resultados del módulo usan Cache-Control private, no-store. GET/HEAD/OPTIONS no crean registros, actualizan salud o reconcilian. HEAD de rutas GET no tiene cuerpo. No hay PUT/PATCH/DELETE, POST de resolución, endpoint público del scheduler ni CRUD genérico; métodos no permitidos devuelven 405 para actores autorizados.

Errores: 400 validación; 401 JWT ausente/expirado/revocado o usuario inactivo; 403 rol sin acceso; 404 alerta ajena/inexistente; 405 método; 409 code/detail; 500 genérico con correlacion UUID y X-Correlation-ID. Logger propio solo guarda clase/correlación, sin SQL, str(exc), traceback, Authorization, cookies ni cuerpo.

Conflictos exactos:

| code | detail |
|---|---|
| alerta_ya_atendida | La alerta ya fue atendida. |
| alerta_resuelta | La alerta está resuelta. |
| alerta_desactualizada | La condición de origen ya no está vigente. |

Motivo de atención es contenido del operador autorizado: no introducir secretos en él. La minimización de campos no equivale a un clasificador DLP de texto libre. No se expone nombre/correo del actor; solo su ID autorizado en esa bandeja/historial.

### Ejemplos de estructura (sintéticos, no respuestas programadas)

```http
GET /api/alertas/?tipo=OBRA_SUSPENDIDA&page=1
Authorization: Bearer <access_token_existente>
```

```json
{
  "count": 1, "next": null, "previous": null,
  "results": [{
    "id": 18, "tipo": "OBRA_SUSPENDIDA", "estado": "PENDIENTE", "severidad": "ALTA",
    "rol_destinatario": "GERENCIA", "recurso_tipo": "OBRA", "recurso_id": 12,
    "recurso_codigo": "OB-000012", "obra": 12,
    "titulo": "Obra suspendida", "descripcion": "La obra se encuentra suspendida.",
    "creado_en": "2026-11-12T15:30:00-03:00", "atendida_por": null,
    "atendida_en": null, "motivo_atencion": null, "resuelta_en": null,
    "acciones_permitidas": ["ATENDER"]
  }]
}
```

```http
POST /api/alertas/18/atender/
Authorization: Bearer <access_token_existente>
Content-Type: application/json

{"motivo":"Revisión coordinada con el equipo."}
```

El frontend sigue next/previous y muestra acciones suministradas; no evalúa saldos, roles o condiciones ni fusiona fuentes. Debe tratar 409 como actualización de estado, no reintentar automáticamente una atención.

## 7. Pruebas y resultados reales

PostgreSQL real en Docker, sin SQLite. Las suites se ejecutan secuencialmente para no compartir simultáneamente la BD test_fyag_db; el worker separado apunta a la BD de desarrollo y nunca a la BD de tests.

| Validación | Resultado |
|---|---|
| docker compose config --quiet | Correcto |
| manage.py check | Sin problemas (0 silenced) |
| makemigrations --check --dry-run | No changes detected |
| migrate --plan | No planned migration operations |
| migrate --noinput | 0001 y 0002 de Alertas aplicadas correctamente en desarrollo |
| test apps.alertas --noinput | **48 aprobadas, 0 fallidas, 8.766 s** |
| Alertas + concurrencia financiera existente | 53 aprobadas, 0 fallidas, 11.641 s (antes del endurecimiento final NULL SQL; validación final en filas siguientes) |
| test --noinput | **Regresión final: 721 aprobadas, 0 fallidas, 142.100 s**, sin errores de callbacks; primera regresión: 715 aprobadas, 153.239 s |
| git diff --check | Sin errores de whitespace; solo advertencias LF/CRLF de Git en Windows |

Cobertura: cuatro tipos, resolución y reaparición, independencia de roles, acuse compartido por cuentas de mismo rol, append-only, restricciones SQL (incluido NULL), rollback del evento, callbacks diferidos/fallidos/descartados, ciclo parcial y recuperación, comando once y bucle con fallo/parada, pagos parciales/totales, anulación y reversión, turnos cierre/observación/subsanación/validación/corrección, vencimiento local y días de 23/25 h, identidad/sesión/roles/claims/flags, privacidad, validación JSON/query, HTTP 400/401/403/404/405/409/500, GET/HEAD/OPTIONS sin writes, empates/páginas y salud stale/healthy.

Concurrencia con conexiones independientes: dos creadores, dos reconciliadores completos, doble POST 200+409, atención vs reconciliación, relectura después del lock, resolución simultánea, recursos distintos sin mutex global, revocación durante espera y locks de pago vs atención. Se observan bloqueos PostgreSQL reales mediante pg_blocking_pids y barreras, no sleeps para fingir carreras.

Migraciones: creación de BD temporal aplica el grafo desde cero. Test dedicado retira solo el esquema Alertas en esa BD temporal, conserva Presupuestos/Obras/Documento existentes, aplica ambas migraciones y compara filas antes/después; reconciliación no modifica los propietarios. No se retrocede esquema ni se eliminan datos en desarrollo para esa prueba.

Rendimiento: prueba de 31 alertas de Gerencia, 25 por página, consultas de primera página **≤8** para dos tipos, sin consultas por cada resultado. Contexto se consulta por tipo y lote (como máximo dos consultas por tipo presente). Resumen agrega por tipo/estado en SQL y consulta la salud, sin visitar cada recurso. Índices de Alertas soportan rol/fecha y rol/estado/fecha; historial tiene alerta/fecha/PK. Los tipos/recurso/generación tienen índices de unicidad. EXPLAIN real del listado activo de Gerencia en la BD local sin alertas eligió Index Scan sobre alerta_rol_fecha_idx (coste estimado 0.14..8.16, rows=1); no se ejecutó ANALYZE ni se interpreta ese plan de base vacía como evidencia de producción. No se presume que cualquier filtro o la subconsulta financiera sea barato con gran volumen: faltan mediciones de producción para justificar nuevos índices propietarios o batch SQL adicional.

Incidencias corregidas durante desarrollo: fixtures con Decimal obligatorio y cronología incompleta, inicio de Turno sobre Obra suspendida y cierre de conexión al invocar el comando dentro de TestCase. La primera regresión aprobó pero reveló callbacks rechazadas por el reloj Python simulado de fixtures de dominios existentes; se diagnosticó únicamente el nombre del constraint, sin imprimir snapshots, y se centralizó la fecha de observación en PostgreSQL. La regresión final de 721 pruebas ya valida esa solución y el endurecimiento NULL SQL, sin errores de callbacks. Persisten únicamente los avisos preexistentes de las pruebas de JWT que deliberadamente generan tokens para usuarios inactivos.

OpenAPI: pruebas comprueban rutas, catálogo, campos y resolución de referencias locales. No se afirma validación por una herramienta OpenAPI externa no ejecutada. **GitHub Actions remoto, Postman y revisión externa no se han ejecutado ni se declaran aprobados.**

## 8. Compatibilidad, riesgos y mejoras

- Los módulos originales conservan sus reglas y locks; las modificaciones son señalizaciones postcommit, no nuevos estados de negocio.
- No hay saldos alternativos: con_cobranza es la única consulta contable de detección, con filtros adicionales de vigencia/saldo positivo exigidos por SPEC.
- El cálculo de cobranza usa hoy_santiago oficial en cada evaluación. El worker vuelve a evaluarlo periódicamente, sin sumar 86400 s ni depender de actividad HTTP.
- Las callbacks son síncronas después del commit y añaden latencia pequeña por recurso; no se afirma una SLA de producción. Una caída se recupera por ciclo.
- El recorrido es acotado en memoria, pero realiza transacciones por recurso y puede resultar costoso a escala. Medir planes SQL, tamaño de backlog y duración de ciclo antes de introducir cambios de índices o proyección masiva.
- Paginación solicitada es por número, no snapshot ni cursor: inserciones concurrentes pueden desplazar elementos entre páginas. Orden total determinista no equivale a inmutabilidad de la bandeja entre requests.
- Historial está protegido en API/ORM y por constraints de forma, no mediante triggers antimanipulación de administradores SQL. Respaldos y permisos mínimos de BD siguen siendo necesarios.
- Vigencia del origen es observación confirmada, no bloqueo de la entidad durante atención. La corrección eventual es explícita y probada; no outbox ni garantía absoluta de incidentes fugaces.
- No hay desviaciones funcionales intencionales respecto de SPEC. Decisiones concretadas: severidad calculada sin columna, reloj PostgreSQL, 400 para página fuera de rango y una misma clave de proyección para ambos roles de una Obra. No amplían permisos ni alteran el contrato.

## 9. Recuperación y rollback

1. Ante worker caído o desactualizada=true, revisar logs por correlación, conectividad PostgreSQL y migraciones; ejecutar --once y reiniciar el proceso supervisado. No arreglarlo mediante GET ni borrar alertas.
2. Reintentar un ciclo es seguro; no reinicia generaciones ni duplica transiciones. Las proyecciones parciales previas se conservan y completan.
3. Para retirar la funcionalidad: detener el reconciliador, desplegar la versión anterior de código/Compose (sin hooks ni rutas de Alertas) y **conservar las tablas** para mantener historia y permitir redeploy. No ejecutar migrate alertas zero en una BD con historia.
4. Si se autoriza explícitamente un rollback destructivo de esquema, requerirá respaldo y revisión de pérdida de alertas/eventos; no es el procedimiento predeterminado ni se ha ejecutado en desarrollo.
5. No revertir migraciones de Comercial/Obras/Finanzas, ni eliminar eventos de origen o modificar pagos para corregir una proyección.

## 10. Punto de revisión

El informe inicial fue revisado favorablemente antes de cualquier commit/push/PR. El responsable autorizó después los commits, integración de main y publicación del PR. La aprobación de merge, CI remoto y Postman corresponde a la fase posterior y al responsable del proyecto; no se realiza merge a main.

## 11. Revisión prepublicación e integración de main

- Se ejecutaron git status, git diff --stat, git diff --check y git fetch origin antes de publicar. El alcance del diff contra main se limita a 30 archivos de Alertas, documentación e integraciones necesarias.
- Los cambios se protegieron en cinco commits coherentes (núcleo transaccional, detección/operación, API, documentación y pruebas), antes de integrar origin/main mediante un commit de merge sin reescribir trabajo ajeno.
- origin/main avanzó a **5e9c9c0** agregando únicamente frontend/.env. Se incorporó ese commit tal cual; el blob de frontend/.env es idéntico al de main y **no aparece en el diff del PR**. No hubo conflictos ni cambios de backend/dependencias provenientes de main.
- La SPEC contractual conserva el mismo blob **5fef4a6413519c61e4677cca3e2f248692bc57a4** que origin/main. No se modificó para ajustar la implementación.
- Revisión de secretos: sin coincidencias de patrones de claves privadas/tokens ni de credenciales locales en los archivos cambiados; los valores no se imprimieron. .env local sigue ignorado. El diff no incorpora .env locales, bases, dumps o bytecode; .env.example solo agrega la cadencia no secreta.
- Pagos: services_pagos.registrar_pago y anular_pago llaman a services_documentos.evento mediante base.evento(pago=...). Ese punto común obtiene pago.documento_id y programa la callback postcommit. Por eso services_pagos.py no requiere modificación. Las pruebas recorren el registro parcial/total, anulación, nueva generación y resolución, además de la carrera de atención con pago en curso.
- Tras integrar main: check sin problemas, makemigrations sin cambios, migrate --plan sin operaciones pendientes, Compose config correcto y nuevo docker compose up -d --build exitoso sobre PostgreSQL existente. El proceso de migraciones terminó sin operaciones nuevas y el reconciliador arrancó automáticamente.
- Reconciliaciones automáticas del nuevo arranque: 2026-11-12T19:34:35Z (0.024143 s) y 19:35:35Z (0.015712 s), confirmando nuevamente la cadencia; ejecución --once: 0.021787 s. La base local seguía sin condiciones activas; no se añadieron datos demostrativos.
- Suite Alertas posterior a integración: **48 aprobadas, 0 fallidas, 8.665 s**. Regresión completa posterior a integración: **721 aprobadas, 0 fallidas, 140.403 s**, sin errores de callbacks. Solo aparecen los avisos preexistentes de tests que generan deliberadamente JWT para usuarios inactivos.
- No se identificaron incompatibilidades con el cambio de main ni problemas técnicos adicionales que requirieran alterar código de negocio. GitHub Actions remoto y Postman no se declaran aprobados por esta validación local.
