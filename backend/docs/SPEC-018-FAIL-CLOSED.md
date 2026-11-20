# SPEC-018 A — corrección fail-closed tras revisión técnica

Fecha: 20-11-2026. Rama `feature/backend-018-seguridad-credenciales`.
Entrega anterior: `242abcb0d40d5053dc91975f98af66498ddb98bc`.
**Hallazgo confirmado, no solo hipótesis:** la versión anterior infería PERSONAL
cuando faltaba la fila de SeguridadCredencial, tanto en lectura simple como en
relación precargada. Sus 918 pruebas no cubrían esa inconsistencia. Este informe
registra la corrección sin reescribir resultados históricos ni declarar SPEC-018
completada, seguridad productiva, despliegue o merge aprobados.

## Impacto y causa

La inferencia se introdujo para soportar creaciones internas sin estado explícito.
Si desaparecía una fila correspondiente a una contraseña temporal, un login con
esa contraseña podía atravesar la rama de sesión normal. También afectaba las
validaciones compartidas de JWT/refresh y cambio propio. Los estados no forman
parte de claims confiables: deben existir y ser coherentes en PostgreSQL.

## Cambio de autoridad y contrato

- `estado_credencial()` ya no devuelve PERSONAL por defecto. La ausencia,
  incoherencia o una relación que no corresponde a la cuenta se proyecta como
  **NO_DISPONIBLE**. No es un nuevo estado SQL ni un bloqueo escalonado.
- `estado_coherente()` comprueba enum, fechas conscientes de zona y orden temporal,
  ausencia de datos temporales en PERSONAL, integridad del grupo de campos de
  desafío, formato de digest y versión entera positiva. Defiende también frente
  a lecturas corruptas sin confiar exclusivamente en constraints de BD.
- Login devuelve el mismo 401 genérico de credenciales inválidas; no emite
  access/refresh ni desafío para un estado ausente/incoherente. JWT/refresh y cambio
  propio se deniegan con 401. El primer cambio tampoco consume ni actualiza una
  cuenta en ese estado.
- Reset TI de objetivo sin estado coherente retorna 409
  `seguridad_no_disponible`, sin generar credencial ni modificar hash/versión/eventos.
  Se retiró `get_or_create` del emisor: no reconstruye PERSONAL silenciosamente.
- Actor TI sin estado coherente no puede administrar aunque se invoque el servicio
  directamente. Documentos y Adjuntos también revalidan estado cuando no reciben
  token explícito, conservando sus matrices de roles y presupuestos SQL.
- Se añade backend Django `CredencialesModelBackend`: también deniega autenticación
  ausente/incoherente fuera de DRF. Las temporales solo se verifican para el flujo
  restringido de API; admin Django y sesiones Django requieren PERSONAL. La
  comprobación de password previa a autorización no tiene setter, por lo que una
  autenticación rechazada no reescribe automáticamente hashes antiguos.
- El backend Django de sesiones cambia de ruta de clase: sesiones Django antiguas
  pueden exigir nuevo login, sin borrar sus filas. JWT vigentes de cuentas PERSONAL
  coherentes conservan su funcionamiento y sus verificaciones de versión/hash.
- GET TI muestra NO_DISPONIBLE y `cambio_obligatorio=true` sin secretos; la futura
  UI debe indicar revisión autorizada, no prometer que primer cambio/reset reparará
  automáticamente esa inconsistencia. OpenAPI conserva nombre de archivo y sube
  versión interna a **1.1.0**.

## Migración aditiva 0007 y creaciones internas

`usuarios.0007_estado_seguridad_al_insertar` añade un trigger PostgreSQL **AFTER
INSERT** en Usuario, que inserta su fila PERSONAL dentro de la misma sentencia/
transacción. Cubre `create_user`, `create_superuser`, `objects.create`, `save` de
una fila nueva, `bulk_create`, inserciones SQL internas y el bootstrap TI.
No depende de señales ORM, tareas asíncronas ni ventanas entre commits.

El alta HTTP guarda primero un hash inutilizable y pasa a INICIAL mediante el
servicio existente, todo dentro de la misma transacción; no hay una cuenta con
contraseña temporal y estado PERSONAL visible entre esos pasos. El comando
`crear_primera_ti` conserva TTY/doble entrada oculta/mutex/auditoría y confirma
estado PERSONAL antes de aceptar el bootstrap. No permite rebootstrap de una TI
existente sin estado.

**No hay RunPython de reparación, UPDATE, DELETE ni backfill nuevo.** La migración
0006 permanece intacta y sigue creando estados PERSONAL para cuentas históricas
de su transición. 0007 no cambia sus hashes, roles, actividad, versiones, estados
ya existentes ni historial. Una ausencia anterior a 0007 queda denegada: su hash
podría ser temporal y no hay base segura para reinterpretarlo como personal.

El trigger no se ejecuta en UPDATE ni en lecturas. Guardar una cuenta existente,
un upgrade de hash o get_or_create que la encuentra no recrea su estado. Si falla
la inserción del estado de una cuenta nueva, falla también el INSERT del usuario.
Los escritores internos que crean cuentas son de confianza y deben respetar la
política de hashing y privilegios: este trigger no convierte acceso SQL arbitrario
en un canal público de alta ni protege contra un administrador de BD malicioso.

## Concurrencia y límites

Se mantienen mutex TI → usuarios por PK → seguridad; autenticación toma el lock
de Usuario antes de revalidar estado para emitir/rotar. No se añaden locks de
Obras/Finanzas ni se relajan presupuestos SQL. Las lecturas precargadas son
snapshots de la consulta actual, nunca un cache compartido entre peticiones.
Si una operación confirma antes de una inconsistencia solapada, puede responder;
sus tokens serán denegados por las peticiones posteriores que lean el estado
ausente. No se promete detener retroactivamente trabajo ya autorizado ni proteger
escrituras SQL ajenas al protocolo transaccional del proyecto.

## Pruebas y evidencia de esta corrección

QA exclusivo `fyag-spec018-failclosed-20261120`, PostgreSQL/Mongo en tmpfs, red
interna sin puertos host y ClamAV propio; runner documental existente. Secretos
de infraestructura externos, ningún acceso de pruebas a datos principales.

Nuevos casos: personal/temporal sin estado; lectura simple y relación precargada;
JWT/refresh y Django; estado incoherente sin deshabilitar constraints; reset/cambio
sin reparación; actor TI ausente; bootstrap seguro; altas internas/bulk y rollback;
migración 0006 compatible y 0007 sin reparar inconsistencias históricas. Cinco
carreras PostgreSQL observan bloqueo real con conexiones independientes: ausencia
frente a login/refresh/primer cambio/reset y tokens emitidos antes de la ausencia.

Las ausencias se simulan **solo en fixtures de la base efímera de tests**. No se
elimina ni repara información de bases de desarrollo/producción. No se instala
0007 ni se ejecutan comandos administrativos sobre servicios principales.

Resultados ejecutados de esta corrección:

- `manage.py check`: sin incidencias.
- `makemigrations --check --dry-run`: sin cambios pendientes.
- Migraciones aplicadas únicamente en el laboratorio nuevo, incluida 0007;
  `migrate --check`: OK.
- Primera ejecución dirigida: **149/149 OK en 16.609 s**. Repetición final, con
  OpenAPI 1.1.0 y su enum/error comprobados: **149/149 OK en 16.584 s**.
  Son **25 pruebas nuevas**, incluidas cinco carreras y la transición 0006 → 0007;
  también se repite el test anterior de cuentas históricas 0005 → 0006.
- OpenAPI: JSON, referencias, rutas resolubles, campos de serializers, enum
  NO_DISPONIBLE y conflicto seguridad_no_disponible verificados por tests. No se
  atribuye una validación externa de OpenAPI no ejecutada.
- Regresión backend completa: **943/943 OK en 223.381 s**, salida 0, sin fallos
  ni errores. Base de tests destruida normalmente; incluye PostgreSQL/Mongo/ClamAV,
  migraciones, concurrencia y presupuestos SQL sin relajar límites. Código/tests/
  OpenAPI cotejados con el manifiesto congelado; después solo se completa informe.
  No se reutiliza como resultado nuevo la suite histórica de 918 tests.
- Diff --check y escaneo de las 16 fuentes: sin secretos QA, claves privadas,
  JWT literales, dumps o artefactos temporales; migración 0006 y SPEC intactas.

Comandos de pruebas: `python manage.py test apps.usuarios --noinput` y
`python manage.py test --noinput`, dentro del contenedor backend del proyecto QA
exclusivo. Logs, secretos de infraestructura y manifiestos se conservan fuera de
Git en el directorio temporal aprobado `fyag-spec018-failclosed-20261120`.

## Riesgos y pendientes

- Cuentas reales sin estado deberán permanecer denegadas hasta revisión de
  procedencia y recuperación institucional expresamente autorizada. No hay una
  orden de reparación masiva segura incluida aquí; no usar crear_primera_ti como
  sustituto ni crear filas PERSONAL a ciegas.
- No revertir a una versión fail-open para recuperar disponibilidad. Preservar
  hashes/estados/eventos y revisar respaldo/restauración coordinados de PostgreSQL.
- 0007 exige permisos de migración para crear función/trigger; el runtime necesita
  poder insertar el estado dentro de la transacción. Un permiso insuficiente debe
  fallar cerrado, no omitir el trigger. No ejecutar su reverse en datos reales.
- TTL 24 h / 5 min y entrega manual entre cuentas sintéticas siguen siendo solo
  QA y NO RATIFICADOS PARA PRODUCCIÓN. Frontend, bloqueos escalonados, recuperación
  de única TI, retención de eventos, TLS confiable y despliegue siguen pendientes.
- `main`, SPEC históricas, PR #45 y confianza TLS Windows deben permanecer intactos.
