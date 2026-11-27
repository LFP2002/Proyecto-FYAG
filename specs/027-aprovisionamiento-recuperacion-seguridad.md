# SPEC-027 — Aprovisionamiento inicial, verificación de correo, recuperación de contraseña y bloqueos de seguridad

> **Estado:** implementación por incrementos; no autoriza despliegue ni activación institucional.
> **Rama:** `fix/auditoria-tecnica-final`, base `87d564bba6d18b274cb7ed009c767e89071b6aec`.
> **Dependencias:** SPEC-002A/002B, 006B, 006C, 018, 018C (C1–C3) y contrato vigente de chat.

**Incrementos implementados:** [verificación voluntaria](../backend/docs/SPEC-027-VERIFICACION.md), [primera TI](../backend/docs/SPEC-027-SETUP.md), [recuperación por correo verificado](../backend/docs/SPEC-027-RECUPERACION.md), [recuperación excepcional TI por infraestructura](../backend/docs/SPEC-027-RECUPERACION-TI.md) y [perfil de bloqueos productivos](../backend/docs/SPEC-027-BLOQUEOS.md), deshabilitado por defecto. La verificación obligatoria queda fuera de este incremento.

## 1. Objetivo y alcance

La evidencia de cierre técnico y los pendientes institucionales se registran en el [informe de validación](../backend/docs/SPEC-027-CIERRE.md).

Permitir la entrega de una instalación vacía, demostrar la titularidad del correo y recuperar cuentas sin conceder acceso implícito. Aplicar los mismos bloqueos a los seis roles. Conservar RBAC, diseño institucional, primer acceso y límites de dominio. Sin cuentas maestras, segundo factor FYAG, cambios de rol ni reactivación como parte de recuperación.

## 2. Precedencia y decisiones funcionales

| Contrato | Actualización explícita cuando se implemente SPEC-027 |
| --- | --- |
| SPEC-006B | El mutex administrativo gobierna tanto `crear_primera_ti` como el asistente. Ambos requieren sistema nunca inicializado y cero usuarios. La CLI interactiva es autorización local de infraestructura, no recuperación. |
| SPEC-006C | El PATCH autorizado solicita cambio: no sustituye dirección ni revoca por ese solo hecho. La confirmación de la nueva dirección sustituye el correo, incrementa la versión una vez y notifica a la anterior. La UI distingue solicitud de confirmación. Mismo correo normalizado sigue siendo no-op. No se habilita una excepción de sustitución inmediata por API. |
| SPEC-018 | Verificar correo no emite sesión ni consume el desafío inicial. Recuperación definitiva por correo verificado puede fijar directamente clave personal mediante confirmación explícita con validadores; la reemisión administrativa sigue siendo temporal y exige primer cambio. |
| SPEC-018C | Conservar fronteras de política y 401 genérico de C2. En producción no se exime a la última TI; la recuperación confirmada por titular y el procedimiento excepcional de infraestructura se añaden al reset TI autorizado. Las guardas y recuperadoras exclusivas de QA permanecen en su perfil. |

## 3. Amenazas e invariantes

- Robo, repetición y confusión de propósito: secretos CSPRNG de al menos 256 bits, digest persistido, propósito exclusivo, expiración y consumo atómico. Binding a usuario, dirección y versión de seguridad; no se repara estado ausente desde flujos públicos.
- Enumeración, inundación y DoS dirigido: usar Redis dedicado por operación, IP confiable e identidad normalizada (identificador opaco), límites atómicos y 503 cerrado ante indisponibilidad. Solo confiar en el proxy explícitamente administrado que elimina cabeceras entrantes. No contar rate limits como clave incorrecta ni extender bloqueos vigentes.
- Robo por logs, analizador de correo o recursos externos: enlaces a origen de configuración con token en fragmento; la UI lo elimina del historial sin persistirlo, lo mantiene solo en memoria y lo envía en POST. GET nunca consume. Referrer-Policy `no-referrer`, `Cache-Control: no-store`, sin rastreadores ni registro de cuerpos sensibles.
- Carreras, rebootstrap y cambio de identidad: estado de instalación monotónico; ninguna revocación o ausencia posterior de usuarios reabre el alta. Revalidar identidad, versión, hash/estado de credencial, rol, actividad y alcance tras el lock relevante. Ninguna transición cambia roles ni `is_active` salvo el alta inicial explícita.
- Operador de infraestructura comprometido: proteger acceso al servidor, registrar referencia y actor de infraestructura, exigir autorización de dos personas fuera de banda. No atribuir eventos a cuentas autenticadas inexistentes.

## 4. Persistencia, migraciones y concurrencia

1. Singleton SQL de instalación, con fecha de inicialización, digest y vencimiento de autorización web. Migración aditiva: marcar si existen usuarios sin modificar cuentas; capturar el primer alta por una vía persistente que cubra inserciones fuera del asistente. La renovación invalida el digest anterior. Consumir clave, marcar inicialización, crear una TI no staff/no superuser y auditar en una sola transacción.
2. Estado de correo por usuario, atado a la dirección confirmada y fecha de verificación; históricos no verificados. Solicitud de nuevo correo pendiente, distinta de dirección actual; serializar confirmación frente a alta/edición y unicidad. Una colisión al confirmar falla sin sustituir la dirección previa.
3. Desafío persistido con digest único, propósito (verificación actual, cambio de correo o recuperación), destinatario, vencimiento, versión de seguridad y marca de consumo/invalidez. Un solo desafío vivo de recuperación por cuenta; una solicitud anónima durante su vigencia no lo sustituye. Tras vencimiento o fallo de entrega confirmado, reemisión explícita bajo cooldown, sin guardar texto plano en colas. Retención acotada de desafíos expirados, independiente del historial de seguridad.
4. Mantener mutex administrativo → usuarios por PK → credencial → acceso → desafíos. Login sin mutex conserva su orden salvo cuando el perfil necesita comprobar una invariante administrativa. No adquirir locks de dominio después de usuario; comprobar el grafo de cada servicio antes de incorporar revalidación. Envío solo tras commit, fuera de locks; una caída entre commit y envío no deshace el alta ni la recuperación.
5. Reutilizar `SeguridadCredencial`, `EstadoAcceso` y versionado; auditoría complementaria tipada con objetivo y actor explícito (titular, TI, sistema, infraestructura). No modificar migraciones 0001–0011 ni retroatribuir eventos. Registrar inicialización, confirmaciones, bloqueos, recuperaciones y revocaciones sin secretos ni payloads; no auditar cada intento anónimo como evento de cuenta.

## 5. Estados, permisos y recuperación

| Acción | Autoridad | Efecto confirmado |
| --- | --- | --- |
| Instalación | TTY autorizada o clave válida, solo instalación nueva | TI activa, `PERSONAL`, correo pendiente, sin sesión. |
| Verificación actual | Token de la dirección vigente | Marca correo verificado; conserva `INICIAL`/`RECUPERACION`/`PERSONAL`. |
| Confirmación de nuevo correo | Token emitido por cambio autorizado | Sustituye correo, confirma titularidad, invalida desafíos incompatibles, revoca sesión y notifica anterior; no desbloquea. |
| Recuperación por correo | Titular con acceso a correo actual verificado; cuenta activa | `PERSONAL` o `RECUPERACION` con evidencia de contraseña personal previa → `PERSONAL` tras elegir y validar la nueva. No reemplaza el primer cambio de `INICIAL` ni de reemisiones sin esa evidencia. Limpia bloqueos cuando el perfil está activo, revoca sesiones y desafíos incompatibles; notifica y exige login nuevo. |
| Reset por TI o infraestructura | TI autorizada según RBAC o `recuperar_acceso_ti` en TTY | Reemite `RECUPERACION` y exige primer cambio. Nunca activa, eleva, crea ni adopta sesión del objetivo. |

Verificación obligatoria separada de la fase de adopción: proteger sesiones operativas, sin bloquear verificación/reenvío ni el primer cambio autorizado. Comprobar TI activa, verificada y recuperable antes de activar. Mantener `NORMAL`, `BLOQUEO_TEMPORAL`, `REQUIERE_TI` (valor persistido de compatibilidad) y `NO_DISPONIBLE`. Cinco fallos dentro de 15 min; bloqueos 15/60/240 min y cuarto ciclo dentro de 24 h hasta confirmación autorizada. Vencimiento y éxito conservan las fronteras de la política vigente; el éxito limpia racha, no ciclos vigentes. Intentos durante bloqueo no cambian vencimiento. Toda transición efectiva revoca sesiones; el login bloqueado no obstaculiza confirmación por correo.

## 6. Contrato HTTP previsto

| Método y ruta | Resultado y restricciones |
| --- | --- |
| GET `/api/auth/setup/estado/` | 200 estado mínimo de instalación, sin cuentas, secretos ni existencia de clave; no autoriza alta. |
| POST `/api/auth/setup/` | 201 sin JWT/cookie; nombre, apellidos, username, email, contraseña/confirmación y clave; rechazar rol/flags. Error genérico para instalación no autorizada; no distinguir clave usada de inválida. |
| POST `/api/auth/correo/verificar/` | 204, token en cuerpo; 400 inválido/vencido/consumido. |
| POST `/api/auth/correo/reenviar/` | 202 genérico; email para dirección vigente, cambio pendiente solo bajo autorización vigente. |
| POST `/api/auth/recuperacion/solicitar/` | 202 genérico: «Si el correo electrónico corresponde a una cuenta habilitada para recuperación, recibirás las instrucciones para restablecer tu contraseña». |
| POST `/api/auth/recuperacion/confirmar/` | 204, token y clave/confirmación en cuerpo; 400 seguro para enlace inválido o validación de clave; ninguna sesión emitida. |
| GET/PATCH `/api/usuarios/{id}/`, GET `/api/usuarios/` | TI exclusiva; proyectar verificación y bloqueo mínimo, no digests ni desafíos. PATCH autorizado de correo devuelve intención pendiente, no cambio consumado. |

Mantener CSRF en POST, CORS restrictivo y errores 429/503 uniformes por operación, sin revelar estado de cuenta. Mantener 401 genérico de login. QA sintético para Postman. Formularios en español, accesibles, con foco, carga y antidoble envío; claro/oscuro, cuatro escalas y 375/768/1280 px.

## 7. Configuración y operación

Django mail, perfiles separados: locmem pruebas; Mailpit privado desarrollo/QA; SMTP autorizado en producción, con TLS/SSL excluyentes, timeout, remitente autorizado y `FYAG_PUBLIC_BASE_URL` HTTPS confiable. Recuperación: 900 s por defecto y configuración validada; verificación e instalación con TTL independientes. Plantillas HTML/texto en español, sin contraseña y con vigencia real. Distinguir aceptación SMTP de entrega. Un envío post-commit con timeout acotado; fallo opaco y reenvío explícito limitado. Medir diferencias temporales evitables antes de activar; respuesta uniforme no demuestra por sí sola ausencia de enumeración.

La activación productiva requiere esquema aplicado, preflight de TI recuperable, entrega verificada, TLS, Redis, guardas de emergencia y autorización operativa explícita registrada en una constancia inmutable vinculada a la configuración. En un arranque ordinario se comprueban esquema, configuración y constancia, no disponibilidad de SMTP/Redis ni estado de la TI; las operaciones dependientes de Redis siguen denegándose si falla. El remitente institucionalmente autorizado puede usar un proveedor o dominio distinto al de la TI. Para Gmail empresarial: cuenta de la organización, 2FA de Google y contraseña de aplicación solo si permitido, STARTTLS 587, validar entrega y remitente; rotar y revocar la credencial antigua. No enviar a destinatarios reales en QA.

`recuperar_acceso_ti`: operador autenticado en servidor, TTY sin eco ni fallback a redirección, cuenta TI existente explícita, identidad institucional comprobada, motivo y referencia, confirmación antes de mutar. Prohibido exponerlo en HTTP o usar la CLI de primera TI como alternativa. Si un rollback no preserva las guardas, retirar tráfico antes de revertir aplicación; no revertir datos ni reabrir instalación. Restaurar solo en destino nuevo a partir de respaldo coordinado y validado; rotar claves y revocar sesiones de forma controlada antes de reanudar tráfico.

## 8. Aceptación y riesgos residuales

- Probar alta concurrente CLI/API, estados clave inválida/expirada/usada, rol inyectado, fallo SMTP y upgrade histórico. Probar los seis roles, direcciones desconocidas/no verificadas, inactivos, cambio de correo/clave posterior a emisión, consumo concurrente, cooldown, propósito, Host, logs, primer cambio y revocación JWT/chat.
- Probar fronteras y concurrencia de C2 en PostgreSQL, fallo de Redis, recuperación por la única TI y revalidación tras revocación, contraseña, desactivación y rol. Probar CSRF, CORS, archivos, inventario, costos, pagos y presupuestos. Validación integral única tras consolidación y ensayo de respaldo/restauración aislados.
- Correo comprometido, bloqueo dirigido, acceso privilegiado a infraestructura y pérdida de SMTP son riesgos residuales. Retención chat no equivale a retención de respaldos. La salida productiva depende de evidencias operativas independientes de las pruebas unitarias.
