# SPEC-018C C2 — contrato backend para equipo frontend y QA

**Implementado únicamente detrás de habilitación QA explícita, deshabilitado por
defecto. No aptitud productiva, merge o SPEC-018 completada. No se modificó React.**

Complementa [Fase A](SPEC-018-FASE-A-CONTRATO.md) y su
[guía de transporte](SPEC-018-INTEGRACION-FRONTEND.md). OpenAPI real de integración:
[SPEC-018C-C2-v1.json](openapi/SPEC-018C-C2-v1.json), versión 3.1.0. El OpenAPI
Fase A permanece intacto y define las otras operaciones existentes. El artefacto
`SPEC-018C-C2-propuesta.json` es histórico, no el contrato vigente de C2 QA.

## 1. Estados independientes

| Dimensión | Valores y significado |
| --- | --- |
| Administrativo | `is_active` true/false. Bloquear o recuperar NO modifica este campo. |
| Credencial | PERSONAL, INICIAL, RECUPERACION; NO_DISPONIBLE proyecta inconsistencia y no se repara. |
| Acceso C2 | NORMAL, BLOQUEO_TEMPORAL, REQUIERE_TI; NO_DISPONIBLE si falta/incoherente la fila. Nunca inferir NORMAL. |

Solo con C2 habilitada, respuestas administrativas de usuarios añaden
`estado_acceso` y `bloqueado_hasta` (ISO8601 o null). Ejemplo parcial TI:
`{"is_active":true,"estado_credencial":"PERSONAL","cambio_obligatorio":false,
"estado_acceso":"BLOQUEO_TEMPORAL","bloqueado_hasta":"2026-11-20T20:00:00+00:00"}`.
El resto de campos Fase A permanece. No contadores, hashes o versiones públicas.
No se añaden campos de bloqueo a `/api/auth/me/`. Con C2 deshabilitada no se
añaden estos campos administrativos y no se registran fallos operativos.

5 contraseñas incorrectas efectivamente verificadas en 15 min móviles: bloqueo
15 min; siguiente ciclo en 24 h: 60 min; tercero: 240 min; cuarto: REQUIERE_TI.
Ventanas `(t−15 min,t]`, `(t−24 h,t]`; bloqueo caduca cuando `t >= hasta`.
Reloj servidor UTC aware, aritmética absoluta incluso DST. UI puede formatear
America/Santiago; su temporizador **no** concede acceso. GET/JWT no escriben estado
ni vacían racha. Login correcto fuera de bloqueo limpia racha, no reincidencia.

En perfil QA explícito REVOCAR_TODAS_QA, cada ciclo revoca access/refresh/sesiones
Django anteriores y desafíos, atómicamente. Expirar bloqueo NO resucita tokens.
REQUIERE_TI exige reemisión autorizada; no expira por reloj ni se limpia por
acierto, correo, rol, activación o cambio propio. Una petición ya autorizada antes
del commit puede finalizar; no prometer cancelación remota de trabajo en curso.

## 2. Consumo de endpoints reales

Todos los requests JSON UTF-8, origen API confiable; nunca reenviar Bearer a
otro origen ni seguir redirects con secretos. Cookies mediante credentials include.

| Método/ruta | Entrada y respuesta real |
| --- | --- |
| GET `/api/auth/csrf/` | 200 `{csrfToken}` y cookie csrftoken; mantener token en memoria. |
| POST `/api/auth/login/` | `{email,password}` de texto. CSRF vigente. Personal: 200 `{access,user:{id,username,email,role},csrfToken}`; refresh solo cookie. Temporal: 200 solo `{estado:"CAMBIO_OBLIGATORIO",desafio,desafio_vence_en,csrfToken}`; sin sesión operativa ni `/me/`/refresh, elimina refresh previo. Login exitoso rota CSRF. |
| POST `/api/auth/primer-cambio-clave/` | Sin Authorization. `{desafio,nueva_clave}`, CSRF vigente. 200 `{estado:"CLAVE_PERSONAL_CONFIRMADA",login_requerido:true}`; borrar desafío y nueva clave, volver a login. Un desafío anterior al bloqueo no sirve. |
| GET `/api/auth/me/` | Bearer access válido; 200 `{id,username,email,role}`. Bloqueado/revocado/inconsistente: 401 sin campos de estado. |
| POST `/api/auth/refresh/` | `{}`, cookie refresh y header CSRF. 200 `{access}` y cookie rotada, sin refresh en JSON. Estado, versión, hash y blacklist revalidados bajo lock. No contar errores como contraseña incorrecta. |
| POST `/api/auth/logout/` | `{}` y CSRF. 204, sin body; elimina/revoca refresh presente. No consume desafíos opacos; borrar memoria al cancelar y respetar TTL/reemisión. |
| POST `/api/auth/cambiar-clave/` | Bearer, `{clave_actual,nueva_clave}`; 204 y nuevo login. Bloqueo se comprueba y este endpoint no es recuperación TI. |
| GET `/api/usuarios/` y `/{id}/` | Solo TI activo, personal y no bloqueado, sesión vigente. Proyección Fase A con estado C2 condicional. Lista paginada 25, filtros originales. Sin secretos en relecturas. |
| POST `/api/usuarios/{id}/restablecer-clave/` | Solo TI activo/persistido, personal no bloqueado, sesión vigente, cuenta ajena, `{motivo:"texto no vacío"}` (max 2000) y verificación manual de identidad QA. 200 proyección excepcional con nueva credencial_temporal/credencial_vence_en, RECUPERACION y acceso NORMAL. No reactiva is_active, no abre sesión, exige primer cambio. |

Alta/activar/desactivar/cambiar rol/perfil/historial conservan contratos Fase A y
guardas 006B/006C. Correo propio confirmado revoca: descartar sesión sin refresh
ni relectura autenticada. Las dos TI recuperadoras configuradas QA no se pueden
desactivar/degradar mientras C2 está activa (`409 recuperacion_qa_protegida`).
**No hay `/desbloquear-seguridad/`**, desbloqueo simple, backdoor ni rebootstrap TI.

### Errores

- **401_GENERICO QA:** login bloqueado, inactivo, expirado, inexistente, incorrecto
  o incoherente → **mismo** `{"detail":"Credenciales inválidas."}`. Sin plazos,
  contador, identidad o Retry-After de cuenta. **No se implementa 423.** Esta elección
  QA no se presenta como ratificación operativa productiva ni solución total a
  enumeración por tiempos o DoS. Throttle puede responder 429 antes de verificar.
- Desafío no disponible: 401 `{"detail":"Desafío no disponible."}`. Reiniciar
  flujo autorizado; no reutilizar ni adivinar desafíos. Sesiones denegadas usan
  detalle genérico existente; borrar access y no entrar en bucle de refresh.
- 400: esquema/tipos/validadores, sin eco del secreto. JSON inválido no cuenta.
- 403: CSRF o rol; CSRF puede devolver HTML, no asumir JSON ni mostrarlo sin sanear.
- 404: cuenta/página no disponible; permisos preceden revelación de existencia.
- 409: `{code,detail}`: seguridad_no_disponible, autooperacion_protegida,
  recuperacion_qa_protegida e invariantes originales. No reparación automática.
- 429: throttle IP/email, Retry-After vigente; no cuenta como clave incorrecta.
- Red/5xx: resultado incierto; no afirmar éxito ni reenviar POST automáticamente.
  Fallos de persistencia durante verificación/recuperación revierten toda la
  transacción. Una entrega HTTP perdida después de commit no puede deshacerlo.

Access, desafío y claves solo en memoria, sin storage/URL/logs/cachés/telemetría.
Refresh `fyag_refresh` HttpOnly/Secure/SameSite Strict/path `/api/auth/` lo gestiona
el navegador; nunca JSON ni lectura JS. Login/primer cambio/refresh/logout llevan
cookie CSRF + X-CSRFToken; sustituir token por el rotado en login. CORS con origins
explícitos y credentials, CSRF_TRUSTED_ORIGINS con esquema. Orígenes separados deben
seguir siendo mismo schemeful site para cookies Strict. CORS no sustituye CSRF.
Permisos usan rol persistido, no flags staff/superuser ni valores del frontend.

## 3. Activación exclusivamente en laboratorio

1. Proyecto compose separado del principal, PostgreSQL/Mongo efímeros y ClamAV
   dedicado. DB **fyag_spec018c_c2_qa**, host **postgres**; tests usan
   **test_fyag_spec018c_c2_qa**. Esos nombres no demuestran aislamiento por sí solos:
   verificar red/contenedor/configuración antes de declarar QA. Sin puertos host
   en el laboratorio de esta entrega, ni cambios al compose principal.
2. Migrar con C2 **apagada**. Preparar solo dos TI **sintéticas** personales activas
   mediante flujos Fase A, completando primer cambio de la segunda; no crear
   institucionales ni usar crear_primera_ti para recuperar una TI existente.
3. En configuración **externa QA**, fijar explícitamente:

   ```text
   FYAG_BLOQUEOS_C2=QA_AISLADO_C2
   FYAG_C2_TI_QA_IDS=<id_qa_1>,<id_qa_2>
   FYAG_C2_RECUPERACION_QA=CONFIRMADA
   FYAG_C2_RIESGO_DOS_QA=ACEPTADO
   FYAG_C2_RESPUESTAS=401_GENERICO
   FYAG_C2_SESIONES_TEMPORALES=REVOCAR_TODAS_QA
   ```

   Sin ATOMIC_REQUESTS: un rechazo de login debe confirmar su contador antes del
   401. No habilitar C1_SIMULACION para integrar HTTP; C2 usa el núcleo bloqueado.
4. Antes de exponer tráfico QA: `manage.py check` y
   `manage.py validar_bloqueos_c2_qa`. Preflight exige ambas TI personales, activas,
   con estados coherentes, hash utilizable/formato identificable y disponibles.
   No comprueba el conocimiento humano del secreto: confirmar manualmente acceso
   y recuperación de ambas TI sintéticas antes del ensayo. No modifica ni crea cuentas.
5. En ejecución, el motor comprueba recuperadoras persistidas. Si falta una o
   no hay al menos una personal disponible, deniega verificación por configuración
   inválida antes de contar; no se continúa silenciosamente. Bajo mutex, el
   siguiente bloqueo de una TI se impide si dejaría sin otra recuperadora útil.
   Esa guarda QA no define el procedimiento institucional pendiente.

Config inválida/no QA/sin confirmaciones/modo 423 se rechaza. Sin flag, C2 permanece
apagada; los estados persistidos no se borran. **No usar desactivar el flag como
recuperación**: quita comprobaciones C2 deliberadamente y puede alterar la validez
de cookies de sesión Django de la etapa anterior. El plan seguro es reemisión TI
y corrección roll-forward, no habilitar/deshabilitar para sortear bloqueos.

## 4. Colección Postman opt-in

[SPEC-018C-C2.postman_collection.json](postman/SPEC-018C-C2.postman_collection.json).
No contiene secretos ni environment exportado. **Runner no ejecutado** en esta
entrega; se validan JSON/schema/scripts y contratos backend, no navegador real.

- Perfil local desechable sin cloud/sync/monitor; Vault con
  `spec018c_c2_ti_email`, `spec018c_c2_ti_password`, `spec018c_c2_new_password`,
  `spec018c_c2_reset_password`. Claves QA robustas diferentes; no usar la cadena
  deliberadamente incorrecta de la colección como contraseña de la cuenta.
- `base_url` efectivo vacío por defecto: solo loopback HTTP(S), sin trailing slash
  ni path; `qa_ack=QA_C2_PREFLIGHT_DOS_TI_DELAY_16000`. Revisar instancia real antes
  de confirmar. HTTPS confiable si cookies Secure; no rebajar producción para HTTP.
- Runner local compatible con Vault, una iteración en orden, **delay >=16000 ms**,
  cookie jar limpio habilitado, sin retries/redirects. Los scripts detienen si el
  intervalo entre logins objetivo es insuficiente. Así se respetan throttles
  5/min email y 20/min IP, sin contar 429 ni deshabilitarlos en backend.
- 20 pasos: CSRF/TI/alta/activación/primer cambio/personal, cinco fallos, lectura
  TI de bloqueo, access/refresh anteriores denegados, reset con reemisión,
  primer cambio de recuperación, desactivación sintética y logout.
- No prueba cuarto ciclo automático: requeriría esperar plazos reales y plan de
  salida; los cuatro ciclos se prueban con reloj controlado en tests PostgreSQL.
  No hay endpoints QA para adelantar reloj ni reducir duraciones.
- Secrets solo Vault y variables locales de una ejecución, cuerpos con JSON.stringify
  para admitir caracteres de contraseña sin inyección. No variables persistentes
  con esos nombres, no guardar/exportar respuestas. Vault/no-store **no impiden**
  que historial, cookies o resultados locales retengan datos resueltos.
- Ante error HTTP/contrato: detiene/limpia. Red/cancelación/cierre puede impedir
  ejecutar scripts: finalizar runner, limpiar cookie jar e historial/resultados
  locales, reconciliar el objetivo sintético y desactivarlo manualmente si quedó
  activo. No repetir alta/reset por pérdida de respuesta. No borrar auditoría.

Pendientes para ambientes reales: recuperación institucional de única TI,
mitigación de DoS (la prueba demuestra el riesgo, no lo resuelve), política final
401/423 y sesiones temporales, retención, TLS, carga y revisión independiente.
