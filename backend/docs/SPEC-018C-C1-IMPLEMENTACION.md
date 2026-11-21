# SPEC-018C — C1: persistencia y motor aislado

Fecha: 20-11-2026. Rama `feature/backend-018c-bloqueos-escalonados`.
Base auditada `b0f16faf1fd4792e82a000f3349f804074d7a7f3`.
Rectora: [SPEC-018C](../../specs/018c-bloqueos-escalonados-backend.md), junto a
[SPEC-018](../../specs/018-seguridad-credenciales-bloqueos.md) y SPEC-006B/018A.
**Solo backend. Sin merge, despliegue, usuarios institucionales ni cambios en
bases principales, frontend o módulos de negocio. C1 NO aplica bloqueos al acceso.**

## 1. Auditoría Fase 0 y dependencias

- La rama contiene Fase A `01bb982` y sus contratos. No parte de un main sin Fase A.
  El PR #46 está separado: head `feature/backend-018-seguridad-credenciales`, SHA
  `ed0d7b68cd3b7e6a3e98df4c1700e57740c6d76a`, open/Draft al auditar; body SHA256
  `5174bc319ca754ed8f19b79f9a560189a2632a61b5f62a1ec8b23e7a4059628a`.
  Main remoto observado `8f611091f3aacce53779839b10919c957c4bd44e`; main local
  `1df5da1bffa57c7fe83b4f16adb2ca6b48a71a23`. Ninguno se modifica/actualiza.
- `SeguridadCredencial` solo representa PERSONAL/INICIAL/RECUPERACION. Ausencia o
  incoherencia proyecta NO_DISPONIBLE y debe seguir fallando cerrado. No reutilizar
  esa tabla ni `is_active` para bloqueos de acceso.
- 0006 hizo backfill histórico sin cambiar hashes; 0007 genera estado de credencial
  mediante AFTER INSERT, cubriendo save/manager/bulk/SQL. Ambas quedan intactas.
- `CredencialesModelBackend` exige contexto POST resuelto a LoginView para claves
  temporales; personales admiten request ausente. No registra errores de contraseña.
- `LoginSerializer` vuelve a comprobar usuario, hash y credencial bajo lock del
  usuario; temporal emite desafío y personal JWT. No cambiarlo en C1. Para C2,
  evitar hashing costoso innecesario dentro de locks y revalidar hash/versión tras
  una verificación fuera de lock antes de contar; una señal antigua no es prueba.
- JWT y refresh revalidan actividad, versión, hash y estado PERSONAL. Refresh usa
  lock Usuario y blacklist para serializar rotación. Ninguno consulta EstadoAcceso
  en C1, aunque una simulación alcance REQUIERE_TI. Esto es deliberado, no bypass
  de una protección ya desplegada: **esa protección aún no está integrada**.
- TI usa mutex advisory 6006006 → usuarios por PK ascendente → credencial. Reset
  reemite temporal y revoca sesiones/desafíos sin activar ni reparar ausencias.
  C1 no modifica esos servicios ni su auditoría `UsuarioEvento`, cuyo actor es
  obligatorio y debe seguir siendo una persona/cuenta real.
- Throttles IP/email usan caché, no son contador PostgreSQL de contraseñas. 429,
  CSRF, parser, inexistente, tokens o red no acreditan una contraseña incorrecta.
- Tests existentes usan PostgreSQL, conexiones separadas, barreras y observación
  `pg_blocking_pids`; se reutiliza ese arnés sin importar clases que dupliquen tests.
  Runner completo también exige Mongo QA autenticado y ClamAV separado.

## 2. Persistencia aditiva: usuarios.0008_estado_acceso_c1

`models_bloqueos.py` registra dos modelos, importados desde `models.py`:

**EstadoAcceso**, 1:1 por Usuario, independiente de credenciales/actividad:

- estado NORMAL / BLOQUEO_TEMPORAL / REQUIERE_TI;
- intentos 0–4 y array `fallos_en` de hasta cuatro timestamps pendientes;
- ventana_inicio (fallo pendiente más antiguo) y ventana_hasta (+15 min);
- bloqueo_inicio y bloqueado_hasta (null para NORMAL y para TI sin caducidad);
- `ciclos_en`: array acotado hasta cuatro inicios de ciclos, no un simple contador
  que perdería la ventana móvil; cardinalidad calcula reincidencia;
- versión positiva de concurrencia, creado_en y actualizado_en;
- timestamps PostgreSQL timestamptz. El motor rechaza reloj naive o regresivo.

**EventoAcceso**, append-only, separado de eventos administrativos:
usuario, tipo, actor_tipo SISTEMA/TITULAR, actor nullable, versión, cantidad_fallos
y creado_en. SISTEMA tiene actor null; TITULAR solo referencia al usuario objetivo.
No existe cuenta ficticia SISTEMA. No hay texto libre, JSON, email, IP, hashes,
contraseñas, prefijos, cookies, JWT o desafíos en este agregado/eventos.

Se coalescen cinco errores en el evento BLOQUEO_TEMPORAL/BLOQUEO_TI con
cantidad_fallos=5. Los primeros cuatro solo actualizan estado acotado, no generan
un evento por request. EXPIRACION y REINICIO_RACHA registran transiciones útiles;
un intento durante bloqueo no escribe ni genera nuevos eventos. No se implementan
DESBLOQUEO_TI ni CREDENCIAL_REEMITIDA aquí: son acciones futuras C2, no automáticas.

Constraints ORM/SQL: contador/array/ventana coherentes, enum, versión, reloj,
estado/plazos/ciclos coherentes y eventos por usuario/versión/tipo únicos. Un check
SQL adicional `acceso_fechas_detalladas`, no expresable con los lookups ORM usados,
valida arrays unidimensionales ordenados/sin null, longitudes, ventana exacta,
última marca <= actualizado_en, inicio de bloqueo y duración ratificada. La función
`fyag_acceso_tiempos_validos` es inmutable y se crea dentro de 0008. Los checks
adicionales SQL son deliberados, no discrepancias de estado de makemigrations.
Eventos no admiten UPDATE/DELETE en ORM ni SQL mediante trigger. Esto no pretende
impedir a un DBA cambiar esquema/TRUNCATE; requerirá privilegios mínimos operativos.

0008 crea tablas/constraints, toma lock SHARE ROW EXCLUSIVE de Usuario dentro de
la migración atómica, hace backfill NORMAL por lotes y crea un AFTER INSERT
**independiente** de 0007. El lock evita huecos de altas entre backfill y trigger;
puede bloquear altas durante migración: programar ventana antes de operar.
Los dos triggers confirman o revierten con el INSERT, también para bulk_create.
El backfill no toca Usuario, credenciales, historial, tokens, sesiones ni Obras.
NORMAL no vuelve operativa una credencial NO_DISPONIBLE: no se crea su fila faltante.

Reverse existe para fixtures QA y revierte triggers/funciones/tablas de C1. Es
destructivo para evidencia C1: **no ejecutarlo en datos reales** ni hacer un reverse
de 0006/0007 como recuperación. Plan operacional: respaldar/restaurar coordinadamente
y corrección roll-forward, preservando estados/eventos. Ningún downgrade productivo
está autorizado por esta entrega.

## 3. Política y fronteras técnicas explícitas

Umbrales ratificados, **no pendientes de ratificación**: cinco fallos/15 min;
bloqueos 15/60/240 min; cuarto ciclo en 24 h → REQUIERE_TI.

Interpretación técnica C1, documentada para revisión C2:

1. En instante servidor t se conservan fallos en **(t−15 min, t]** y ciclos en
   **(t−24 h, t]**. Exactamente en el límite izquierdo expiran. Es ventana móvil,
   no ventana fija desde primer error ni reinicio a medianoche.
2. Fallos 1–4 actualizan racha. El quinto consume el grupo, añade un inicio de ciclo
   y calcula duración por ciclos vigentes. Intentos pendientes quedan en cero.
3. En bloqueo temporal, antes de su vencimiento, aciertos/fallos/revisiones no
   alteran estado, versión, plazo o eventos. No prolongan el bloqueo.
4. **t >= bloqueado_hasta** permite transición explícita a NORMAL, registra
   EXPIRACION y permite contar el siguiente fallo. No necesita cron ni workers
   con memoria; la fila puede seguir materializada como temporal hasta evaluación.
5. Un acierto comprobado fuera de bloqueo vacía solo racha; preserva ciclos vigentes
   y evidencia histórica. Una racha caducada no produce un evento por cada error viejo.
6. La reincidencia se calcula por cada inicio de ciclo en 24 h móviles. Cuando
   expiran ciclos antiguos, la siguiente duración usa los ciclos restantes + uno.
7. REQUIERE_TI no caduca ni lo libera un acierto, cambio de reloj, revisión o
   transcurso de 24 h. Se conservan cuatro marcas de evidencia del disparo; solo
   una futura recuperación autorizada C2 podrá limpiarlo. No hay liberación TI C1.
8. Reloj UTC aware del servidor; el calculador normaliza entradas aware a UTC
   antes de operar para no sumar minutos de pared durante el cambio DST chileno.
   Una prueba cruza el fin de DST y exige 900 segundos absolutos. UI futura puede
   formatear America/Santiago sin recalcular autorización. El motor no recibe
   reloj ni contraseña del HTTP.

`politica_bloqueos.py`: calculador puro con dataclasses inmutables y señal tipada
CLAVE_INCORRECTA / CLAVE_CORRECTA / REVISAR_VENCIMIENTO / SIN_VERIFICACION.
La última es no-op incluso para housekeeping; no representar errores HTTP como
CLAVE_INCORRECTA. No recibir ni almacenar el valor de contraseña fallida.

Configuración central en settings: `BLOQUEOS_C1_POLITICA`, validada por system
check `usuarios.E018` y al invocar servicio. Debe coincidir exactamente en valores
y tipos con la política ratificada, incluido tuple de duraciones. Esta versión
de constraints fija umbrales: cambiarlos exige revisión/migración, no editar env.
Configuración ausente/inválida falla check y servicio, no usa fallback débil.

**`BLOQUEOS_C1_SIMULACION_HABILITADA=False` por defecto**, sin lectura de env que
pueda habilitar operación silenciosamente. Tests usan override_settings explícito.
Sin habilitación el adaptador rechaza escrituras antes de consultar SQL. El motor
puro calcula políticas, no toca cuentas. La habilitación no conecta endpoints.

## 4. Transacciones y concurrencia

`bloqueos.registrar_verificacion(usuario_id, senal)` es servicio interno de
simulación; no API ni prueba de identidad. No llamarlo con valores del cliente.
Inexistente retorna sin crear estado; SIN_VERIFICACION retorna sin consultar filas.
Para señal válida: atomic → lock Usuario → lock SeguridadCredencial → lock
EstadoAcceso → reloj servidor tras esperar locks → cálculo puro → persistencia y
eventos → commit. No toma mutex TI ni locks de negocio ni llama servicios externos,
hashing o emisión JWT dentro de su transacción. Debe llamarse en C2 respetando el
orden completo, nunca tomando el mutex administrativo después del usuario.

La fila Usuario serializa incrementos y umbral incluso con múltiples conexiones.
Segundo quinto intento ve bloqueo confirmado y no duplica ciclo/evento. Versión
propia de acceso no modifica sesion_version; no hay revocación operativa C1.
Unique de evento refuerza no duplicación. Fallo de evento/constraint o rollback
externo revierte contador, estado y evidencia conjuntamente. Versión agotada,
estado ausente/incoherente o credencial NO_DISPONIBLE rechazan sin reparación.
No reintentos automáticos ni I/O externo bajo lock. No memoria de worker como verdad.

Persistencia se verifica cerrando/reabriendo conexión, con transacciones realmente
simultáneas (no SQLite ni mocks de locks) y con dos intérpretes Python nuevos que
confirman incrementos sobre la misma BD `test_` efímera. Ningún contador depende
de memoria del proceso. No se atribuye un reinicio real del contenedor PostgreSQL,
cuyos datos QA son tmpfs.

## 5. QA y evidencia

Laboratorio nuevo `fyag-spec018c-c1-20261120`, standalone compose.premerge-qa.yaml,
PostgreSQL/Mongo tmpfs, ClamAV dedicado, red interna sin puertos host, bind backend
readonly. Secretos/manifiestos fuera de Git en temporal aprobado de OpenCode.
Solo cuentas sintéticas @example.test en bases efímeras de tests.

Primera ejecución dirigida encontró validación Django de actor nullable que
rechazaba SISTEMA sin actor. Se corrigió con blank=True, sin cuenta ficticia.
También se corrigió import de clase TestCase que duplicaba pruebas existentes.
Un mock de throttle se completó con wait() para representar correctamente 429;
no se alteró el throttle productivo. Usuarios pasó inicialmente 193 pruebas en
21.754 s; después se añadió normalización/prueba DST. Ese resultado no se presenta
como evidencia final de la versión posterior. La suite global iniciada antes de
este último ajuste se repitió con hashes finales congelados.
La ejecución global previa pasó **987 pruebas en 226.310 s**, pero importó el
código anterior al ajuste DST; no se usa como evidencia final. El calculador
actualizado pasó sus 13 pruebas puras, incluida DST, en 0.002 s.

Verificaciones sobre la versión final congelada (317 archivos Python/JSON):

- `python manage.py check`: 0 incidencias.
- `python manage.py makemigrations --check --dry-run`: sin cambios.
- `python manage.py migrate --noinput`: todas aplicadas solo al QA nuevo;
  `python manage.py migrate --check`: salida 0.
- Usuarios final: **194/194 OK en 21.832 s**, incluye 36 pruebas nuevas respecto
  de las 158 de la base; nueve tests de contexto/consumo de Fase A intactos.
- Regresión backend final: **988/988 OK en 230.626 s**, sin fallos ni errores,
  salida 0 y BD de tests destruida normalmente. Incluye concurrencia PostgreSQL,
  Mongo/ClamAV QA, migraciones y regresión completa de autenticación y negocio.
  Los 317 archivos Python/JSON cotejados con manifiesto final conservaron hashes
  durante ambas ejecuciones finales; después solo se completa este informe.
- OpenAPI vigente 3.0.3 y propuesta futura 3.1.0 validan con
  openapi-spec-validator 0.7.2 instalado en temporal externo, sin cambiar
  dependencias del proyecto. `paths` futuro vacío, contrato HTTP vigente intacto.
- Diff check y escaneo de los 15 archivos: sin secretos QA, tokens GitHub,
  JWT literales o claves privadas; no equivale a garantía absoluta de ausencia.
- 101 archivos frontend cotejados por SHA256 con manifiesto inicial, sin cambios
  ni añadidos. Migraciones históricas, SPEC y reglas de negocio intactas.

Archivos de la entrega (todos bajo `backend/`):

- `apps/usuarios/models.py`, `models_bloqueos.py`: registro/modelos independientes.
- `apps/usuarios/politica_bloqueos.py`, `bloqueos.py`: calculador y adaptador SQL.
- `apps/usuarios/apps.py`, `checks_bloqueos.py`, `config/settings.py`: configuración
  validada y simulación deshabilitada de forma predeterminada.
- `apps/usuarios/migrations/0008_estado_acceso_c1.py`: única migración nueva.
- `apps/usuarios/tests/test_politica_018c.py` (13), `test_bloqueos_018c.py` (17),
  `test_concurrencia_018c.py` (5), `test_migracion_018c.py` (1): **36 tests nuevos**.
- `docs/SPEC-018C-C1-IMPLEMENTACION.md`, `docs/SPEC-018C-C2-CONTRATO-FUTURO.md`,
  `docs/openapi/SPEC-018C-C2-propuesta.json`: informe/plan y diseño API futuro.

## 6. Riesgos y siguiente fase

No usar C1 para anunciar seguridad operativa: **login/JWT/refresh/primer cambio/
reset TI todavía ignoran este estado por diseño** y no exponen campos nuevos.
El contrato API vigente Fase A permanece intacto. No se implementó React ni hubo
tests/build frontend. No se ejecutó Postman ni QA navegador para C1 sin endpoints.

Decisiones pendientes antes de C2: recuperación excepcional de única TI (sin
rebootstrap), defensa frente a bloqueo malicioso de terceros, 401 frente a 423 y
Retry-After sin enumeración, alcance sobre sesiones ya emitidas, verificación
institucional previa a recuperación, acceso/retención de eventos y carga/contención.
No habilitar transición irreversible operativa para única TI sin procedimiento.
Estado acotado no limita crecimiento histórico indefinido: retención se debe
ratificar; no se añade borrado de auditoría ni conservación infinita productiva.

Plan C2: ratificar pendientes → diseñar integración de verificación y señales
no obsoletas bajo locks → conectar todos los validadores de sesión y permisos
sin N+1 → recuperar mediante reemisión TI atómica sin activar is_active → pruebas
concurrentes bloqueo/login/refresh/desafío/reset y cinco roles → contrato OpenAPI
definitivo y colección QA con recuperación segura. Ver
[contrato futuro para frontend](SPEC-018C-C2-CONTRATO-FUTURO.md).
