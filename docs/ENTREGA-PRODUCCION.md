# FYAG — Lista de verificación de entrega y puesta en producción

Este documento no autoriza merge, despliegue ni activaciones. La [matriz de 28 hallazgos](AUDITORIA-TECNICA-FINAL.md#matriz-vigente-de-consolidación) separa cierres técnicos de decisiones pendientes. Registrar responsable, fecha, SHA, referencia de evidencia y aprobación para cada control; no adjuntar secretos ni datos de usuarios.

## Entrega técnica

- [ ] Identificar el candidato por SHA, comprobar coincidencia local/remota y árbol limpio. Preservar SPEC, OpenAPI y evidencia histórica. Revisar el diff y asociar los resultados nuevos al SHA evaluado.
- [ ] Obtener CI verde para el candidato: Backend y Frontend CI existentes, más Production Compose CI. Una ejecución dirigida no equivale a regresión global. Programar, autorizar y ejecutar esa regresión aparte antes de promover el candidato.
- [ ] Confirmar `pip check` y auditoría del runtime, npm completo (incluido tooling) y solo runtime, escaneo de imágenes y procedencia/digests aprobados. Si persiste picomatch u otro aviso, corregir o registrar una aceptación nueva y acotada; el antecedente de PR #44 no está ratificado para esta entrega.
- [ ] Validar instalación limpia, actualización desde la versión real y matriz de permisos por rol. Confirmar contratos HTTP/OpenAPI, seis roles y perfiles representativos de navegador/accesibilidad. No omitir las guardas QA para lograr una prueba verde.

## Preparación institucional (antes de abrir tráfico)

- [ ] Aprobar responsable, ventana, plan de retirada/reversión y revisión de cambios. Separar entorno y secretos externos según [infraestructura productiva](INFRAESTRUCTURA-PRODUCCION.md), verificar ACL de ficheros y rotación, y ensayar primera instalación o recuperación excepcional TI según corresponda.
- [ ] Asignar host, DNS, puertos, firewall/NAT y egress de SMTP y firmas ClamAV. Comprobar cadena, SAN, renovación y alertas TLS; verificar HTTPS/WSS, cookies, CSRF, origen e IP cliente real sin confiar en cabeceras de terceros. Aprobar dimensionamiento, logs restringidos, reloj y monitoreo de proceso, SQL, motores, firmas, disco y antigüedad de ciclos.
- [ ] Autorizar proveedor SMTP, remitente y egress; probar entrega real a la TI verificada sin registrar enlaces. Si se aprueba activar bloqueos productivos, reunir referencias y emitir constancia según [SPEC-027](../backend/docs/SPEC-027-BLOQUEOS.md). Si no, mantener el perfil deshabilitado; un overlay válido no acredita entrega ni activación.
- [ ] Aprobar política de copias, cadena de custodia, segregación de claves, copias externas/inmutables y retención legal. Fijar RPO/RTO, medirlos con volumen representativo y ensayar restauración en un `fyag-dr-*` nuevo sin tráfico. Verificar ACL, inventarios, sesiones revocadas, Redis vacío, purga previa y reconciliadores antes de una reapertura aprobada.
- [ ] Aprobar por separado el tratamiento de Chat y la programación de purgas. Mantener `chat-mantenimiento` y `FYAG_CHAT_PURGA_AUTORIZADA` sin activar hasta entonces. No alterar respaldos históricos para hacer coincidir su retención con la del sistema activo.
- [ ] Firmar go/no-go y validar salud privada, recorrido de negocio y evidencias de entrega tras la apertura autorizada. Ante fallos de restauración o permisos, mantener el destino aislado; no reabrir con identidades privilegiadas ni eludir guardas.

## Alcance y riesgos residuales

- No se añadieron funciones ni se retiraron archivos rastreados: no se confirmó otro temporal o componente muerto. Se distinguieron instrucciones vigentes de notas históricas, se cotejaron dependencias runtime/pruebas, imports de los smokes, consumidores del JSON de purga, plantillas y exclusiones. La revisión por nombres y firmas del árbol rastreado no certifica todo el historial, ni sustituye un escáner y rotación ante cualquier exposición.
- La CI nueva reutiliza smokes bajo sus guardas sintéticas: HTTPS y `ready` en Compose base, denegaciones web y Chat con PostgreSQL real, integridad del respaldo y restauración offline con purga, fallos recuperables y contención. No reproduce la conversión in situ, todas las identidades, SMTP real, WSS institucional ni el volumen de operación.
- Riesgos técnicos conservados: duración residual del access tras logout, gastos manuales inciertos que requieren conciliación y acoplamientos diferidos. Arquitectura de un nodo, sin HA/PITR; SQL, Mongo y archivos no son una transacción distribuida. Los datos caducados pueden seguir en copias bajo custodia. Los resultados previos de laboratorio no certifican producción.

## Verificación de esta consolidación

- 28 filas únicas, 40 OpenAPI JSON/YAML parseados, enlaces locales de las guías revisados, sintaxis de Python de despliegue y de YAML/Bash de CI, y render del Compose base y SMTP. `pip check` de la imagen productiva y coherencia `package.json`/lock aprobados; no se cambiaron versiones.
- Construcción local de las cuatro imágenes y smoke AUD-025 de web en PostgreSQL 18.6 nuevo: migración, denegaciones, auditoría de solo anexado y un ingreso idempotente. `verify` y cuatro rechazos del verificador AUD-023 aprobados sobre una copia sintética previa que no se modificó. No se volvió a levantar ni se eliminaron recursos de los laboratorios anteriores.
- La repetición íntegra de la nueva CI no se certifica en este corte: el Docker local agotó sus subredes al levantar el origen con los servicios de borde. Se limpiaron solo los proyectos nuevos de esta verificación. Respaldo/restauración con Chat y bloqueo concurrente conservan evidencia anterior en el registro de auditoría; queda pendiente la primera ejecución del workflow completo en GitHub. Sin regresión global, merge ni despliegue.
