# SPEC-018 — Seguridad de credenciales, primer acceso y bloqueo escalonado (FYAG)

> **Estado: SPEC BASE RATIFICADA PARCIALMENTE — 20-11-2026.**
> Nueva etapa acordada por el responsable del proyecto tras reunión con el profesor. Los requisitos de credenciales están confirmados; **los umbrales de bloqueo de la sección 6.3 fueron ratificados posteriormente** en [SPEC-018C](018c-bloqueos-escalonados-backend.md), ya integrada en `main`. Las restantes decisiones de seguridad/operación indicadas como pendientes siguen sin ratificación.
> **Rama documental:** docs/spec-018-seguridad-credenciales-bloqueos. **Base:** main, commit 1df5da1bffa57c7fe83b4f16adb2ca6b48a71a23.
> **Estado de implementación:** la Fase A de backend fue implementada en el [PR #46](https://github.com/LFP2002/Proyecto-FYAG/pull/46), aún pendiente de merge; los bloqueos de la Fase C no están implementados. La aprobación de este documento **no autoriza** desplegar ni fusionar código de implementación.

## 1. Contexto y precedencia

1. Complementa las SPEC-002A/002B (JWT, CSRF, sesiones), SPEC-006/006B (administrador TI, usuarios y auditoría) y SPEC-006C (revocación tras cambio de correo). En caso de contradicción, las reglas nuevas deben identificarse expresamente y aplicarse solo desde la migración correspondiente; conservar los hechos históricos.
2. Código base contrastado en main: Usuario hereda AbstractUser; email es identificador único de login; rol y sesion_version se validan desde PostgreSQL; JWT access corto, refresh HttpOnly y revocación por cambio de contraseña/identidad; protección de última TI y de última Gerencia activa.
3. Hoy el endpoint de creación exige que TI suministre password y crea inicialmente un usuario inactivo. TI puede establecer una clave ajena; el usuario activo puede cambiar la propia. Login cuenta con throttles por IP y correo, pero **no** tiene política persistida de bloqueo escalonado, ni cambio forzoso de clave temporal.
4. La existencia de limitaciones de frecuencia HTTP **no** equivale a contabilizar intentos inválidos de contraseña. Los cambios deben ser transaccionales, comprobables en varios workers y mantener trazabilidad.
5. Los nuevos roles, inventario, presupuestos aprobados por Finanzas, materiales, mermas y chat pertenecen a SPEC posteriores. Esta entrega no altera RBAC de negocio.

## 2. Objetivo

- TI crea una cuenta sin elegir ni conocer permanentemente una contraseña de usuario: el servidor genera una credencial inicial aleatoria criptográficamente segura y la entrega **una sola vez** mediante un canal controlado.
- Antes de acceder a módulos de negocio, cada usuario nuevo debe definir una contraseña personal que cumpla validadores Django. No puede operar con la credencial temporal.
- Establecer bloqueos temporales progresivos por intentos fallidos y, tras reiteración, un bloqueo administrativo de seguridad que requiera intervención de TI para restablecer el acceso.
- Proporcionar mensajes claros, coherentes y no enumerables; revocar sesiones, impedir bypass por refresh/JWT y auditar cada transición relevante.
- Mantener la protección de última TI, última Gerencia, sesiones, técnicos asignados e historial administrativo preexistente.

## 3. Alcance y exclusiones

**Incluye para nuestro equipo:** backend DRF/PostgreSQL, migraciones aditivas, servicios transaccionales, serializadores, seguridad de autenticación/recuperación, tests Django/PostgreSQL, Postman, OpenAPI y documentación de consumo API para el equipo React externo. **No se modifica `frontend/` salvo autorización expresa del responsable.**

**Excluye:** MFA, SSO, registro público, acceso por username, recuperación autogestionada por correo, SMS, envío masivo de contraseñas, reseteo de la primera TI mediante el comando de aprovisionamiento, cambios en autorización de Obras/Finanzas, bloqueo de recursos de bodega, claves almacenadas en MongoDB, código de producción o cambios del reverse proxy ajenos a la autenticación.

## 4. Matriz de autoridad

| Operación | TI | Usuario titular | Otros roles |
| --- | --- | --- | --- |
| Alta de cuenta y activación/desactivación administrativa | Sí, con reglas SPEC-006B | No | No |
| Emisión o reemisión de credencial inicial temporal | Sí, sobre cuenta ajena y con motivo cuando sea reemisión | No | No |
| Primer cambio obligatorio de contraseña | No puede sustituir la voluntad del usuario | Sí, con desafío de uso único | No |
| Cambio de contraseña ordinaria | No elige la del usuario | Sí, autenticado con clave anterior | No |
| Desbloqueo administrativo por reiteración de fallos | Sí, con motivo y auditoría | No | No |
| Consultar detalle técnico de bloqueos de otros | Sí, mínimo necesario | No | No |
| Consultar datos de negocio mediante credencial temporal | No | No | No |

El rol se revalida contra la base persistida, no contra claims suministrados por el cliente. is_staff/is_superuser no confieren poderes TI. No existe elevación automática ni permisos administrativos por conocer una contraseña.

## 5. Ciclo de cuenta y credencial inicial

### 5.1 Alta desde TI

1. Mantener POST /api/usuarios/ bajo el RBAC existente. El cuerpo ya **no** aceptará password ni campos de seguridad administrados por el servidor; los intentos de enviarlos obtienen 400.
2. Generar credencial aleatoria mediante generador criptográficamente seguro del servidor, con entropía adecuada (como mínimo 128 bits), sin usar hora, nombre, email ni generadores seudoaleatorios no criptográficos.
3. Guardar exclusivamente el hash robusto permitido por Django; marcar necesidad de primer cambio en estado persistido y conservar creación de cuenta inicialmente inactiva, salvo cambio de política aprobado. El paso TI de activación permanece explícito.
4. La credencial inicial aparece **solo en la respuesta de creación autorizada**, en un campo separado del serializer de lectura, marcado no almacenado y no recuperable por GET. Mostrarla una vez en UI TI, con advertencia de tratamiento confidencial. No incluirla en logs, auditoría, errores, URLs, analítica, tests reales ni capturas de evidencia.
5. Si la entrega se pierde o expira, TI realiza **reemisión**, generando una credencial nueva; nunca se recupera la anterior. No enviar por email/SMS sin un canal seguro formalmente acordado.
6. La expiración temporal y canal de entrega se fijarán antes de implementar (sección 12).

### 5.2 Primer acceso obligatorio

1. Un usuario inactivo sigue sin poder iniciar sesión. Tras activación, puede autenticarse con credencial temporal **únicamente para iniciar cambio de clave**.
2. Una validación correcta de la credencial temporal devuelve una respuesta inequívoca de cambio obligatorio, **sin emitir access JWT normal ni cookie refresh de sesión operativa**. Se concede un desafío acotado, ligado al usuario y versión de sesión, de duración corta y un solo uso.
3. POST /api/auth/primer-cambio-clave/ recibe el desafío temporal y nueva contraseña sobre conexión con controles CSRF/cookies coherentes. Debe comprobar autenticidad, expiración, versión, consumo único y validadores Django; ningún otro recurso acepta ese desafío como Authorization.
4. Una transacción SQL confirma nuevo hash, elimina obligatoriedad, consume el desafío, incrementa sesion_version, registra evento y revoca cualquier token previo aplicable. Tras éxito, el usuario inicia **una sesión normal nueva** con su contraseña personal.
5. Si falla o caduca el desafío, no se abre sesión de negocio y se requiere repetir el acceso temporal, siempre que la credencial inicial esté vigente. El frontend no conserva secretos en localStorage/sessionStorage ni permite navegación de negocio en modo de cambio.
6. Evitar reutilizar la contraseña inicial como nueva contraseña. Los validadores de longitud, similitud y claves comunes de Django siguen vigentes.

### 5.3 Reemisión y restablecimiento mediante TI

1. Nueva acción explícita POST /api/usuarios/{id}/restablecer-clave/ con motivo obligatorio y respuesta excepcional que exhibe una nueva credencial temporal una sola vez.
2. Protecciones existentes: TI activo y vigente, prohibición de autorrestablecimiento inseguro, locks por orden establecido en SPEC-006B y prevención de desactivación del último TI.
3. Restablecer revoca JWT y refresh anteriores, fuerza primer cambio y registra quién autorizó, cuándo y por qué, sin snapshots de contraseñas ni hashes.
4. Si el usuario estaba bloqueado por seguridad, el servicio limpia el bloqueo de forma auditada. Una cuenta desactivada administrativamente no se reactiva implícitamente por el simple restablecimiento; TI sigue el flujo explícito de activación.
5. El endpoint legado /api/usuarios/{id}/establecer-clave/ que recibe una clave elegida por TI deberá cerrarse o adaptarse mediante transición documentada, nunca mantener una ruta paralela que eluda el primer cambio.

## 6. Política de intentos fallidos y bloqueos

### 6.1 Modelo de estados

- **HABILITADA:** cuenta administrativamente activa, sin bloqueo vigente y con contraseña normal.
- **CAMBIO_OBLIGATORIO:** credencial temporal válida, restringida exclusivamente al cambio.
- **BLOQUEO_TEMPORAL:** rechazar autenticación durante la ventana de bloqueo; el resto de permisos no cambia.
- **BLOQUEO_SEGURIDAD_TI:** acceso operativamente deshabilitado hasta restablecimiento autorizado por TI.
- **DESACTIVADA_ADMIN:** conserva la semántica actual is_active=False y el motivo administrativo; no se equipara automáticamente con un fallo de contraseña.

Un bloqueo de seguridad debe causar **denegación efectiva** en login, refresh, autenticación JWT y acceso a módulos aunque is_active permanezca True por integridad referencial o protección de obligaciones activas. La UI TI lo presenta como cuenta bloqueada/desactivada por seguridad, sin borrar relaciones ni falsificar una desactivación administrativa.

### 6.2 Reglas de contabilización

1. Contabilizar solo verificaciones de contraseña incorrectas contra cuenta existente, sin revelar su existencia; no contar errores de red, 429 de throttle, fallos CSRF, sesiones expiradas ni intentos con contraseña correcta.
2. Mantener en PostgreSQL un estado de seguridad por cuenta, persistente y consistente entre workers/reinicios. No depender exclusivamente del caché local de throttling.
3. Al superar umbral, registrar bloqueo temporal con horario calculado por servidor (America/Santiago para visualización; timestamps conscientes de zona en persistencia) y motivo de sistema.
4. Los intentos válidos reinician racha de fallos según la política, **no** borran eventos históricos ni deshacen un bloqueo vigente.
5. Tras los bloqueos temporales reiterados definidos, entrar en BLOQUEO_SEGURIDAD_TI. Solo TI puede desbloquearlo mediante recuperación auditada; cambios de correo, rol, refresh, JWT antiguo o perfil no lo sortean.
6. No almacenar contraseñas intentadas ni indicar cuál fue incorrecta. La respuesta a credenciales inválidas es genérica; el estado de bloqueo definitivo se comunica al titular cuando su identidad se verifica suficientemente, sin facilitar enumeración de cuentas.
7. Conservar throttles por IP/email; validar X-Forwarded-For solo a través del proxy inverso confiable. Incluir protección contra abuso deliberado de bloqueos por un atacante que conozca correos de terceros.

### 6.3 Umbrales **RATIFICADOS** (ver SPEC-018C)

| Parámetro | Política confirmada | Estado |
| --- | --- | --- |
| Fallos consecutivos que activan bloqueo | 5 | RATIFICADO |
| Ventana para contar fallos | 15 minutos | RATIFICADO |
| Duración de primer bloqueo | 15 minutos | RATIFICADO |
| Duración de segundo bloqueo | 60 minutos | RATIFICADO |
| Duración de tercer bloqueo | 240 minutos | RATIFICADO |
| Bloqueo definitivo por reiteración | Cuarto ciclo de 5 fallos dentro de 24 horas → `REQUIERE_TI` | RATIFICADO |

Los umbrales fueron confirmados por el responsable del proyecto el 20-11-2026 y se describen con detalle en [SPEC-018C](018c-bloqueos-escalonados-backend.md). Se centralizarán en settings con validación y pruebas de frontera; **su ratificación no autoriza despliegue productivo**. Las decisiones restantes sobre única TI, anti-enumeración y sesiones todavía requieren cierre.

### 6.4 Continuidad administrativa

No bloquear automáticamente el único TI sin prever recuperación institucional verificable. La regla de última TI es invariancia crítica. Documentar procedimiento excepcional fuera de banda, auditado y con autorización administrativa, **sin** reejecutar crear_primera_ti cuando existe TI. La respuesta a bloqueo repetido de la única cuenta TI es **PENDIENTE DE DECISIÓN**. Tampoco vulnerar la protección de última Gerencia ni modificar asignaciones de técnicos o turnos para liberar bloqueos.

## 7. Contrato HTTP previsto (cambios aún NO implementados)

| Método/ruta | Actor | Resultado esencial |
| --- | --- | --- |
| POST /api/usuarios/ | TI | 201, cuenta inicial inactiva, indicador cambio obligatorio y entrega excepcional de credencial temporal una sola vez; password de cliente prohibido |
| POST /api/usuarios/{id}/restablecer-clave/ | TI | 200, motivo registrado, sesiones revocadas y nueva credencial temporal de exposición única |
| POST /api/auth/login/ | Público con CSRF | 200 normal actual si habilitado; éxito temporal con respuesta diferenciada de cambio obligatorio y desafío restringido; fallos genéricos |
| POST /api/auth/primer-cambio-clave/ | Titular con desafío restringido | 200 de cambio confirmado, desafío consumido, sin sesión normal automática |
| POST /api/auth/cambiar-clave/ | Usuario ya autenticado | Contrato existente, preservado |
| POST /api/usuarios/{id}/desbloquear-seguridad/ | TI | 200/409, motivo obligatorio, auditado; sin revivir automáticamente cuentas desactivadas por otro motivo |
| GET /api/usuarios/{id}/ e historial | TI | Estado operativo mínimo y eventos autorizados, sin contraseñas, hashes, desafíos o contadores sensibles innecesarios |

**Errores:** 400 validación/formato; 401 credenciales no válidas; 403 rol no autorizado; 404 identificador no accesible; 409 conflicto de estado/versionado; 423 como estado candidato solo para bloqueo comprobado sin filtración de identidad (revisar compatibilidad); 429 limitación por abuso, Retry-After cuando corresponda. No reinterpretar fallos de red/5xx como confirmación de una escritura; no repetir resets automáticamente.

Los campos exactos de respuestas, TTL de desafíos, rate limiting y estados de error quedan sujetos a contrato final de OpenAPI previo a código. Endpoint de primer cambio no debe permitir navegar datos de negocio.

## 8. Persistencia, locks, auditoría y migración

1. Preferir tabla de estado de seguridad 1:1 por usuario y eventos append-only; mantener Usuario.sesion_version y validar seguridad vigente en autenticación, no en el frontend únicamente.
2. Registrar eventos CREACION_CREDENCIAL_TEMPORAL, CAMBIO_INICIAL, BLOQUEO_TEMPORAL, BLOQUEO_SEGURIDAD_TI, REEMISION, DESBLOQUEO_TI con actor TI/usuario/SISTEMA distinguibles, fecha, causa codificada y contador no sensible. No inventar un usuario TI ficticio como actor de eventos automáticos.
3. Respetar orden actual de adquisición de locks administrativos (mutex TI y usuarios por PK); el login necesita transacciones cortas y locks consistentes. No bloquear recursos de Obras/Finanzas después de locks de usuarios.
4. Implementar idempotencia/protección de repetición para desafíos y resets con estados SQL y restricciones; dos intentos concurrentes no pueden crear dos credenciales utilizables, consumir dos veces un desafío ni emitir dos sesiones autorizadas.
5. Migración aditiva: usuarios actuales permanecen habilitados con sus contraseñas vigentes, salvo bloqueos explícitos preexistentes; no convertir en temporal su clave ni resetear contraseñas históricas. Historial anterior, sesiones e invariantes de roles se preservan. Nuevas cuentas siguen la política nueva.
6. Los datos de bloqueo deben poder restaurarse tras reinicio y no depender de reloj del cliente. No introducir MongoDB ni un servicio adicional sin justificarlo.
7. Registrar procedimientos seguros de rollback: preservar hashes, estado de bloqueo y eventos; nunca eliminar logs de seguridad o reactivar en masa como medida de emergencia.

## 9. Experiencia de usuario y accesibilidad

- Formulario TI **sin campo de contraseña elegida**. Tras alta, mostrar credencial temporal en pantalla confidencial con confirmación de entrega, sin persistencia en el navegador. Pérdida o expiración -> reemisión TI.
- Login normal informa credenciales inválidas sin revelar cuentas. Primer inicio dirige exclusivamente a pantalla de cambio obligatorio; mensaje claro y confirmación sin exponer la clave.
- Bloqueo temporal informa que se debe esperar (sin revelar datos sensibles); bloqueo definitivo indica que debe solicitar restablecimiento a Administrador TI, luego de verificar adecuadamente la cuenta.
- TI ve estados separados: inactivo administrativo, activo, primer cambio pendiente, temporalmente bloqueado, requiere TI. No confundir causa administrativa con causa de seguridad.
- Mostrar reenvío/desbloqueo como operaciones con confirmación, motivo y relectura. Botones accesibles, respuestas de error específicas y formularios responsivos.
- La pantalla no concede permisos: todo se verifica nuevamente en el backend.

## 10. Pruebas y criterios de aceptación

### Backend — automatizadas / Postman QA

1. Creación TI sin password cliente, hash válido, usuario inactivo y entrega de credencial una sola vez. Rechazar password arbitrario enviado por cliente.
2. Cuenta TI y Gerencia protegidas; otro rol no puede crear ni resetear (403 incluso con is_superuser).
3. Activación no elimina cambio obligatorio; login temporal jamás emite access normal, refresh ni acceso negocio.
4. Primer cambio correcto habilita login con nueva clave y revoca temporal; misma clave inicial rechazada.
5. Desafío vencido, manipulado, usado dos veces, para otro usuario o tras reemisión -> rechazo; carreras concurrentes sin doble consumo.
6. No exponer temporales, hashes, JWT o secretos en eventos, serializers de lectura, logs y respuestas de errores.
7. Intentos equivocados generan bloqueos según umbrales aprobados; una IP ajena no debe poder evadir rate-limit; error 429 no incrementa contadores internos.
8. Bloqueos persisten entre reinicios/workers; expiración correcta en frontera temporal; cambio de día y zona Chile sin errores.
9. Bloqueo definitivo niega login, refresh y JWT previamente expedido, aunque la cuenta sea nominalmente is_active.
10. Recuperación TI auditada revoca sesiones, reinicia el estado de seguridad sin activar una cuenta manualmente desactivada.
11. Concurrencia de reset con login/refresh/primer cambio y con cambio administrativo de rol/email: ninguna sesión antigua permanece válida.
12. Proteger la última TI y última Gerencia activa; con técnicos vinculados no falsificar cambios operativos. Escenario especial del único TI requiere decisión pendiente explícita.
13. Cuentas inexistentes frente a existentes: tiempos y mensajes razonablemente equivalentes; seguridad frente a enumeración y denegación de servicio por bloqueo malicioso.
14. Migración ascendente sobre usuarios ya creados conserva hashes, historial y permisos; revertir esquema exige plan evaluado, no ejecución destructiva.
15. Regresión completa de apps.usuarios y autenticación, luego suite total Django/PostgreSQL/Mongo QA según runner de proyecto.
16. Colección Postman con variables sintéticas, credenciales de QA, recuperación controlada y orden seguro; no ejecutar contra usuarios reales ni único TI institucional.

### Frontend

17. Formulario de creación no pide clave arbitraria y no expone accidentalmente secreto inicial.
18. Pantalla de primer cambio impide navegar o consultar API de negocio; fallos conservan opciones seguras.
19. Mensajes diferenciados de temporal, definitivo y administrativo; sin filtración de cuenta.
20. Restablecimiento autorizado requiere motivo, confirmación y relectura; error de red no se presenta como éxito.
21. 375/768/1280 px, teclado, accesibilidad y cambio de contexto de usuario; pruebas React/build.
22. JWT solo en memoria y refresh únicamente HttpOnly, CSRF correcto, CORS/orígenes existentes sin degradación; TLS confiable necesario antes de producción, sin instalar CA local en Windows sin permiso.

### CI / entrega

23. makemigrations --check --dry-run, manage.py check, tests backend, frontend tests/build, auditorías de dependencias y OpenAPI consistente.
24. Informar resultados realmente ejecutados, migraciones, riesgos y plan de reversión; no atribuir aprobación humana, QA real o despliegue no realizados.
25. Dejar al menos una evidencia reproducible de recuperación TI y denegación de acceso con token emitido antes del bloqueo.

## 11. Plan de implementación propuesto

1. **PR documental (esta rama):** revisar/ratificar SPEC-018 y decisiones abiertas, sin código.
2. **PR backend:** la Fase A de credenciales está implementada y en revisión en PR #46; la Fase C de bloqueos exige implementación y PR separados tras la especificación aprobada.
3. **Integración frontend externa:** entregar contrato OpenAPI y Postman al equipo responsable de React. Nuestro equipo no edita `frontend/` salvo autorización expresa.
4. **QA integrado:** navegador real, Postman secuencial sobre datos sintéticos, pruebas de seguridad y CI.
5. **Merge:** solo tras revisión y autorización explícita del responsable; despliegue productivo exige controles TLS y operacionales adicionales.

## 12. Decisiones pendientes para ratificación

- **RATIFICADO:** 5 intentos/15 minutos, bloqueos 15/60/240 minutos y cuarto ciclo dentro de 24 horas requiere TI; consultar SPEC-018C. No presentar esos umbrales como pendientes.
- Vencimiento de contraseña temporal (propuesta 24 horas) y desafío de primer cambio (propuesta 5 minutos), con tratamiento de vencimientos y reemisión.
- Canal permitido para entregar la clave generada de manera privada al titular; no asumir email ni chat.
- Recuperación segura si el **único** Administrador TI queda bloqueado; quién verifica identidad y ejecuta procedimiento excepcional.
- Formato definitivo de errores de login de cuenta bloqueada, evitando enumeración; condiciones exactas para 423 y Retry-After.
- Política de conservación y acceso a eventos de seguridad, con privacidad y trazabilidad.

**Regla de aprobación:** los umbrales de SPEC-018C están aprobados para implementación de backend. La recuperación del único TI, el canal productivo, la anti-enumeración y la retención aún requieren aprobación para su operación. No se permite desplegar ni hacer merge de código sin autorización separada.

## 13. Referencias al código y documentos existentes

- specs/002a-autenticacion-jwt.md y specs/002b-hardening-autenticacion.md
- specs/006-backend-usuarios-roles.md, specs/006b-administrador-ti.md y specs/006c-correo-propio-sesion.md
- backend/apps/usuarios/models.py, serializers.py, authentication.py, views.py, throttles.py
- [SPEC-018C — bloqueos escalonados](018c-bloqueos-escalonados-backend.md) y [PR #46 — implementación Fase A](https://github.com/LFP2002/Proyecto-FYAG/pull/46)
- backend/apps/usuarios/services_usuarios.py, serializers_usuarios.py y views_usuarios.py
- frontend/src/ (auth y Usuarios), backend/config/settings.py, compose.yaml
- Tests actuales de TI y autenticación en backend/apps/usuarios/tests/
