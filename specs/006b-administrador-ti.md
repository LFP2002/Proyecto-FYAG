# SPEC-006B — Administración exclusiva de TI y matriz RBAC de cinco roles

**Estado:** implementada e integrada en `main` mediante [PR #24](https://github.com/LFP2002/Proyecto-FYAG/pull/24) (11-11-2026). **Código:** `backend/apps/usuarios/`, `frontend/src/pages/Usuarios.jsx`. **Evidencia:** [informe 006B](../backend/docs/SPEC-006B-IMPLEMENTACION.md). Este documento **complementa y prevalece sobre SPEC-006** cuando existe contradicción, sin reescribir las decisiones históricas.

## Política vigente de autorización

- Cinco valores persistidos para `Usuario.rol`: `GERENCIA`, `ADMINISTRATIVO_FINANZAS`, `SUPERVISOR_OBRAS`, `TECNICO`, `ADMINISTRADOR_TI`; PostgreSQL restringe el catálogo mediante constraint y migración incremental `usuarios.0005_administrador_ti`.
- Únicamente `ADMINISTRADOR_TI` activo y con sesión válida puede leer, crear y modificar cuentas o leer su auditoría bajo `/api/usuarios/`. Gerencia **no** administra cuentas. `is_superuser`, `is_staff`, grupos, flags y claims de cliente no conceden acceso.
- TI no recibe permisos operativos en Clientes, Presupuestos, Obras, categorías y Finanzas. El backend verifica rol persistido y `sesion_version`. El frontend no es el control de acceso.
- Cada rol autenticado puede consultar `/api/auth/me/` y cambiar su propia contraseña mediante `POST /api/auth/cambiar-clave/`.

## Contratos HTTP implementados

| Método | Recurso | Restricción |
|---|---|---|
| GET/POST | `/api/usuarios/` | TI; listado paginado (25), filtros estrictos `rol` y `activo`; alta inactiva |
| GET/PATCH | `/api/usuarios/{id}/` | TI; sólo perfil `email,username,first_name,last_name` |
| POST | `/api/usuarios/{id}/activar/` | TI; motivo obligatorio |
| POST | `/api/usuarios/{id}/desactivar/` | TI; motivo, guardias y revocación |
| POST | `/api/usuarios/{id}/cambiar-rol/` | TI; rol/motivo, guardias y revocación |
| POST | `/api/usuarios/{id}/establecer-clave/` | TI; motivo, validadores Django y revocación |
| GET | `/api/usuarios/{id}/historial/` | TI; 25/página, snapshots públicos acotados |
| POST | `/api/auth/cambiar-clave/` | Cada usuario activo, contraseña actual/nueva; 204 y nuevo login |

Las operaciones son transaccionales, con auditoría de cambios y sesiones revocadas cuando cambian rol, actividad, email o contraseña. No hay altas públicas ni bajas físicas; se rechazan campos administrados por el servidor. `GET /api/auth/me/` conserva `id,username,email,role`. Los códigos 400/401/403/404/405/409 se mantienen según el contrato de SPEC-006, modificando actor administrador a TI.

## Integridad concurrente y aprovisionamiento

- El mutex transaccional PostgreSQL `pg_advisory_xact_lock(6006006)` serializa administración y bootstrap; `select_for_update` ordena filas de TI/Gerencia, actor y objetivo por PK.
- Prohibido desactivar/degradar la **última TI activa** (`409 ultima_ti`) o la **última Gerencia activa** (`409 ultima_gerencia`), aún con peticiones concurrentes. TI no puede desactivarse, cambiar su propio rol ni establecer administrativamente su propia contraseña (`409 autooperacion_protegida`).
- Un técnico con responsabilidad, membresía no terminal o turno abierto no puede desactivarse ni cambiar a rol no técnico (`409 asignaciones_pendientes`); no alterar Obras desde Usuarios para resolverlo.
- El comando interactivo `crear_primera_ti` crea exclusivamente la primera TI, con TTY, doble ingreso oculto, validación y hashing, sin secretos en CLI/entorno y evento auditable. No crea una segunda TI si existe incluso una inactiva; la recuperación institucional requiere proceso administrativo separado.
- Los secretos nunca se publican en el repositorio, los JWT access permanecen en memoria y refresh en cookie HttpOnly. No utilizar credenciales de prueba reales en Postman exportado.

## Frontend y despliegue

React monta el módulo Usuarios únicamente para TI; incorpora CRUD autorizado, filtros, paginación, auditoría, reconciliación de escrituras y no hace mutaciones optimistas. La API puede estar en origen explícito configurado mediante `VITE_API_BASE_URL` si se respeta HTTPS, CORS de allowlist, CSRF y cookies same-site; React **nunca** accede directamente a PostgreSQL o MongoDB. La corrección de sesión tras cambio del correo propio se documenta en SPEC-006C.

## Validación y trazabilidad

- PR #24: Backend CI Django/PostgreSQL y Frontend CI React/Vite, ambos **success** en commit `459274a9c75094761df66d25c4849baf4e312898`; 643 tests backend y 142 frontend declarados por el PR.
- Colecciones Postman ejecutadas localmente por el operador: dos recorridos reportados con 0 fallos. No sustituye pruebas automatizadas en CI ni verificación de un entorno desplegado.
- Probar siempre roles positivos y denegados, guardias de última TI/Gerencia, concurrencia, normalización/email duplicado, revocación access/refresh y auditoría sin secretos.
- Referencias: [SPEC-006](006-backend-usuarios-roles.md), [SPEC-006C](006c-correo-propio-sesion.md), `backend/apps/usuarios/tests/`, `frontend/tests/`.
