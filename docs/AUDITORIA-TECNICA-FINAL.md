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
| AUD-025 | Pendiente comprobar roles motor/migración/runtime en QA independiente. Instancia actual sin modificaciones. |
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
