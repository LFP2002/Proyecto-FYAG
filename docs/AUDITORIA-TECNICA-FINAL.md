# Auditoría técnica final — plan y registro de evidencia

Base auditada: `87d564bba6d18b274cb7ed009c767e89071b6aec`. Rama local: `fix/auditoria-tecnica-final`. Sin autorización de publicación, merge ni despliegue.

## Orden de trabajo

1. Acordar precedencia y modelo en [SPEC-027](../specs/027-aprovisionamiento-recuperacion-seguridad.md).
2. Verificar guards y reconciliación; preservar orden de locks, probar con PostgreSQL real y fixtures sintéticos.
3. Aislar infraestructura, fijar dependencias efectivas y auditar sin suprimir hallazgos.
4. Integrar correo/verificación, instalación, recuperación y C2/emergencia, con pruebas dirigidas por etapa y sin activar producción.
5. Incorporar UI y contratos. Verificar componentes residuales por consumidores antes de retirar.
6. Validación integral única sobre solución consolidada; no usar resultados históricos como evidencia nueva.

## Registro inicial

- `origin/main` se actualizó por fetch y coincidió con la base auditada. El árbol estaba limpio. Se creó la rama sin mover `main`.
- `crear_primera_ti` ya usa mutex PostgreSQL, pero su predicado solo busca TI (no certifica instalación nunca inicializada ni conjunto vacío de usuarios). C2 existente se restringe a QA y conserva 401 genérico; no se debe reutilizar su excepción de última recuperadora en producción.
- RESULTADOS históricos de 1.451 backend y 316 frontend son referencias, no pruebas de esta rama. La validación de navegador no usará Edge Headless/CDP ni scripts dinámicos PowerShell bloqueados.

## Corte de revisión local — entrega parcial

**Desarrollo y evaluación académica: APTO CON OBSERVACIONES** para revisar este avance, no para dar por terminada la auditoría. **Producción: NO APTO.** SPEC-027 precede al código, pero sus flujos no se implementaron en este corte. No hubo migraciones nuevas, cambios institucionales ni cambios al `.env` local.

| Hallazgo | Estado y decisión |
| --- | --- |
| AUD-001 | Fijadas versiones directas y transitivas en el entorno Linux/Python 3.13.18; instalación runtime limpia y `pip check` correctos. Falta regresión funcional completa con la resolución nueva. |
| AUD-002 | Retirados `RoleSwitch`, `TecnicoApp` y `MATRIX` sin consumidores de runtime; pruebas contractuales trasladadas al árbol activo. Pendiente revisar exhaustivamente otras implementaciones antiguas. |
| AUD-003 | Hooks separados; sin unificación masiva. |
| AUD-004 | Acoplamientos existentes conservados; no se certifica su revisión completa. |
| AUD-005 | README actualizado para CI, disponibilidad y credenciales. Queda revisar el resto de documentación operativa. |
| AUD-006 | Componentes conservados salvo código sin uso; no se dividieron por tamaño. |
| AUD-007 | Pendiente. C2 mantiene guardas QA; no se activaron bloqueos productivos. |
| AUD-008 | Pendiente Redis de seguridad y pruebas de degradación; no se cambió el throttle vigente. |
| AUD-009 | Enlace local PostgreSQL limitado a loopback; backend y Mongo ya en loopback y Redis/ClamAV sin puertos publicados. Pendiente configuración productiva independiente. |
| AUD-010 | Logout revoca el refresh; el access previo puede durar hasta su vencimiento de 10 min si no se invalida por otra transición de seguridad. No se cambió el contrato. Recuperación/bloqueos deben revocar también sesiones ya emitidas. |
| AUD-011 | Los hooks vinculan sus operaciones a sesión/usuario/rol y descartan conciliaciones de otra generación. Confirmada una respuesta de escritura tardía que antes devolvía éxito tras invalidar el scope. Pendiente cobertura adicional por módulo y navegador. |
| AUD-012 | Pendiente inventariar locks de dominio y verificar las cuatro carreras de autorización en PostgreSQL. |
| AUD-013 | Los gastos manuales conservan su contrato: un resultado incierto requiere conciliación antes de reenviar; la defensa de UI no garantiza deduplicación del dominio entre clientes. Sin cambios. |
| AUD-014 | Se conserva el histórico de solicitudes/mermas al cerrar; sin cambios. |
| AUD-015 | Pendiente verificar licencia y fuente de IBM Plex Sans antes de alojar localmente. |
| AUD-016 | No ejecutado: no se abrió un navegador interactivo autorizado en QA; no se usó automatización prohibida. |
| AUD-017 | Sin React Router. |
| AUD-018 | CSS global conservado. |
| AUD-019 | Índice OpenAPI por alcance y precedencia; propuestas e histórico separados. SPEC-027 aún sin contrato ejecutable. |
| AUD-020 | Etiquetas históricas atribuidas a Gerencia. No se cambió agrupación, estado persistido ni resolución de pendientes por Finanzas. |
| AUD-021 | Navegación por rol conservada. |
| AUD-022 | Pendiente medir seguimiento comercial; no se cambiaron consultas. |
| AUD-023 | Pendiente procedimiento coordinado y ensayo de restauración aislada. Los procedimientos previos por motor no acreditan consistencia cruzada. |
| AUD-024 | Ampliadas exclusiones Git y del contexto Docker backend. Inventario de nombres sensibles y búsqueda acotada de firmas de claves privadas y credenciales no arrojaron candidatos en rastreados; esto no certifica el historial ni detección exhaustiva. Se conserva `.env.example`. |
| AUD-025 | Implementado y validado en Compose productivo aislado; ver el apartado AUD-025. Instancia actual sin modificaciones. |
| AUD-026 | Job `pip-audit==2.10.0` con artefactos y sin exclusiones. Auditoría local ejecutada; el workflow GitHub no se ejecutó desde esta rama local. |
| AUD-027 | Se conserva `FYAG_CHAT_RETENCION_DIAS` (30 por defecto, rango 1–90) y `FYAG_CHAT_PURGA_INTERVALO` (3600 s por defecto). Revisar recuentos usando `python manage.py purgar_chat --dry-run` en QA antes de autorizar `--once` o `--continuo`. Pendiente decidir retención de copias y ensayar recuperación del almacenamiento privado. Sin purga ejecutada. |
| AUD-028 | Implementados `/health/live/` (proceso) y `/health/ready/` (SQL con error opaco). Compose comprueba liveness y no espera salud de Redis de chat ni enlaza reinicios a auxiliares. Pendiente observar comportamiento real con el proxy/configuración productivos. |

### Evidencia de este corte

- Frontend dirigidas: **100/100**, 1.467,347 ms; build **1,21 s**, chunk principal **203,56 kB** minificado. Auditorías npm completa y runtime: cero avisos reportados.
- Salud: **4/4** en QA existente (0,009 s) y **4/4** en imagen runtime limpia (0,010 s). Esta segunda ejecución solo usa `SimpleTestCase`, red deshabilitada y el runner estándar; el runner documental requiere Mongo QA autenticado y rechazó ese contenedor sin credenciales. No se cambió su guarda. Readiness con SQL real en QA: **200**. Django `check` sin hallazgos y `makemigrations --check --dry-run` dijo `No changes detected` usando la conexión QA; el primer intento sobre nombre de base no creado solo verificó el modelo, no el historial.
- Pillow 12.3.0: `pip-audit` reportó **42 avisos**, todos con versión corregida 13.0.0. Se actualizó únicamente Pillow respecto al inventario efectivo; nueva imagen, `pip check` y `pip-audit`: sin incompatibilidades ni vulnerabilidades conocidas reportadas. Falta la regresión completa de flujos de imágenes, incluidos adjuntos y chat.
- `docker compose config --quiet` aceptó la configuración local. No se levantó ni reinició el stack. Los probes nuevos no declaran que las migraciones estén aplicadas ni que los módulos auxiliares estén sanos.
- No se hizo la validación integral: no hay versión consolidada de SPEC-027. No se ejecutaron instalación/upgrade, suites completas, Postman de SPEC-027 (colección aún no creada), navegador, pruebas AUD-012 ni restauración coordinada (procedimiento aún no integrado). No se probó SMTP real: no autorizado en QA.

### Operación y pasos pendientes

Para revisión local seguir [README](../README.md) y usar `.env.example` solo como plantilla, sin sobreescribir configuración. No hay variables nuevas obligatorias ni migraciones. El comando histórico `crear_primera_ti` permanece sin cambios: solo ejecutar en una instalación nueva, migrada y sin usuarios desde TTY; no usar para recuperar acceso. El comando de emergencia, Mailpit y el setup web todavía no existen. La [SPEC-027](../specs/027-aprovisionamiento-recuperacion-seguridad.md) documenta las guardas y la configuración Gmail/STARTTLS previstas; no habilitarlas por inferencia.

Para volver a la referencia, usar revisión local de los commits de código y reconstruir la imagen previa en un entorno aislado. No hay migraciones nuevas que revertir. No reinstalar deliberadamente Pillow 12.3.0 ni exponer PostgreSQL como parte de un rollback: conservar estas correcciones hasta disponer de alternativa revisada. Ante incidentes todavía no hay evidencia de recuperación coordinada: preservar dumps lógicos y archivos privados bajo acceso restringido; no copiar directorios activos de motores ni restaurar sobre datos existentes. Antes de producción hacen falta especificación implementada, TLS/WSS confiable, SMTP/entrega autorizados, TI recuperable y emergencia ensayada, mínimo privilegio, persistencia y respaldo/restauración verificados, más firma institucional.

## Continuación desde `d274e024c1a2ed0f65a99857017e2452dcadfbd8`

Este apartado actualiza el corte anterior; los cinco commits de la base se conservaron.

| Requisito | Estado en esta continuación |
| --- | --- |
| AUD-008 | Login en Redis dedicado y con límites por IP/correo en una operación Lua, sin cache local de respaldo. Redis no disponible devuelve 503; el servicio exige un secreto independiente en Compose. Pendientes recuperación, verificación, setup y trasladar los límites que siguen locales en refresh y primer cambio. El proxy aún necesita un canal autorizado para conservar la IP real; hoy no se usan cabeceras aportadas por clientes. |
| AUD-012 | Obras, participantes, turnos/evidencias de turnos, gastos manuales y declaraciones/cortesía de costos releen actor y credenciales después de adquirir los locks pertinentes cubiertos, sin invertir el orden. Cuatro carreras de edición verificadas; pendientes Finanzas, inventario exhaustivo de otros caminos y cobertura concurrente para cada dominio. |
| SMTP y Mailpit | Servicio Django independiente de proveedor, configuración validada, plantillas HTML/texto, envío post-commit y fallo opaco. Mailpit opcional, privado y limitado a destinatarios `.test`; captura confirmada. Aún no hay endpoints que emitan desafíos ni se probó un proveedor real. |
| Primera instalación | `usuarios.0012_instalacionfyag` agrega estado persistente, conserva cuentas al actualizar y marca el primer alta incluso fuera de la CLI. La CLI exige instalación nunca inicializada y cero usuarios; no es recuperación. Falta autorización temporal y panel/API web. |
| Resto de SPEC-027 | Pendientes verificación y transición de históricos, recuperación de 15 min, revocación de JWT/chat por esos flujos, desbloqueo, C2 productivo, comando de emergencia, interfaces y contratos OpenAPI/Postman. No se expusieron flujos parciales que pudieran reactivar cuentas o cambiar roles. |
| Infraestructura productiva | Pendientes configuración independiente, separación de roles PostgreSQL y respaldo/restauración coordinados. No hubo despliegue ni intervención sobre datos institucionales. |

Validación dirigida en QA: login/Redis **22/22** (5,263 s), compatibilidad de C2 **28/28** (1,641 s), Obras/concurrencia y turnos **28/28** (6,308 s), gastos/costos y sus carreras **80/80** (15,081 s), SMTP **4/4** (0,050 s), instalación/migración/CLI **9/9** (1,586 s). Pillow **13.0.0** en imagen runtime y **5/5** pruebas (1,411 s) de fotografías/evidencias, adjuntos PNG/JPEG y chat. Aplicación de todas las migraciones en base de pruebas vacía, y ensayo `0011 → 0012` con cuenta sintética conservada. `makemigrations --check --dry-run`: sin drift. Compose local con Mailpit validó su definición; se confirmó un mensaje sintético mediante la API de Mailpit, sin usar destinatarios reales. No se ejecutó regresión completa, Postman ni validación productiva.

## AUD-012 — Revalidación después de esperas SQL

Base: `783a06d4c86c27d20c42c823f6d129899fb8292a`. Este apartado actualiza las dos filas históricas de AUD-012. Los servicios conservan el actor de entrada como referencia de sesión y releen actividad, rol persistido, versión, hash y acceso con los validadores de cada dominio. Cuando la espera puede ocurrir al persistir, la comprobación final sigue dentro del `atomic`: una denegación revierte las escrituras y descarta las notificaciones `on_commit`. No se agregaron locks de Usuario a Finanzas ni se invirtió `Presupuesto → Obra → Documento → Pago`.

| Dominio | Operaciones revisadas y resultado | Evidencia específica |
| --- | --- | --- |
| Finanzas: documentos | Alta y cierre sin cobro revalidan tras la raíz; la reversión, tras `DocumentoCobro`. El alta vuelve a comprobar antes del evento si el `INSERT` esperó por folio. | Revocación tras lock de presupuesto (alta), cambio de hash tras lock de documento (reversión), desactivación tras lock de obra (sin cobro). |
| Finanzas: pagos | Alta y replay UUID comprueban la sesión tras el lock de documento o la resolución de la colisión; se revalida el `INSERT` exitoso antes del evento. Anulación revalida tras `PagoDocumento`. | Cambio de rol durante el alta y bloqueo de seguridad durante la anulación; pruebas dirigidas de idempotencia, saldo y concurrencia. |
| Finanzas: egresos | Alta/replay, colisión UUID y anulación: se conservan los puntos de revalidación de fila/inserción/colisión; el validador compara también hash y rol original. | Cambio de hash tras lock de egreso y durante colisión de UUID; solo persisten el alta y el evento del ganador. |
| Comercial | Alta, edición, activación y desactivación de Clientes: comprobación posfila y, para alta/edición, pospersistencia bajo unicidad de identificación. Presupuestos: alta/edición, partidas, fijación de precio, decisiones de Finanzas y cliente, anulación y revisión conservan la comprobación final contra el rol persistido inicial bajo sus locks de seguridad. | Suites dirigidas de Clientes, autoridad 020A y concurrencia 024; sin nueva carrera por cada transición. |
| Inventario | Alta/edición de artículos e ingreso de stock; autorizaciones, entregas, devoluciones, valorización y regularización de materiales; creación/decisión de solicitudes y mermas. Se amplió el cotejo de sesión, se conservó el actor original en ingreso y se añadió comprobación tras `GastoObra` en devolución. | Suites dirigidas de inventario y concurrencia de materiales, solicitudes y mermas; no hay matriz nueva por cada tipo. |
| Obras | Alta/edición, responsable, participantes, inicio/suspensión/reanudación/finalización; turnos y evidencias, gastos manuales, declaración/validación/cortesía de costos; alta, renombre y actividad de categorías. Se añadió comprobación tras las esperas tardías de participantes, control de costos y unicidad de categoría. | Nueva carrera de hash en renombre de categoría y de revocación en anulación de gasto tras esperar el control de costos; las demás pruebas son dirigidas de contrato/concurrencia existente. |
| Alertas y Chat | Atención de alerta: comprobación tras advisory y fila (la comprobación final usa la fila bloqueada). Chat: creación de conversación, publicación de texto/archivo, marca de lectura y emisión/consumo/renovación de tickets/canal. Los mutadores HTTP fortalecen el cotejo del actor; la renovación de canal comprueba sesión y vigencia tras bloquear la fila. | Suites dirigidas de Alertas/Chat y nueva carrera de revocación durante renovación de canal; la fecha de vigencia no cambia. |
| Adjuntos y Documentos | Subida de informe técnico y respaldo de factura: revalidación tras advisory y destino (`Presupuesto → Obra → Documento`) antes de publicar; si falla la comprobación posinserción se conserva la compensación existente. Anotaciones de adjuntos y de evidencias: CAS en Mongo, con lectura SQL previa, sin locks SQL mantenidos durante el CAS. | Nueva carrera HTTP de revocación al esperar `Obra`: 401, sin fila ni archivo publicado. Contratos de respaldo y CAS de factura verificados con Mongo QA autenticado. No se ensayó carrera SQL en el CAS de evidencias. |
| Usuarios | Alta, edición, activación/desactivación, rol y restablecimiento TI pasan por `_admin()` después del advisory y de los locks de cuentas; se añadió cotejo del hash/rol original. Cambio de clave propia coteja el actor después de bloquear su fila. | Nueva carrera de hash durante el mutex TI: la baja no modifica cuenta ni crea evento. Los flujos de autenticación, refresh, verificación y recuperación se inventariaron aparte: usan contraseña, refresh o desafío propio; no se certifican sus carreras completas en este corte. |
| Dashboard, Reportes y Auditoría | No se identificaron mutadores HTTP de datos de negocio en sus vistas. No se extrapola a administración Django, CLI, migraciones, reconciliadores ni purgas de sistema. | Inventario estático, sin pruebas nuevas de estos módulos. |

Las carreras nuevas usan conexiones independientes y `pg_blocking_pids()` antes de confirmar el cambio de autoridad. Los cambios de hash, rol y actividad se aíslan del incremento de versión. El caso de bloqueo registra cinco señales reales de la máquina C1 en PostgreSQL y activa solo el selector de lectura para aislar el efecto de `EstadoAcceso`; no activa ni valida la política productiva de SPEC-027. En Finanzas se verificó que no quedaran altas, reversiones, anulaciones o eventos de negocio de la operación denegada. Documentos y Pagos mantienen 403 por actividad/rol y 401 por sesión inválida; Egresos mantiene su distinción propia. La prueba HTTP de JWT revocado en pagos confirma la propuesta de cambio de correo antes de exigir 401: según SPEC-027, la mera propuesta no revoca.

En una tanda de 315 pruebas dirigidas, las 310 ajenas a cinco incidencias de Adjuntos aprobaron, incluidas las selecciones de Comercial e Inventario. Cuatro incidencias exigían el runner documental y una aserción asumía que el directorio de publicación existía en una subida denegada. Se corrigió la aserción para verificar ausencia de archivos y se repitieron esos casos con Mongo efímero autenticado y ClamAV: la tanda de Adjuntos, Chat, Alertas y categorías terminó **56/56**. La tanda final de Finanzas, Obras y Usuarios terminó **241/241**, incluidas las siete carreras financieras. Son selecciones con solapamiento, no un total de pruebas distintas.

El alcance es la revalidación tras las esperas revisadas, no una garantía de serialización universal con revocaciones posteriores a la última lectura, ni una certificación de todos los locks implícitos/diferidos o de transacciones entre PostgreSQL, Mongo y archivos. No se ejecutó regresión global, merge ni despliegue.

## AUD-009 — Infraestructura productiva independiente

Base: `ffb0216a0ef8bff8ec29598018bc87ed9b581165`. [Compose productivo](../compose.production.yaml) y [guía de instalación y operación](INFRAESTRUCTURA-PRODUCCION.md). Sustituye el pendiente histórico de AUD-009, sin modificar el Compose ni `.env` de desarrollo, ni los perfiles QA existentes.

- En el proyecto de laboratorio independiente, solo Nginx publicó HTTP/HTTPS en loopback. El proxy y Django corrieron sin privilegios ni montajes de código; Daphne no expuso TCP. Un cliente aislado envió valores de IP y protocolo falsos: la clave del límite de login en Redis correspondió a la IP real del socket del cliente, no a las cabeceras.
- Construcción runtime y smoke HTTPS/WSS aprobado antes y después de reiniciar: redirección canónica, SPA compilada, TLS con CA explícita, rechazo de CA no confiable y SNI incorrecto, cookies, CSRF/CORS y WSS con ticket y `pong`. Redis seguridad autenticado por TLS rechazó un nombre de certificado no coincidente y tráfico en claro; Redis Chat permaneció separado. ClamAV aceptó un `INSTREAM` benigno con firmas de laboratorio; no se validó actualización externa de firmas.
- Tras reiniciar proxy, web, motores y workers se recuperó el estado saludable. Se comprobó persistencia de una cuenta SQL, un marcador AOF y marcadores de los tres volúmenes privados. Mongo autenticado y los reconciliadores de Alertas/Documentos/Adjuntos y purgador Chat pasaron sus comprobaciones de ciclo; no es un ensayo de restauración. El consumidor SMTP procesó una solicitud en Redis y entregó correo sintético por STARTTLS autenticado a Mailpit privado.
- **3/3** pruebas del adaptador Unix y **3/3** de límites Redis existentes. Las guardas SPEC-027 rechazaron arranque con bloqueos productivos sin autorización; el valor por defecto sigue deshabilitado. No se cambió el almacén de confianza del equipo. Quedan las verificaciones de red, DNS, renovaciones, credenciales, firmas, SMTP y operación institucionales de la guía. No se abordaron AUD-025 ni AUD-023; sin regresión global, merge ni despliegue.

### OBS-007 — Firma de recuperación entre web y correo

El overlay SMTP comparte una clave HMAC persistente solo entre web y consumidor, sin montar las claves generales de Django o JWT en correo. Se comprobó que se rechazan valores ausentes o inválidos y que web rechaza reutilizar cualquiera de esas dos claves. Desarrollo y QA conservan la firma anterior; la [guía operativa](INFRAESTRUCTURA-PRODUCCION.md#rotación-de-la-clave-de-recuperación-obs-007) describe la rotación y la invalidación de enlaces pendientes.

En Compose aislado con perfil productivo autorizado solo para el laboratorio, PostgreSQL, Redis TLS y Mailpit STARTTLS autenticado, se verificaron solicitud HTTPS, procesamiento, recepción, confirmación sin sesión, nuevo login y rechazo de reutilización y de la contraseña anterior. Una solicitud sobrevivió a la parada y arranque del consumidor y el enlace siguió válido tras otro reinicio; una cuenta con bloqueo temporal real volvió a `NORMAL` con evento de recuperación. **18/18** pruebas dirigidas, incluida `test_mailpit_confirmacion_y_login_manual` de primera instalación, antes omitida. No se cambió el asistente ni se usó infraestructura institucional.

## AUD-025 — Mínimo privilegio PostgreSQL

Base: `161e99f2fd6ea98e082f03a1f63070d644648b12`. [Matriz de permisos](../backend/config/production_migrate.py) y [procedimiento operativo](INFRAESTRUCTURA-PRODUCCION.md#roles-postgresql-aud-025). El administrador conserva la base; migraciones posee el esquema y los objetos de aplicación. Web, operaciones de seguridad y cada worker tienen credenciales SQL independientes. La matriz no concede DDL a runtime; los eventos y constancias no se pueden modificar, borrar ni truncar desde web. La única mutación de recibos de Chat permitida es la caducidad controlada por el trigger existente.

- **Instalación y conversión:** PostgreSQL 18.6 real en dos proyectos Compose productivos aislados. En el volumen nuevo se aplicaron las migraciones con `fyag_sql_migration`. En el legado se mantuvieron la cuenta TI, su contraseña, estado y evento de instalación; `usuarios_usuario` conservó OID y filenode (`16467`) y cambió de propietario sin recrear el volumen.
- **Permisos y negocio:** el [smoke web](../deploy/tests/smoke_sql_privileges.py) comprobó atributos de rol y denegaciones de DDL, escalamiento y mutación/borrado/truncamiento de eventos y constancias seleccionados. Se comprobó ingreso de inventario y replay idempotente; también alta e inicio de obra, cierre de turno con evidencia y publicación de Chat como web. El [smoke de workers](../deploy/tests/smoke_sql_workers.py) verificó denegaciones con las cinco identidades, alertas con evento, proyecciones no vacías en Mongo y purga con mensaje caducado, recibo preservado, reserva retirada y mensaje vigente intacto.
- **SPEC-027:** instalación HTTPS pendiente → alta `201` sin sesión → estado instalado → segundo intento `409` y login `200`. La emisión se ejercitó mediante el servicio subyacente con el rol operativo y la CLI rechazó el uso sin TTY. Se registró una constancia por CLI, se arrancó web con bloqueos productivos y se confirmó recuperación sintética con Mailpit STARTTLS y HMAC. La recuperación excepcional TI comprobó credencial temporal y evento mediante el servicio con `fyag_sql_security`; no se ensayó la CLI interactiva completa.

Solo pruebas dirigidas con datos sintéticos; no acreditan entrega SMTP institucional ni sustituyen una ventana de conversión aprobada. Sin cambios a desarrollo, QA existente o instalaciones institucionales; sin AUD-023, regresión global, merge ni despliegue.
