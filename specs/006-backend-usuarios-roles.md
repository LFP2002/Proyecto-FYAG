# SPEC-006 — Administración de usuarios y roles (backend)

**Estado:** definida para implementación; **no implementada**. Documento acordado el 10 de noviembre de 2026. Rama de documentación: `docs/spec-006-usuarios-roles`. Rama sugerida para implementación posterior: `feature/backend-006-usuarios-roles`.

**Precedencia y alcance:** ampliar `specs/002a-autenticacion-jwt.md` y `specs/002b-hardening-autenticacion.md` sin degradar sus contratos. Se reutiliza `apps.usuarios.Usuario` y la autenticación existente; no se modifican las reglas de Comercial, Obras, costos o aprobación. SPEC-006 es **exclusivamente backend** (Django, DRF, PostgreSQL y pruebas). No incluye frontend ni depende de MongoDB.

## 1. Punto de partida comprobado

- Django utiliza `AUTH_USER_MODEL = "usuarios.Usuario"`, heredado de `AbstractUser`, con `USERNAME_FIELD = "email"`, email único normalizado, `username` como alias y cuatro roles persistidos.
- Roles exactos: `GERENCIA`, `ADMINISTRATIVO_FINANZAS`, `SUPERVISOR_OBRAS`, `TECNICO`.
- API actual bajo `/api/auth/`: `csrf/`, `login/`, `refresh/`, `logout/` y `me/`. El access JWT se entrega en JSON; refresh JWT en cookie HttpOnly; existe CSRF, rotación/blacklist y verificación de cambio de contraseña.
- No existen actualmente endpoints DRF de CRUD de usuarios ni una política formal de administración de roles. `is_staff` y `is_superuser` son campos heredados, **no** roles FYAG.
- Las asignaciones operativas residen en PostgreSQL, especialmente `Obra.tecnico_responsable`, `ObraParticipante` y `TurnoObra`. Es indispensable preservar historial y evitar desactivar técnicos con obligaciones operativas vigentes.
- El backend ya cuenta con pruebas Django/PostgreSQL y workflow Backend CI. El frontend existente debe conservar su autenticación sin depender de esta implementación.

## 2. Objetivo y entregables

Permitir a **Gerencia** administrar cuentas internas con operaciones transaccionales, permisos estrictos, historial inmutable y revocación coherente de sesiones; permitir a cada usuario activo cambiar su propia contraseña.

Entregables:
1. API de lectura paginada, alta, edición de datos de perfil y consulta de una cuenta.
2. Acciones explícitas de activar, desactivar, cambiar rol y establecer nueva contraseña por Gerencia.
3. Endpoint autenticado de cambio de contraseña propio.
4. Invariantes de seguridad sobre última Gerencia activa, autooperaciones y técnicos vinculados a Obras.
5. Invalidación inmediata de sesiones JWT afectadas y trazabilidad en PostgreSQL.
6. Tests de contratos, permisos, concurrencia y regresión de la autenticación existente; documentación de uso.

## 3. Matriz de autorización

| Operación | GERENCIA | ADMINISTRATIVO_FINANZAS | SUPERVISOR_OBRAS | TECNICO |
| --- | --- | --- | --- | --- |
| Listar/ver otras cuentas | Sí | No | No | No |
| Crear cuentas | Sí | No | No | No |
| Editar datos de otra cuenta | Sí | No | No | No |
| Activar/desactivar | Sí, con guardias | No | No | No |
| Cambiar rol | Sí, con guardias | No | No | No |
| Establecer contraseña ajena | Sí, con guardias | No | No | No |
| Consultar historial administrativo | Sí | No | No | No |
| Cambiar **su propia** contraseña | Sí | Sí | Sí | Sí |
| Consultar perfil propio `/api/auth/me/` | Sí | Sí | Sí | Sí |

- Exigir `is_authenticated`, `is_active` y el valor **persistido** de `Usuario.rol`, sin confiar en parámetros del cliente ni en un rol embebido en JWT.
- Ningún usuario de rol distinto a `GERENCIA` adquiere privilegios de gestión por `is_superuser`, `is_staff`, Django Groups o claims introducidos por el cliente.
- No hay registro público ni administración por los roles distintos de Gerencia; el frontend nunca constituye una frontera de autorización.
- Las rutas administrativas no devuelven información de otras cuentas a usuarios sin permiso. El endpoint `me/` mantiene su contrato existente.

## 4. Modelo de datos e integridad

Reutilizar `Usuario` y sus campos actuales:
- `id` inmutable; `email` requerido y único (normalizado con trim y minúsculas); `username` requerido, alias único; `first_name` y `last_name` opcionales; `rol` exactamente uno de los cuatro valores; `is_active` booleano.
- `password` se almacena exclusivamente mediante el hashing estándar de Django y sus validadores. Nunca se persiste, devuelve ni registra una contraseña en texto plano.
- `is_staff`, `is_superuser`, `groups`, `user_permissions`, `last_login` y campos de tokens no son editables desde estas API.
- Añadir `sesion_version`: entero positivo, valor inicial 1, controlado por el servidor para invalidación explícita de credenciales; crear migración **nueva**, sin reescribir las existentes.
- Añadir `UsuarioEvento` append-only en PostgreSQL: `usuario_objetivo` (FK PROTECT), `actor` (FK PROTECT), `tipo`, `motivo`, `datos_anteriores` / `datos_nuevos` JSON restringidos y `creado_en` de servidor. Eventos de creación, edición, activación, desactivación, cambio de rol, establecimiento y cambio propio de contraseña. Los eventos de contraseña solo indican el **tipo de operación**, nunca valores, hashes, tokens ni señales que permitan reconstruir secretos.
- No exponer PUT/DELETE de `Usuario` ni endpoints para editar o borrar eventos. La baja es lógica (`is_active=False`) para conservar FKs e historial; no borrar usuarios históricos vinculados a Obras, presupuestos u otros registros.
- Toda mutación y su evento de auditoría se confirman en **una transacción PostgreSQL**; un fallo debe revertir ambos.

## 5. Contrato REST

Base: `/api/usuarios/`; añadir al enrutador de `config/urls.py` o a `apps.usuarios.urls` sin alterar las rutas `/api/auth/` existentes.

| Método y ruta | Función / entrada | Actor | Éxito |
| --- | --- | --- | --- |
| GET `/api/usuarios/` | Lista paginada; filtros opcionales `rol`, `activo=true|false`, `page` | G | 200 |
| POST `/api/usuarios/` | Alta interna | G | 201 |
| GET `/api/usuarios/{id}/` | Ficha administrativa | G | 200 |
| PATCH `/api/usuarios/{id}/` | Campos básicos de perfil | G | 200 |
| POST `/api/usuarios/{id}/activar/` | `motivo` obligatorio | G | 200 |
| POST `/api/usuarios/{id}/desactivar/` | `motivo` obligatorio | G | 200 |
| POST `/api/usuarios/{id}/cambiar-rol/` | `rol` y `motivo` obligatorios | G | 200 |
| POST `/api/usuarios/{id}/establecer-clave/` | `nueva_clave` y `motivo` obligatorios | G | 200 |
| GET `/api/usuarios/{id}/historial/` | Eventos administrativos paginados | G | 200 |
| POST `/api/auth/cambiar-clave/` | `clave_actual`, `nueva_clave` | Usuario propio activo | 204 |

**Alta:** JSON con `email`, `username`, `first_name` y `last_name` opcionales, `rol` y `password` obligatorios. Crear **inactivo por defecto**, sin aceptar `is_active` en el body; Gerencia debe activar expresamente cuando esté lista la cuenta. Las contraseñas iniciales se entregan por canal seguro fuera del sistema; no enviar por correo desde esta SPEC. No generar credenciales predefinidas ni crear cuentas de demostración en migraciones.

**PATCH perfil:** solo `email`, `username`, `first_name`, `last_name`; no acepta `rol`, `password`, `is_active` ni campos administrados por el servidor. Los cambios de email deben invalidar sesiones anteriores por ser la identidad de acceso. Un PATCH sin cambios reales retorna 200 sin evento ni cambio de fecha.

**Lectura:** proyección permitida `id`, `username`, `email`, `first_name`, `last_name`, `rol`, `is_active`, `date_joined`; nunca exponer hash, versiones internas ni permisos Django heredados. Listado paginado con 25 registros por página, orden determinista por ID, sin parámetros desconocidos o repetidos; filtro por rol del catálogo y activo con valores estrictos. Historial paginado de 25, orden estable y con snapshots filtrados.

**Activar/desactivar:** el motivo explica la decisión. Repetir una activación/desactivación en el mismo estado retorna 200 sin duplicar evento ni invalidar nuevamente sesiones; cualquier cambio efectivo incrementa la versión. La desactivación impide inmediatamente acceder y renovar tokens.

**Cambiar rol:** acción independiente y motivo obligatorio. Valor idéntico produce 409 `sin_cambios`. Cambiar a `GERENCIA` no eleva `is_staff` ni `is_superuser`. El cambio real incrementa `sesion_version` y genera evento. Se deben verificar dependencias operativas del usuario antes de alterar el rol.

**Contraseñas:** Django `validate_password` + `set_password`, nunca asignar el atributo `password` directamente. El cambio propio verifica `clave_actual`; la administración de contraseña ajena solo es para Gerencia y requiere motivo. En éxito, incrementar `sesion_version` y exigir nuevo login; no devolver contraseña, hash ni tokens. No implementar recuperación por email, enlaces mágicos ni auto-registro.

Todas las entradas de escritura usan serializers estrictos: rechazar campos desconocidos, tipos erróneos y claves administradas por servidor. Identificadores de URL deben ser enteros positivos; el actor siempre proviene de `request.user`.

## 6. Invariantes de negocio y protección

### 6.1 Última Gerencia y protección frente a acciones propias

- Debe permanecer **al menos una cuenta GERENCIA activa** en la base de datos después de cada operación.
- Bloquear desactivación o degradación de la última Gerencia activa, incluso con dos solicitudes concurrentes. Verificar contra filas bloqueadas bajo transacción, con orden de locking estable.
- No permitir que Gerencia se desactive, cambie su propio rol o establezca administrativamente su propia contraseña mediante las rutas de terceros. Para su contraseña debe utilizar la ruta de cambio propio con clave actual.
- No permitir cambiar `is_staff`, `is_superuser` ni flags heredados mediante ningún contrato; no deducir privilegios FYAG de esos flags.
- Si un administrador pierde el rol activo a través de un proceso autorizado, sus sesiones previas deben quedar revocadas antes de cualquier nueva solicitud.

### 6.2 Técnicos y Obras

- Si una cuenta `TECNICO` es responsable principal de cualquier Obra no terminal, tiene membresías activas de Obras no terminales o tiene turnos abiertos en cualquier Obra, **rechazar desactivación y cambio a otro rol con HTTP 409**, informando una descripción no sensible de las asignaciones pendientes.
- La vía correcta es primero reasignar responsable, desasignar participantes donde corresponda y cerrar turnos mediante las operaciones existentes de Obras, respetando sus guardias. Nunca modificar desde `usuarios` esas asignaciones para forzar el cambio.
- Los vínculos históricos de Obras finalizadas se conservan; no borrar ni reasignar actores en registros históricos.
- Activar un Técnico previamente inactivo o cambiar otro rol a Técnico no lo incorpora automáticamente a ninguna Obra. Sus membresías se administran exclusivamente mediante las rutas de Obras.
- Para otros roles, no borrar ni alterar objetos históricos de Comercial/Obras al desactivar. Los permisos futuros reflejan siempre el rol persistido vigente.

### 6.3 Estado de sesión coherente

La política actual usa Simple JWT, access en memoria, refresh HttpOnly, cookies protegidas y `CHECK_REVOKE_TOKEN`. Conservar todo lo anterior.

- Incorporar `sesion_version` como claim emitido por el servidor tanto en access como refresh.
- La autenticación de cualquier access compara su versión con la almacenada en `Usuario` y rechaza 401 si falta o no coincide; no confiar en el rol del token.
- El endpoint de refresh debe verificar además usuario existente, activo y versión vigente **antes de emitir otro access**. Un refresh anterior al cambio de rol, email, contraseña o estado no puede renovar la sesión.
- Incrementar atómicamente `sesion_version` en cambio efectivo de rol, email, activación/desactivación y contraseña. Mantener blacklist/rotación y el comportamiento actual de CSRF; no aceptar cookies de refresh en otros endpoints.
- El cambio de clave propio devuelve 204 y obliga a iniciar sesión nuevamente. Los tokens previos quedan inutilizables; no falsificar revocación remota ni permitir reutilización de refresh.
- Despliegue: los tokens emitidos **antes** de incorporar la nueva claim carecen de versión; deben invalidarse y los usuarios deberán volver a iniciar sesión una vez. Documentar esa transición y probarla.
- El frontend existente puede restaurar una sesión válida y reenviar al login al recibir 401; no es parte de esta SPEC agregar UI de administración. `/api/auth/me/` conserva las claves `id`, `username`, `email` y `role`.

## 7. Respuestas, errores y concurrencia

- 200/201/204 según las rutas descritas.
- 400 para validación, email o username duplicados, contraseña inválida o campos desconocidos; representar errores por campo sin secretos.
- 401 para credenciales inválidas, token expirado, desactivación o versión de sesión obsoleta.
- 403 para rol no autorizado; tampoco hay bypass por `is_superuser`.
- 404 para usuario o evento fuera del alcance; no exponer cuentas a roles ajenos.
- 405 para PUT/DELETE y métodos inexistentes.
- 409 para última Gerencia activa, autooperación protegida, técnico con dependencias operativas, cambio de rol idéntico o conflictos de estado concurrentes.
- La capa de servicios transaccionales es autoridad: usar `select_for_update` y un orden de bloqueos estable para última Gerencia / cuenta objetivo / verificaciones de dependencias. Las comprobaciones solo visuales no garantizan la integridad.
- Evitar doble escritura y dobles eventos ante concurrencia. Mantener errores claros, sin filtrar tokens, contraseñas, stack traces ni datos financieros de Obras.
- Normalizar `email` con `strip().lower()`; capturar colisiones de unicidad tanto de validación como de DB y transformarlas en errores controlados, sin ocultar otros `IntegrityError` inesperados.
- Nunca confiar en `is_active`, `rol` o `sesion_version` enviados por la interfaz.

## 8. Arquitectura recomendada

- `apps.usuarios/models.py`: campo versión y evento histórico.
- `apps.usuarios/serializers_usuarios.py`: contratos estrictos de administración (o archivo equivalente separado del login).
- `apps.usuarios/services_usuarios.py`: casos de uso transaccionales, guardias, locking y eventos.
- `apps.usuarios/permissions.py`: gestión solo Gerencia activa.
- `apps.usuarios/views_usuarios.py` y `urls.py`: vistas DRF/rutas de administración; mantener autenticación separada.
- `apps.usuarios/views.py`, `serializers.py` y/o clase de autenticación específica: soporte de versión JWT, refresh y cambio propio de clave **sin romper** login/logout/me ni CSRF.
- `apps.usuarios/migrations/`: migración incremental, sin reescribir migraciones previas.
- `apps.usuarios/tests/`: tests separados por dominio, contratos, sesiones y carreras.
- No tocar `database/`, `backend/scripts/`, MongoDB, prototipos del frontend ni otras aplicaciones salvo un ajuste justificado de enrutamiento/autenticación compartida.
- No crear un segundo modelo de usuario ni relocalizar cuentas entre bases; PostgreSQL es fuente de verdad.

## 9. Matriz mínima de pruebas

1. Gerencia crea usuario inactivo y lo activa con motivo; login inicial requiere activación.
2. Alta acepta los cuatro roles y rechaza otros; email normalizado y único; username único; contraseña hash y validadores.
3. Lista de 25/página, filtros válidos/invalidos, orden estable, detalle e historial.
4. AF, S y T reciben 403 para cada operación administrativa; superusuario con rol distinto también 403.
5. Gerencia edita campos permitidos; PATCH sin cambios no crea evento; campos bloqueados dan 400.
6. Gerencia activa/desactiva; repetición no duplica evento; el usuario inactivo recibe 401 en login, access y refresh.
7. Gerencia cambia rol; permisos de endpoints Comercial/Obras reflejan rol persistido, nunca se heredan permisos anteriores.
8. No se puede desactivar/degradar la última Gerencia activa, ni a sí misma; pruebas concurrentes independientes para dos gerentes.
9. Técnico principal, participante activo o con turno abierto no puede desactivarse ni dejar de ser técnico; después de resolución operativa autorizada sí.
10. Cambio propio de clave exige clave anterior; cambio ajeno solo Gerencia; validación de contraseña; nunca exponer secretos en JSON/historial/logs.
11. Cambio de rol/email/clave/estado revoca access y refresh previos; 401 para claim obsoleta y para token previo a nueva versión, sin bypass de validación.
12. Rotación, blacklist, CSRF, cookies HttpOnly, `/api/auth/login/`, `/me/`, `/logout/` y restauración de sesión siguen cumpliendo SPEC-002A/002B.
13. Integridad y auditoría: todo cambio efectivo crea evento, rollback si falla evento, no DELETE; doble POST no produce dos cambios.
14. Verificar creación de BD desde cero y con datos históricos reales; no alterar asociaciones de Obras/comercial.
15. Ejecutar `python manage.py check`, `python manage.py makemigrations --check --dry-run`, `python manage.py migrate --noinput`, `python manage.py test` y confirmar Backend CI verde.

Las pruebas de concurrencia deben utilizar PostgreSQL real y conexiones independientes (por ejemplo `TransactionTestCase`), no SQLite ni pausas artificiales que simulen transacciones.

## 10. Fuera de alcance

- Pantallas React de usuarios, perfiles o cambio de contraseña (frontend posterior).
- Registro público, OAuth, SSO, MFA, invitaciones por email, recuperación automática de contraseña, delegación de administración y roles adicionales.
- Eliminación física de usuarios, reasignación automática de técnicos, modificación de presupuestos/obras, turnos o costos.
- Facturación, cobranza, alertas, dashboard, reportes y auditoría global. El `UsuarioEvento` de esta SPEC es un historial administrativo local; la integración futura con auditoría general/MongoDB no es requisito ni debe duplicar escrituras en este incremento.
- Implementación de scripts MongoDB de otros colaboradores; se revisarán únicamente si afectan directamente la seguridad o los contratos de este backend.

## 11. Entrega y flujo de integración

1. Esta PR incorpora **solo la SPEC**, sin afirmar que los endpoints estén implementados ni que se ejecutó CI de backend por un cambio documental.
2. Después del merge crear `feature/backend-006-usuarios-roles` desde `main` actualizado.
3. OpenCode implementa backend y pruebas sin frontend, documenta contratos exactos y resultados reproducibles.
4. Revisar técnicamente los cambios; no hacer commit/push antes de la revisión de la implementación.
5. Commit, push, PR de código con descripción completa, Backend CI, revisión y merge.
6. Actualizar el estado documental de SPEC-006 como implementada **solo después de verificar** el PR de código y sus pruebas.

## 12. Fuentes de referencia

- `specs/001-backend-structure.md`.
- `specs/002a-autenticacion-jwt.md` y `specs/002b-hardening-autenticacion.md`.
- `backend/apps/usuarios/{models.py,views.py,serializers.py,urls.py,services.py}`.
- `backend/config/{settings.py,urls.py}`.
- `backend/apps/obras/{models.py,services.py,permissions.py}`.
- `specs/004-gestion-obras.md` y `specs/004b-costos-finalizacion.md`.
- Workflow `.github/workflows/backend-ci.yml`.
