# SPEC-018 — guía de integración para el equipo frontend externo

Fecha: 20-11-2026. Complemento del [contrato Fase A](SPEC-018-FASE-A-CONTRATO.md),
[fail-closed](SPEC-018-FAIL-CLOSED.md) y [OpenAPI 1.1.1](openapi/SPEC-018A-v1.json).
**Alcance de esta entrega: backend y documentación. No se implementó Fase B React ni
se modificó `frontend/`. El cliente antiguo necesita adaptación antes de desplegar.**
Prevalecen SPEC-018 y SPEC-005A/006B/006C. Sin nuevos endpoints ni migraciones.
Solo desarrollo/QA; TTL temporal 24 h y desafío 5 min son configurables y **NO
RATIFICADOS PARA PRODUCCIÓN**. Entrega manual únicamente entre cuentas sintéticas.

## 1. Transporte, identidad y cookies

- JSON UTF-8; incluir `Content-Type: application/json` en escrituras.
- `fetch` hacia el origen API explícitamente confiable, con `credentials: 'include'`.
  No reenviar Authorization a URLs arbitrarias, redirects ni enlaces de paginación
  sin verificar origen/ruta. HTTPS confiable en ambientes con cookies Secure.
- Access JWT **solo en memoria**, header `Authorization: Bearer <access>` para
  `/me/`, administración y cambio propio. No persistirlo en storage, URL o logs.
- Refresh solo en cookie `fyag_refresh`: HttpOnly, Secure, SameSite Strict,
  path `/api/auth/`. No leerlo desde JS ni enviarlo como JSON/Bearer.
- Obtener `GET /api/auth/csrf/` → 200 `{"csrfToken":"<token>"}` y cookie
  `csrftoken`. Mantener token en memoria; header `X-CSRFToken` en login,
  primer cambio, refresh y logout. Login exitoso rota CSRF: sustituirlo por
  `csrfToken` de la respuesta antes de cualquier escritura posterior.
- La administración y cambio propio autentican con JWT; no dependen de sesión
  Django ni usan la cookie refresh como autorización administrativa.
- En orígenes separados: configurar explícitamente `CORS_ALLOWED_ORIGINS`,
  `CORS_ALLOW_CREDENTIALS=True` y `CSRF_TRUSTED_ORIGINS` (esquema incluido), según
  configuración del backend. Sin wildcard con credenciales. El sitio debe ser el
  mismo **schemeful site** para SameSite Strict: CORS no habilita cookies cross-site.
  Puertos distintos son orígenes distintos; subdominios no implican cross-site
  si comparten esquema y dominio registrable. No relajar Strict para sortear esto.
- CORS no reemplaza CSRF ni RBAC. Una API separada no necesita exponer Set-Cookie
  a JS: el navegador administra la cookie. Postman no reproduce estas restricciones.

## 2. Autenticación y primer acceso

1. Obtener CSRF y enviar `POST /api/auth/login/` con
   `{"email":"<correo>","password":"<clave>"}`; normalización trim/minúsculas
   del correo en servidor. No enviar una sesión Bearer previa al login.
2. **Personal:** 200 `{"access":"<JWT>","user":{"id":1,"username":"<alias>",
   "email":"<correo>","role":"TECNICO"},"csrfToken":"<rotado>"}` y Set-Cookie
   refresh. Actualizar identidad/CSRF en una única transición; se puede consultar
   `GET /api/auth/me/` con Bearer para confirmar perfil operativo.
3. **Temporal activa y vigente:** 200 **solo**
   `{"estado":"CAMBIO_OBLIGATORIO","desafio":"<opaco>",
   "desafio_vence_en":"<ISO8601>","csrfToken":"<rotado>"}`.
   El backend elimina la cookie refresh anterior. Esto **no es authenticated**:
   no `/me/`, refresh, módulos de negocio ni navegación operativa. Borrar cualquier
   access/identidad anterior. Guardar desafío solo en memoria y mostrar únicamente
   la pantalla de cambio inicial. Login nuevo sustituye al desafío anterior.
4. Confirmar nueva clave localmente y enviar **sin Authorization**
   `POST /api/auth/primer-cambio-clave/`, cookie/header CSRF actualizados y
   exclusivamente `{"desafio":"<opaco>","nueva_clave":"<entrada del titular>"}`.
   200 **solo** `{"estado":"CLAVE_PERSONAL_CONFIRMADA","login_requerido":true}`.
   No hay sesión automática. Borrar desafío/contraseñas y volver a login.
   No reutilizar temporal; validadores Django vigentes. Un 400 permite corregir
   entrada; un 401 de desafío exige recomenzar primer acceso mientras sea posible.
5. `POST /api/auth/refresh/`, body `{}`, cookie/header CSRF → 200
   `{"access":"<JWT nuevo>"}` y cookie refresh rotada. No refresh en JSON.
   Estado PERSONAL, hash y versión se revalidan en servidor; 401 elimina la sesión
   local, no abre un bucle de refresh. Serializar renovaciones (single-flight).
6. `POST /api/auth/logout/`, body `{}`, cookie/header CSRF → 204, sin body;
   invalida refresh presente y elimina cookie. Limpiar memoria incluso si falla
   la red, sin afirmar revocación remota confirmada. **Logout no consume desafíos
   opacos**: cancelación borra memoria; servidor limita por TTL, sustitución,
   consumo y cambios de versión. Un access ya emitido no se revoca por logout
   de la cookie únicamente; permanece sujeto a expiración/versionado.
7. Cambio personal: `POST /api/auth/cambiar-clave/` con Bearer y
   `{"clave_actual":"<actual>","nueva_clave":"<nueva>"}` → 204, revocación y
   nuevo login. No usar este endpoint para primer cambio ni restablecimiento TI.

No almacenar desafío/contraseñas/tokens en localStorage, sessionStorage, URLs,
telemetría, caches, Redux persistido, logs o historial de navegación.
No mostrar éxito tras red/5xx. No repetir automáticamente ningún POST de cambio.

## 3. Administración TI

Únicamente rol **persistido** `ADMINISTRADOR_TI`, activo, con JWT válido. Gerencia,
Finanzas, Supervisor y Técnico no administran usuarios; flags staff/superuser no
conceden TI. TI no recibe por ello permisos de negocio. El frontend no es autoridad.

Proyección administrativa normal (GET/acciones):
`id`, `username`, `email`, `first_name`, `last_name`, `rol`, `is_active`,
`date_joined`, `estado_credencial`, `cambio_obligatorio`.
Los roles son `GERENCIA`, `ADMINISTRATIVO_FINANZAS`, `SUPERVISOR_OBRAS`,
`TECNICO`, `ADMINISTRADOR_TI`. No añadir Bodeguero.

| Método/ruta | Request y resultado |
| --- | --- |
| GET `/api/usuarios/?page=1&rol=TECNICO&activo=true` | 200 `{count,next,previous,results}`; filtros opcionales; 25 por página. |
| GET `/api/usuarios/{id}/` | 200 proyección normal; nunca recupera secretos. |
| POST `/api/usuarios/` | `{"email":"<correo>","username":"<alias>","rol":"TECNICO"}`; opcionales first_name/last_name. 201 proyección **inactiva**, INICIAL, cambio_obligatorio true, más `credencial_temporal` y `credencial_vence_en` ISO8601. No enviar password, is_active ni estado. |
| PATCH `/api/usuarios/{id}/` | Subconjunto de email/username/first_name/last_name; 200 proyección confirmada. Correo efectivamente cambiado revoca sesiones. Si es correo propio confirmado, descartar sesión sin relectura ni refresh (006C). |
| POST `/api/usuarios/{id}/activar/` | `{"motivo":"<texto>"}` → 200 proyección; no prolonga TTL ni elimina cambio obligatorio. |
| POST `/api/usuarios/{id}/desactivar/` | Mismo body → 200 proyección; revoca. Guardas de última TI/Gerencia, autooperación y obligaciones vigentes. Sin DELETE físico. |
| POST `/api/usuarios/{id}/cambiar-rol/` | `{"rol":"TECNICO","motivo":"<texto>"}` → 200 proyección; guardas y revocación existentes. |
| POST `/api/usuarios/{id}/restablecer-clave/` | `{"motivo":"<texto>"}` → 200 proyección excepcional con temporal/vence_en, RECUPERACION. Solo cuenta ajena; no activa. Revoca sesiones/desafíos anteriores. Confirmación explícita antes de enviar. |
| POST `/api/usuarios/{id}/establecer-clave/` | Retirada: 409 operacion_retirada para TI autorizado (autooperación protegida); nunca usar nueva_clave para establecer contraseñas ajenas. |
| GET `/api/usuarios/{id}/historial/?page=1` | 200 paginado, 25 eventos: id/usuario_objetivo/actor/tipo/motivo/datos_anteriores/datos_nuevos/creado_en. Sin secretos; snapshots de eventos de claves vacíos. |

Motivo: texto no vacío, máximo 2000 caracteres. Perfil: alias/nombres hasta 150,
email hasta 254. Cuerpos administrativos estrictos, sin campos gestionados extra.

Capturar respuesta excepcional **antes** de relecturas; mostrar temporal una única
vez, confidencial, copia manual advertida. Borrar al cerrar/cambiar identidad.
No introducirla en caches/listas/historial/auditoría frontend. El servidor no puede
impedir que un receptor copie una respuesta: “una exposición” significa que ningún
GET posterior permite recuperar el secreto. Si se perdió, reemisión TI explícita,
tras reconciliar estado; no repetir alta/reset automáticamente por un fallo de red
o relectura. Dos resets pueden confirmar, pero solo el último es válido.

Estados: PERSONAL → cambio_obligatorio false; INICIAL/RECUPERACION → true incluso
vencidas; NO_DISPONIBLE → true, **inconsistencia de seguridad**, no PERSONAL ni
bloqueo escalonado. No ofrecer reparación/primer cambio automático. Login/JWT/
refresh/cambio fallan; reset responde 409 seguridad_no_disponible sin reparar.

## 4. Errores y concurrencia

| HTTP | Tratamiento |
| --- | --- |
| 400 | Objeto de errores de campo/listas o non_field_errors; no eco del secreto. Corregir entrada. |
| 401 | Login genérico `{"detail":"Credenciales inválidas."}`; desafío `{"detail":"Desafío no disponible."}`; JWT/refresh inválidos/revocados según endpoint. No revelar identidad ni causa interna. |
| 403 | CSRF o permisos. CSRF puede devolver HTML, no asumir JSON; no mostrar HTML sin sanitizar. |
| 404 | Cuenta no disponible/página inexistente. Permisos se verifican antes de revelar existencia. |
| 409 | `{"detail":"<mensaje>","code":"<código>"}`: entre otros autooperacion_protegida, ultima_ti, ultima_gerencia, asignaciones_pendientes, sin_cambios, version_agotada, operacion_retirada, seguridad_no_disponible. Reconciliar, no reparar automáticamente. |
| 429 | Respetar Retry-After; sin reintento automático de mutaciones. No equivale a fallo de contraseña ni bloqueo escalonado. |
| Red/5xx | Resultado incierto. No anunciar éxito ni repetir POST. Reconsulta autorizada sin secretos o intervención TI explícita. |

Abortar solicitudes al cambiar identidad/cancelar y descartar respuestas tardías
mediante generación de sesión; un aborto local no garantiza rollback remoto.
Serializar doble clic y refresh; una respuesta previa a reset puede llegar después,
pero sus tokens ya no sirven. No ejecutar refresh concurrente con transición a
login restringido. La vuelta atrás no debe restaurar secretos ni sesión anterior.
Al vencer desafío, borrar memoria y pedir nuevo inicio; el reloj servidor decide.
Primer cambio consume desafío atómicamente: dos envíos no producen dos cambios.
Respuestas con secretos usan no-store/no-cache; el consumidor debe impedir su
retención aunque intermediarios o herramientas no respeten esos headers.

## 5. Colección Postman

Importar [SPEC-018.postman_collection.json](postman/SPEC-018.postman_collection.json).
**No ejecutada en Postman en esta entrega**; validación estática no equivale a Runner.
No contiene secretos ni entorno exportado. Pasos 00–17: CSRF, TI, alta/lectura/
activación, login/cambio inicial/personal/me, reset TI, access y refresh anteriores
denegados, recuperación, renovación normal, desactivación sintética y logout.

Preparación manual, solo QA aislado:

1. TI QA sintética preexistente y personal; nunca única TI institucional. Esta
   colección crea su objetivo único `spec018-<UUID>@example.test`, sin usar IDs reales.
2. `base_url` efectivo vacío por defecto: configurar únicamente origen loopback
   `https://localhost:<puerto>` o `http://127.0.0.1:<puerto>` sin path/trailing slash.
   Set `qa_ack=SOLO_QA_AISLADO_SPEC018`. Scripts verifican variables efectivas para
   impedir bypass mediante environment, destino y orden. Loopback no demuestra
   aislamiento de datos: verificar manualmente la instancia antes de confirmar.
   Este laboratorio de regresión no expone puertos host; no cambiarlo en producción.
3. Vault local: `spec018_ti_email`, `spec018_ti_password`, `spec018_new_password`,
   `spec018_reset_password`. Dar permiso a scripts Vault en Runner local compatible.
   Usar claves QA diferentes, aleatorias y válidas según Django; para las plantillas
   se exigen 16–128 caracteres ASCII alfanuméricos o `!@#$%^&*_.+-`, sin comillas,
   backslash o saltos. Esta restricción de plantilla no cambia la API de contraseñas.
4. Cookie jar automático habilitado y limpio para ese host; no configurar Cookie
   manual. Cookies Secure requieren HTTPS confiable; HTTP solo si QA configura
   deliberadamente cookies no Secure. No debilitar configuración productiva.
5. Runner local completo, una iteración, en orden, sin retries ni redirects (la
   colección los desactiva), sin monitores/cloud/sync/export de resultados. Secretos
   pasan a variables locales `pm.variables`, nunca collection/environment/globals.
   No agregar variables persistentes con sus nombres. No guardar respuestas.
6. Errores HTTP/contrato detienen cadena y limpian variables locales. Error de red,
   cancelación o cierre del Runner pueden impedir scripts de limpieza: finalizar
   ejecución, limpiar cookie jar y revisar historial/resultados locales según la
   versión de Postman. Vault protege el origen del secreto, no las respuestas,
   cuerpos resueltos ni copias de historial. Usar perfil local desechable sin sync.
7. Éxito deja objetivo inactivo, no lo elimina. Ante interrupción puede quedar
   activo: identificarlo por correo QA de la ejecución, reconciliar y desactivarlo
   manualmente con TI QA. No reanudar una mutación a ciegas. Logout final limpia
   refresh del objetivo, no revoca automáticamente el access TI de otra identidad.

La colección no sustituye las pruebas Django de expiración, estado ausente,
concurrencia o cinco roles. QA **real en navegador queda pendiente** para CSRF,
preflight/CORS, cookies Strict/Secure, navegación atrás, memoria y carreras UI.
No se ejecutaron pruebas ni build frontend por la restricción de alcance.
