# SPEC-018C C2 — diseño previo, integración y evidencia

Base: `a7fa98ec4c09b551a40b47e4e5781d6c06b3872f`.
Rama dedicada `feature/backend-018c-c2-autenticacion`. Solo backend.
Este diseño se registra **antes de modificar autenticación**. No autoriza merge,
producción, cambios en frontend, PR #46/#48 ni migraciones 0006/0007/0008.

## Auditoría y decisiones de diseño QA (Fase 0)

Referencias auditadas: SPEC-018/018C, informe C1, contrato futuro C2, contrato Fase A,
SPEC-006B y 006C. C1 aporta ventanas móviles, locks y eventos, pero está aislado.

- Django backend verifica hash fuera de transacción y LoginSerializer vuelve a
  verificar bajo lock: C2 usará una verificación sin setter fuera del lock y
  revalidará identidad/hash/versión/rol/actividad/credencial al adquirirlo. Si el
  snapshot cambió, se deniega sin contar ni reintentar hashing bajo lock.
- C2 comparte una única operación entre Django y serializer, sin doble conteo.
  La emisión JWT/desafío ocurre bajo el lock del usuario. Fallo de contraseña se
  retorna como resultado, no excepción dentro de atomic, para confirmar contador
  antes del 401. Errores SQL/emisión/eventos revierten la operación completa.
- Inexistentes realizan trabajo de hash dummy, sin crear estado ni contar. No
  existe promesa de tiempos idénticos: diferencias de DB/algoritmos/contención
  requieren medición y mitigación adicional antes de producción.
- CSRF, parser y throttles IP/email preceden verificación pública. Nunca inferir
  fallo de clave a partir de un status HTTP, JWT, refresh o excepción de servidor.
- Lock ordinario: Usuario → SeguridadCredencial → EstadoAcceso. Login de TI:
  mutex administrativo 6006006 → cuentas TI de recuperación por PK → credencial
  objetivo → acceso objetivo. No tomar mutex después del usuario. Reset conserva
  mutex → usuarios por PK → credencial → acceso, sin locks de negocio.
- Revalidaciones JWT/permisos leerán estado con precarga, sin mutaciones ni N+1.
  NO_DISPONIBLE de cualquier agregado deniega; nunca se recrea estado al autenticar.
  Una petición ya autorizada antes del commit de bloqueo no puede deshacerse por
  HTTP; lecturas posteriores y escrituras con revalidación no aceptarán el estado.

### Habilitación estricta y recuperación

Por defecto C2 deshabilitada y contratos Fase A/C1 intactos. Solo configuración
explícita QA: entorno aislado declarado, nombre DB exclusivo C2 (o su test_), host
PostgreSQL del laboratorio, dos IDs TI QA diferentes, confirmación de recuperación
manual QA y aceptación explícita del riesgo DoS. Configuración inválida deniega
check/servicio, sin fallback a seguridad débil. No se aceptará un modo producción.

Un preflight verificará dos TI sintéticas activas, personales, con estado coherente
y acceso disponible antes de habilitar las pruebas. Durante operación se mantiene
al menos una recuperadora disponible. El quinto error de una TI no puede bloquear
la última recuperadora utilizable: bajo mutex y locks se deniega sin nueva transición
si la otra TI no puede recuperarla. No es una política institucional ratificada:
es una guarda QA para no ensayar bloqueo irreversible del único TI. Tampoco se
permite desactivar/degradar las dos cuentas de recuperación configuradas en QA.
Sin procedimiento institucional aprobado **no hay activación en ambientes reales**.

### Sesiones y respuestas: alternativas antes de habilitar QA

Para temporales se consideran (a) suspender uso hasta caducar, conservando tokens,
o (b) revocar todas las sesiones mediante versión, exigiendo login nuevo incluso
tras caducar. (a) puede resucitar una sesión comprometida; (b) facilita DoS dirigido.
**Solo QA, opción explícita REVOCAR_TODAS_QA**, sin default operativo. Cada ciclo
incrementa sesion_version y limpia desafíos atómicamente; REQUIERE_TI siempre
revoca. Django ligará su hash de sesión a sesion_version cuando C2 esté habilitada.
Ninguna transición modifica is_active, rol, hash de contraseña u obligaciones.

Se implementará exclusivamente el perfil QA explícito **401_GENERICO**: misma
respuesta de login para clave incorrecta, inexistente, bloqueada o inconsistente;
sin 423 ni Retry-After de cuenta que facilite enumeración. La propuesta 423 no
se declara aprobada ni implementada; 429 de throttle conserva su contrato.

### Recuperación administrada

Solo `POST /api/usuarios/{id}/restablecer-clave/`, TI activo/persistido, sesión
personal válida, objetivo ajeno y motivo obligatorio. Reutilizar reemisión CSPRNG,
revocación y primer cambio. Limpiar acceso únicamente dentro de esa transacción
tras reemisión confirmada; nuevo evento TI inmutable y enlazado al evento REEMISION
para conservar motivo/actor sin duplicar texto libre. No desbloqueo simple ni
reutilización de contraseña anterior. Migración nueva 0009, sin tocar 0006–0008.
Activar/desactivar/rol/correo no liberan bloqueo. NO_DISPONIBLE produce conflicto
sin reparar hash/estado. Recuperación única TI institucional sigue pendiente.

## Verificación y entrega

### Implementación y hallazgos

- `autenticacion_c2.py`: verificador único C2 para serializer y Django. Una sola
  comprobación hash fuera del lock; snapshots obsoletos se rechazan sin contar.
  Un hash inutilizable/no identificado no acredita contraseña incorrecta. No se
  serializan contraseñas, entradas fallidas ni sus hashes en auditoría.
- `bloqueos.py`: núcleo bloqueado extraído para reutilizar C1 sin abrir una segunda
  operación de simulación ni invertir locks. Política pura y 0008 intactas.
- `acceso.py`, `configuracion_c2.py`: validación/lectura fail-closed y gate QA;
  precargas en JWT, listado TI y revalidaciones de Documentos/Adjuntos, sin cambiar
  sus reglas de negocio. Las últimas también validan acceso sin token explícito.
- `backends.py`, `serializers.py`, `authentication.py`, `credenciales.py`,
  `services_usuarios.py`: login, Django, refresh, primer cambio y recuperación.
- `models.py`: hash de sesión Django ligado a sesion_version solo en modo C2.
- `models_bloqueos.py`, `recuperacion_c2.py` y **0009_recuperacion_acceso_c2**:
  nueva entidad RecuperacionAcceso, actor/objetivo ajenos, versiones consecutivas,
  OneToOne a REEMISION con motivo. Trigger valida enlace, actor TI activo y
  credencial RECUPERACION; UPDATE/DELETE prohibidos en ORM/SQL. No se agrega
  texto libre ni secretos al nuevo evento. Auditoría administrativa original
  conserva motivo y revocación, sin inventar usuario SISTEMA.
  0009 también protege por trigger la REEMISION enlazada: no permite alterar su
  motivo/actor por UPDATE SQL después de crear la recuperación. No cambia filas
  históricas ni definiciones de migraciones anteriores.
- `serializers_usuarios.py`/`views_usuarios.py`: estado_acceso/bloqueado_hasta solo
  en proyección TI con C2 habilitada; no en me ni módulos de negocio.
- `throttles.py`: guard de tipo objeto evita que un JSON lista provoque `.get`
  sobre lista/500 antes del serializer. Tasas y política de throttle intactas.
- `config/settings.py`, check y comando `validar_bloqueos_c2_qa`: defaults apagados,
  precondiciones explícitas; preflight no crea/repara usuarios ni desbloquea.
- Contrato de consumo/OpenAPI real 3.1 y colección Postman opt-in; diseño futuro
  marcado histórico sin presentar 423 como implementado.

Cada ciclo revoca de forma transaccional con contador/evento. Un error de emisión,
persistencia o auditoría revierte la unidad; una respuesta perdida después de
commit no puede garantizarse revertida. No contar a partir de red/HTTP/5xx.
Credencial temporal vencida o cuenta inactiva se deniegan sin contar en C2 QA.
No hay almacenamiento permanente del resultado/snapshot de verificación.

Desactivar el gate no es recuperación y retira controles deliberadamente; no se
autoriza como rollback de seguridad. En particular cambia el hash de sesión
Django respecto de la etapa previa. Preservar versionado/eventos y recuperar con
reemisión TI; respaldo y roll-forward antes de cambios de esquema. El reverse de
0009 existe para QA, elimina evidencia C2 y **no se ejecuta en datos reales**.

### Laboratorio y evidencia real

Proyecto nuevo **fyag-spec018c-c2-20261120**, standalone con override externo que
solo establece DB exclusiva **fyag_spec018c_c2_qa**. Red interna sin puertos host,
PostgreSQL/Mongo tmpfs, ClamAV propio, backend bind readonly. Nunca compose
principal ni DB principal. Secrets/manifiestos fuera de Git en temporal aprobado.
Dos cuentas exclusivamente sintéticas @example.test con claves CSPRNG no
exportadas se usaron para el preflight en la DB QA; las pruebas usan test_ aparte.

- Migraciones aplicadas solo a QA nueva, incluida 0009; check y makemigrations
  --check --dry-run sin incidencias/cambios; migrate --check se comprueba al cierre.
- Check con C2 por defecto apagada: 0 incidencias. Check mediante `docker exec -e`
  con todos los flags QA explícitos: 0 incidencias. El comando real
  `validar_bloqueos_c2_qa` confirmó ambas recuperadoras sintéticas.
- Primeros 34 tests C2 dirigidos: **34/34 OK en 3.565 s**. Después se añadieron
  pruebas del contrato, 429 real y hash inutilizable; no se recicla ese resultado
  como evidencia final. Ejecución intermedia Usuarios: 231 OK/29.101 s, anterior
  al último caso de hash inutilizable, por lo que también se repite.
- Usuarios intermedio: **232/232 OK en 28.813 s**. La revisión posterior añadió
  exclusión de hashes inutilizables de las recuperadoras QA y una prueba de la
  guarda, para no tratar una cuenta PERSONAL sin clave utilizable como recuperación.
  Se repiten suites completas con ese ajuste; el resultado anterior no se atribuye
  a la versión posterior. Los ciclos usan reloj controlado, no espera de horas.
  La regresión global intermedia pasó 1026/1026 en 266.009 s, pero había importado
  la versión anterior al refuerzo de recuperadoras: se repite también, sin
  presentarla como evidencia final de la revisión posterior.
- Usuarios final de publicación: **233/233 OK en 28.315 s**, **39 pruebas nuevas**
  respecto de C1, con refuerzo de hashes recuperadores y protección SQL de la
  REEMISION enlazada. La migración 0009 final se reaplicó únicamente en la DB QA
  dedicada, comprobando antes que no había evidencia C2 que eliminar y cotejando
  usuarios/credenciales/acceso antes/después. Ninguna DB principal fue tocada.
- Regresión backend final de publicación: **1027/1027 OK en 257.853 s**, salida 0,
  sin fallos ni errores y BD de tests destruida normalmente. Incluye PostgreSQL,
  Mongo/ClamAV QA, migraciones, concurrencia y presupuestos SQL de regresión.
  Los 330 archivos Python/JSON cotejados con el manifiesto de publicación no
  cambiaron durante las ejecuciones finales; después solo se completó este informe.
- OpenAPI C2 3.1.0 y colección conforme a schema oficial Postman v2.1, validados
  con openapi-spec-validator 0.7.2/jsonschema en temporal externo; sin dependencias
  nuevas en el proyecto. Ambos scripts compilan con AsyncFunction de Node.
  Mock Node ejecutó los 20 pasos de scripts, limpieza final, escape de contraseñas
  JSON y cuatro rechazos de destino/delay; no hace HTTP ni ejecuta Runner.
- No se ejecutó Postman Runner ni navegador real. Tests HTTP Django con CSRF,
  validación estática y mocks de script no se presentan como esas verificaciones.
- No se modificó frontend ni se ejecutaron sus tests/build por restricción expresa.
- Manifiesto final de **330 archivos Python/JSON** (runtime, pruebas, migraciones,
  OpenAPI y colección) congelado antes de verificaciones finales; frontend conserva
  **101 archivos** cotejados por SHA256. Escaneo de **31 archivos** de entrega sin
  secretos QA, tokens GitHub, JWT literales o claves privadas. No garantía absoluta.
- Migraciones 0006–0008, SPEC y reglas de Finanzas/Comercial/Obras sin diff.
  Documentos/Adjuntos solo reciben revalidación compartida de acceso, no cambios RBAC.
- PR #46: head ed0d7b68cd3b7e6a3e98df4c1700e57740c6d76a, body SHA256
  5174bc319ca754ed8f19b79f9a560189a2632a61b5f62a1ec8b23e7a4059628a.
  PR #48: head a7fa98ec4c09b551a40b47e4e5781d6c06b3872f, body SHA256
  00b2500cc9d3005f6fac6b0da4ed410c1b66db5b2a0b1c8c7669e57884671573.
  Ambos open/Draft observados, sin edición. Main local 1df5da1bffa57c7fe83b4f16adb2ca6b48a71a23
  y remoto 8f611091f3aacce53779839b10919c957c4bd44e permanecen separados e intactos.

Archivos de pruebas nuevos: `c2_helpers.py`, `test_autenticacion_018c_c2.py`,
`test_concurrencia_018c_c2.py`, `test_migracion_018c_c2.py`, `test_contrato_018c_c2.py`.
Incluyen casos positivos/negativos, los cuatro ciclos con reloj controlado,
expiración, cinco roles, CSRF/JSON/429 real, estado ausente, hash/snapshot obsoleto,
DoS dirigido, última recuperadora, sesiones Django/JWT/refresh/desafío, reemisión,
rollback y carreras PostgreSQL observadas con conexiones distintas. No se relajan
pruebas anteriores ni presupuestos de consultas existentes.

## Límites y pendientes operativos

La denegación dirigida por un tercero sigue siendo un riesgo demostrado: los
throttles no son una solución completa, especialmente con IP distribuidas.
Tiempo de hash dummy no prueba indistinguibilidad estadística bajo contención.
No se aprueba política institucional para bloquear/recuperar única TI, ni 423,
sesiones temporales productivas, retención, carga, TLS o despliegue. El nuevo
endpoint de desbloqueo simple **no existe**; no hay bypass Gerencia/bootstrap.
La guarda QA de última recuperadora no sustituye verificación institucional.
No declarar SPEC-018 completada hasta cerrar esas decisiones.
