# SPEC-006B — Administrador de TI

> **Registro de estado real (11-11-2026): IMPLEMENTADA E INTEGRADA EN `main` mediante [PR #24](https://github.com/LFP2002/Proyecto-FYAG/pull/24).** El documento original que sigue fue redactado antes del commit, PR y pruebas remotas; sus expresiones «no se hace commit», «CI pendiente», «Postman pendiente» o «no ejecutado» son un reporte temporal de la entrega inicial, no el estado vigente. El PR integró 26 archivos; scripts legados 004A quedaron fuera. GitHub Actions confirmó **Backend CI** y **Frontend CI** exitosos en commit `459274a9c75094761df66d25c4849baf4e312898`. Se reportaron 643 tests Django y 142 React, junto a dos recorridos Postman con cero fallos; estos últimos son evidencia manual reportada, no ejecución de GitHub Actions. La UI fue validada funcionalmente, pero su refinamiento visual queda a cargo del equipo frontend. La corrección incremental de UX tras cambiar el correo propio se desarrolla en SPEC-006C; las suites CI/QA de esa rama requieren validación independiente.


Entrega para revisión en `feature/006b-administrador-ti`. Amplía SPEC-006 conforme al requerimiento de quinto rol. La SPEC histórica no se reescribe. No se hace commit, push, PR ni merge.

## Resultado y matriz

Nuevo rol persistido: **ADMINISTRADOR_TI**. Es el único autorizado para listar, consultar, crear, editar, activar/desactivar, cambiar rol, establecer contraseña ajena y leer auditoría en `/api/usuarios/`.

| Capacidad | TI | Gerencia | AF | Supervisor | Técnico |
|---|---|---|---|---|---|
| Administrar cuentas/auditoría de Usuarios | Sí | No | No | No | No |
| Comercial, Obras y Finanzas | No | Permisos de negocio existentes | Sin cambios | Sin cambios | Sin cambios |
| Perfil y cambio de contraseña propios | Sí | Sí | Sí | Sí | Sí |

No hay privilegios por is_staff, is_superuser, grupos o claims del cliente. TI puede administrar roles de otras cuentas por diseño, pero no recibe acceso implícito al negocio. El backend sigue siendo la frontera de autorización; menú/estado React no otorgan permisos.

## Archivos

### Backend nuevos

- `backend/apps/usuarios/migrations/0005_administrador_ti.py`.
- `backend/apps/usuarios/management/__init__.py`, `management/commands/__init__.py`, `management/commands/crear_primera_ti.py`.
- `backend/apps/usuarios/tests/test_administrador_ti.py`.
- Este informe: `backend/docs/SPEC-006B-IMPLEMENTACION.md`.

### Backend modificados

- `backend/apps/usuarios/models.py`: catálogo de cinco roles y constraint ampliada.
- `permissions.py`, `views_usuarios.py`: autorización exclusiva TI, sin alterar contratos REST ni proyecciones.
- `services_usuarios.py`: actor TI, bloqueo conjunto TI/Gerencia, última TI y aprovisionamiento inicial auditado.
- `tests/test_administracion.py`, `tests/test_concurrencia_006.py`, `tests/test_dependencias_006.py`: actores de administración pasan de Gerencia a TI; se amplía catálogo, denegación y carreras. Se conservan validaciones, rollback, sesiones y dependencias operativas.
- `backend/apps/finanzas/tests/test_documentos.py`, `test_pagos.py`: únicamente fixture TI como actor autorizado del cambio administrativo que prueba revocación; las reglas financieras no cambian.
- `backend/config/settings.py`: middleware CORS optativo, lista explícita de orígenes y exposición de headers públicos para separación frontend/API; no cambia la autenticación ni las cookies.

### Frontend nuevos

- `frontend/src/usuarios/api.js`: rutas, filtros, paginación segura, proyecciones de cuentas y auditoría.
- `frontend/src/auth/config.js`: origen API opcional, HTTPS y sin credenciales/ruta/query en configuración.
- `frontend/tests/usuarios-domain.test.js`, `usuarios-ui.test.js`.

### Frontend modificados

- `frontend/src/data/constants.js`: quinto rol, notas, menú exclusivo TI, módulo inicial y matriz de cinco columnas.
- `frontend/src/app.jsx`: montaje real de Usuarios únicamente para TI.
- `frontend/src/pages/Usuarios.jsx`: reemplaza el prototipo por integración HTTP real.
- `frontend/src/auth/client.js`: reconoce TI, permite origen API explícito con credentials include, conserva access/CSRF en memoria, sanea errores públicos de Usuarios.
- `frontend/src/comercial/api.js`: verificación de enlaces de paginación contra el origen API configurado; compartida también por Obras y Usuarios. No sigue enlaces remotos arbitrarios.
- `frontend/tests/frontend-contract.test.js`: sustituye los supuestos históricos de cuatro roles y Usuarios sin integrar por el nuevo contrato, sin retirar las pruebas de sesión ni navegación.

No se modifican migraciones anteriores, reglas de Comercial/Obras/Finanzas, MongoDB, `database/`, scripts ajenos, dependencias ni archivos de entorno. `backend/scripts/` ya estaba sin seguimiento y queda intacto/fuera del ZIP.

## Backend: integridad y transición

### Migración

`usuarios.0005_administrador_ti` reemplaza la constraint `usuarios_rol_valido` y amplía choices conservando max_length=30. No cambia IDs, hashes, nombres, roles existentes, actividad, versiones ni asociaciones; no crea ni promueve cuentas. La prueba incremental 0004 → 0005 preserva usuarios y la asignación histórica de Obra.

Al desplegar, Gerencia pierde inmediatamente la autorización de Usuarios por comprobación del rol persistido, aunque conserve un JWT válido para el negocio. No se invalidan indiscriminadamente sesiones por ampliar el catálogo. Los cambios efectivos de rol, email, contraseña y estado siguen incrementando sesion_version, invalidando access y refresh previos.

### Bloqueos y guardias

Se conserva `pg_advisory_xact_lock(6006006)` como mutex transaccional del pequeño dominio administrativo. Ahora protege también el bootstrap; funciona incluso si aún no existen filas TI. Después se bloquean las cuentas activas TI/Gerencia, actor y objetivo por PK ascendente.

- `_admin` relee actividad, rol TI y versión del actor bajo lock.
- Última TI activa: 409 `ultima_ti` al desactivar o cambiar a otro rol. Una TI inactiva no sirve de relevo.
- Última Gerencia activa: protección independiente, 409 `ultima_gerencia`, aunque existan varias TI.
- Se conserva `autooperacion_protegida`: no auto-baja, cambio de rol propio ni establecimiento administrativo de contraseña propia. La contraseña propia usa la ruta auth existente con clave actual.
- Se mantienen `asignaciones_pendientes`, validadores, proyecciones, hashing, auditoría transaccional y no-op/idempotencia administrativa existentes.
- Usuarios no adquiere locks de Obra/Presupuesto/Turno después de Usuario. Los EXISTS de obligaciones no bloquean Obras; asignaciones e inicio de turnos existentes serializan sobre la fila del técnico. No se invierte Presupuesto → Obra → Técnico.
- Dos TI que se desactivan/degradan mutuamente dejan una activa; la segunda puede recibir 403 porque su actor ya perdió actividad/rol. Dos operaciones TI sobre dos Gerencias dejan una Gerencia activa y la segunda recibe ultima_gerencia.

Las protecciones corresponden al protocolo de servicios/API/comando. Escrituras SQL directas o un DBA pueden eludir el ORM; no se introduce otro CRUD de administración ni se convierten flags Django en rol de negocio.

### Comando seguro para la primera TI

**No se ejecutó contra la BD de desarrollo para inventar una cuenta.** Solo se probó con fixtures en bases temporales. El operador autorizado debe ejecutarlo con su identidad institucional real, después de aplicar migraciones:

```bash
docker compose exec backend python manage.py crear_primera_ti --email '<correo institucional real>' --username '<alias institucional real>'
```

En una shell interactiva del servicio Render, el equivalente es:

```bash
python manage.py crear_primera_ti --email '<correo institucional real>' --username '<alias institucional real>'
```

Opcionales: `--first-name` y `--last-name`. No usar `-T`, pipe ni stdin redirigido para el aprovisionamiento. Requiere TTY y solicita contraseña oculta y confirmación mediante getpass; aborta si no puede desactivar eco (GetPassWarning), ante interrupción, formato/validadores inválidos o duplicidad. No admite argumento de contraseña, lectura desde variables de entorno ni credenciales predeterminadas. No pegar secretos en comandos, historial, tickets o capturas.

El servicio adquiere el mismo mutex antes de comprobar existencia. Crea **una** TI activa, sin is_staff/is_superuser y con contraseña validada/hasheada. Creación y evento CREACION se confirman juntos. El actor del evento es la propia cuenta inicial, con motivo explícito de aprovisionamiento manual, sin cuenta ficticia de sistema ni snapshot de contraseña. Una TI existente, incluso inactiva, impide rebootstrap: no es un mecanismo público de recuperación ni una vía para crear una segunda cuenta privilegiada.

Una segunda ejecución concurrente espera al mutex y falla sin otra fila/evento. Las demás TI se crean inactivas y se activan exclusivamente desde `/api/usuarios/` con una TI ya autenticada. Si existe una TI inactiva/inaccesible, aplicar un procedimiento operacional autorizado de recuperación con respaldo y auditoría, no promover Gerencia silenciosamente ni desactivar guardias. No se automatiza recuperación fuera del alcance.

**Orden de entrega recomendado:** respaldo → migración incremental → reemplazar todas las instancias backend por la versión con permisos TI → aprovisionar primera TI por terminal autorizada → publicar frontend compatible → verificar login/permisos. Evitar convivir con instancias antiguas que aún autoricen Gerencia en Usuarios. No retroceder la constraint a cuatro roles cuando existan cuentas TI: fallaría antes de perder datos; preferir corrección hacia adelante o restauración planificada.

## Frontend: integración real

- TI entra directamente en Usuarios y roles, único módulo del menú, usando el layout adaptable existente. Gerencia ya no tiene esa sección y conserva sus módulos de negocio.
- Listado real de 25/página, filtros rol/actividad, detalle, creación inactiva, PATCH de perfil, acciones con motivo, contraseña ajena y auditoría con paginación independiente.
- Mi contraseña usa `POST /api/auth/cambiar-clave/`, clave actual/nueva, y cierra la sesión tras éxito. Editar el propio email obliga a nuevo login por revocación.
- Solo se envían campos permitidos; no se mandan estados, flags, actores, timestamps ni versiones desde formularios.
- No usa seed, toggle local, persistencia simulada, almacenamiento de tokens en navegador ni escrituras optimistas. Confirma con relecturas de API; si falta confirmar, bloquea nuevas escrituras hasta Actualizar. Un 409 muestra código público y no reenvía automáticamente la operación.
- Contraseñas solo en inputs de tipo password/estado efímero, se limpian después de cada envío, también en error. No se muestran en auditoría ni mensajes. Los snapshots de contraseñas se vacían defensivamente aunque una respuesta incorpore campos extra.
- Proyecciones y validación de respuestas; no se renderizan hashes, versiones, permisos heredados ni datos desconocidos. API malformada se maneja como error controlado.
- Cambio de identidad/rol o logout desmonta vistas, aborta peticiones y descarta respuestas tardías. Montar Usuarios con otro rol no realiza consultas administrativas.

Las fixtures HTTP de los tests React son exclusivamente pruebas automatizadas; la aplicación productiva usa el cliente autenticado y `/api/usuarios/` reales.

## Arquitectura Render / Neon / Atlas

No se incorpora acceso directo del navegador a bases de datos. React habla únicamente con Django; PostgreSQL conserva cuentas, roles y auditoría. MongoDB/Atlas y scripts de otros compañeros no se consultan ni modifican por este incremento.

Por defecto se mantiene el despliegue mismo origen con rutas relativas `/api/` y `credentials: same-origin`; Vite conserva su proxy local sin reescribir Origin o cookies. Para frontend/API separados:

- En el build frontend, configurar opcionalmente `VITE_API_BASE_URL=https://api.<dominio-propio>` (solo origen HTTPS; HTTP únicamente loopback de desarrollo). Es configuración pública, no un secreto. El cliente restringe las rutas a `/api/`, envía credentials include únicamente al origen configurado, no sigue redirects y no permite Authorization arbitraria del caller.
- Backend: `DJANGO_ALLOWED_HOSTS` para el host API, `DJANGO_CORS_ALLOWED_ORIGINS` para el origen frontend exacto y `DJANGO_CSRF_TRUSTED_ORIGINS` para ese mismo origen. CORS vacío por defecto; sin wildcard. Solo aplica a `/api/`; permite credenciales y expone Retry-After/Idempotency-Replayed, no secretos. CORS no reemplaza RBAC/CSRF. Un preflight vacío no es autorización para leer la API.
- Mantener HTTPS, HttpOnly, Secure en producción y SameSite=Strict. Frontend y API deben ser **same-site** (por ejemplo app/api del mismo dominio registrable) o desplegar un proxy `/api/` mismo origen. Dos subdominios arbitrarios `*.onrender.com` no garantizan cookies same-site; no resolverlo relajando CSRF/SameSite ni almacenando refresh en JavaScript.
- Para Neon, usar la configuración PostgreSQL existente con host/puerto/base/usuario/contraseña gestionados como secretos backend y TLS requerido/verificado según la conexión de Neon (por ejemplo PGSSLMODE y certificados del proveedor). Los locks advisory transaccionales no dependen de una sesión persistente y se liberan al commit/rollback; no usar locks advisory de sesión en un pool transaccional.
- Atlas sigue siendo configuración exclusiva de los módulos que lo requieran, sin credenciales en Vite ni en este ZIP. No se promete un despliegue remoto ya realizado: Render/Neon/Atlas reales no se ejecutaron durante esta entrega.

## Verificaciones reales

Validación final en Docker con Django **5.2.19** y PostgreSQL **18.6** (`connection.vendor=postgresql`, `pg_version=180006`), no SQLite. Las bases temporales se crean desde cero y se destruyen al terminar.

| Comando | Resultado |
|---|---|
| `docker compose exec -T backend python manage.py check` | Sin problemas, 0 silenciados |
| `docker compose exec -T backend python manage.py makemigrations --check --dry-run` | No changes detected |
| `docker compose exec -T backend python manage.py migrate --noinput` | Applying usuarios.0005_administrador_ti... OK; repetición final: No migrations to apply |
| `docker compose exec -T backend python manage.py test apps.usuarios --noinput` | **79 pruebas, 11.112 s, OK** |
| `docker compose exec -T backend python manage.py test --noinput` | **643 pruebas, 124.085 s, OK**, regresión completa |
| `npm test` desde frontend | **142 pruebas, 142 OK, 0 fallos**, 1477.0533 ms |
| `npm run build` desde frontend | **OK**, Vite 6.4.5, 83 módulos, 1.16 s |
| `git diff --check` | Sin errores de whitespace; avisos LF/CRLF de Git en Windows |

Se inició únicamente backend/PostgreSQL porque el contenedor estaba detenido, mediante `docker compose up -d --no-deps postgres backend`; no se inició MongoDB. La primera suite frontend detectó supuestos históricos de cuatro roles/Usuarios sin integrar y luego una fixture incompleta de Clientes; se actualizaron los contratos y la fixture. La suite de bootstrap detectó el tipo TextChoices del rol en el snapshot inicial: se corrigió a su valor string, conservando la validación estricta. Ejecuciones intermedias posteriores: Usuarios 78 pruebas/10.872 s OK y suite global 642 pruebas/126.960 s OK. La última ampliación protege también el comando contra impresión de detalles SQL inesperados que pudieran contener hashes; no altera la propagación de errores inesperados de los servicios. Los resultados finales figuran arriba. Las advertencias de tokens inactivos pertenecen a tests negativos de JWT, no a logins autorizados.

Cobertura: cinco roles, 403 incluso con flags/claims falsos, negocio de Gerencia conservado, TI excluido de negocio, revocación access/refresh al cambiar hacia/desde TI, última TI y última Gerencia independientes, autooperaciones, dependencias de técnicos, bootstrap sin secretos y rollback, migración con usuarios/hash/asignaciones preservados, CORS cerrado, menú, CRUD real, errores, filtros/paginación, auditoría y respuestas tardías descartadas.

Concurrencia: se conservan las carreras de técnicos, turnos y refresh de SPEC-006 con actor TI; se prueban TI cruzadas, operaciones concurrentes sobre las dos Gerencias y dos comandos de bootstrap. Conexiones PostgreSQL independientes, Event y bloqueo observado con pg_blocking_pids, sin sleeps.

No se ejecutaron CI remoto, Postman, navegador real ni despliegue Render/Neon/Atlas. Esos pasos quedan pendientes de revisión/autorización; npm test usa componentes React montados, no un navegador completo.

## Procedimiento Postman y prueba manual

1. Usar entorno de revisión y aplicar migración. El operador aprovisiona su primera TI con el comando interactivo anterior. No importar contraseñas/usuarios demo ni inventar cuentas en migraciones. Crear las otras cuentas de prueba por API con TI y activación explícita, conservando Gerencia activa.
2. Obtener CSRF con GET `/api/auth/csrf/`. POST login con correo/contraseña de TI, cookie CSRF y header X-CSRFToken. Conservar CSRF rotado y cookie refresh HttpOnly para refresh/logout; access Bearer solo en variables locales no compartidas. `/me/` debe devolver role=ADMINISTRADOR_TI y las cuatro claves históricas.
3. TI: GET `/api/usuarios/?rol=TECNICO&activo=true&page=1`; listar/detalle/historial 200. POST alta con email, username, rol, password y nombres opcionales → 201 inactivo. Login de esa cuenta falla hasta POST activar con motivo. No aceptar is_active, flags, grupos, versión ni campos desconocidos en alta/PATCH.
4. Editar perfil → 200; repetir sin cambios no crea evento. Cambiar email, rol, actividad o contraseña → tokens antiguos de la cuenta afectada devuelven 401 en me/refresh; nuevo login refleja rol real. No confiar en claims de rol manipulados.
5. G/AF/S/T: intentar listado/detalle/alta/PATCH/activar/desactivar/cambiar-rol/establecer-clave/historial y OPTIONS Usuarios → 403, aun con flags Django. Gerencia debe seguir leyendo sus rutas de Clientes, Presupuestos, Obras y Finanzas según contratos existentes.
6. TI: GET/POST/OPTIONS Comercial, Obras, categorías y Finanzas → 403. No intentar resolver asignaciones desde TI: realizarlo con Supervisor por los flujos de Obras. Un técnico responsable/participante activo o con turno abierto no puede desactivarse ni cambiar a otro rol; después de resolución operativa autorizada sí.
7. Intentar auto-baja, cambio de rol propio y contraseña propia por ruta administrativa → 409; usar auth/cambiar-clave para la contraseña propia. Última TI sin relevo activo → ultima_ti. TI intentando baja/degradación de última Gerencia → ultima_gerencia, independientemente de cuántas TI haya. No forzar la ausencia de esos roles por SQL en producción.
8. Activar/desactivar idéntico retorna 200 sin evento/versión extra; rol idéntico retorna 409 sin_cambios. Revisar auditoría y snapshots vacíos en contraseñas. No hay PUT/DELETE genéricos.
9. En React, iniciar con TI: solo menú Usuarios y roles, tabla desde API, filtros y páginas reales, detalle y auditoría. Crear/editar/activar/desactivar/cambiar rol/establecer clave con respaldo de acción; comprobar por Postman que persistió realmente. Gerencia no debe mostrar la sección, y una pérdida de sesión debe retirar los datos protegidos.
10. Probar ancho móvil: menú abre/cierra con navegación/Escape; tablas desplazables sin ocultar acciones; labels, errores y estado de carga visibles. Un conflicto o pérdida de conexión exige Actualizar antes de otro envío; no se declara éxito local.
11. Para API separada, verificar en navegador real origen/CORS/CSRF, cookies HttpOnly/Secure/SameSite y login/refresh/logout bajo dominios same-site HTTPS. Rechazar origen ajeno, evitar guardar tokens en archivos de entorno exportados o logs.

No se incluye una colección Postman con credenciales: el procedimiento permite construirla y revisarla después del ZIP.

## Paquete

`revision-spec-006b.zip`: archivos nuevos/modificados de esta entrega y este informe, rutas relativas al repositorio. Excluye secretos, `.env`, DB, dependencias, cachés, build dist, `.git`, datos locales de prueba, entregas anteriores y scripts ajenos. Las pruebas automatizadas del código sí se incluyen. Revisión humana antes de cualquier integración.
