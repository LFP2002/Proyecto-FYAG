# SPEC-011 — Reportes y exportaciones reales (backend)

**Estado: IMPLEMENTADA E INTEGRADA EN `main` mediante [PR #37](https://github.com/LFP2002/Proyecto-FYAG/pull/37).** El módulo `apps.reportes` ofrece las cinco rutas REST definidas y las exportaciones auténticas CSV, XLSX y PDF. El contrato OpenAPI se encuentra en `backend/docs/openapi/SPEC-011-v1.json`. El frontend continúa bajo responsabilidad de sus colaboradores; el prototipo anterior no equivale a integración frontend. Las secciones contractuales siguientes documentan las reglas del backend integrado.

## 1. Objetivo, contexto y precedencia

Proveer a los perfiles autorizados un catálogo de reportes, tres consultas tabulares paginadas y exportaciones **reales** en CSV, XLSX y PDF. Las consultas y los archivos deben reflejar las **mismas fuentes de verdad**, filtros y reglas financieras de los módulos ya integrados. El frontend consumirá datos JSON y descargará blobs autenticados sin recalcular montos.

Fuentes verificadas en `main`: `apps.obras.Obra` y `CierreCostosObra` inmutable; `apps.comercial.Presupuesto` e ítems, con `calcular_subtotal` y `sumar_monto_neto`; `apps.finanzas.DocumentoCobro`, `PagoDocumento` y `con_cobranza` (subconsulta de pagos activos); `apps.dashboard` (SPEC-010, PR #34); Usuarios/JWT versionado y Auditoría (SPEC-008, PR #27). SPEC-009 Alertas no se integra directamente en los reportes.

**Precedencia:** conservan autoridad las validaciones, fórmulas, restricciones, permisos y modelos originales de Comercial, Obras, Finanzas y Usuarios. Las discrepancias materiales deben elevarse antes de modificar contratos. No reimplementar el motor de costos ni el de pagos, ni introducir tarifas o porcentajes de avance del prototipo.

## 2. Seguridad y autorización (RBAC contractual)

| Rol persistido y activo | Catálogo | Obras | Rentabilidad | Cobranzas |
|---|---|---|---|---|
| GERENCIA | Sí: tres tipos | JSON + exportación | JSON + exportación | JSON + exportación |
| ADMINISTRATIVO_FINANZAS | Sí: solo cobranzas | 403 | 403 | JSON + exportación |
| SUPERVISOR_OBRAS | 403 | 403 | 403 | 403 |
| TECNICO | 403 | 403 | 403 | 403 |
| ADMINISTRADOR_TI | 403 | 403 | 403 | 403 |
| Sin sesión, inactivo, JWT expirado/revocado | 401 | 401 | 401 | 401 |

Permisos efectivos siempre se evalúan **en el servidor** y vuelven a comprobar `Usuario.rol`, `is_active` y `sesion_version` persistidos; no confiar en claims, menús React, `is_staff/is_superuser` ni URLs generadas por el navegador. Gerencia puede ver rentabilidad interna; Finanzas **nunca** recibe costos, tarifas, márgenes, descripciones libres, documentos de otros tipos ni detalle de evidencias privadas en sus proyecciones de Reportes. Evitar filtraciones por 403/404 diferenciados, `OPTIONS`, errores y nombre de archivo. No retornar RUT, correo, teléfono, folio de respaldo, referencias bancarias, fotos, datos de personas ni notas libres de módulos propietarios.

Todas las rutas requieren `Authorization: Bearer <JWT>`. `GET/HEAD/OPTIONS` permitidos para el rol y recurso autorizados; métodos de escritura → 405 después de autorización, sin efectos colaterales. `Cache-Control: private, no-store` y `Vary: Authorization` para respuestas JSON y binarias. Identidad inválida → 401; rol sin acceso → 403. No usar tokens en querystring, enlaces públicos, firmas transferibles ni descargas anónimas.

## 3. Rutas REST v1

| Método | Ruta | Roles |
|---|---|---|
| GET | `/api/reportes/catalogo/` | G, AF |
| GET | `/api/reportes/obras/` | G |
| GET | `/api/reportes/rentabilidad/` | G |
| GET | `/api/reportes/cobranzas/` | G, AF |
| GET | `/api/reportes/{tipo}/exportar/?formato=csv\|xlsx\|pdf` | Segun tipo y rol |

`tipo` es únicamente `obras`, `rentabilidad` o `cobranzas`. Tipo no definido para usuario autenticado de rol habilitado → 404 controlado; tipo real no autorizado → 403, sin revelar información tabular. Todas las rutas usan slash final. El cuerpo en listados/catálogo es JSON y las exportaciones son archivos reales. **No se habilitan descargas hasta implementar los tres formatos completos.**

### 3.1 Catálogo

`GET /api/reportes/catalogo/` no admite querystring. El catálogo devuelve únicamente lo visible para el rol actual y no informa el catálogo completo cuando el rol no lo permite.

Esquema estable, ejemplo sintético de Gerencia:

~~~json
{
  "moneda": "CLP",
  "zona_horaria": "America/Santiago",
  "formatos": ["csv", "xlsx", "pdf"],
  "reportes": [
    {"tipo": "obras", "titulo": "Reporte de obras", "filtros": ["desde", "hasta", "cliente", "estado", "fecha_base"], "formatos": ["csv", "xlsx", "pdf"]},
    {"tipo": "rentabilidad", "titulo": "Rentabilidad de obras finalizadas", "filtros": ["desde", "hasta", "cliente"], "formatos": ["csv", "xlsx", "pdf"]},
    {"tipo": "cobranzas", "titulo": "Cobranzas de documentos vigentes", "filtros": ["desde", "hasta", "cliente", "estado"], "formatos": ["csv", "xlsx", "pdf"]}
  ]
}
~~~

Para AF, `reportes` contiene **solo cobranzas**. `titulo` no incluye métricas no implementadas. El catálogo no entrega archivos o URLs temporales.

### 3.2 Parámetros comunes y convención temporal

Para los tres listados, parámetros aceptados:
- `desde=YYYY-MM-DD` y `hasta=YYYY-MM-DD`: ambos presentes o ambos ausentes. Fechas civiles válidas, en zona `America/Santiago`. Inclusivos; longitud máxima **366 días civiles** (comprobar `(hasta-desde).days <= 365`), `desde <= hasta`, `hasta <= hoy Santiago`.
- **Por defecto:** primer día del mes civil actual de Santiago hasta hoy Santiago, incluso si no hay registros.
- `cliente`: ID entero positivo, sin signos, ceros iniciales ni exponenciales, máximo 2⁶³-1; filtra `presupuesto__cliente_id` o `obra__presupuesto__cliente_id` según fuente.
- `page`: únicamente listados JSON; entero positivo, sin signos, ceros a la izquierda, decimales ni valores vacíos. Por defecto 1. Tamaño fijo **25**. Página fuera de rango → 400 con clave `page`.
- `estado` y `fecha_base` exclusivamente para los tipos indicados en §3.3.
- `formato` **únicamente exportación**; obligatorio y uno de `csv`, `xlsx`, `pdf`, en minúsculas. Exportar con `page` es 400.

Todo querystring se valida contra whitelist específica: parámetros desconocidos, repetidos (`getlist`), vacíos, mal tipados, fecha inexistente, rango invertido, futuro, `9999-12-31` que cause overflow o `cliente=0` → **400**. No interpretar filtros inexistentes como datos inexistentes. La ausencia de registros válidos → 200 con cero y archivo con encabezados.

Fechas civil Santiago: `desde` comienza en medianoche local inclusiva; `hasta` termina en medianoche local siguiente exclusiva; los timestamps se comparan en PostgreSQL con su offset correcto según DST (días de 23/25 h). `fecha_corte` es instante ISO8601 con offset Santiago (no forzar -03/-04). **Los estados filtrados son estado actual en el momento de lectura, no históricos reconstruidos.** No generar registros posteriores al instante `fecha_corte`.

### 3.3 Matriz de filtros por tipo

| Tipo | Campo fecha filtrado | Estado permitido | Otro parámetro |
|---|---|---|---|
| `obras` | `Obra.creado_en` por defecto | `PLANIFICADA\|EN_PROCESO\|SUSPENDIDA\|FINALIZADA\|CANCELADA` | `fecha_base=CREACION\|FINALIZACION` |
| `rentabilidad` | `Obra.finalizado_en` | Fijo `FINALIZADA`; no acepta `estado` ni `fecha_base` | `cliente` |
| `cobranzas` | `DocumentoCobro.fecha_emision` | `PENDIENTE\|PARCIAL\|PAGADA\|VENCIDA` calculado con `con_cobranza` | `cliente` |

Para obras, `fecha_base=FINALIZACION` selecciona **solo obras actualmente FINALIZADA**, sin `finalizado_en` nulo; opcional `estado=FINALIZADA` es compatible; cualquier otro `estado` con esa fecha_base → 400 por contradicción. `fecha_base=CREACION` admite los cinco estados. Si `estado` se omite, no filtra estados en CREACION.

`rentabilidad` incluye exclusivamente FINALIZADA con `CierreCostosObra`; una FINALIZADA seleccionada sin cierre real → **409** `cierre_costos_inconsistente`, no omitir ni coste cero. `cobranzas` incluye **solo documentos actualmente VIGENTE**, con saldo y estado actuales aunque su fecha de emisión pertenezca a un periodo anterior. No se reconstruyen la cartera ni pagos a una fecha histórica.

## 4. Esquemas JSON exactos

Cada listado `GET /api/reportes/{tipo}/` entrega el siguiente envelope y **las mismas claves** para los tres tipos. `count` y `totales` corresponden al **filtro completo**, no solo a las 25 filas de `results`.

~~~json
{
  "count": 0,
  "next": null,
  "previous": null,
  "results": [],
  "totales": {},
  "periodo": {"desde": "2026-11-01", "hasta": "2026-11-12"},
  "moneda": "CLP",
  "fecha_corte": "2026-11-12T18:00:00-03:00"
}
~~~

En una respuesta real, `totales` usa el esquema específico del tipo, nunca `{}`. `next`/`previous` son URL a la misma API, sin JWT, o `null`; parámetros serializados y host seguro. JSON monetario se devuelve como **string decimal exacto de dos cifras fraccionarias**, incluidos cero y margen negativo (por ejemplo `"-12.34"`); nunca float, NaN ni notación científica. Campos ISO y nullability se fijan a continuación.

### 4.1 Obras — filas y totales

Orden estable: `Obra.creado_en DESC, Obra.id DESC` si `fecha_base=CREACION`; `Obra.finalizado_en DESC, Obra.id DESC` si `fecha_base=FINALIZACION`.

Cada `results[]` contiene exactamente:
- `obra`: integer >0.
- `codigo_obra`: string, formato oficial `OB-000037` (mínimo 6 cifras, sin suponer límite artificial para ID alto).
- `cliente`: integer >0.
- `cliente_nombre`: string desde `Cliente.nombre_legal`.
- `categoria_nombre`: string desde `CategoriaServicio.nombre`.
- `estado`: uno de los 5 estados actuales.
- `tecnico_responsable`: integer o null; `tecnico_nombre`: string o null, nombre laboral o `username` autorizado.
- `fecha_programada`: string YYYY-MM-DD o null.
- `creado_en`: timestamp ISO8601 con offset Santiago.
- `finalizado_en`: timestamp ISO8601 con offset Santiago o null.
- `presupuesto_neto`: string de dinero neto CLP calculado desde `Presupuesto` por línea.

**Totales:**

~~~json
{"obras": 0, "presupuesto_neto": "0.00"}
~~~

`obras` coincide con `count`, `presupuesto_neto` suma el mismo conjunto filtrado. El reporte no afirma que una Obra haya generado ingresos por su presupuesto y **no expone avance porcentual, costo parcial ni margen proyectado**.

### 4.2 Rentabilidad — filas y totales

Orden estable: `Obra.finalizado_en DESC, Obra.id DESC`.

Cada `results[]` contiene exactamente:
- `obra`: integer >0.
- `codigo_obra`: string.
- `cliente`: integer >0.
- `cliente_nombre`: string.
- `finalizado_en`: timestamp ISO8601 con offset Santiago, no null.
- `moneda`: siempre `"CLP"`.
- `presupuesto_neto`: string Decimal.
- `costo_real_neto`: string Decimal del cierre inmutable.
- `margen_neto`: string Decimal = `presupuesto_neto - costo_real_neto`, admite negativo.
- `tiene_cortesia_sin_cobro`: boolean verdadero si existe `CortesiaObra` vigente de tipo SIN_COBRO.

**Totales:**

~~~json
{"obras": 0, "presupuesto_neto": "0.00", "costo_real_neto": "0.00", "margen_neto": "0.00"}
~~~

La suma del `margen_neto` es diferencia entre los totales netos y debe coincidir con la suma de márgenes de las mismas filas. Una cortesía **no elimina costos** y el margen no es ganancia contable, ingresos cobrados ni impuesto declarado. Aplicar las funciones de Comercial `calcular_subtotal/sumar_monto_neto` en el mismo orden de redondeo por línea; no usar producto agregado sin redondeo, ni `Sum` sobre joins que multipliquen cierres.

### 4.3 Cobranzas — filas y totales

Orden estable: `DocumentoCobro.fecha_emision DESC, DocumentoCobro.id DESC`.

Cada `results[]` contiene exactamente:
- `documento`: integer >0.
- `obra`: integer >0.
- `codigo_obra`: string oficial.
- `cliente`: integer >0.
- `cliente_nombre`: string.
- `tipo_documento`: `"FACTURA_AFECTA"` o `"FACTURA_EXENTA"`.
- `folio_externo`: **string** de dígitos ASCII, preservando todos sus ceros a la izquierda.
- `fecha_emision` y `fecha_vencimiento`: YYYY-MM-DD.
- `moneda`: `"CLP"`.
- `monto_documentado_bruto`: string Decimal, igual a `DocumentoCobro.monto_total`.
- `abonado`: string Decimal de pagos **activos**.
- `saldo`: string Decimal derivado.
- `estado_cobranza`: `"PENDIENTE"`, `"PARCIAL"`, `"PAGADA"` o `"VENCIDA"`, desde `con_cobranza` con hoy civil Santiago.

**Totales:**

~~~json
{
  "documentos": 0,
  "monto_documentado_bruto": "0.00",
  "abonado": "0.00",
  "saldo": "0.00",
  "saldo_vencido": "0.00"
}
~~~

`documentos` coincide con `count`. Los totales utilizan exactamente el mismo filtro de documentos y estado actual que la tabla; `monto_documentado_bruto = abonado + saldo` con aritmética exacta. `saldo_vencido` agrega solo documentos cuyo estado calculado es VENCIDA. No contar dos veces documentos con varios pagos, pagos anulados o documentos revertidos. Si los cálculos oficiales detectan saldo negativo, abonos superiores a documentos, importe no finito o sumatorias fuera de rango → **409** con código seguro, no 200 con totales engañosos.

Las proyecciones de Cobranzas son **idénticas** para Gerencia y Administrativo/Finanzas: este último no adquiere permisos de Rentabilidad por consultar otro tipo.

## 5. Exportaciones reales CSV, XLSX y PDF

`GET /api/reportes/{tipo}/exportar/?formato=csv|xlsx|pdf` acepta todos los filtros del **mismo tipo** de §3.3, salvo `page`. No admite `page`, `limit`, filtros adicionales, cabeceras de preferencias de fórmula, ni `formato` múltiple. Aplica **el mismo orden, proyecciones y totales completos** de su listado. La exportación representa la totalidad del conjunto filtrado hasta un máximo de **10.000 filas**; no exportar solo la página 1.

**Controles de volumen antes de generar archivos:**
- Si `count > 10000` → `413` con `{"code":"exportacion_demasiado_grande","detail":"..."}`, sin archivo parcial.
- Límite adicional de **50 MiB por archivo terminado**. Si se supera, responder 413 **antes de enviar cabeceras de éxito o bytes**; liberar temporales.
- Presupuesto de memoria acotado: usar iteradores/lotes y archivos privados de almacenamiento temporal cuando sea necesario; no cargar 10.000 objetos con relaciones y contenido binario simultáneamente.
- `HEAD` valida autorización, filtros y límites, devuelve cabeceras esperables y cuerpo vacío **sin renderizar el archivo completo**. `OPTIONS` restringido por rol no revela datos.
- Se recomienda throttle por usuario autenticado para exportación (por ejemplo **5/minuto** con 429 y `Retry-After` si está disponible); su alcance real en varias instancias dependerá de cache compartida y debe documentarse, nunca sustituye RBAC.

**Cabeceras de éxito (200):**
- CSV: `Content-Type: text/csv; charset=utf-8`.
- XLSX: `Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`.
- PDF: `Content-Type: application/pdf`.
- Todas: `Content-Disposition: attachment; filename="fyag-{tipo}-YYYYMMDD-HHMMSS.{ext}"`, nombre ASCII controlado generado por servidor, sin filtros ni nombres de cliente.
- `X-Content-Type-Options: nosniff`, `Cache-Control: private, no-store`, `Vary: Authorization`. No usar `text/html`, `application/json` ni adjuntos vacíos con HTTP 200 simulando un reporte.

**Presentación compartida:** los archivos contienen título claro, tipo, `periodo`, `fecha_corte` con offset, moneda, filtros aplicados representados de forma segura, total de filas, encabezados y todos los totales. Deben mantener claves y significado de las filas JSON, con nombres humanos y unidades; la exportación puede añadir páginas/hoja de metadatos, pero no cambiar filtros ni cifras.

### 5.1 CSV

- UTF-8 con BOM **EF BB BF** para interoperabilidad con Excel en Chile; separador **punto y coma (`;`)**, encabezados de columna fijos, comillas dobles escapadas y finales de línea `\r\n` (CRLF). Documentar el delimitador y el BOM.
- Valores dinámicos no confiables (nombre de cliente/categoría/técnico, códigos externos, etc.) se tratan como **texto**, con normalización segura que impida ejecución de fórmulas al abrir en hojas de cálculo: neutralizar `=`, `+`, `-`, `@`, tabulaciones, CR/LF, caracteres de control y variantes precedidas de espacios o Unicode de ancho cero que evadan la revisión. Las celdas monetarias de origen validado **no** son texto de usuario: preservar signo `-` legítimo de márgenes negativos, sin anteponer marcadores que cambien su valor monetario.
- `folio_externo` se conserva exactamente como caracteres en el CSV. **Advertencia al consumidor:** Excel puede convertir texto numérico automáticamente y quitar ceros si se abre con inferencia; para garantizar ceros y tipo texto en Excel usar XLSX, o importar CSV fijando la columna Folio como texto. No usar fórmulas `="0001"` para preservar ceros.
- Textos no confiables que requieren prefijo de seguridad se exportan como texto neutralizado, no ejecutable; pruebas con varias aplicaciones lectoras, sin prometer protección absoluta frente a importaciones que ignoren convenciones CSV.

### 5.2 XLSX

- Archivo Office Open XML real (ZIP/XML), sin macros, vínculos externos, hojas ocultas maliciosas, fórmulas ejecutables ni `hyperlink` formado desde datos.
- Folios, IDs, fechas y texto identificador preservan su **tipo textual** cuando sea necesario, incluido `"00001234"`. Proteger nombres de hoja y celdas contra caracteres ilegales y caracteres de control.
- Montos: preservar valor decimal exacto. Para importes de hasta 15 dígitos significativos se pueden escribir celdas numéricas con formato de dos decimales **solo cuando las pruebas de roundtrip justifiquen que no se alteró el valor**; por encima de esa precisión, exportar como **texto decimal exacto** y advertirlo en una hoja de metadatos. Nunca convertir montos de 38 dígitos a `float` a ciegas.
- Se incluye hoja principal con filas filtradas y hoja `Resumen` con fechas, zona, filtros, `fecha_corte`, `count` y todos los totales. No usar fórmulas para totalizar valores que se calculan en el backend.
- Recomendar `openpyxl`, versión compatible, rango de versión acotado y licencia/vulnerabilidades verificadas antes de incorporarla en `backend/requirements.txt`. El PR documental no agrega dependencias.

### 5.3 PDF

- Archivo PDF real y legible, con título, periodo, fecha de corte, filtros, totales y tabla paginada, encabezados repetidos, saltos de página, números de página y manejo de textos largos. Diseñar anchos y/o orientación horizontal para que **no se recorten columnas**; los montos grandes y caracteres acentuados deben ser legibles.
- Incluir etiqueta inequívoca **«Reporte de gestión — no es documento tributario ni DTE»**. No emular facturas del SII.
- Recomendar motor PDF mantenido y adecuado para Django (por ejemplo ReportLab) con dependencias y licencias verificadas; evitar cargar recursos remotos, URLs arbitrarias o templates HTML sin sanitizar. Fuentes admitidas deben gestionarse conforme a licencias y sin exponer archivos de sistema.
- Limitar páginas/memoria/tiempo según presupuesto operativo y rechazar 413 controlado cuando el archivo supera 50 MiB, antes de responder HTTP 200.

## 6. Consistencia PostgreSQL y generación segura de binarios

**Principio:** cada respuesta JSON o cada archivo debe usar un **único snapshot coherente** de PostgreSQL. Reutilizar el patrón validado de SPEC-010 (`REPEATABLE READ, READ ONLY` dentro de una transacción exclusiva para consultas); no ampliar aislamiento a la sesión o aplicaciones ajenas, ni iniciar negocio mutador. En un resultado de reporte, `count`, `totales`, `results` y la clasificación de cartera pertenecen al mismo instante. El corte de fecha y el hoy civil se capturan coherentemente al inicio para las fórmulas que dependan de tiempo.

**Advertencia de streaming:** Django puede ejecutar un generador de `StreamingHttpResponse` **después** de finalizar la transacción de la vista. No devolver un queryset perezoso o generador que consulte PostgreSQL fuera del snapshot. Una estrategia aceptable es **generar completamente el archivo a un temporal privado dentro del snapshot** (o en un servicio explícito que mantenga la transacción viva durante el cómputo y render), verificar límites y recién entonces devolver `FileResponse` con ciclo de vida de archivo seguro y limpieza posterior. `FileResponse` debe cerrarse y eliminar el temporal tanto en éxito como al cancelar la conexión; demostrarlo con pruebas. No conservar bytes ni temporales de reportes sin retención formal aprobada.

**La exportación y un JSON solicitado en otra llamada pueden diferir si el dominio cambió entre ambas solicitudes.** No afirmar instantánea compartida entre llamadas ni introducir `snapshot_id` de acceso persistente inexistente. Las pruebas de comparación deben ejecutarse con datos controlados sin mutaciones intermedias, o validar independencia de snapshots.

La petición de reporte **no escribe datos de negocio**, no invoca servicios de mutación, no registra facturas/pagos y no mezcla tipos de importes. `count`, aggregate y materialización por lotes deben evitar N+1 y explosiones por joins. Usar `select_related` y `prefetch_related` por página o lote; `EXPLAIN ANALYZE`, recuentos de queries y memoria temporal medidos en PostgreSQL real. Una consulta larga puede presionar MVCC: definir umbral de tiempo, logging y métricas, no dejar transacciones eternas.

## 7. Trazabilidad de exportaciones y auditoría

**Hallazgo de integración:** `apps.auditoria.adapters.FUENTES` es un registro **cerrado** de eventos de negocio existentes. No tiene fuente `REPORTES_EVENTO` ni un API público para escribir eventos de lectura. No registrar exportaciones fingiendo que son `FINANZAS_EVENTO` o `OBRA_EVENTO`, ni modificar el catálogo de auditoría sin SPEC adicional aprobada.

**Contrato v1 de trazabilidad operativa:** registrar eventos **estructurados de servidor** de solicitud, exportación completada o error, con `actor_id`, `rol`, `tipo`, `formato`, `fecha_corte`, `cantidad_filas`, `resultado`, `duracion_ms` y `correlacion` opaca, más huella de filtros si es necesaria. No registrar tokens, cookies, cuerpo del archivo, nombres legales, RUT, folios, montos individuales ni queries SQL con datos. Distinguir «archivo generado y enviado por HTTP» de «descarga confirmada en navegador»: el servidor no puede probar que el usuario lo guardó.

Estos eventos existen en logs operativos con la política de retención vigente, **no** en la bandeja REST de Auditoría global de SPEC-008. Si FYAG requiere auditoría **persistente e inmutable, consultable por API**, se deberá especificar explícitamente un modelo/fuente propia y la autorización de integración a Auditoría en otro incremento; no presentar logs efímeros como registro persistente garantizado.

No introducir migraciones o nuevas tablas en SPEC-011 v1 solo por los logs. Fallos de generación no deben dejar temporales ni resultados parciales; errores internos registran clase/correlación sin traza sensible.

## 8. Errores y protección operativa

- **200:** datos JSON válidos, exportación real o catálogo filtrado por rol (cero registros permitido).
- **400:** query desconocida, repetida o malformada; fecha inválida o futura; tipo de filtro incompatible; página fuera de rango; exportación sin formato/con formato no permitido; `page` en exportación.
- **401:** identidad ausente, inactiva o JWT expirado/revocado.
- **403:** rol sin permisos sobre catálogo/tipo/listado/exportación.
- **404:** tipo exportable desconocido para actor autenticado habilitado, sin filtrar información de otras rutas.
- **405:** método no admitido para actor autorizado; no permitir escritura.
- **409:** corrupción verificable en costos cerrados o cartera, con `{"code":"cierre_costos_inconsistente","detail":"..."}`, `saldo_inconsistente` o código financiero estable, sin totales engañosos.
- **413:** máximo de 10.000 filas o archivo excede 50 MiB, `code=exportacion_demasiado_grande`, sin transmisión parcial.
- **429:** límite de tasa de exportaciones alcanzado, respuesta DRF con `Retry-After` cuando sea posible; documentar política/caché real.
- **500:** error no anticipado, JSON saneado sin SQL, excepciones privadas, PII, tokens o contenido de archivo. Añadir correlación opaca y logs de mínima exposición.

Errores de permisos se evalúan antes de consultas de datos cuando es posible. No cachear respuestas sensibles en proxies; `Content-Security-Policy` y `X-Content-Type-Options` acordes a descarga. No generar un 200 con archivo roto para encubrir un error de negocio.

## 9. Arquitectura y dependencias de implementación

Implementar únicamente dentro de `backend/apps/reportes/`, más el `include` de `backend/config/urls.py`, documentación y dependencias justificadas:

- `permissions.py`: matriz por rol/tipo, revalidación de identidad persistida.
- `filtros.py`: query estricta, fechas civiles, estados y parámetros según tipo.
- `consultas.py`: querysets base, projecciones en lotes y totales exactos; integra fuentes de Obras/Finanzas/Comercial, sin crear nuevo motor contable.
- `services.py`: orquestación del corte, snapshot transaccional, correlación JSON/export.
- `serializers.py`: filas exactas, totales, catálogo y envelope.
- `exportadores/ (csv.py, xlsx.py, pdf.py)` o estructura semejante: formato y seguridad de archivos, independiente de la lógica de dominio.
- `views.py` y `urls.py`: HTTP, throttling, headers, errores, FileResponse y limpieza.
- `tests/` con PostgreSQL real, binarios verificables, RBAC, concurrencia y límites.
- `backend/docs/SPEC-011-IMPLEMENTACION.md` y `backend/docs/openapi/SPEC-011-v1.json`.

**Dependencias:** la base `backend/requirements.txt` todavía **no incluye** librerías para XLSX ni PDF. OpenCode debe investigar y justificar bibliotecas compatibles (sugeridas: openpyxl y ReportLab), versiones acotadas, licencias, vulnerabilidades conocidas, peso de imagen, reproducibilidad y procedimiento de rollback. Cambiar `requirements` y reconstrucción Docker es una modificación esperada y admitida **en el PR de código**, no en la documentación. No recurrir a LibreOffice headless ni a servicios externos de conversión como dependencia implícita.

No modificar modelos o migraciones de otros dominios. Evitar nuevas migraciones en este incremento salvo necesidad formal detectada y aprobada; no mezclar auditoría general con las exportaciones.

## 10. Matriz de QA y criterios de aceptación

1. Catálogo por rol exacto; 3 reportes para Gerencia y solo Cobranzas para AF; otros roles 403, sin filtros de texto para bypass.
2. Tres listados JSON contractuales, 25 filas, `count` y `totales` de todo el filtro, tipos, nullability, orden estable y coincidencia del total con `count`. Página inválida/no existente 400.
3. Periodo default mes actual, máximo 366 días, fechas civiles Santiago, DST 23/25 h, filtros cliente/estado/fecha_base, duplicados/desconocidos y exportación `page` rechazada.
4. Obras: estados reales, fecha_base correcto, responsable/categoría, sin avance ficticio y presupuesto neto idéntico a Comercial, incluyendo fraccionales con ROUND_HALF_UP por línea.
5. Rentabilidad: solo Obras FINALIZADAS con cierre inmutable, margen positivo/cero/negativo, cortesía SIN_COBRO, cierre ausente 409, rango vacío 200.
6. Cobranzas: documento vigente y folio con ceros, pagos activos, pagos anulados, documento revertido, vencimiento calculado por día Santiago, saldo agregado exacto, integridad 409; proyección de AF sin costos ni tarifas.
7. JSON ↔ exportación: con DB quieta, mismo filtro, `count`, orden, columnas y totales para los tres formatos, incluso 25+ páginas; sin consultar solo la primera página.
8. CSV UTF-8 BOM + `;` + CRLF, acentos y textos con comillas/saltos, neutralización de fórmulas, margen negativo genuino, documentación de folio al importar.
9. XLSX ZIP real que puede abrir un parser; tipos de folio/moneda, importes exactos de 38 dígitos como texto, celdas sin fórmulas, hoja Resumen, sin macros/links externos.
10. PDF real con firma `%PDF-`, legibilidad, paginación, acentos, totales, títulos, número de páginas, sin cortar columnas y sin simular un DTE.
11. 0 registros: JSON con `count=0` y totales `"0.00"`, archivos igualmente válidos con encabezados, sin excepciones por tablas vacías.
12. 10.000 filas exactas → exportación válida si respeta tamaño; 10.001 → 413 y no bytes parciales; archivo >50 MiB → 413 saneado; temporales privados se eliminan en éxito, error y desconexión.
13. Control RBAC 401/403, 404/405, `HEAD/OPTIONS`; flags/claims falsos no elevan permisos; caches privados, `nosniff`, Content-Disposition seguro, ningún JWT en URL.
14. Throttle 429 bajo umbral configurado; explicitar límite en deployment multi-worker. Logs de exportación con mínima metadata; sin falsos eventos económicos ni datos sensibles.
15. Snapshot PostgreSQL `REPEATABLE READ, READ ONLY` real: mientras se registra/anula pago, revierte documento o finaliza obra, cada archivo y listado conserva conteos, filas y totales del mismo instante; sin bloquear escrituras de negocio.
16. Performance: sin N+1, memoria acotada, consultas por lote, perfil SQL con cientos/miles de filas, medición de temporales/páginas PDF y regresión sin alterar Comercial/Obras/Finanzas.
17. `manage.py check`, `makemigrations --check --dry-run`, pruebas `apps.reportes`, regresión completa sobre PostgreSQL real, CI backend y suite Postman funcional/negativa ejecutada por el responsable.
18. Documentación operativa, OpenAPI completo para las cinco rutas (incluida la parametrizada), tres formatos descargables y rollback de dependencias/código; no entregar solo CSV alegando SPEC cerrada.

### Limitaciones explícitas del alcance

Una respuesta representa un snapshot por solicitud, **no** un histórico financiero reconstruido ni garantía de igualdad entre consultas hechas en instantes distintos. Los reportes de rentabilidad no son informes tributarios ni de utilidades contables; las exportaciones no prueban que el usuario guardó el archivo. Un CSV abierto con inferencia automática de Excel puede convertir folios a número; XLSX conserva el dato como texto.

## 11. Fuera de alcance

No desarrollo UI, PDF SII/DTE, facturación electrónica, contabilidad formal, transferencias bancarias, sincronización externa, notificaciones por email, link público de descarga, esquema de BI persistente, snapshots históricos retroactivos, porcentaje de avance, costos presupuestados como costos reales, margenes proyectados, cambios de permisos de otros módulos ni procesos asíncronos ilimitados.

## 12. Flujo de entrega con OpenCode y control Git

1. Este contrato se revisa en PR **solo Markdown** y se fusiona a `main` únicamente con autorización del responsable.
2. Una vez integrado, OpenCode crea `feature/backend-011-reportes` desde `origin/main` actualizado. Debe comprobar `git status`, frontend ajeno y secretos antes de comenzar.
3. OpenCode implementa y prueba localmente con PostgreSQL real. Antes de **cualquier commit/push/PR**, entrega informe técnico de arquitectura, fórmula, seguridad, dependencia, exportación, auditoría operativa, pruebas, performance, riesgos y rollback. **Se detiene a esperar revisión**.
4. Después de la revisión y autorización se generan commits técnicos atómicos y PR de implementación. No hacer merge autónomo.
5. ChatGPT inspecciona el diff real, CI y riesgos de precisión, permisos, archivos y temporales. Prepara suite Postman importable; usuario ejecuta y comunica resultados con `passed/failed/skipped`.
6. Merge de implementación **solo** tras evidencia aprobada y consentimiento explícito; luego actualizar SPEC-011 a integrada mediante nuevo PR documental autorizado.
7. No guardar prompts de OpenCode como archivos del repositorio; entregarlos completos en conversación. Cada SPEC nueva/actualizada en GitHub exige avisar al usuario que actualice copia local.

## 13. Referencias inspeccionadas

- `backend/apps/reportes/` (esqueleto), `backend/config/{settings.py,urls.py}`, `backend/requirements.txt`.
- `backend/apps/obras/models.py`, `backend/apps/obras/urls.py`, `backend/apps/comercial/{models.py,calculos.py}`.
- `backend/apps/finanzas/{models.py,consultas_cobranzas.py,views_pagos.py,views_documentos.py,serializers_documentos.py,validaciones.py}`.
- `backend/apps/dashboard/{consultas.py,consistencia.py}` (SPEC-010 integrada, PR #34).
- `backend/apps/auditoria/{adapters.py,permissions.py}` (SPEC-008: catálogo cerrado de eventos existentes).
- `backend/apps/usuarios/{authentication.py,models.py}`, SPEC-006B/006C.
- `frontend/src/pages/Reportes.jsx` (prototipo, fuera de alcance), `specs/008-011-mapa-backend-pendiente.md`.

**Definición de «backend listo para frontend»:** contrato aprobado, cinco rutas funcionales con tres formatos reales, tests PostgreSQL/CI y Postman satisfactorios, esquema OpenAPI publicado y PR de implementación fusionado en `main`. Esta SPEC escrita **no equivale** a implementación.

## 14. Estado de integración verificado (12-11-2026)

- **Contrato documental:** PR [#36](https://github.com/LFP2002/Proyecto-FYAG/pull/36), fusionado en `main` antes de implementar.
- **Código de implementación:** PR [#37](https://github.com/LFP2002/Proyecto-FYAG/pull/37), fusionado en `main` con commit `b9b9082c988eda083e61b1422b73fe7e063495fc`.
- **SHA final del PR revisado:** `36af35d9fc7c570082e5c5464fb8d195e4405036`; cinco commits y 30 archivos; no se modificaron frontend, modelos ni migraciones.
- **Backend CI:** verificado exitoso (`completed/success`) para dicho SHA antes del merge.
- **Pruebas locales declaradas por OpenCode:** 48 de Reportes y 807 de regresión completa, ambas con cero fallidas.
- **Postman:** el responsable confirmó la finalización de las pruebas y autorizó expresamente el merge, **sin informar cantidades exactas de passed/failed/skipped**. No registrar 0 fallidas en Postman sin esa evidencia específica.
- **API:** rutas `/api/reportes/catalogo/`, `/obras/`, `/rentabilidad/`, `/cobranzas/` y `/{tipo}/exportar/`; esta última produce CSV/XLSX/PDF según el tipo y rol.
- **Dependencias y operación:** revisar `backend/docs/SPEC-011-IMPLEMENTACION.md` y `backend/requirements*.txt`; se actualizaron Docker, Compose y CI de pruebas. Reconstruir backend local tras traer cambios.
- **Riesgos residuales:** throttle por proceso sin caché compartida, `HEAD` sin tamaño final de archivo, API privada de limpieza openpyxl fijada y desconexión proxy productiva no probada. Requieren seguimiento de despliegue.

Las referencias anteriores actualizan el estado del documento; no reescriben los requisitos técnicos que ya fueron aprobados e implementados.
