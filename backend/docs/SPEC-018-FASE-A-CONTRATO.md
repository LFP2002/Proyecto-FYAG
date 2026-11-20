# SPEC-018 Fase A — contrato backend / integración React

Contrato de implementación, 20-11-2026. No declara SPEC-018 completada.
Autorización conversacional del responsable: **solo desarrollo y QA**.
Credencial temporal 86400 segundos y desafío 300 segundos, configurables mediante
`FYAG_CREDENCIAL_TEMPORAL_TTL_SECONDS` y `FYAG_PRIMER_CAMBIO_TTL_SECONDS`.
Ambos son **NO RATIFICADOS PARA PRODUCCIÓN**. Reloj del servidor, expiración
inclusiva (`ahora >= vence` rechaza); plazo temporal desde generación, no activación.
Entrega exclusivamente manual entre cuentas sintéticas QA; sin email/chat/SMS.

## Estado

`is_active` sigue siendo exclusivamente administrativo. La lectura administrativa
añade `estado_credencial` (`PERSONAL`, `INICIAL`, `RECUPERACION`, `NO_DISPONIBLE`) y
`cambio_obligatorio` (false solo para PERSONAL). INICIAL/RECUPERACION exigen cambio
aun si están vencidas. Las cuentas históricas conservan hashes y sesiones; no
se les impone cambio retroactivo. No se exponen versiones ni digest/desafío en GET.

**Corrección fail-closed posterior a revisión:** `NO_DISPONIBLE` es una proyección
de registro ausente/incoherente, no un cuarto estado SQL ni un bloqueo escalonado.
Nunca equivale a PERSONAL. Login, JWT, refresh, sesión Django y cambio de contraseña
se deniegan; el booleano sigue true, pero la UI no debe proponer primer cambio ni
reintentar reset: requiere revisión autorizada. No se repara al leer o guardar.
La migración 0006 conserva su backfill histórico; 0007 crea estado coherente solo
al insertar cuentas nuevas, atómicamente, incluidos bootstrap y ORM/bulk/SQL interno.

## Endpoints

- `POST /api/usuarios/`: TI activo/persistido con sesión normal vigente.
  JSON: `email`, `username`, `rol`; opcionales `first_name`, `last_name`.
  `password` y campos administrados se rechazan con 400. Retorna 201 con proyección
  administrativa habitual, los dos campos de estado y `credencial_temporal` y
  `credencial_vence_en` (ISO8601). Cuenta inactiva, estado INICIAL.
- `POST /api/usuarios/{id}/restablecer-clave/`: TI, cuenta ajena y
  `{"motivo":"texto no vacío"}`. Retorna 200 con la misma proyección excepcional,
  estado RECUPERACION. No activa la cuenta. Nuevo hash/versión y desafíos previos
  invalidados. Contraseña solo aparece en esta respuesta; si se pierde, reemitir.
  Si falta estado coherente del objetivo: 409 `seguridad_no_disponible`, sin crear
  estado ni modificar hash, versión o auditoría. No es una reparación implícita.
- `POST /api/usuarios/{id}/establecer-clave/`: ruta retirada, nunca establece clave;
  TI autorizado recibe 409 `operacion_retirada` (autooperación: 409 protegida).
  No acepta nueva_clave como alternativa. Otros roles siguen denegados.
- `POST /api/auth/login/`: email/password y CSRF como antes. PERSONAL conserva
  respuesta actual access/user/csrfToken y refresh exclusivamente HttpOnly.
  Temporal activa y vigente retorna **200** exclusivamente
  `{"estado":"CAMBIO_OBLIGATORIO","desafio":"<opaco>","desafio_vence_en":"<ISO8601>","csrfToken":"<rotado>"}`.
  No access, user ni refresh operativo; se elimina cookie refresh anterior del
  navegador. Nueva emisión invalida el desafío anterior. Expiración de desafío
  limitada también por vencimiento de la credencial temporal.
- `POST /api/auth/primer-cambio-clave/`: JSON estricto
  `{"desafio":"<opaco>","nueva_clave":"<entrada del titular>"}`, con cookie CSRF y
  X-CSRFToken vigentes. No necesita Bearer y no lo utiliza. 200
  `{"estado":"CLAVE_PERSONAL_CONFIRMADA","login_requerido":true}`; sin sesión
  automática, elimina cookie refresh. Consumo, nuevo hash, estado PERSONAL,
  incremento de versión y evento se confirman atómicamente. La contraseña temporal
  no puede reutilizarse; validadores Django vigentes.
- `POST /api/auth/cambiar-clave/`: sesión normal, clave_actual/nueva_clave, 204
  y nuevo login como antes. Temporal no autentica este recurso ni `/me/` ni negocio.
- GET de usuarios/listas/historial y respuestas posteriores nunca recuperan claves.
  No hay endpoints de bloqueo/desbloqueo escalonado en esta fase.

## Errores y repetición

- 400: esquema/tipos/campos prohibidos/validadores de nueva_clave, sin eco del valor.
- 401 genérico: login inválido, cuenta inactiva, temporal vencida, JWT revocado,
  estado de seguridad ausente o incoherente;
  desafío inválido, vencido, consumido, reemplazado o ligado a versión anterior:
  `{"detail":"Desafío no disponible."}`. No revelar identidad ni motivo interno.
- 403: CSRF u otro rol; flags staff/superuser no dan TI.
- 404: cuenta no accesible para TI; permisos se comprueban antes de revelar cuentas.
- 409: conflictos administrativos existentes o ruta retirada.
- 429: throttles existentes; el primer cambio reutiliza el límite IP de refresh,
  sin introducir umbrales de bloqueo de cuenta. Nunca contar 429 como fallo de clave.
- Sin reintentos automáticos de reset/alta/primer cambio tras red/5xx. Reconciliar
  estado; una credencial perdida exige reemisión TI y un desafío perdido permite
  login temporal nuevo mientras la credencial siga vigente. Dos resets pueden
  confirmar en secuencia, pero solo la última credencial queda utilizable.
- Respuestas con secretos: `Cache-Control: no-store`, `Pragma: no-cache`.

## Persistencia, auditoría y concurrencia

Tabla SQL 1:1, con estados y constraints; desafío opaco aleatorio con digest SHA256
único y sin texto claro persistido. Identidad/versionado/TTL y consumo se verifican
bajo lock del usuario antes de mutar estado. Auditoría sin snapshots de secretos:
CREACION existente y CREACION_CREDENCIAL_TEMPORAL, REEMISION, CAMBIO_INICIAL.
Eventos históricos conservados. Reset: mutex TI → usuarios por PK → seguridad;
login/refresh/cambio: usuario → seguridad, nunca adquirir mutex después de usuario.
Sin locks de Obras/Finanzas. Un login/refresh anterior al reset puede responder,
pero sus tokens ya no sirven después del reset. No prometer orden de entrega HTTP.

## Integración React posterior (no implementada aquí)

Guía de consumo para el equipo externo y colección QA:
[SPEC-018-INTEGRACION-FRONTEND.md](SPEC-018-INTEGRACION-FRONTEND.md).
Las temporales solo autentican con request POST resuelto a LoginView en
`/api/auth/login/`; sin request, admin, otras rutas o contexto incompleto se deniegan.
Las personales conservan autenticación Django sin request. No hay bypass para tests.

- `auth/client.js` y AuthContext: estado CAMBIO_OBLIGATORIO separado de authenticated;
  no `/me/`, refresh ni montaje de negocio; desafío solo en memoria, borrar al
  finalizar/cancelar/logout/cambiar identidad. No localStorage/sessionStorage/URL.
- Nueva pantalla de cambio inicial; renovar CSRF según login, confirmación local
  de nueva clave y navegación a login tras 200. No anunciar sesión iniciada.
- `Usuarios.jsx`: quitar campo password del alta y nueva_clave de reset TI;
  usar restablecer-clave con motivo/confirmación. Capturar la respuesta excepcional
  antes de relecturas; mostrar secreto confidencial una vez, no guardarlo en cache,
  historial, telemetría ni capturas. Cerrar pantalla borra el secreto en memoria.
- Mantener comportamiento SPEC-006C de correo propio, scopes/abortos y escrituras
  inciertas. La UI antigua no es compatible con alta/reset nuevos: necesita esta
  integración antes de despliegue. No se degrada backend para mantener el bypass.

## Pendientes

Frontend, bloqueos escalonados y umbrales, política productiva de TTL/canal,
recuperación institucional de única TI, retención de eventos, TLS confiable y
autorización de despliegue. No modificar confianza Windows ni PR documental #45.
