# SPEC-018C — C3: validación de seguridad backend

Fecha: 20-11-2026. Rama exclusiva `feature/backend-018c-c3-validacion`.
Base exacta: `54bde4dd0cff935f4f68ae5bdc88481cbc97acd9` (C2).

**Conclusión:** dos defectos reproducidos y corregidos, con regresiones nuevas.
**246/246 Usuarios y 1040/1040 backend aprobadas sobre el código final congelado.**
La aprobación de pruebas QA **no cierra SPEC-018 ni acredita aptitud productiva**.
No se autoriza merge, despliegue, activación real ni recuperación institucional.

## 1. Estado y alcance real

| Clasificación | Alcance |
| --- | --- |
| IMPLEMENTADO | A/C1/C2 heredadas; C3 añade guarda de reemisión de última recuperadora QA, rechazo de hashes malformados en login A/C2 y 13 pruebas. |
| PROBADO | PostgreSQL real aislado: regresiones dirigidas, carreras, SQL/triggers, HTTP Django/DRF con CSRF; contratos estáticos y mocks Postman. Resultados finales en §4. |
| PENDIENTE | Runner local/Vault, navegador real/React, carga representativa, indistinguibilidad estadística y decisiones institucionales de §7. |
| NO AUTORIZADO | Merge/despliegue/producción; cambios frontend/main/PR #46/#48/#49; cuentas o bases institucionales. |

Rectoras revisadas: [SPEC-018](../../specs/018-seguridad-credenciales-bloqueos.md),
[SPEC-018C](../../specs/018c-bloqueos-escalonados-backend.md), informes
[C1](SPEC-018C-C1-IMPLEMENTACION.md), [C2](SPEC-018C-C2-IMPLEMENTACION.md) y
[consumo C2](SPEC-018C-C2-CONSUMO.md). Los estados históricos de las SPEC no se
reescriben. Se conserva la política ratificada: **5 fallos/15 min; 15/60/240 min;
cuarto ciclo en 24 h → REQUIERE_TI**. Sin nuevos defaults productivos.

Auditoría de código: `usuarios/backends.py`, `authentication.py`, `serializers.py`,
`credenciales.py`, `autenticacion_c2.py`, `acceso.py`, `configuracion_c2.py`,
`recuperacion_c2.py`, `bloqueos.py`, `politica_bloqueos.py`, modelos, servicios TI,
vistas, throttles, cookies, configuración CORS/CSRF y migraciones 0006–0009.
Se revisaron las revalidaciones de Documentos/Adjuntos y los contratos/rutas de
Obras/Finanzas; la regresión global es la comprobación automatizada del resto de
módulos. No es una certificación formal ni una prueba exhaustiva de toda
intercalación posible, dependencia externa o ruta de red/navegador.

### Resultados de la revisión

- Login C2: hash único fuera de atomic/locks, sin setter; snapshot de identidad,
  hash, versión, rol, actividad y estado temporal revalidado bajo lock. Snapshot
  obsoleto deniega sin contar ni reintentar hash dentro del lock.
- Fallo real retorna `None` y confirma el contador antes de emitir 401. Errores de
  DB/emisión revierten atomic; no se cuentan CSRF/JSON/429/inexistentes/tokens.
  La nueva captura de formato no absorbe errores SQL ni excepciones arbitrarias.
- Login A conserva su doble comprobación y hashing bajo lock de emisión. Es una
  limitación de coste/contención heredada, no se rediseñó por estilo en C3.
- C2 TI: mutex 6006006 → usuarios por PK → credencial → acceso. Administración:
  mismo mutex → TI/Gerencias activas/actor/objetivo por PK. Login ordinario,
  refresh y primer cambio: usuario → credencial → acceso. No se añade inversión
  de locks. La guarda nueva de reset se evalúa dentro de la atomic y del mutex
  que ya obtiene `_admin`; no basta una comprobación previa sin serialización.
- JWT/refresh revalidan versión/hash/actividad/PERSONAL/acceso persistidos. Refresh
  comprueba blacklist otra vez tras lock. Cada ciclo QA revoca sesiones y desafíos
  atómicamente; expirar bloqueo no resucita tokens. Sesión Django liga su hash a
  `sesion_version` en C2. REQUIERE_TI no expira ni se limpia con login correcto.
- Falta/incoherencia de credencial o acceso deniega; no se recrea estado al
  autenticar. Hash malformado también deniega, sin convertirlo en fallo de clave;
  no se modifica ni repara el hash, ni se cambia la proyección administrativa del
  agregado de acceso por esa razón.
- Recuperación: TI persistido/activo, sesión personal vigente, objetivo ajeno,
  motivo; reemisión CSPRNG + versión + desafío nuevo obligatorio + auditoría.
  No reactiva `is_active` ni permite usar la clave anterior/desbloqueo simple.
- 0006 inicializa históricos sin cambiar hashes/sesiones; 0007 crea estado de
  credencial solo en INSERT; 0008 crea acceso, constraints de ventanas/ciclos y
  eventos inmutables; 0009 enlaza recuperación a REEMISION autorizada y protege
  tanto recuperación como reemisión enlazada. **0006–0009 intactas** en C3.
  Triggers activos y rechazo SQL comprobados; no se agregaron migraciones.
- Precargas evitan N+1 en JWT/lista TI; revalidaciones de permisos pueden agregar
  lecturas deliberadas. El perfil medido de login incorrecto usa más SQL para
  existente que inexistente (§5); no afirmar coste constante.

## 2. Hallazgos, causa raíz y corrección mínima

### C3-01 — Alta, disponibilidad QA: reset de última recuperadora

**Antes:** TI1/TI2 configuradas y personales; TI1 reemite TI2, que queda pendiente
de primer cambio. Una TI3 activa, personal, válida pero fuera del par configurado
podía reemitir TI1. Ambas configuradas quedaban temporales; `recuperadoras_qa()`
rechazaba nuevas verificaciones por no haber ninguna PERSONAL disponible.
Requiere privilegio TI; no es un bypass anónimo ni un cambio de umbrales.

**Causa:** la guarda protegía bloqueos y desactivación/degradación, pero no la
transición PERSONAL → RECUPERACION durante una reemisión por tercera TI.

**Corrección:** `credenciales.emitir_temporal`, solo con C2 QA habilitada y objetivo
configurado: exigir otra recuperadora personal disponible antes de generar clave,
hash o evento. Si no, `409 recuperacion_qa_protegida`. `_admin` ya mantiene mutex y
locks de las TI. Reset normal y recuperación de una TI bloqueada siguen posibles
desde la otra personal. No se ha definido recuperación institucional de única TI.

**Evidencia:** test inicial falló con `APIException not raised`; regresión final
verifica 409, hash/versión intactos y ausencia de evento adicional. Carrera real
entre dos resets de TI3 confirma solo uno y conserva una recuperadora.

### C3-02 — Media, robustez: hash persistido malformado

**Antes:** un hash identificable como PBKDF2 con coste no entero provocaba
`ValueError` en Django, propagada como error de servidor en login, tanto con C2
como sin ella. Requiere datos persistidos corruptos/importación fuera de contrato;
el endpoint no permite suministrar un hash arbitrario.

**Corrección:** en `autenticacion_c2.verificar_acceso` y
`backends.CredencialesModelBackend.authenticate`, capturar únicamente errores de
formato/tipo/desbordamiento del verificador y denegar genéricamente. Sin contar,
emitir, rehash automático ni reconstruir estado. `RuntimeError` inesperado continúa
propagándose como error interno, sin incrementar contador; no se ocultan todos los
errores bajo un 401. No se limita ni cambia el coste ratificado de hashes válidos.

**Evidencia:** regresión inicial C2 produjo un error `ValueError`; reproducción
independiente A también produjo `ValueError`. Ambas regresiones finales exigen 401;
C2 exige contador cero. No se eliminaron ni relajaron aserciones existentes.

## 3. Laboratorio y reproducibilidad

Proyecto compose **nuevo** `fyag-spec018c-c3-20261120`; nunca se reusó C2 ni compose
principal. `compose.premerge-qa.yaml` standalone + override externo para DB
`fyag_spec018c_c2_qa` (nombre impuesto por gate heredado) dentro del **nuevo**
PostgreSQL C3, host `postgres`; tests en `test_fyag_spec018c_c2_qa`. Mongo autenticado
y ClamAV C3 propios. Red interna, sin puertos host; backend montado readonly;
PostgreSQL/Mongo tmpfs. No hubo tráfico institucional ni credenciales reales.
Entorno observado: Python 3.13.18, Django 5.2.19, DRF 3.18.3, SimpleJWT 5.5.1,
psycopg 3.3.9, django-cors-headers 4.9.0; PostgreSQL de la imagen `postgres:18`.

Secretos/env/override/manifiestos/logs permanecen fuera de Git en el temporal
aprobado `C:\Users\jugue\AppData\Local\Temp\opencode\fyag-spec018c-c3-20261120`.
No publicar ese directorio indiscriminadamente. Fixtures sintéticas @example.test,
hashes PBKDF2 reales en perfil acotado; dos TI personales disponibles y logins de
ambas comprobados en proceso, sin revelar sus contraseñas. El resto de tests usa
hasher rápido explícito para determinismo; **no** se extrapola su duración a carga.

Comandos desde la raíz (abreviar el nombre de contenedor solo tras verificarlo):

```powershell
docker exec fyag-spec018c-c3-20261120-backend-1 python manage.py check
docker exec fyag-spec018c-c3-20261120-backend-1 python manage.py migrate --noinput
docker exec fyag-spec018c-c3-20261120-backend-1 python manage.py makemigrations --check --dry-run
docker exec fyag-spec018c-c3-20261120-backend-1 python manage.py migrate --check
docker exec fyag-spec018c-c3-20261120-backend-1 python manage.py test apps.usuarios --noinput
docker exec fyag-spec018c-c3-20261120-backend-1 python manage.py test --noinput
docker exec fyag-spec018c-c3-20261120-backend-1 python manage.py test apps.usuarios.tests.test_validacion_018c_c3 apps.usuarios.tests.test_concurrencia_018c_c2 apps.usuarios.tests.test_migracion_018c_c2 --noinput
git diff --check
```

Preflight real mediante `docker exec -e` con TODOS los flags del §3 de consumo C2:
`QA_AISLADO_C2`, IDs `1,2`, `CONFIRMADA`, `ACEPTADO`, `401_GENERICO`,
`REVOCAR_TODAS_QA`; ejecutar `manage.py validar_bloqueos_c2_qa`. No añadir estos
valores a defaults del proyecto. Checks estructurales no sustituyen preflight.

## 4. Resultados exactos C3

| Verificación | Resultado |
| --- | --- |
| Reproducción inicial C3-01/C3-02 | 2 tests: 1 fallo + 1 error, esperados para demostrar defectos. Log `regresiones-antes.log`. |
| Reproducción adicional C3-02 en A | 1 error esperado, log `hash-fase-a-antes.log`. |
| Dirigidas finales C3 + carreras C2 + migración C2 | **22/22 OK, 3.083 s**; incluye 13 nuevas C3. |
| Django check apagado / configuración QA explícita | 0 incidencias en ambos. |
| Preflight C2 explícito en laboratorio C3 | Aprobado; dos recuperadoras sintéticas. |
| Migraciones | Aplicación limpia hasta 0009 OK; sin cambios de modelos ni pendientes. Suites históricas de migración/reversión ejecutadas sobre test DB. |
| Usuarios final | **246/246 OK, 29.336 s**, salida 0; 233 heredadas + 13 nuevas. |
| Backend completo final | **1040/1040 OK, 267.395 s**, salida 0; 1027 heredadas + 13 nuevas. Sin fallos, errores ni skips informados; DB test eliminada normalmente. |
| Triggers/constraints | 6 triggers esperados habilitados (`O`); UPDATE/DELETE de eventos y reemisión enlazada rechazados; contadores/estado inválidos rechazados por SQL. |
| OpenAPI | A y C2 validados como 3.1 mediante openapi-spec-validator/jsonschema externos, sin dependencias nuevas en proyecto. |
| Postman estático | Schema oficial v2.1 válido, 20 pasos; scripts compilan; mock Node de 20 pasos, limpieza, escape JSON y 4 rechazos de destino/delay OK. Sin HTTP. |
| Postman Runner/Vault | **NO EJECUTADA**; ver §6. |
| Navegador real/React | **NO EJECUTADO**, frontend no modificado. |
| Secretos e integridad | 5 archivos de entrega sin hallazgos de claves privadas, JWT/GitHub literales ni secretos efímeros del laboratorio; 138 archivos protegidos y 331 Python/JSON congelados cotejados por SHA256. No es garantía absoluta de ausencia de secretos. |
| git diff --check | Comprobación de trabajo e índice previa a publicación; sin errores de whitespace. |

Runtime/tests/JSON congelados en manifiesto externo de **331 archivos** antes de
las suites finales; se cotejan al cierre. Los logs finales se guardan como UTF-8
binario directo de subprocess (`usuarios-final.log`, `backend-final.log`), con
salida real de docker propagada; no inferir éxito solo de PowerShell/Tee-Object.
SHA256 de evidencia externa final:

- `usuarios-final.log`: `d037a287c7b6b0b896cdaf00dad79e1b573d9385f7a731b5d177106b03e5b198`.
- `backend-final.log`: `b22b7628222e5654f6e9f22356466f78dbd0ecdb359957b35fa537e917a3e66b`.

Los mensajes de tokens emitidos a usuarios inactivos y errores simulados de
reportes pertenecen a casos negativos heredados; el resultado de unittest fue OK,
no se dedujo aprobación de la ausencia de mensajes en stderr.

## 5. Abuso y rendimiento: observación frente a límites

Perfil **acotado**, no ensayo de saturación ni dimensionamiento: cuatro workers
con conexiones separadas, barrera durante hash y cierre de conexiones en finally;
PBKDF2 real, cuatro aciertos al mismo objetivo. 4/4 OK, pared **0.1627 s**;
duraciones **0.1615/0.1589/0.1515/0.1514 s**, hash fuera de atomic en los cuatro.
Un fallo existente: **0.1315 s, 8 queries**; inexistente: **0.1284 s, 2 queries**.
Son muestras individuales bajo recursos locales compartidos; no constituyen
percentiles, coste constante, prueba de resistencia DoS ni indistinguibilidad.
Fuente y salida externas: `perfil_qa.py`, `perfil-qa.log`. No se agotaron conexiones
ni se indujo saturación deliberada del host.

| Riesgo residual | Evaluación / mitigación propuesta, NO implementada como política productiva |
| --- | --- |
| Bloqueo dirigido/distribuido — alto | C3 reproduce cinco IP diferentes bloqueando una cuenta. Email comparte cuota en este proceso, pero cinco verificaciones permitidas bastan; esperar/repartir IP no elimina DoS. Requiere controles perimetrales, detección adaptativa y procedimiento de asistencia ratificado, sin variar umbrales unilateralmente. |
| Enumeración — medio | Login genérico sin plazos ni Retry-After de cuenta; diferente coste SQL, estados, algoritmos legacy y contención siguen observables potenciales. Medir distribuciones con diseño estadístico antes de afirmar indistinguibilidad. |
| Hash/CPU — alto bajo abuso | Dummy para inexistentes consume hash real; hash único fuera de lock C2 evita prolongar lock por verificación, no evita CPU exhaustion. Throttle DRF no es control global de capacidad. Proponer límites de concurrencia/colas en borde y métricas sin identidades/secretos. |
| Throttle distribuido — alto | Sin caché compartida explícita no asumir cuota global entre workers/instancias. DRF no garantiza contadores atómicos frente a carreras; proxy/IP confiables deben configurarse y probarse. No confiar ciegamente en X-Forwarded-For. |
| Conexiones/contención — medio/alto | Esperas mantienen conexiones; mutex TI serializa administración y bloqueos TI. Reset/primer cambio/cambio propio aún calculan hashes bajo locks. Usar pool/límites/timeout medidos, política de errores transaccional y carga representativa; no habilitar cancelación/retries automáticos de POST inciertos. |
| Carreras — cobertura limitada | Tests observan bloqueos PostgreSQL con conexiones distintas y timeouts, no sleeps; login/bloqueo/reset/refresh y última TI cubiertos. Sin deadlock observado en esas carreras; no garantía universal ni rollback de petición autorizada antes del commit. |
| Logout — medio | Revoca refresh presente y elimina cookie; access ya emitido permanece hasta expiración/revocación por versión. C3 lo prueba explícitamente. No prometer logout global ni revocación de toda cadena concurrente de refresh. |
| Recuperación TI — alto operativo | Guarda QA reforzada; hash identificable no prueba conocimiento humano ni validez criptográfica exhaustiva. Probar acceso de ambas TI. Procedimiento institucional de única TI sigue pendiente; no usar bootstrap ni flag off como bypass. |
| SQL privilegiado/retención — medio | Triggers cubren UPDATE/DELETE normales, no DBA/superusuario, deshabilitar triggers, TRUNCATE o compromiso del rol propietario. Separar privilegios, respaldos, acceso DBA y retención aprobada. No probar destrucción sobre datos institucionales. |

## 6. Postman: NO EJECUTADA y plan manual reproducible

Colección auditada, sin cambios:
[SPEC-018C-C2.postman_collection.json](postman/SPEC-018C-C2.postman_collection.json).
`Postman.exe` existe en `%LOCALAPPDATA%\Postman`, pero esta sesión no tiene
herramienta para controlar la GUI/confirmar Runner local y permisos Vault ni una
sesión Vault QA autorizada. No se leyó almacenamiento personal ni se arrancó
Cloud/monitores; no se sustituyó por Newman/CLI. La mera instalación no demuestra
acceso seguro a Runner. Mocks/tests HTTP no son evidencia de Runner.

Ejecución humana pendiente (ver también §4 de consumo C2):

1. Crear **otro proyecto QA nuevo**, nunca arrancar principal o reutilizar datos
   institucionales. Usar standalone y secretos externos. Migrar con C2 apagada.
   Preparar dos TI sintéticas: primera por `crear_primera_ti` interactivo con
   contraseña oculta; segunda por alta/activación/primer cambio de Fase A. Confirmar
   login personal de ambas. No reutilizar ni intentar recuperar por bootstrap las
   cuentas del perfil C3, cuyas claves no se exportaron.
2. El lab auditado no expone puertos. Para Runner, preparar **solo en ese nuevo QA**
   un override externo con backend `python manage.py runserver 0.0.0.0:8000 --noreload`
   y proxy TLS dedicado hacia `backend:8000`, publicado únicamente como
   `127.0.0.1:8443:8443`. Ejemplo Caddyfile externo:

   ```text
   https://localhost:8443 {
       tls internal
       reverse_proxy backend:8000
   }
   ```

   Montar ese archivo readonly en proxy QA, con CA/estado también externos.
   Aprovisionar imagen/proxy de manera controlada; confiar **solo** la CA QA en el
   perfil Postman local desechable y verificar el certificado. No deshabilitar TLS,
   no cambiar Secure/Strict de cookies ni abrir 0.0.0.0 en el host. Esta exposición
   manual/proxy **no se ejecutó ni validó** en C3; registrar su preflight antes de
   introducir secretos. Validar CSRF_TRUSTED_ORIGINS según el origen realmente usado.
3. Configurar externamente los seis flags explícitos de consumo C2 con IDs de
   esas dos TI; `check` y `validar_bloqueos_c2_qa` deben aprobar antes de tráfico.
   Si una falla, detener; no reconstruir estado ni desactivar seguridad para pasar.
4. Perfil Desktop local desechable, sin sync/Cloud/monitor. Importar colección;
   variables `base_url=https://localhost:8443`,
   `qa_ack=QA_C2_PREFLIGHT_DOS_TI_DELAY_16000`. Sin variables persistentes que
   oculten nombres sensibles locales. Vault únicamente:
   `spec018c_c2_ti_email`, `spec018c_c2_ti_password`,
   `spec018c_c2_new_password`, `spec018c_c2_reset_password`.
5. Runner local compatible con `pm.vault`, permiso otorgado a esa colección; cookie
   jar limpio habilitado, redirects/retries desactivados, **1 iteración, delay
   >=16000 ms**, orden 00–19 completo. No ejecutar colección en paralelo.
6. Registrar fecha, versión Desktop, preflight, destino, delay, 20/20 pasos y
   aserciones o fallo exacto; redactar tokens/claves/cookies y no exportar historial
   con cuerpos resueltos. No anunciar éxito si solo se revisó schema/script.
7. Verificar objetivo sintético desactivado y logout. Red/cancelación puede impedir
   limpieza de scripts: reconciliar manualmente sin repetir alta/reset, desactivar
   objetivo si procede, limpiar jar/memoria/resultados y detener QA sin borrar
   auditoría. Vault/no-store no impiden retención de respuestas locales.

La colección cubre el primer ciclo; cuarto ciclo/expiraciones largas se prueban
con reloj controlado en PostgreSQL, sin endpoint para adelantar reloj ni reducir
umbrales. El ensayo de esperas reales de horas sigue pendiente.

## 7. Contratos React, dependencias y autorización

**Sin cambios en frontend.** El equipo React debe implementar según consumo A/C2:

- Tratar dimensiones `is_active`, credencial y acceso independientemente; campos
  C2 administrativos condicionales, nunca estado de autorización confiado al cliente.
- Login temporal no concede sesión: guardar desafío solo en memoria, primer cambio
  con CSRF y luego login nuevo; reemplazar CSRF rotado. Limpiar secretos al salir.
- Access solo memoria; refresh HttpOnly/Secure/Strict/path `/api/auth/`, credentials
  include; no leer cookie desde JS ni esperar refresh en JSON.
- 401 genérico QA, **no 423 implementado** ni temporizador revelado en login. Leer
  plazos solo desde canal TI autorizado; reloj servidor prevalece. No bucles de
  refresh ni retries automáticos de mutaciones ante red/5xx.
- Respetar 403 CSRF (posible HTML), 429 Retry-After y 409 tipado. La nueva guarda
  usa `recuperacion_qa_protegida` ya documentado; no intentar reset repetido.
- Logout borra memoria y cookie, pero no prometer revocación inmediata global de
  access. Cambio de correo propio confirmado revoca, sin relectura autenticada.

Dependencias observadas por API pública GitHub, **open/Draft, sin modificación**:

| PR | Fase / head SHA | Body SHA256 |
| --- | --- | --- |
| #46 | A, `ed0d7b68cd3b7e6a3e98df4c1700e57740c6d76a` | `5174bc319ca754ed8f19b79f9a560189a2632a61b5f62a1ec8b23e7a4059628a` |
| #48 | C1, `a7fa98ec4c09b551a40b47e4e5781d6c06b3872f` | `00b2500cc9d3005f6fac6b0da4ed410c1b66db5b2a0b1c8c7669e57884671573` |
| #49 | C2, `54bde4dd0cff935f4f68ae5bdc88481cbc97acd9` | `7ae99229e4afaa54ce396970a426b23d90bc162c1614e692bf0e1b5f07e088db` |

C3 hereda A/C1/C2 por ascendencia, no fusiona esos PR ni sustituye sus aprobaciones.
Main local `1df5da1bffa57c7fe83b4f16adb2ca6b48a71a23`, remoto observado
`8f611091f3aacce53779839b10919c957c4bd44e`, sin actualización de sus refs locales.

### Checklist para una autorización futura, NO concedida aquí

- [ ] Revisión independiente de seguridad y aprobación explícita de dependencias
  #46/#48/#49 y C3; CI del SHA efectivamente publicado (no inferirlo de tests locales).
- [ ] Runner/Vault real y navegador React en origen/TLS/cookies finales.
- [ ] Ratificar recuperación institucional de única TI, verificación de identidad,
  custodia, asistencia y simulacro sin bypass ni reactivación implícita.
- [ ] Ratificar respuesta 401/423, sesiones temporales, TTL/entrega y retención.
- [ ] Mitigar DoS, cuotas compartidas, proxy confiable, CPU/conexiones/locks;
  pruebas de carga y enumeración estadística con presupuesto seguro.
- [ ] Plan de migración/privilegios/respaldo/retención y roll-forward ensayado;
  desactivar flag NO es rollback de seguridad ni recuperación.
- [ ] Autorización **separada y explícita** de merge; ninguna en esta entrega.
- [ ] Autorización **separada y explícita** de despliegue/activación; ninguna aquí.

La publicación en la rama C3 entrega evidencia y correcciones de desarrollo/QA,
no satisface por sí sola ninguna de esas autorizaciones.
