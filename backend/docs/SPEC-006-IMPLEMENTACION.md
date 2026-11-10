# SPEC-006 — Implementación para revisión técnica

Rama: `feature/backend-006-usuarios-roles`. Solo backend. Sin commit, push ni PR.
La SPEC oficial no se modifica ni se declara integrada antes de la revisión.

## Archivos entregados

Nuevos en `backend/apps/usuarios/`:

- `authentication.py`: validación de identidad, actividad, versión y hash revocado.
- `tokens.py`: emisores access/refresh versionados; almacenamiento coherente del outstanding.
- `services_usuarios.py`: casos de uso, transacciones, guardias y auditoría.
- `serializers_usuarios.py`: escrituras estrictas y lecturas por lista permitida.
- `views_usuarios.py`, `urls_usuarios.py`: API administrativa y contraseña propia.
- `migrations/0004_usuarios_roles_sesiones_auditoria.py`: versión inicial 1, constraint positiva y eventos con FKs PROTECT.
- `tests/test_administracion.py`, `test_sesiones_006.py`, `test_dependencias_006.py`, `test_concurrencia_006.py`, `test_migracion_006.py`.

Modificados:

- `backend/apps/usuarios/{models.py,permissions.py,serializers.py,views.py,urls.py}`.
- `backend/config/{settings.py,urls.py}`.
- Solo el import del emisor de tokens en pruebas anteriores: `usuarios/tests/test_auth.py`; `comercial/tests/{test_cliente_api.py,test_presupuesto_api.py}`; `obras/tests/{test_api_004a.py,test_gastos.py,test_migracion_participantes.py,test_participantes.py,test_servicios_004a.py,test_turnos.py}`.
- Este informe: `backend/docs/SPEC-006-IMPLEMENTACION.md`.

No se cambian frontend, MongoDB, `database/`, `backend/scripts/`, reglas de Comercial/Obras ni migraciones anteriores.

## Contratos

Solo Gerencia activa, con rol consultado en PostgreSQL:

| Método | Ruta | Entrada | Éxito |
|---|---|---|---|
| GET | `/api/usuarios/` | `rol`, `activo=true\|false`, `page` opcionales | 200 |
| POST | `/api/usuarios/` | `email`, `username`, `rol`, `password`; nombres opcionales | 201 |
| GET | `/api/usuarios/{id}/` | — | 200 |
| PATCH | `/api/usuarios/{id}/` | Solo email, username, first_name, last_name | 200 |
| POST | `/api/usuarios/{id}/activar/` | motivo | 200 |
| POST | `/api/usuarios/{id}/desactivar/` | motivo | 200 |
| POST | `/api/usuarios/{id}/cambiar-rol/` | rol, motivo | 200 |
| POST | `/api/usuarios/{id}/establecer-clave/` | nueva_clave, motivo | 200 |
| GET | `/api/usuarios/{id}/historial/` | page opcional | 200 |

Cualquier rol activo: `POST /api/auth/cambiar-clave/`, con `clave_actual` y `nueva_clave`, devuelve 204, elimina cookie refresh y exige nuevo login.

Alta siempre inactiva. Lista e historial: 25 por página; orden por ID y por fecha/ID, respectivamente. Lecturas sin hashes, versiones internas ni permisos Django. Sin registro público ni PUT/DELETE.

Errores: 400 validación/duplicados; 401 sesión inválida; 403 rol no autorizado; 404 recurso inexistente; 405 método no permitido; 409 con `code` para `ultima_gerencia`, `autooperacion_protegida`, `asignaciones_pendientes`, `sin_cambios` (y protección excepcional `version_agotada`). Activación/desactivación idéntica y PATCH sin cambios no generan evento ni revocación.

## Decisiones y límites

1. Las mutaciones administrativas adquieren `pg_advisory_xact_lock(6006006)`, luego bloquean Gerencias activas, actor y objetivo por PK ascendente. El mutex serializa el pequeño dominio administrativo, evita phantoms entre operaciones 006 y se libera automáticamente al terminar la transacción. Sacrifica paralelismo administrativo por simplicidad e integridad.
2. Usuarios **no bloquea Obras**. Consulta obligaciones con EXISTS bajo el lock del técnico. Los servicios existentes de asignación e inicio de turno bloquean ese Usuario y serializan las carreras sin invertir Presupuesto → Obra → Técnico. La resolución de obligaciones se realiza exclusivamente en Obras.
3. Login revalida credenciales bajo lock del Usuario; refresh verifica existencia, actividad, versión y hash, y vuelve a comprobar blacklist después del lock antes de rotar. Una rotación anterior a una revocación puede completar, pero los tokens que emitió quedan igualmente obsoletos al confirmarse la revocación.
4. Email, rol, estado y contraseña incrementan versión; alias/nombres no. Se conserva CHECK_REVOKE_TOKEN, rotación, blacklist, cookie HttpOnly, SameSite, Secure según entorno y rutas auth.
5. **Despliegue:** todos los tokens anteriores sin `sesion_version` reciben 401. Es intencional: informar a usuarios que deben iniciar sesión una vez tras desplegar/aplicar migración. No se crean cuentas ni credenciales en migraciones.
6. Auditoría y cambio se confirman juntos. Snapshots permitidos de perfil/rol/actividad; eventos de contraseña con snapshots vacíos. Modelo/queryset rechazan edición/borrado y el serializer filtra defensivamente. Estas protecciones no sustituyen permisos de base de datos: un DBA con SQL directo puede eludir el ORM. No hay auditoría global ni escritura MongoDB.
7. Dos Gerencias que se desactiven/degraden cruzadamente dejan una activa; la segunda operación puede recibir 403 porque su actor ya perdió el rol/actividad. No se permite autooperación aunque existan varias Gerencias.
8. Discrepancia documental: refresh y logout **ya tenían** `csrf_protect` en la base real. Se preserva y prueba con CSRF exigido; no se atribuye la protección existente a una incorporación nueva.
9. Las invariantes corresponden a estos servicios. Escrituras directas por shell/SQL u otros futuros puntos de administración deben usar el mismo protocolo; no se altera Django Admin para introducir otro flujo.

## Validación automatizada

Ejecución en contenedor con Django 5.2.19 y PostgreSQL 18.6 (`connection.vendor=postgresql`, `pg_version=180006`). Las bases temporales se crean desde cero y se destruyen al terminar. La prueba incremental retrocede 0004 → 0003 en la base de pruebas y vuelve a avanzar, preservando IDs, hashes y asociaciones de Obras/Presupuestos, sin inventar auditoría histórica.

Las carreras usan `TransactionTestCase`, conexiones independientes, eventos, límites de bloqueo y `pg_blocking_pids`; sin sleeps. Incluyen Gerencias cruzadas, alta/activación duplicada, asignación/participantes frente a baja/rol, inicio de turno y refresh/blacklist/revocación.

Resultados finales (prefijo de todos los comandos: `docker compose exec -T backend`):

| Comando | Resultado |
|---|---|
| `python manage.py check` | `System check identified no issues (0 silenced).` |
| `python manage.py makemigrations --check --dry-run` | `No changes detected` |
| `python manage.py migrate --noinput` | `Applying usuarios.0004_usuarios_roles_sesiones_auditoria... OK` |
| `python manage.py showmigrations usuarios` | 0001, 0002, 0003 y 0004 aplicadas `[X]` |
| `python manage.py test --noinput` | **550 pruebas, 77.215 s, OK**, base temporal destruida |
| `git diff --check` (host) | Sin errores de whitespace; avisos de conversión LF/CRLF de Git en Windows |

Ejecuciones intermedias: Usuarios 40 pruebas detectó un nombre real de constraint de email no contemplado; se corrigió su traducción. Usuarios 50 detectó dos errores de fixtures operativos (baja incoherente de participante y acción de cancelación inexistente); se corrigieron sin cambiar Obras. Después, Usuarios **62 pruebas, 9.097 s, OK** y suite completa **548 pruebas, 77.775 s, OK**. La última suite de 550 incluye además identificadores JWT malformados y rotación anterior a revocación. Las advertencias de Simple JWT al emitir tokens para una cuenta inactiva son intencionales en los tests negativos, no fallos ni emisión desde login.

No se ejecuta GitHub Actions: sin push/PR no puede afirmarse CI remoto verde. Tampoco se automatizó un navegador real; la comprobación manual siguiente sigue pendiente y no se presenta como ejecutada.

## Prueba manual (entorno de revisión)

Usar cuentas de prueba propias ya existentes, nunca credenciales de producción. No añadir cuentas a migraciones. Levantar servicios con la configuración local habitual y aplicar `docker compose exec -T backend python manage.py migrate --noinput`.

### Login, CSRF y cookies en navegador

Con la aplicación/API en el origen local permitido, abrir DevTools y ejecutar en su consola (ajustar origen si se usa proxy):

```javascript
const base = 'http://localhost:8000';
let csrf = (await (await fetch(base + '/api/auth/csrf/', {
  credentials: 'include'
})).json()).csrfToken;
// Introducir email/contraseña de prueba de Gerencia; no guardar ni compartirlos.
const email = prompt('Email de prueba');
const password = prompt('Contraseña de prueba');
const loginResponse = await fetch(base + '/api/auth/login/', {
  method: 'POST', credentials: 'include',
  headers: {'Content-Type': 'application/json', 'X-CSRFToken': csrf},
  body: JSON.stringify({email, password})
});
const login = await loginResponse.json();
const oldCsrf = csrf;
csrf = login.csrfToken;
const access = login.access;
```

- Comprobar 200 y `/me/` con `Authorization: Bearer ${access}` devuelve solo id/username/email/role.
- En Application/Network, refresh es HttpOnly, SameSite Strict, path `/api/auth/`; Secure en entorno no DEBUG. No aparece en JSON ni `document.cookie`.
- POST refresh/logout sin `X-CSRFToken`, con token incorrecto o `oldCsrf` devuelve 403. Con `csrf` actual refresh devuelve 200 y rota la cookie; logout devuelve 204 y la borra. Origen no permitido debe fallar. En despliegue HTTPS comprobar también Secure y Origin/Referer reales.
- No copiar tokens/contraseñas a informes, capturas compartidas, URLs ni historial de comandos. Si el frontend está en otro origen, usar la configuración CORS/CSRF existente; no ampliar orígenes para evitar errores.

### Administración y revocación

Con access de Gerencia y cliente REST que no persista secretos:

1. POST usuarios con email/alias únicos, rol TECNICO y contraseña válida. Verificar 201 e inactivo; login nuevo falla 401. POST activar con motivo; login ahora 200.
2. GET lista/detalle/historial. Probar `?rol=TECNICO&activo=true`, página 2; filtros desconocidos/repetidos → 400. PUT/DELETE → 405.
3. PATCH nombres/alias: token anterior sigue válido. PATCH email: access y refresh anteriores → 401; nuevo login por nuevo email funciona. No se aceptan flags, rol ni password por PATCH.
4. Cambiar rol o establecer contraseña: tokens antiguos → 401. Con nuevo login comprobar permisos de Comercial/Obras según rol actual. Repetir rol → 409 sin_cambios.
5. Con cada rol no Gerencia intentar todas las rutas administrativas → 403, incluso con flags Django heredados. Todos los roles activos pueden cambiar clave propia: clave actual incorrecta → 400; correcta → 204 y nuevo login obligatorio.
6. Intentar auto-baja/cambio propio de rol/clave por ruta administrativa → 409. Con una única Gerencia activa intentar baja/degradación → ultima_gerencia. No dejar el entorno sin Gerencia por escrituras directas.
7. Asignar técnico principal/participante en Obras mediante sus rutas existentes e iniciar turno cuando corresponda. Baja/cambio a otro rol → 409. Cerrar turno y reasignar/desasignar desde Obras; entonces baja/cambio funciona. Confirmar conservación de vínculos históricos.
8. Repetir activar/desactivar en mismo estado: 200 sin evento adicional. Historial de contraseñas tiene snapshots vacíos; nunca contiene claves, hashes, tokens ni versión.

## ZIP de revisión

`revision-spec-006.zip` contiene únicamente los archivos nuevos/modificados de esta entrega y este informe, con rutas relativas al repositorio. Es un paquete incremental sobre la rama base, no un despliegue completo. Excluye `.env`, bases de datos, dependencias, caches, frontend, scripts ajenos y `.git`. Revisar antes de cualquier commit.
