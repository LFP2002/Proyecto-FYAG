# SPEC-018C — Bloqueos escalonados por intentos fallidos y recuperación TI (solo backend)

> **Estado:** POLÍTICA DE UMBRALES RATIFICADA POR EL RESPONSABLE — 20-11-2026. Los valores de la sección 4 están aprobados para diseño e implementación backend, **no constituyen autorización de despliegue en producción**. Recuperación de la única TI, comunicaciones de error, retención y otros puntos de la sección 13 siguen pendientes. No existe implementación de esta Fase C.
> **Rama:** `docs/spec-018c-bloqueos-escalonados-backend` (desde `main`).
> **Dependencias:** SPEC-018 general en PR [#45](https://github.com/LFP2002/Proyecto-FYAG/pull/45) y Fase A backend en PR [#46](https://github.com/LFP2002/Proyecto-FYAG/pull/46), commit `01bb982ac60c96f4e2558ccfd36b5022c5430637`, **ambos Draft/no fusionados** en la fecha de redacción.
> **Contrato de trabajo FYAG:** únicamente backend Django/DRF/PostgreSQL, documentación OpenAPI y pruebas automatizadas/Postman. **No modificar `frontend/`** salvo autorización expresa. El equipo frontend consumirá contratos API completamente documentados.

## 1. Requerimiento de negocio confirmado

El responsable del proyecto indicó, tras hablar con el profesor:

1. Registrar los intentos reiterados de contraseña incorrecta.
2. Aplicar bloqueos de tiempo progresivos.
3. Ante reincidencia tras los bloqueos temporales, desactivar **operativamente el acceso** y comunicar al titular que debe solicitar intervención de TI para restablecer su contraseña.
4. Solo un Administrador TI autorizado puede efectuar la recuperación administrativa una vez alcanzado el bloqueo definitivo.
5. Conservar trazabilidad, seguridad de cuentas, roles actuales y servicios existentes.

**Importante:** se interpretará «desactivar la cuenta» como impedir efectivamente el acceso por motivos de seguridad, **sin alterar automáticamente `Usuario.is_active`**. Ese campo ya representa la activación/desactivación administrativa y su cambio tiene invariantes sobre última TI/Gerencia y obligaciones operativas de técnicos. Los estados de seguridad deben distinguirse y exponerse a TI mediante API.

## 2. Precedencia e invariantes

- SPEC-002A/002B: autenticación por email, CSRF, JWT versionados, access solo en memoria, refresh HttpOnly/Secure/Strict y límites de login existentes.
- SPEC-006/006B/006C: TI exclusivo, protección de última TI/Gerencia, mutex administrativo, historial, cambio de correo propio y revocación.
- SPEC-018 Fase A: `SeguridadCredencial` `PERSONAL/INICIAL/RECUPERACION` y estado proyectado `NO_DISPONIBLE`; migraciones 0006 y 0007, hash/TTL/desafío/primer cambio; denegación fail-closed. **No reinterpretar `NO_DISPONIBLE` como bloqueo por contraseña incorrecta.**
- Una cuenta nueva permanece inicialmente inactiva hasta activación explícita por TI. El bloqueo de seguridad no la activa, no prolonga credencial temporal y no repara estados ausentes.
- El frontend no determina autorización ni contadores. CORS/CSRF no sustituyen los controles del backend.
- Sin modificación de pagos, presupuestos, costos, obras, MongoDB, roles ni entidades comerciales.

## 3. Estados propuestos

| Estado de acceso | Significado | Conducta |
| --- | --- | --- |
| `NORMAL` | Sin bloqueo por intentos | Puede seguir autenticándose si `is_active` y credencial son válidos. |
| `BLOQUEO_TEMPORAL` | Bloqueo de duración definida por configuración | Rechazar autenticación durante el intervalo; sin reiniciar ni extender reloj por un intento durante el bloqueo. |
| `REQUIERE_TI` | Reincidencia sobre umbral; recuperación obligatoria | Denegar acceso y solicitudes protegidas hasta intervención TI documentada. |
| `NO_DISPONIBLE` | Estado persistido ausente/corrupto, **no** cuenta incorrecta | Denegar, investigar y restaurar de modo autorizado; no restablecer ni generar PERSONAL automáticamente. |

Los estados de acceso son **independientes** de `SeguridadCredencial.estado` y de `is_active`. `NO_DISPONIBLE` ya es una proyección del estado de credenciales, no crear una transición automática desde ese estado por fallos de login.

El vencimiento de un bloqueo temporal habilita un nuevo intento; no elimina eventos ni el historial de ciclos de bloqueos. La caducidad se mide en UTC con reloj del servidor y se presenta en zona `America/Santiago`.

## 4. Umbrales RATIFICADOS — implementación backend autorizada con condiciones

| Parámetro | Valor confirmado | Estado |
| --- | --- | --- |
| Intentos inválidos consecutivos | **5** | RATIFICADO 20-11-2026 |
| Ventana móvil para contar fallos | **15 minutos** | RATIFICADO 20-11-2026 |
| Primer ciclo de bloqueo | **15 minutos** | RATIFICADO 20-11-2026 |
| Segundo ciclo | **60 minutos** | RATIFICADO 20-11-2026 |
| Tercer ciclo | **240 minutos** | RATIFICADO 20-11-2026 |
| Cuarto ciclo dentro de 24 h | **`REQUIERE_TI`** | RATIFICADO 20-11-2026 |
| Ventana de reincidencia de ciclos | **24 horas** | RATIFICADO 20-11-2026 |
| Intentos durante bloqueo | No reinician ni prolongan plazo | Propuesta técnica |
| Recuperación definitiva | TI verifica identidad y reemite credencial temporal | Requerimiento funcional; detalle operativo pendiente |

**Política confirmada:** el primer grupo de cinco fallos activa 15 min. Tras expirar, cinco fallos nuevos activan 60 min; el tercer grupo, 240 min; si ocurre un cuarto grupo de cinco dentro de 24 horas, requiere TI. El inicio y expiración exactos de la ventana de reincidencia, y cómo un login correcto afecta a la racha o a ciclos previos, requieren definición técnica explícita y pruebas que no debiliten los umbrales confirmados. La propuesta conservadora es mantener el historial de ciclos durante 24 h aunque ocurra un login correcto; documentar esta interpretación antes de implementarla.

Los valores anteriores quedaron ratificados en esta conversación para el desarrollo del backend. Deben centralizarse en configuración validada y probarse en fronteras temporales. **La ratificación funcional no autoriza despliegue en producción:** falta aprobar recuperación institucional de única TI, mitigaciones contra bloqueo malicioso, política de errores y retención. Si falta configuración obligatoria o habilitación operativa, fallar en arranque/validación, no «activar silenciosamente» seguridad débil.

## 5. Modelo de persistencia propuesto

Crear un agregado SQL **1:1 por Usuario**, independiente de `SeguridadCredencial`, con:

- Estado de acceso, racha de errores, inicio de ventana, inicio/expiración de bloqueo, número de ciclos dentro de ventana, timestamp del primer ciclo, versión de control/concurrencia y timestamps de última modificación.
- Constraints para impedir estados imposibles (bloqueo temporal sin vencimiento, `REQUIERE_TI` con desbloqueo automático, contador negativo, fechas no conscientes, etc.).
- Eventos inmutables `FALLO_CREDENCIAL` (preferentemente agregado/coalescido, sin cada contraseña), `BLOQUEO_TEMPORAL`, `BLOQUEO_TI`, `DESBLOQUEO_TI` y `CREDENCIAL_REEMITIDA`. Evitar crecimiento sin límite de un evento por intento si no es necesario.
- Actor tipado `SISTEMA`, `TI` o `TITULAR`, relación opcional con cuenta interna según modelo, motivo codificado y descripciones acotadas. **No inventar un usuario real «SISTEMA» para satisfacer un FK.**
- Nunca almacenar contraseña ingresada, prefijos/sufijos, valores JWT, cookies, desafíos, IP completas sin necesidad justificada ni hashes de entradas fallidas.
- Migración aditiva y backfill seguro: cuentas existentes `NORMAL` sin alterar hashes/roles/actividad/eventos; las cuentas inconsistentes `NO_DISPONIBLE` siguen denegadas y no se reparan.
- Generación atómica del estado para cuentas nuevas consistente con el trigger 0007 o mecanismo SQL igualmente transaccional. Evitar señales ORM que omitan `bulk_create`.

La política de retención y minimización de eventos es **pendiente de ratificación**. La auditoría operativa no debe depender de mensajes temporales del futuro chat.

## 6. Concurrencia y orden transaccional

1. Preservar orden existente: administración TI toma mutex administrativo → usuarios por PK ascendente → estado de credencial → nuevo estado de acceso, de ser necesario; el orden final se fijará tras auditar usos en Fase A.
2. Login: cargar/lockear Usuario por PK → estado de credencial → estado de acceso; serializar incremento de errores, bloqueo y emisión de JWT/desafíos. No iniciar lock administrativo después de lock de Usuario.
3. No adquirir locks de Obras, Presupuestos, Finanzas o Documentos luego del usuario. No provocar N+1 por endpoint; integrar precargas en autenticación y consultas administrativas.
4. Dos intentos simultáneos que cruzan umbral activan **un solo** ciclo de bloqueo. Un acierto concurrente no emite tokens operativos si el bloqueo ya confirmó primero.
5. Si una sesión/tokens se emitieron antes de una transición confirmada a `REQUIERE_TI`, el estado persistido debe impedir su reutilización posterior. Verificar versión y bloqueo en autenticación, refresh y permisos; no confiar en claims o memoria de workers.
6. Mantener throttles de IP/email pero **no contabilizar 429 como contraseña inválida**. CSRF, errores de red o formato no cuentan. Revalidar identidad y contraseña con defensas contra enumeración.
7. Definir estrategia para intentos sobre cuentas inexistentes sin permitir diferenciarlas por error, duración o cabeceras. Los contadores por cuenta solo se crean para cuentas existentes, sin exponer si existen.

## 7. Respuestas API previstas (backend, no implementadas)

### Login `POST /api/auth/login/`

- Contraseña incorrecta, cuenta inexistente/inactiva o credencial temporal vencida → 401 genérico existente `{"detail":"Credenciales inválidas."}`. No indicar cuenta ni si se alcanzará un umbral en el siguiente intento.
- Contraseña correcta **y** bloqueo temporal comprobado: **propuesta** 423 con `{"code":"bloqueo_temporal","detail":"Acceso temporalmente bloqueado.","disponible_desde":"<ISO8601>"}`. No emitir JWT, refresh ni desafío. **Importante:** comprobar contraseña antes de devolver estado diferenciado; de lo contrario podría enumerarse la cuenta con solo conocer email.
- Contraseña correcta y `REQUIERE_TI`: **propuesta** 423 con `{"code":"solicitar_ti","detail":"Cuenta bloqueada por seguridad. Solicite a TI el restablecimiento de su contraseña."}`, sin JWT ni cookie operativa.
- `NO_DISPONIBLE` mantiene 401 genérico; esta inconsistencia nunca se auto-repara desde login.
- Protección 429 por throttles de IP/email prevalece; no contar su respuesta como fallo de contraseña.
- La política de difusión de `Retry-After` y 423 depende de aprobación anti-enumeración y de pruebas. La UI futura podrá distinguir estados por `code`, pero no se implementa React en esta etapa.

### Administración TI

- GET `/api/usuarios/{id}/` y listado: ampliar la proyección exclusivamente para TI con `estado_acceso`, `bloqueado_hasta` (nullable) y datos mínimos de reincidencia requeridos por la operación, **sin** exponerlos en `/api/auth/me/` ni en módulos de negocio.
- POST `/api/usuarios/{id}/restablecer-clave/`: si `REQUIERE_TI`, reemitir nueva credencial temporal usando el flujo ya implementado, con motivo, transacción, revocación y auditoría, **solo** después de la verificación institucional del titular. No reactivar `is_active` implícitamente. El éxito libera bloqueo únicamente si la nueva temporal fue confirmada.
- **Alternativa por ratificar:** POST `/api/usuarios/{id}/desbloquear-seguridad/` para liberar bloqueo sin cambiar clave. **Recomendación:** no permitirlo en `REQUIERE_TI`, pues el acuerdo del profesor exige restablecer contraseña; si se acepta, exigir razón excepcional, autorización y auditoría.
- Las operaciones administrativas existentes de activar/desactivar/cambiar rol/cambiar email no deben liberar el bloqueo por efecto lateral.
- Los cambios confirmados deben ser idempotentes donde corresponda; **no** repetir automáticamente POST de restablecimiento después de timeout/5xx: la última credencial generada es la válida.
- Errores: 400 validación, 401 sesión revocada, 403 rol, 404 recurso no accesible, 409 conflicto/revisión, 423 acceso bloqueado (si se ratifica), 429 throttle. Mantener `Cache-Control: no-store` en respuestas sensibles.

## 8. Recuperación TI y el problema del único Administrador TI

El requisito «solo TI recupera la cuenta» necesita un procedimiento excepcional seguro si se bloquea la única cuenta `ADMINISTRADOR_TI`.

- **Preferencia de arquitectura:** disponer de dos cuentas TI institucionales administradas de forma independiente, con credenciales seguras y responsabilidad de recuperación definida.
- **Si solo existe una:** documentar un proceso manual fuera de banda con verificación de identidad, doble autorización humana, intervención auditada y respaldo; no convertir `crear_primera_ti` en bypass ni permitir que Gerencia adquiera rol TI implícitamente.
- **Pendiente:** confirmar quién autoriza esa recuperación, si el único TI también podrá llegar a `REQUIERE_TI`, y el mecanismo extraordinario autorizado. **No implementar bloqueo irreversible de la única TI** sin un plan aprobado.
- Un atacante que conozca el correo de un tercero puede forzar intentos fallidos. Evaluar controles de mitigación (rate limits por IP/red/identidad, señales de abuso y retardos) sin ofrecer una vía de bypass para sesiones válidas o cuentas privilegiadas.
- Bloqueos temporales y definitivos nunca deben eliminar obligaciones operativas, reasignar Técnicos, borrar historial ni cambiar roles.

## 9. Compatibilidad con credenciales temporales y primer cambio

- Las credenciales temporales emitidas por alta/recuperación siguen durando **24 horas en QA**, desafío de primer cambio **5 minutos en QA**, ambos NO RATIFICADOS PARA PRODUCCIÓN.
- El control de bloqueos aplica a la comprobación de contraseñas tanto de estado `PERSONAL` como de `INICIAL/RECUPERACION`, salvo excepción definida y probada explícitamente.
- Un desafío válido para primer cambio no puede saltar un bloqueo de seguridad confirmado; el proceso debe denegar y exigir nuevo flujo autorizado cuando corresponda.
- Un reset TI revoca desafíos, access y refresh anteriores, conserva `is_active` y exige primer cambio; la recuperación del bloqueo no debe abrir una sesión normal.
- Cambios de correo, cambio personal y `refresh` respetan los bloqueos sin vaciar sus contadores ni sus eventos, salvo transición explícita aprobada.

## 10. Pruebas automatizadas imprescindibles

**Usuarios y backend (Django/DRF/PostgreSQL):**
1. Racha de fallos por cuenta existente y normalización email; identidad inexistente no revela existencia.
2. Cuarto/quinto intento en misma ventana, frontera exacta del reloj y reinicio de ventana.
3. Primer, segundo y tercer bloqueo con duraciones ratificadas; cuarto ciclo dentro de 24 h → requiere TI. Probar transiciones y fronteras exactas.
4. Ningún intento durante bloqueo prolonga `bloqueado_hasta`; contraseñas correctas e incorrectas respetan bloqueo sin bypass.
5. Un login válido fuera del bloqueo reinicia la racha, conserva historia de ciclos y no elimina evidencia.
6. `429`, errores CSRF/JSON, errores de red y cuenta inexistente no incrementan el contador persistido de contraseña incorrecta.
7. Dos o más logins concurrentes alrededor de umbral crean una sola transición; PostgreSQL real, conexiones independientes.
8. Login/refresh/JWT concurrentes con bloqueo definitivo y reset TI; versiones y denegación consistentes.
9. Acceso de la cuenta bloqueada a Obras, Finanzas, Documentos, Adjuntos, Auditoría, Alertas, Dashboard y Reportes → sin bypass incluso si access token fue emitido antes del bloqueo.
10. Login temporal y desafío de primer cambio no permiten eludir bloqueo.
11. Restablecimiento TI con motivo: libera bloqueo según política y emite temporal únicamente una vez; no activa `is_active` ni altera rol.
12. Usuario de otro rol, flags `is_staff/is_superuser` o TI con sesión revocada no puede recuperar cuentas.
13. Falla de persistencia durante bloqueo o reset revierte contador/estado/eventos como una unidad.
14. `NO_DISPONIBLE` conserva fail-closed; no crear PERSONAL a ciegas ni reparar hashes.
15. Migraciones 0006/0007 → nueva, rollback documental, preservación de cuentas históricas y tabla de seguridad por nueva cuenta.
16. Verificar ausencia de secretos/PII sensible en logs, auditoría, API, OpenAPI y Postman.
17. Verificar no-N+1 en autenticación y consultas administrativas, manteniendo contratos de presupuesto SQL.
18. Suite completa backend, `manage.py check`, `makemigrations --check --dry-run` y tests de concurrencia.

**Postman QA:** flujo secuencial sobre **cuentas sintéticas** en laboratorio aislado, usando cookies/CSRF reales, sin reintentar mutaciones automáticamente. Separar pruebas de bloqueo temporal del bloqueo TI para no dejar cuentas institucionales deshabilitadas. La prueba de bloqueo definitivo exige confirmación de disponer de TI QA de recuperación y plan manual de salida.

**Contrato frontend:** documentar OpenAPI 3.1, estados/códigos, ejemplos válidos, compatibilidad JWT/CSRF/cookies, reacción ante 423/429/401 y ausencia de JWT en bloqueos; no editar `frontend/`.

## 11. Propuesta de arquitectura y entregas

1. **Esta rama, documentación:** umbrales ratificados; conservar pendientes el caso de única TI, la política de respuestas y otras salvaguardas antes de habilitar operación real. No escribir backend en este PR.
2. **Fase C1 backend:** migración y modelo de estados, contadores transaccionales y eventos; sin activar umbrales en producción. Puede exigir subfase después de ratificación.
3. **Fase C2 backend:** integración de login, JWT/refresh/autenticación Django y reset TI; pruebas de seguridad y concurrencia.
4. **Fase C3 QA:** documentación OpenAPI, Postman aislado, pruebas de regresión y CI con evidencia reproducible.
5. **PR de implementación dedicado** posterior al PR #46 o correctamente apilado; **sin merge ni despliegue** hasta aprobación expresa.

No crear rama implementadora desde un `main` que no incluya Fase A sin aclarar dependencia. Mantener commits de Fase C separados y no extender PR #46 con cambios de esta fase. Los umbrales están confirmados; otras reglas operativas siguen pendientes.

## 12. Riesgos y límites operacionales

- **Denegación de servicio dirigida:** un tercero puede bloquear cuentas legítimas con correos conocidos. Evaluar limitaciones de abuso y alertas, evitando que un CAPTCHA o mensaje de error exponga existencia.
- **Pérdida de acceso TI:** sin recuperación extraordinaria documentada, un único administrador podría quedar bloqueado indefinidamente.
- **Disponibilidad y consistencia:** serialización SQL con `select_for_update` en login puede afectar throughput bajo ataque; medir contención y no relajar locks por conveniencia.
- **Privacidad:** mantener datos de intentos por mínimo necesario, con retención aprobada. No registrar contraseñas ni entradas en claro.
- **Integración:** equipos frontend deben basarse en OpenAPI, no inferir la política por temporizadores locales.
- **Producción:** TLS confiable, cookie Secure/Strict, proxy y logging sin secretos, respaldo/restauración, monitoreo y pruebas de carga antes de habilitar.

## 13. Política confirmada y decisiones operativas aún pendientes

1. **RATIFICADO 20-11-2026:** **5 intentos**, ventana de **15 min**, bloques de **15/60/240 min**, **cuarto ciclo dentro de 24 h** → `REQUIERE_TI`. No volver a presentar estos parámetros como pendientes de aprobación.
2. Confirmar que `REQUIERE_TI` exige **reemisión de credencial temporal** y primer cambio, sin desbloqueo simple.
3. Decidir el alcance de bloqueo temporal sobre **access JWT ya emitidos**, refresh y sesiones existentes. Se recomienda revocación de sesiones ante bloqueo confirmado, pero exige evaluar mitigación de ataques de bloqueo.
4. Aprobar la semántica del **423 solo después de contraseña correcta**, o elegir 401 genérico + canal institucional de recuperación para evitar cualquier filtración.
5. Definir plan de recuperación cuando la cuenta TI afectada es **la única TI**.
6. Acordar retención mínima de eventos de seguridad y tratamiento de IP/metadatos.
7. Confirmar que sigue vigente el veto de cambiar `is_active` automáticamente por intentos fallidos, preservando integridad de Obras y roles.

**No se ejecutaron tests, Postman ni código de esta Fase C en esta rama documental.** Los umbrales de sección 4 están ratificados como requisito funcional para implementación backend; esto **no** acredita implementación, aptitud para producción ni aprobación de los puntos pendientes.
