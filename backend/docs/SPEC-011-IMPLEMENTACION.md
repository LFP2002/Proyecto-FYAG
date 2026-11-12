# SPEC-011 — Implementación backend de Reportes

## 1. Estado y alcance

Implementación local en `feature/backend-011-reportes`, sobre
`8622a554d40d74d9e551c3c39676f1a445960404` (PR #36). Contrato de referencia:
`specs/011-reportes-backend.md`, leído íntegramente antes de implementar.
La rama estaba limpia y coincidía con `origin/main` al comenzar.

Incluye catálogo, tres consultas independientes y las nueve combinaciones
CSV/XLSX/PDF. No cambia frontend, modelos, migraciones ni reglas económicas.
No crea tablas, archivos públicos ni eventos económicos en Auditoría.
Al cerrar la validación local no se habían realizado commits, push, PR, merge ni
despliegue productivo. La revisión preliminar posterior autorizó preparar commits,
publicar la rama y abrir PR hacia `main`; no autoriza merge. Los resultados de CI
remoto y el identificador del PR se informarán en la entrega de publicación.

Contrato para integración: [OpenAPI 3.1](openapi/SPEC-011-v1.json).

## 2. Arquitectura e inventario

| Archivo bajo `backend/apps/reportes/` | Responsabilidad |
| --- | --- |
| `catalogo.py` | Registro cerrado de tipos, columnas, formatos y límites |
| `permissions.py` | Matriz RBAC y relectura persistida de usuario |
| `filtros.py` | Whitelist estricta, fechas civiles, rango y paginación |
| `consistencia.py` | Snapshot PostgreSQL, presupuesto de tiempo, errores controlados |
| `consultas.py` | Fuentes propietarias, importes oficiales y totales globales |
| `serializers.py` | Proyecciones cerradas y fechas ISO Santiago |
| `services.py` | Orquestación, materialización, temporal y logs JSON |
| `views.py` | Contrato HTTP, negociación, headers, HEAD y errores saneados |
| `throttles.py` | Tasa de exportación por usuario |
| `urls.py` | Registro de las cinco rutas contractuales |
| `exportadores/comun.py` | Normalización, metadatos y proxy de tamaño |
| `exportadores/csv.py` | CSV UTF-8 BOM, `;`, CRLF y neutralización |
| `exportadores/xlsx.py` | OOXML write-only, precisión textual y cleanup XML/ZIP |
| `exportadores/pdf.py` | PDF A3 horizontal paginado y fuente embebida |
| `tests/base.py` | Fixtures reales reutilizadas de Dashboard/Finanzas y lectores |
| `tests/test_api.py` | Contratos, roles, filtros, precisión, DST e integridad |
| `tests/test_exportaciones.py` | Nueve binarios, tipos, seguridad, límites y limpieza |
| `tests/test_concurrencia.py` | Veinte intercalaciones con conexiones PostgreSQL reales |
| `tests/test_operacion.py` | Presupuesto de tiempo y perfil de 1.000 filas |

Modificaciones externas justificadas:

- `backend/config/urls.py`: incluye exclusivamente `/api/reportes/`.
- `backend/config/settings.py`: expone `Content-Disposition` y `X-Correlation-ID`
  a JavaScript CORS; no amplía orígenes, credenciales, cookies ni CSRF. Logger
  específico `apps.reportes.services` INFO a consola, sin duplicación ni cambio
  del nivel global, para que los eventos estructurados se emitan realmente.
- `backend/apps/finanzas/consultas_cobranzas.py`: argumento interno opcional
  keyword-only `hoy`; por defecto conserva `hoy_santiago()`. Permite fijar el día
  civil del snapshot; no altera fórmula ni contratos existentes. Prueba de
  equivalencia con el caller original.
- `backend/requirements.txt`: bibliotecas runtime y dos transitivas nuevas fijadas.
- `backend/requirements-test.txt`: agrega lector PDF QA, sin importarlo en runtime.
- `backend/Dockerfile`: `ARG REQUIREMENTS_FILE=requirements.txt`, copia ambos
  requisitos y permite elegir QA explícitamente.
- `compose.yaml`: backend de desarrollo instala requisitos QA para ejecutar
  pruebas dentro del contenedor. Migraciones y reconciliador conservan runtime.
- `.github/workflows/backend-ci.yml`: instala requisitos QA y amplía su clave de
  caché; no declara que CI remoto haya sido ejecutado.
- Este informe y `backend/docs/openapi/SPEC-011-v1.json`.

## 3. Contrato REST y filtros

| Ruta GET | Acceso | Datos |
| --- | --- | --- |
| `/api/reportes/catalogo/` | G/AF | Solo tipos autorizados al rol |
| `/api/reportes/obras/` | G | Proyección de Obras; neto oficial |
| `/api/reportes/rentabilidad/` | G | FINALIZADA con cierre inmutable |
| `/api/reportes/cobranzas/` | G/AF | Documentos VIGENTE; misma proyección para ambos |
| `/api/reportes/{tipo}/exportar/` | Según tipo | `formato=csv|xlsx|pdf` obligatorio |

Listados: `count`, `next`, `previous`, `results`, `totales`, `periodo`, `moneda`,
`fecha_corte`; 25 filas fijas. Totales del filtro entero, incluso al consultar
una página posterior. Orden fecha base descendente e ID descendente. Sin filas:
página 1 válida, totales cero; páginas posteriores devuelven 400.

- `desde` y `hasta` juntos, YYYY-MM-DD válido, sin futuro ni inversión y máximo
  366 días inclusivos. Por defecto: día 1 del mes actual de Santiago hasta hoy.
- `cliente`: entero positivo ASCII dentro de bigint, sin signos ni ceros iniciales.
- Obras: cinco estados reales, `fecha_base=CREACION|FINALIZACION` (default CREACION).
  FINALIZACION exige estado FINALIZADA u omitido.
- Rentabilidad: solo fechas y cliente; no acepta estado ni fecha_base.
- Cobranzas: fecha_emision y estado derivado PENDIENTE/PARCIAL/PAGADA/VENCIDA.
- Se rechazan parámetros desconocidos, repetidos o vacíos, incluidos `format`
  (atajo DRF), `limit` y `page` en exportación.
- `page` inválida o fuera de rango: 400. No hay tamaño de página configurable.
- Límites civiles mediante inicio del día siguiente en `America/Santiago`, no
  suma de 86.400 segundos. Se prueban días DST de 23 y 25 horas.
- Importes JSON strings de dos decimales; folio externo siempre texto.

HEAD/OPTIONS están sujetos a autenticación y rol, sin cuerpos de descarga.
HEAD de exportación valida filtros, integridad y máximo de filas sin crear ni
renderizar archivo. No promete `Content-Length`: el tamaño comprimido/final no
puede conocerse sin renderizar; GET aplica los 50 MiB reales antes de transmitir.
Esta distinción también consta en OpenAPI.

Negociación explícita JSON para catálogo/listados/errores; el parámetro `formato`
gobierna el `FileResponse`. `Accept: application/pdf` no provoca un 406 antes de
la autorización y validación. La query `format` no elude la whitelist.

## 4. Seguridad

GERENCIA: todos los tipos; ADMINISTRATIVO_FINANZAS: catálogo restringido y
Cobranzas. SUPERVISOR_OBRAS, TECNICO y ADMINISTRADOR_TI: 403. No hay elevación por
`is_staff`, `is_superuser`, grupos o claims de rol. Se reutiliza JWT versionado
del sistema y se releen actividad, rol y `sesion_version` en PostgreSQL; para
listados/archivos se repite dentro del snapshot.

401: sesión ausente/expirada/revocada/inactiva. 403: rol/tipo no autorizado.
404: tipo exportable desconocido para rol habilitado. 405: mutación por actor
autorizado. 400: filtros. 409: fuente inconsistente. 413: volumen. 429: tasa.
500: fallo inesperado/timeout saneado con identificador de correlación.

Headers de la fachada: `Cache-Control: private, no-store`, `Vary: Authorization`,
`X-Content-Type-Options: nosniff`, CSP `default-src 'none'; sandbox`. Descargas con
MIME real y nombre ASCII controlado `fyag-{tipo}-{YYYYMMDD-HHMMSS}.{formato}`.
Sin JWT en URL ni rutas públicas. El frontend debe usar Bearer y leer blob en
éxito; ante error, interpretar JSON y respetar `Retry-After` en 429.

Throttle GET/HEAD: 5/min por usuario, compartido entre tipos y formatos. OPTIONS
no genera archivos ni consume esa tasa. El caché local predeterminado limita por
proceso, no todo el despliegue: en múltiples workers se debe configurar un caché
compartido. DRF throttle es control operativo aproximado, no un cupo atómico.

## 5. Exactitud económica

- Presupuesto: `calcular_subtotal(cantidad, precio_unitario)` por línea y
  `sumar_monto_neto`, con Decimal y ROUND_HALF_UP oficial. Acumulación con contexto
  de precisión 80; no float ni total redondeado a partir de líneas sin redondear.
- Rentabilidad: únicamente FINALIZADA; `cierre_costos.costo_total` persistido.
  `margen_neto = presupuesto_neto - costo_real_neto`. Sin cierre: 409
  `cierre_costos_inconsistente`; nunca costo cero inventado.
- `tiene_cortesia_sin_cobro` señala cortesía real; no borra costos ni convierte
  margen en ingreso cobrado o utilidad contable.
- Cobranzas: `con_cobranza` propietario, subconsulta de pagos activos sin
  multiplicar documentos; excluye documentos revertidos. Se conserva el estado
  derivado oficial al día del corte. No se mezcla bruto documentado con neto.
- Saldo negativo, abono fuera de relación o total distinto de abono+saldo: 409
  `saldo_inconsistente`; agregados fuera del rango financiero: 409
  `importe_fuera_rango`. La validación abarca todo el filtro, no solo la página.

## 6. Archivos auténticos y temporales

CSV: BOM UTF-8, delimitador `;`, CRLF, módulo `csv` para comillas. Metadatos y
totales antes de la cabecera tabular. Se neutralizan textos que, tras blancos y
controles, comiencen en `=`, `+`, `-`, `@` mediante apóstrofo. Los importes
monetarios negativos genuinos, incluidos totales, no reciben apóstrofo. Se
conserva el folio en el contenido, pero Excel puede inferirlo numérico al abrir
CSV: importar columna como texto o preferir XLSX; no se inyecta una fórmula para
preservarlo.

XLSX: openpyxl write-only; hojas Resultados y Resumen. Importes, IDs y folios como
texto exacto para evitar el límite de 15 dígitos de Excel; booleanos como booleanos.
Sin macros, fórmulas ni vínculos externos. Cabeceras y anchos definidos; resumen
con metadatos/totales. Consumidores no deben asumir celdas monetarias numéricas.

PDF: ReportLab Canvas y una fila Table a la vez; A3 horizontal, ajuste de textos,
encabezados repetidos, páginas, fecha de corte, moneda y totales. Fuente Vera TTF
embebida incluida en ReportLab, sin acceso remoto. Acentos y montos de 38 dígitos
verificados mediante extracción real de texto. Aviso de reporte de gestión, no
documento tributario ni DTE. No se afirma inspección visual manual de cada página.

Se normalizan controles, bidi/zero-width, surrogates y no-caracteres XML. La
normalización de seguridad puede cambiar esos caracteres invisibles respecto de
JSON, sin modificar montos/cálculos. PDF escapa markup antes de Paragraph.

Máximo 10.000 filas y 50*1024*1024 bytes, inclusivos. Conteo previo y proxy seekable
que verifica antes de cada write; comprobación final antes de FileResponse.
Sobre límite: 413 JSON sin iniciar bytes HTTP 200. Prueba real de 10.000 filas CSV
y 10.001 rechazadas para los tres formatos y HEAD. Límite real de 50 MiB probado
en el proxy; 413 HTTP de los tres exportadores probado con límite reducido, no
se afirma haber generado un PDF/XLSX válido de 50 MiB.

`TemporaryFile` privado (permiso observado en Docker Linux: 0o600), sin directorio
público ni persistencia intencional. Se completa dentro del snapshot y luego se
transfiere su propiedad a FileResponse. Error de generación/construcción de
respuesta: cierre explícito. Éxito/desconexión: cierre del recurso por el iterable
WSGI/Django. Pruebas consumen parcialmente y cierran la respuesta, comprobando el
descriptor. No se probó desconexión real a través de proxy productivo remoto.

openpyxl usa temporales XML: cierre de hojas y cleanup explícito también en
errores; ZipFile en contexto explícito. Esta parte utiliza `_writer` privado de
openpyxl fijado en 3.1.5: al actualizar, repetir pruebas de cleanup. En Linux el
archivo principal puede estar desvinculado mientras existe el descriptor; al
cerrarlo se libera. No es garantía de borrado físico de bloques ni de ausencia
de swap/backups del host: configurar almacenamiento temporal según política.

## 7. Consistencia y recursos

Transacción propia `REPEATABLE READ, READ ONLY`, snapshot fijado con
`pg_current_snapshot()` antes de revalidación y agregados. Rechaza un atomic
exterior para no degradar silenciosamente el aislamiento. Corte único y zona
Santiago; `SET LOCAL statement_timeout=30000ms`, sin cambio de aislamiento global.
Presupuesto cooperativo de procesamiento de 60 s y máximo 2.000 páginas PDF;
filas PDF que no caben de forma legible se rechazan con 413, no se recortan.

La consulta no usa locks de escritura. Pruebas concurrentes confirman commits del
escritor antes de liberar al lector pausado entre totales/filas. Count, filas,
totales, estados y archivo permanecen en el snapshot previo. FileResponse ya no
ejecuta SQL (prueba con CaptureQueriesContext durante consumo/cierre).

Lotes de 200, `.values()` y cursor iterator; consultas de líneas por lote, no por
fila. JSON solo materializa 25 filas, aunque computa totales del filtro completo.
Los snapshots de solicitudes distintas pueden diferir: volver a descargar no
reutiliza el snapshot de una página anterior, ni reconstruye cartera histórica.

El límite de tiempo es cooperativo, no un watchdog duro para toda llamada de
biblioteca. El tamaño final de 50 MiB no limita cada XML intermedio ni toda la
memoria del proceso. ReportLab retiene estructuras de páginas; openpyxl consume
disco temporal. Limitar concurrencia, espacio temporal y recursos del contenedor;
los resultados locales siguientes no constituyen un SLA ni benchmark productivo.

## 8. Trazabilidad

Logger dedicado INFO `apps.reportes.services`, JSON por evento con actor ID, rol,
tipo/formato de catálogo, cantidad de filas, corte, duración, resultado y UUID de
correlación generado por servidor. No registra filtros libres, tokens, cookies,
contenido completo, folios, importes, SQL o datos personales innecesarios.

Resultados: `solicitud`, `validada_head_sin_generacion`,
`archivo_generado_no_confirma_descarga`, `error`. No se afirma que el usuario haya
guardado el archivo. Errores internos registran clase, no excepción completa.
Rechazos anteriores al servicio (autenticación, permiso, throttle) no generan un
evento de archivo generado. No se altera el catálogo cerrado de Auditoría.
Configurar retención/acceso a logs; este módulo no crea un almacén de auditoría.

## 9. Dependencias y Docker

| Paquete fijado | Uso | Licencia declarada | Python requerido |
| --- | --- | --- | --- |
| openpyxl 3.1.5 | XLSX runtime | MIT | >=3.8 |
| reportlab 5.1.0 | PDF runtime | BSD | >=3.9,<4 |
| et-xmlfile 2.0.0 | Transitiva openpyxl | MIT | >=3.8 |
| charset-normalizer 3.5.2 | Transitiva ReportLab | MIT | >=3.7 |
| pypdf 7.0.1 | Lector QA exclusivamente | BSD-3-Clause | Compatible con Python 3.13 ejecutado |

PyPI y OSV consultados para las cinco versiones durante la implementación:
sin avisos conocidos devueltos por OSV; esto no garantiza ausencia absoluta de
vulnerabilidades. Licencias instaladas verificadas en dist-info, incluida licencia
Bitstream Vera junto a la fuente, que permite distribución con software bajo sus
condiciones. No se añaden extras gráficos/Cairo/aceleradores ni servicios externos.
Pillow ya existía en requisitos. Runtime no importa pypdf.

Fuentes de comprobación: `https://pypi.org/pypi/{paquete}/{version}/json` y
`https://api.osv.dev/v1/query` (ecosistema PyPI, nombre y versión exactos).
Wheels consultadas: openpyxl 250.910 B, ReportLab 2.018.647 B, pypdf 416.136 B.
Python de imagen: 3.13.18; instalación y `pip check` correctos.

Dos reconstrucciones Compose realizadas correctamente durante implementación.
Imagen backend de desarrollo antes: 319.755.724 B; segunda medición después:
332.885.102 B (+13.129.378 B), incluidos QA y código de esa construcción. No es
una medida aislada del peso runtime ni de la imagen final con este informe.
Dependencias preexistentes no estaban íntegramente fijadas y siguen así: no se
introduce un lock global ajeno al alcance.

## 10. Evidencia de validación

Pruebas sobre PostgreSQL real de Compose, `TransactionTestCase`, sin SQLite ni
mock de las fuentes económicas. Fixtures contractuales temporales, sin poblar la
base de desarrollo con reportes inventados. Lectores: `csv`, openpyxl y pypdf;
inspección ZIP OOXML sin fórmulas, macros o vínculos.

### Resultados

Ejecución local del 12-11-2026. No se considera aprobado un proceso todavía activo.

| Comprobación | Evidencia disponible |
| --- | --- |
| Suite Reportes antes del último ajuste HTTP/logger | 48 Passed, 0 Failed, 36,109 s |
| Suite Reportes sobre estado final | 48 Passed, 0 Failed, 36,562 s |
| Regresión completa sobre estado final | 807 Passed, 0 Failed, 199,314 s |
| Regresión anterior al último ajuste HTTP/logger | 807 Passed, 0 Failed, 203,604 s |
| `manage.py check` | Sin incidencias |
| `makemigrations --check --dry-run` | No changes detected |
| `migrate --plan` | No planned migration operations |
| `python -m pip check` | No broken requirements found |
| `docker compose config --quiet` | Exit 0 |
| Construcción/inicio Compose | Correctos |
| Smoke HTTP real dentro de Compose, cinco rutas con Accept PDF y sin JWT | 5/5 devuelven 401 JSON, no-store y nosniff |
| `git diff --check` | Correcto; avisos de conversión LF/CRLF del entorno, no errores |
| Revisión de alcance | 30 archivos modificados/nuevos; frontend/modelos/migraciones intactos; sin nuevos CSV/XLSX/PDF/tmp/log en Git |
| Revisión de secretos | Sin coincidencias de firmas comunes de claves privadas, tokens GitHub/AWS/JWT en archivos cambiados; no sustituye un escáner exhaustivo |

Cobertura: matriz roles/claims/flags, sesiones, HEAD/OPTIONS, contratos y filtros
estrictos, redondeo por línea, margen positivo/cero/negativo, cortesías, cierres
ausentes, corrupción, pagos parciales/completos/anulados, documentos revertidos,
vencimiento, paginación/totales, DST, nueve archivos, cero filas, precisión grande,
acentos/textos maliciosos, MIME/CORS, límites, throttle, temporales, errores y SQL
fuera de snapshot. Veinte intercalaciones: registro de pago, anulación, registro
de documento, reversión y finalización de obra, cada una JSON/CSV/XLSX/PDF.

Warnings `OrigenInconsistente` son casos negativos 409 esperados; avisos de token
de usuario inactivo pertenecen también a pruebas negativas existentes.
Correcciones encontradas durante desarrollo: keyword duplicada del filtro de
creación, precisión del fixture límite, cierre ZIP/XML al fallar, CSV de totales
negativos, negociación Accept binario/atajo format y emisión operativa de INFO.
No hay validación de CI remoto, Postman ni frontend; no se declaran aprobados.

Validación local cerrada: las dos suites finales terminaron con `OK` y eliminaron
su base de pruebas. No quedan ejecuciones pendientes. La aceptación de publicación
y el criterio de integración en main siguen sujetos a revisión, CI y Postman del
flujo contractual; no se presentan como ya completados.

### Perfil reproducible de 1.000 obras

Medición de la suite específica final, fixture de una línea
por obra, `tracemalloc` (pico Python, no RSS total), tiempo local incluyendo captura
de consultas. JSON: primera página con totales de 1.000, archivos: todas las filas.

| Salida | SQL | Tiempo s | Bytes salida | Pico Python B |
| --- | ---: | ---: | ---: | ---: |
| JSON | 16 | 0,121 | 8.199 | 239.591 |
| CSV | 21 | 0,424 | 105.786 | 596.138 |
| XLSX | 21 | 1,283 | 53.171 | 601.725 |
| PDF | 21 | 5,733 | 100.846 | 2.296.110 |

PDF: 34 páginas. EXPLAIN ANALYZE de selección paginada: nodo Limit, 25 filas,
planning 0,267 ms, execution 0,321 ms. No demuestra rendimiento idéntico para
clientes con muchas líneas/pagos o para todos los tamaños de producción.

Comandos de reproducción (secuenciales; no competir por `test_fyag_db`):

```bash
docker compose up -d --build
docker compose exec -T backend python manage.py check
docker compose exec -T backend python manage.py makemigrations --check --dry-run
docker compose exec -T backend python manage.py migrate --plan
docker compose exec -T backend python -m pip check
docker compose exec -T backend python manage.py test apps.reportes --noinput
docker compose exec -T backend python manage.py test --noinput
docker compose config --quiet
```

## 11. Despliegue y rollback (procedimiento, no ejecutado en producción)

1. Tras revisión y autorización de publicación, construir imagen con
   `REQUIREMENTS_FILE=requirements.txt` para runtime y requisitos QA para tests.
2. Ejecutar check, revisión de migraciones, suite Reportes y regresión completa
   sobre PostgreSQL. No hay migraciones nuevas que aplicar por SPEC-011.
3. Desplegar con Bearer sobre HTTPS, temporal privado con espacio/controles del
   host, límites de recursos y concurrencia. No usar runserver como servidor
   productivo. Garantizar cierre del iterable/respuesta en WSGI/proxy.
4. Configurar caché compartida para throttle multiworker, retención de logs y
   timeouts del proxy coherentes con generación (el presupuesto no es SLA).
5. Smoke autenticado por G/AF, catálogo restringido y tres formatos; comprobar
   headers privados/CORS, errores JSON, CPU/disco/RSS y desconexión del proxy real.
6. No habilitar ATOMIC_REQUESTS exterior para estos servicios sin rediseñar su
   transacción propia. Revisar planes con volumen productivo antes de escalar.

Rollback: desplegar imagen/configuración anterior aprobada, retirar registro de
rutas de Reportes y la configuración logger/CORS añadida si se revierte código.
Revertir exclusivamente cambios de SPEC-011 y requisitos nuevos en una revisión
controlada; no resetear trabajo ajeno ni eliminar volúmenes. La extensión opcional
de Finanzas puede revertirse junto con el caller. No hay rollback de esquema ni
datos financieros que deshacer. Las rutas dejarán de existir: coordinar con el
frontend antes de retirar el servicio. Reconstruir imágenes para retirar librerías;
no borrar dependencias a mano dentro de contenedores en servicio.

## 12. Riesgos residuales y límites declarados

- Consistencia por respuesta, no entre páginas/descargas separadas; rol revocado
  después de fijar el snapshot puede afectar una solicitud posterior, no reescribir
  el snapshot de lectura ya autorizado.
- Throttle local aproximado hasta configurar caché compartida.
- CSV puede sufrir inferencia de Excel; XLSX preserva importes como texto exacto.
- HEAD no anticipa tamaño final; GET siempre lo verifica antes de enviar.
- No se garantiza tiempo duro, RSS constante, borrado físico ni control de
  concurrencia global; aplicar límites de infraestructura y observar producción.
- PDF probado con lector/extracción, no revisión visual exhaustiva ni todos los
  scripts Unicode. Vera cubre los acentos del contrato, no cualquier alfabeto.
- Cleanup de openpyxl depende de API privada de versión fijada; repetir al actualizar.
- Desconexión simulada mediante cierre parcial real de FileResponse, no prueba
  de un proxy productivo. El cliente puede perder la conexión durante transmisión;
  eso no convierte una generación fallida en éxito ni confirma guardado local.
- OpenAPI comprobado como JSON y por referencias/proyecciones contra serializers;
  no se afirma validación con una herramienta externa completa de OpenAPI.

**Punto de detención actualizado:** publicación de commits y PR autorizada tras
revisión preliminar. Detenerse después de comprobar Backend CI para auditoría
independiente y suite Postman. No realizar merge.
