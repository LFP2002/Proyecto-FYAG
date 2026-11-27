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
| AUD-023 | Respaldo y restauración coordinados implementados y ensayados en Compose aislado; ver el apartado AUD-023. |
| AUD-024 | Ampliadas exclusiones Git y del contexto Docker backend. Inventario de nombres sensibles y búsqueda acotada de firmas de claves privadas y credenciales no arrojaron candidatos en rastreados; esto no certifica el historial ni detección exhaustiva. Se conserva `.env.example`. |
| AUD-025 | Implementado y validado en Compose productivo aislado; ver el apartado AUD-025. Instancia actual sin modificaciones. |
| AUD-026 | Job `pip-audit==2.10.0` con artefactos y sin exclusiones. Auditoría local ejecutada; el workflow GitHub no se ejecutó desde esta rama local. |
| AUD-027 | Implementado y ensayado en Compose aislado; programación deshabilitada sin autorización. Ver el apartado AUD-027. |
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
- **SPEC-027 (primera tanda):** instalación HTTPS pendiente → alta `201` sin sesión → estado instalado → segundo intento `409` y login `200`. La CLI de emisión rechazó el uso sin TTY. Se registró una constancia por CLI, se arrancó web con bloqueos productivos y se confirmó recuperación sintética con Mailpit STARTTLS y HMAC. Se comprobó el servicio subyacente de recuperación excepcional TI con `fyag_sql_security` y bloqueos productivos activos.

Solo pruebas dirigidas con datos sintéticos; no acreditan entrega SMTP institucional ni sustituyen una ventana de conversión aprobada. Sin cambios a desarrollo, QA existente o instalaciones institucionales; sin AUD-023, regresión global, merge ni despliegue.

### Cierre de la validación interactiva de AUD-025

Base: `34ac93fb68aeb1612f99a7bf358b43ce6ad219c4`. Proyecto Compose productivo aislado `fyag-aud025-tty`, volumen PostgreSQL 18.6 nuevo, datos sintéticos y perfil de bloqueos por defecto. El [smoke dirigido](../deploy/tests/smoke_security_pty.py) ejecutó ambas CLI completas mediante `python -m config.security_cli` dentro de `operaciones_seguridad`, en una PTY real del kernel Linux con `/dev/tty` controlador en primer plano, sin sustituir `getpass`. Se comprobó que `session_user` y `current_user` eran `fyag_sql_security`, sin membresías ni privilegios de administración o creación en el esquema; el único secreto PostgreSQL montado en el servicio era el operativo.

| Prueba | Resultado |
| --- | --- |
| `emitir_clave_instalacion` | Emisión con operador y referencia, evento SQL y alta HTTPS sin sesión. Reutilización `409` y nueva emisión rechazada tras el alta. |
| `recuperar_acceso_ti`: autorización y cancelación | Referencia ausente rechazada. Con referencia sintética y respuesta `NO`, cancelación sin cambiar contraseña, versión de sesión ni auditoría; la sesión previa siguió válida. Solo la confirmación exacta permitió emitir la temporal. La validez de la aprobación de dos personas sigue siendo un control humano fuera de banda, no una comprobación de tickets por la CLI. |
| `recuperar_acceso_ti`: emisión y primer cambio | Temporal válida para `CAMBIO_OBLIGATORIO`, sin access ni cookie de renovación. Access y refresh previamente válidos rechazados con `401`. El primer cambio requirió login manual: la temporal quedó inválida y la nueva contraseña permitió iniciar sesión. |
| Auditoría | Un único evento SQL con operador, referencia y motivo; el endpoint de auditoría TI lo atribuyó a `INFRAESTRUCTURA` y no incluyó contraseñas, clave de instalación, temporal ni tokens. |

La PTY no se transcribió: los secretos se usaron en memoria para las comprobaciones HTTPS. El contenedor efímero tuvo desactivado el registro de Docker y la evidencia solo contiene resultados. No se detectaron defectos funcionales. Para reproducir: iniciar `proxy`, `redis-seguridad` y `redis` en el proyecto aislado con una base nueva `fyag_aud025_tty`, certificados sintéticos cuyo CA esté disponible en `redis_ca`, y un overlay exclusivo de laboratorio que añada la red `edge` a `operaciones_seguridad` y fije su `logging.driver: 'none'`. Pasar el smoke por stdin a `docker compose … run --rm --no-deps -T operaciones_seguridad python -`; `-T` afecta solo al verificador exterior, que crea la PTY real para cada CLI. No aplicar ese overlay en instalaciones institucionales.

## AUD-023 — Respaldo y restauración coordinados

Base: `ee984d49e56e46dcd953f458d5d4dc9e3f43fe98`. [Runbook, retención y medición](RESPALDO-RESTAURACION.md). El comando detiene la entrada y los escritores, verifica aislamiento, usa `pg_dump`/`pg_restore` y `mongodump`/`mongorestore`, copia los tres almacenes privados y cifra el manifiesto y los datos con AES-256 e integridad OpenPGP. Solo admite destino nuevo `fyag-dr-*`. PostgreSQL usa la identidad propietaria de migraciones para los objetos de aplicación, no el administrador ni web; se aplica la matriz AUD-025 del destino.

- Origen `fyag-aud023-source` y destino nuevo `fyag-dr-aud023-final`: PostgreSQL **18.6**, MongoDB **8.0.34** y Redis **7.4.7**. Corte `2026-11-27T17:32:35.185Z`; paquete cifrado **604.500 bytes**; respaldo **6,16 s**, verificación criptográfica e inventario **0,17 s**, primera restauración offline satisfactoria **35,10 s**. El [smoke](../deploy/tests/smoke_backup_aud023.py) comprobó saldo `5,250`, subtotal de costo `31.250,00`, eventos y relaciones SQL, dos proyecciones Mongo con anotación y revisión, bytes verificables en los tres almacenes, restricciones para web, rechazo de refresh anterior y login personal vigente.
- Redis de seguridad tenía un marcador en origen; se verificó `DBSIZE=0` en los dos Redis nuevos. Se conservaron el bloqueo SQL y el historial; la restauración invalidó desafíos y credencial temporal de la fixture, tickets, canales y versiones de sesión. No se reactivó el asistente en la base inicializada. La limpieza de una clave pendiente está implementada, pero no se ensayó una segunda fuente sin inicializar. La nueva autorización SPEC-027 con SMTP institucional no formó parte de este ensayo.
- [Negativas dirigidas](../deploy/aud023/check_negative.py): se rechazaron bytes cifrados alterados, componente ausente, payload reempaquetado con SHA-256 incorrecto, formato incompatible y un proyecto previamente ocupado. El intento fallido se dejó aislado; se retomó en otro proyecto sin eliminar volúmenes.
- Segunda restauración en volúmenes nuevos (`fyag-dr-aud023-rto`): incidente simulado `17:35:31.092Z`, **RPO 175,91 s** respecto del corte; restauración offline **37,74 s** y **RTO 64,08 s** hasta proxy saludable y verificación de la aplicación. No se conmutó tráfico real.

Solo Compose aislado y datos sintéticos. Los tiempos no son SLA ni incluyen transferencia externa, aprobación humana, DNS, ni rehabilitación SMTP. No se intervino infraestructura institucional, no se eliminaron volúmenes y no se abordó AUD-027, regresión global, merge ni despliegue.

## AUD-027 — Retención y purga de Chat

Base: `c79e88342b1c7674031a7f7a4efb94a0146371ea`. [Operación y límites](RETENCION-CHAT.md). Se recorren todos los lotes por clave dentro del corte, con transacciones acotadas y sin bloquear las conversaciones atendidas por otros procesos. Un retiro fallido conserva su tumba SQL y no detiene lotes posteriores. Los informes separan identificados, eliminados, pendientes y fallidos; un ciclo fallido o pendiente no se acredita como éxito. No cambió la matriz de privilegios AUD-025.

- PostgreSQL 18.6 y archivos privados reales en Compose aislado. El [smoke](../deploy/tests/smoke_chat_aud027.py) preparó siete mensajes caducados, un vigente y una reserva antigua. Se comprobó el valor por defecto de 30 días, se aceptaron 1 y 90 y se rechazaron 0 y 91. El worker continuo se negó a arrancar sin autorización explícita. `--dry-run --lote 2` identificó siete mensajes y una reserva sin modificar filas ni bytes.
- Una transacción concurrente bloqueó una conversación con cuatro caducados; otros lotes avanzaron. Una obstrucción real del filesystem causó un retiro fallido con tumba persistida. La CLI en el rol Chat terminó con código **1**, aunque eliminó otros cuatro archivos de la cola. Tras reinicio, retirando la obstrucción y ejecutando otro contenedor efímero, el reintento terminó completo. Solo quedó el vigente y su archivo; el replay de un acto caducado devolvió `409` sin republicar.
- Respaldo AUD-023 con los caducados aún presentes (**9,17 s**). En otro proyecto con volúmenes nuevos, la restauración y purga offline (**40,48 s**) eliminaron los siete mensajes y sus archivos antes de abrir tráfico, conservaron los recibos mínimos y dejaron intacto el vigente. No se alteraron copias anteriores ni se aprobó una política de retención de copias.

Solo pruebas dirigidas con datos sintéticos; sin intervención institucional, regresión global, merge ni despliegue.

### OBS-008 — Contención durante la purga de efímeros

Base: `de67bab4812872ae41cbf4e36615c73c15f39980`. Los `DELETE` de cupos, tickets y canales usan un `lock_timeout` local de 50 ms por bloqueo. Solo ante SQLSTATE `55P03` se revierte y divide el lote; las mitades se reintentan con 5 ms por bloqueo hasta posponer la fila ocupada. Se conservan `SELECT` y `DELETE` sin `UPDATE`; la contención queda separada de los fallos y los pendientes se vuelven a contar al cierre.

El [ensayo dirigido](../deploy/tests/smoke_chat_obs008.py) en PostgreSQL 18.6 y Compose aislado sostuvo bloqueos de fila reales en una conexión web independiente, mientras el rol productivo Chat ejecutó la CLI con lotes de dos. Para cada entidad identificó cinco caducados, eliminó tres y dejó dos bloqueados y pendientes, sin fallos; terminó con código **1** mientras los locks seguían activos (**2,44 s**, incluido Compose). Al liberarlos, el siguiente ciclo eliminó los dos restantes de cada tabla, dejó cero pendientes y terminó con código **0** (**2,05 s**). Se verificó que el rol Chat no tenía `UPDATE` ni siquiera por columna en esas tablas. Sin regresión global, merge ni despliegue.
