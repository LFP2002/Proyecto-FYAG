# SPEC-005A — Integración del frontend: autenticación real y sesión

**Estado:** propuesta de implementación, no integrada. 8 de noviembre de 2026.

## 1. Contexto verificado

- Backend FYAG en `main`: SPEC-001, 002A/002B, 003A/003B y 004A/004B-1…004B-5 integradas; SPEC-004B cerrada tras PR #13, Backend CI aprobado.
- Frontend React 18 + Vite 5 tiene un login de demostración y estado local, sin consumir las API para autenticar; `RoleSwitch` modifica el rol visual localmente.
- Los módulos backend `finanzas`, `dashboard`, `reportes`, `alertas` y `auditoria` existen como scaffolds, no como funcionalidades completas.
- Django expone `/api/auth/csrf/`, `/api/auth/login/`, `/api/auth/refresh/`, `/api/auth/logout/` y `/api/auth/me/`.
- `frontend/vite.config.js` ya tiene un proxy de `/api` a `http://localhost:8000`; Docker Compose inicia backend y bases de datos, no Vite.
- `frontend/src/app.jsx` importa `./components/Login` y el archivo existente es `frontend/src/components/login.jsx`: corregir la discrepancia de mayúsculas para entornos de archivos case-sensitive.

## 2. Objetivo y límites

Sustituir el inicio de sesión simulado por el mecanismo real de Django JWT, y proteger el marco general de navegación según el usuario autenticado. Este bloque **no** integra aún los CRUD de Clientes, Presupuestos, Obras o Finanzas; estos tendrán incrementos posteriores. Evitar mostrar módulos con botones simulados como si escribieran en la base de datos.

## 3. Contrato backend existente — inalterable

- `GET /api/auth/csrf/`: `{ "csrfToken": "…" }`, con cookie CSRF. Se debe enviar `X-CSRFToken` en login, refresh y logout, según SPEC-002B.
- `POST /api/auth/login/`: `{ "email": "...", "password": "..." }`. Responde `{ "access": "...", "user": { "id", "username", "email", "role" }, "csrfToken": "..." }`; refresh token solo en cookie HttpOnly bajo `/api/auth/`.
- `POST /api/auth/refresh/`: lee refresh cookie, rota tokens y responde nuevo `access`. No solicita ni recibe refresh por JSON.
- `POST /api/auth/logout/`: revoca refresh y elimina la cookie; respuesta 204 en éxito.
- `GET /api/auth/me/`: requiere `Authorization: Bearer <access>` y devuelve `id`, `username`, `email`, `role`.
- Roles del backend: `GERENCIA`, `ADMINISTRATIVO_FINANZAS`, `SUPERVISOR_OBRAS`, `TECNICO`.

## 4. Seguridad de sesión y autenticación

1. Reemplazar `DEMO_USERS`, credenciales precargadas y selector de «perfil de prueba» por formulario `email` + `password`; el rol **proviene exclusivamente** del backend autenticado.
2. Mantener access token solo en memoria (estado/contexto/módulo JS), nunca en `localStorage`, `sessionStorage`, IndexedDB, URL o cookies accesibles por JS.
3. Refresh token se mantiene exclusivamente en cookie HttpOnly; nunca leerlo ni guardarlo en JS.
4. Usar peticiones same-origin `/api/...` pasando `credentials: 'same-origin'` o `include` correctamente, con Vite proxy en desarrollo. No desactivar CSRF ni rebajar SameSite/HttpOnly.
5. Obtener CSRF por `/api/auth/csrf/` antes de login y en el arranque si procede. Tras login actualizar el CSRF con `csrfToken` rotado devuelto por backend.
6. En recarga de página, intentar restaurar sesión por `POST /api/auth/refresh/` usando cookie y CSRF; confirmar identidad/rol con `/api/auth/me/`. Sin refresh válido, mostrar login sin sesión.
7. Manejar expiración de access token: ante 401 de peticiones autenticadas, intentar **una sola renovación compartida** para solicitudes concurrentes y reintentar cada petición a lo sumo una vez. Si falla, limpiar sesión y presentar login. No crear ciclos infinitos.
8. Logout real por `/api/auth/logout/` con CSRF; limpiar inmediatamente el token y estado de usuario aunque la llamada falle, informar si la revocación remota no pudo confirmarse.
9. No mantener usuario/rol anterior tras logout, error de identidad o pérdida de sesión.
10. Las protecciones visuales son complementarias: el backend sigue autorizando recursos/acciones; nunca usar `is_superuser` como bypass ni confiar en roles enviados por el navegador.
11. Evitar logs que incluyan passwords, tokens o cookies, y evitar mensajes que revelen la existencia de cuentas.

## 5. UX, navegación y estados

- Pantalla de login sin selector de roles ni cuentas demo; estados de envío, validación, errores 400/401/403/429, pérdida de conexión y recuperación.
- Al iniciar, un estado breve de restauración de sesión evita mostrar contenido protegido antes de conocer la identidad.
- El layout muestra alias real y rol mapeado desde `user.role`; adaptar el menú a las capacidades visibles, sin permitir cambiar manualmente el rol.
- Deshabilitar/eliminar `RoleSwitch` de navegación productiva; si queda código de depuración, no debe ser accesible en la aplicación.
- Los módulos aún simulados deben indicarse explícitamente como **no conectados** y no guardar cambios locales que puedan confundirse con persistencia real. Se permite una pantalla informativa temporal, sin romper el diseño general.
- Técnica/o conserva experiencia móvil adaptada a su rol, sin simular cargas persistidas.
- Cambios mínimos de estilos para coherencia visual; evitar refactor completo no relacionado.

## 6. Arquitectura y compatibilidad

- Centralizar cliente HTTP para auth y futuras operaciones; separar helpers CSRF/sesión y UI.
- No reescribir servicios del backend de autenticación ni mover credenciales a variables públicas de Vite.
- Mantener `npm run dev` del frontend y `docker compose up -d` del backend como arranque local separado.
- Revisar rutas case-sensitive y compilación con `npm run build`.
- Evitar enviar tokens en query string, usar `Authorization: Bearer` y `Content-Type: application/json` cuando corresponda.
- No introducir una segunda política de autenticación con cookies de sesión Django para API.

## 7. Pruebas y criterios de aceptación

1. Login válido con email y password reales; rol mostrado coincide con `/me/`.
2. Login incorrecto 401, datos incompletos 400 y limitación 429 sin ingreso ficticio.
3. Selector de roles/usuarios demo eliminado.
4. Refresh cookie HttpOnly no aparece en JSON y no está disponible desde JS.
5. Access token ausente tras cerrar navegador/pestaña; recarga puede restaurar sesión únicamente mediante refresh permitido.
6. Logout llama al backend; limpia frontend y evita el uso de rol anterior.
7. Token vencido: una renovación y un reintento máximo; refresh vencido termina sesión.
8. Dos 401 simultáneos no producen ráfaga de refresh concurrentes.
9. CSRF correcto en login/refresh/logout; falla sin CSRF según política del backend.
10. `TECNICO` no puede convertirse en `GERENCIA` mediante UI o estado local; 403 del backend permanece visible.
11. Los módulos de negocio no conectados no ejecutan escrituras simuladas como si fueran reales.
12. `npm run build` completo, sin errores de mayúsculas/importaciones; backend `python manage.py check` y suite completa sin regresión.
13. Pruebas de frontend automatizadas para cliente HTTP/sesión y estados de autenticación, incorporando librerías de test livianas si no existen; no usar credenciales reales en repositorio.

## 8. Exclusiones

- Integración CRUD de clientes/presupuestos/obras; datos económicos, turnos y evidencias.
- Facturas, cuentas por cobrar, pagos, cobranzas y contabilidad real.
- MFA, recuperación de contraseña, usuarios externos, notificaciones, despliegue productivo, HTTPS en desarrollo.
- Migraciones de base de datos o modificaciones de reglas de negocio previamente aprobadas.

## 9. Entregables

- Frontend autenticado mediante API JWT/CSRF real y sesión segura.
- Pruebas de frontend y build de producción exitosos.
- Documentación mínima de arranque de Vite y backend.
- Informe de límites y módulos que todavía necesitan integración de API.
- No hacer commit, push ni PR hasta revisión humana.
