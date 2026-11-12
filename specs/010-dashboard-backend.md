# SPEC-010 — Dashboard gerencial: indicadores reales y contratos REST

**Estado: DEFINIDA PARA IMPLEMENTACIÓN; NO IMPLEMENTADA EN `main`.** La aplicación `apps.dashboard` existe únicamente como esqueleto, sin rutas en `backend/config/urls.py`. Esta SPEC fija el contrato del backend y no entrega endpoints hasta que OpenCode los implemente, pruebe y se fusione su PR. El frontend lo desarrollarán los compañeros y no forma parte de este incremento.

## 1. Contexto, objetivo y precedencia

Proyecto-FYAG utiliza Django 5, DRF, PostgreSQL y autenticación JWT versionada. Comercial administra Clientes/Presupuestos; Obras administra la ejecución y el cierre inmutable de costos; Finanzas administra documentos externos, pagos recibidos registrados y cobranzas; Auditoría (SPEC-008) y Alertas (SPEC-009) ya están integradas y tienen APIs propias.

**Objetivo:** exponer una fachada REST exclusivamente de lectura que permita a Gerencia visualizar operación actual, rentabilidad económica de Obras efectivamente finalizadas y situación **actual** de cobranza, mediante cifras verificables y sin duplicar la lógica de dominio.

**Precedencia:** conservar SPEC-002A/002B, SPEC-003A/003B, SPEC-004/004B, SPEC-006B/006C, SPEC-007 y sus implementaciones ya integradas. Si existe contradicción entre una fórmula propuesta y la fuente real, detener el cambio contractual para revisión. Los prototipos React, los mocks y los gráficos estáticos no constituyen datos ni evidencia del backend.

## 2. Alcance y matriz de acceso

| Rol persistido | GET/HEAD/OPTIONS `/api/dashboard/*` | Nivel de detalle |
|---|---|---|
| GERENCIA | Permitido | Indicadores de negocio y presupuesto/cierre autorizados |
| ADMINISTRATIVO_FINANZAS | 403 | Sin dashboard gerencial; conserva Finanzas propias |
| SUPERVISOR_OBRAS | 403 | Sin dashboard gerencial; conserva Obras propias |
| TECNICO | 403 | Sin costos, rentabilidad ni información ajena |
| ADMINISTRADOR_TI | 403 | Sin negocio; administra Usuarios exclusivamente |
| Anónimo/sesión revocada | 401 | No revela metadatos financieros |

La autorización ocurre **en Django**, comprobando `Usuario.rol` persistido, `is_active` y `sesion_version` de JWT vigente; jamás confiar en flags `is_staff/is_superuser`, claims manipulados ni visibilidad del menú React. `OPTIONS` tampoco facilita un bypass de permisos. Los métodos de escritura a un rol autorizado deben devolver 405; no hay POST/PUT/PATCH/DELETE de Dashboard.

No exponer listas de pagos, identificadores bancarios, razones de cierre o snapshots de auditoría, detalles de tarifarios ni evidencias de turnos. Las vistas no se utilizan para operar presupuestos, Obra o Finanzas.

## 3. Fuentes de verdad y semántica financiera

| Indicador | Fuente verificada | Regla exacta |
|---|---|---|
| Conteos de Obras actuales | `obras.Obra.estado` | 5 estados PLANIFICADA/EN_PROCESO/SUSPENDIDA/FINALIZADA/CANCELADA |
| Presupuestos pendientes actuales | `comercial.Presupuesto.estado` | Contar PENDIENTE_GERENCIA, sin filtro de periodo |
| Obras finalizadas en el periodo | `Obra.estado`, `finalizado_en` | Contar solo FINALIZADA dentro de fechas civiles elegidas |
| Presupuesto neto de cierre | `Obra.presupuesto.monto_neto` | Suma de subtotales **de cada línea redondeada** usando `comercial.calculos.calcular_subtotal/sumar_monto_neto` |
| Costo real neto de cierre | `obras.CierreCostosObra.costo_total` | Fotografía inmutable asociada a Obra FINALIZADA |
| Margen económico cerrado neto | Presupuesto y costo real anteriores | `margen_real_neto = presupuesto_neto - costo_real_neto` sobre el **mismo conjunto** de Obras finalizadas con cierre |
| Cartera financiera actual | `finanzas.DocumentoCobro` VIGENTE y `finanzas.consultas_cobranzas.con_cobranza` | Bruto documentado, abonos activos, saldo y saldo vencido según consulta oficial |

**Precisión obligatoria:** `Presupuesto.monto_neto` es propiedad calculada a partir de líneas y `PresupuestoItem.subtotal` redondea por línea con `Decimal(ROUND_HALF_UP)`; **no sustituir por `Sum(cantidad * precio_unitario)` sin redondear cada producto exactamente igual**. Una optimización SQL es admisible solo si pruebas demuestran equivalencia exacta para precios/cantidades fraccionales, agregación y casos límite. Mantener resultados monetarios como strings decimales con **dos decimales**; nunca floats, NaN, Infinity ni notación científica. El margen puede ser negativo.

`CierreCostosObra.costo_total` registra costos realmente aceptados al finalizar, no el costo parcial de Obra EN_PROCESO. Si existe una Obra FINALIZADA sin cierre, es una **inconsistencia de origen**: no omitirla silenciosamente, no fabricarle costo cero y no devolver un margen artificial. Responder `409 {"code":"cierre_costos_inconsistente","detail":"..."}` para los endpoints que calculan rentabilidad y registrar diagnóstico interno sin exponer datos sensibles. Otras inconsistencias financieras verificadas por la fuente conservarán un error seguro con código estable.

Documentos y pagos son **brutos**: una factura externa vigente se cuenta una vez, y sus pagos activos son abonos, no documentos adicionales. No sumar el abonado al documento; no incluir pagos anulados ni documentos revertidos en la cartera actual. Reutilizar `con_cobranza` y las mismas fórmulas, límites de Decimal y validaciones de `CobranzasResumenView`. `saldo_vencido` corresponde a `estado_cobranza_calculado=VENCIDA` (saldo positivo y fecha vencida), en zona civil Santiago.

**Cortesía SIN_COBRO:** no reduce a cero `CierreCostosObra.costo_total`. El margen económico presupuesto menos costo se conserva para comparación de Obras, pero **NO representa ingreso devengado, cobrado, utilidad contable o ganancia tributaria**. Ninguna cifra sustituye la emisión de DTE por SII ni afirma que FYAG efectuó transferencias bancarias.

## 4. Contratos REST públicos — v1

| Método | Ruta | Semántica |
|---|---|---|
| GET | `/api/dashboard/resumen/` | KPIs actuales y rentabilidad de obras finalizadas en periodo |
| GET | `/api/dashboard/serie-obras/` | Serie mensual de Obras FINALIZADAS |
| GET | `/api/dashboard/obras-activas/` | Obras EN_PROCESO paginadas y con proyección autorizada |

Todas las rutas requieren slash final y `Authorization: Bearer <JWT>`. Solo GET/HEAD/OPTIONS autorizados, sin sesiones por cookie nuevas. `Cache-Control: private, no-store`, `Vary: Authorization` cuando corresponda; no publicar respuestas en cachés compartidas.

Las fechas/timestamps se expresan en `America/Santiago`; timestamps ISO8601 con offset correcto para la fecha, sin forzar permanentemente `-03:00` por el horario de verano. La moneda es `CLP`.

### 4.1 GET /api/dashboard/resumen/

Parámetros opcionales estrictos: `desde` y `hasta`, ambos `YYYY-MM-DD` y **ambos presentes o ambos ausentes**; `desde <= hasta`, máximo **366 días civiles inclusivos**. No aceptar duplicados, vacíos, fechas imposibles ni parámetros desconocidos (400). Se admiten fechas pasadas; el periodo no reconstruye el histórico de estados/cobranza.

**Periodo por defecto:** desde el día 1 del mes situado cinco meses antes del mes actual de Santiago, hasta **hoy Santiago**, ambos incluidos. Así representa seis meses calendario con el actual parcial. Ejemplo **solo ilustrativo**: si hoy Santiago es 12-11-2026, periodo por defecto 2026-06-01 a 2026-11-12. Aceptar hasta futuro solo si se acuerda explícitamente como cambio contractual; v1 rechaza `hasta > hoy_santiago()` con 400.

**Respuesta JSON estable (valores sintéticos, no información real):**

~~~json
{
  "generado_en": "2026-11-12T17:10:00-03:00",
  "zona_horaria": "America/Santiago",
  "moneda": "CLP",
  "periodo": {"desde": "2026-06-01", "hasta": "2026-11-12"},
  "operacion": {
    "obras_por_estado_actual": {
      "PLANIFICADA": 0, "EN_PROCESO": 0, "SUSPENDIDA": 0,
      "FINALIZADA": 0, "CANCELADA": 0
    },
    "presupuestos_pendientes_gerencia_actual": 0,
    "obras_finalizadas_periodo": 0
  },
  "rentabilidad_cerrada_periodo": {
    "obras_con_cierre": 0,
    "presupuesto_neto": "0.00",
    "costo_real_neto": "0.00",
    "margen_real_neto": "0.00"
  },
  "cobranza_actual": {
    "documentos_vigentes": 0,
    "monto_documentado_bruto": "0.00",
    "abonado": "0.00",
    "saldo": "0.00",
    "saldo_vencido": "0.00"
  }
}
~~~

**Semántica temporal de cada bloque:**
- `operacion.obras_por_estado_actual` y `presupuestos_pendientes_gerencia_actual`: **fotografía actual** de todas las entidades, **no** filtradas por periodo; incluir siempre las cinco claves y ceros.
- `operacion.obras_finalizadas_periodo`: Obras cuyo **estado actual** es FINALIZADA y `finalizado_en` cae dentro del periodo civil inclusivo.
- `rentabilidad_cerrada_periodo`: mismas Obras finalizadas en periodo, con cierre real obligatorio. `obras_con_cierre` coincide con `obras_finalizadas_periodo` cuando las fuentes son íntegras. La suma de presupuesto, la suma del cierre y el margen deben corresponder al mismo conjunto sin duplicaciones por joins.
- `cobranza_actual`: todos los documentos **actualmente VIGENTE** y pagos activos a la fecha de la consulta, sin filtro histórico por `periodo`. `monto_documentado_bruto = abonado + saldo` con igualdad exacta de `Decimal`, sujeta a integridad de los registros.

No sumar netos de Obras con brutos de Documentos ni convertir una métrica «actual» en gráfica histórica. Si `operacion.obras_finalizadas_periodo` y `rentabilidad_cerrada_periodo.obras_con_cierre` divergen, tratarlo como error de origen, no maquillar cifras.

### 4.2 GET /api/dashboard/serie-obras/

Query: solo `meses`, entero decimal sin signos, 1–12, por defecto 6; desconocidos o repetidos, cero, negativos, ceros a la izquierda ambiguos, decimales y valores vacíos → 400. Los meses son civiles de `America/Santiago`, terminando en el mes actual. Medir `finalizado_en` y `estado=FINALIZADA`. Cada Obra suma una sola vez en el mes de su finalización.

JSON de ejemplo (mostrar tantas entradas como `meses`; este ejemplo utiliza `meses=3`):

~~~json
{
  "metrica": "OBRAS_FINALIZADAS",
  "zona_horaria": "America/Santiago",
  "puntos": [
    {"mes": "2026-09", "cantidad": 0},
    {"mes": "2026-10", "cantidad": 0},
    {"mes": "2026-11", "cantidad": 0}
  ]
}
~~~

Entregar **exactamente `meses` puntos**, orden cronológico ascendente, `mes` string `YYYY-MM`, `cantidad` integer no negativo, incluir meses sin registros en cero. El mes actual es parcial; no incluir finalizaciones futuras. No usar `Obra.creado_en`, `iniciado_en`, fecha de presupuesto ni etiqueta «obras ejecutadas» para describir una métrica que realmente significa «obras finalizadas».

### 4.3 GET /api/dashboard/obras-activas/

Query: solo `page`, entero positivo decimal sin signos ni duplicados; por defecto 1. `page` inválida o fuera de rango → **400** con campo `page`, no 404 de paginador estándar. Tamaño de página fijo: **25**. Solo Obras con `estado=EN_PROCESO`; una Obra SUSPENDIDA se muestra en los conteos de estado, pero no en este listado. Orden `creado_en DESC, id DESC`; evitar N+1 y no descargar todas las Obras para paginar.

Contrato DRF `{count,next,previous,results}` (next/previous: string URL paginada o null, no URL a otro origen):

~~~json
{
  "count": 1,
  "next": null,
  "previous": null,
  "results": [
    {
      "id": 37,
      "codigo": "OB-000037",
      "cliente": 18,
      "cliente_nombre": "Cliente ejemplo",
      "categoria_nombre": "Mantención",
      "estado": "EN_PROCESO",
      "tecnico_responsable": 9,
      "tecnico_nombre": "Profesional de ejemplo",
      "fecha_programada": "2026-11-18",
      "presupuesto_neto": "1250000.00"
    }
  ]
}
~~~

Tipos: `id`, `cliente` enteros; `tecnico_responsable` entero o null (por compatibilidad del serializer, aunque el estado real exige responsable); `codigo`, `cliente_nombre`, `categoria_nombre`, `estado`, `presupuesto_neto` strings; `tecnico_nombre` string o null; `fecha_programada` fecha ISO string o null. Los nombres/IDs de usuario son atributos operativos permitidos exclusivamente a Gerencia; no incluir email, RUT, descripciones libres, tarifas, costos parciales, porcentajes de avance ni `margen_proyectado`. `codigo` usa la propiedad real de Obra, `OB-` + PK con seis dígitos mínimos. Presupuesto neto se calcula con sus ítems aplicando el redondeo real.

### 4.4 Contrato general de errores

- `200` lectura válida, aun con cero registros. No devolver `null` donde se pactó cero numérico o `"0.00"`.
- `400` filtros y tipos inválidos, duplicados, fechas invertidas/futuras, meses inválidos, página inválida/fuera de rango.
- `401` identidad no autenticada, inactiva o JWT expirado/revocado.
- `403` cualquier rol distinto a Gerencia.
- `405` métodos de escritura no soportados para Gerencia.
- `409` integridad de cierre o cartera detectada como inconsistente, con `code` estable, sin entregar sumatorias engañosas.
- `500` error interno controlado, sin SQL/traceback ni identificadores sensibles en la respuesta. Correlación de error solo a través de IDs opacos y logs saneados.

El contrato actual no incorpora un endpoint para exportaciones ni series financieras históricas; estos pertenecen a SPEC-011.

## 5. Consistencia, concurrencia y rendimiento

- Cada respuesta de `resumen/` debe evaluar sus múltiples agregaciones sobre una **fotografía SQL coherente dentro de la misma solicitud**, para evitar combinar conteos/costos/documentos observados antes y después de una transacción financiera. Usar transacción read-only con snapshot PostgreSQL estable (`REPEATABLE READ` según diseño validado) y registrar `generado_en`. No bloquear las entidades de Finanzas ni introducir locks que interfieran con pagos. La consistencia se promete **solo por respuesta**, no entre requests separados del Dashboard.
- Un filtro temporal usa el instante civil de inicio de `desde` incluido y de inicio del día siguiente a `hasta` excluido, con `ZoneInfo("America/Santiago")`. No avanzar días mediante `86400` segundos ni fijar offsets constantes (DST).
- Reutilizar las fórmulas de `comercial.calculos` y de `finanzas.consultas_cobranzas`; cualquier consulta optimizada debe contrastarse con datos del endpoint de origen y casos de ROUND_HALF_UP por línea. En listas paginadas prefetchear líneas de presupuestos de las Obras visibles **después de paginar**, sin reconstruir montos en React ni hacer N+1.
- Sumas monetarias de múltiples Obras deben calcularse con `Decimal` y precisión suficiente, en PostgreSQL numeric o en lotes acotados según profiling. No insertar todas las filas históricas en memoria ni crear caches persistentes de datos gerenciales sin diseño aprobado.
- Evitar duplicaciones de entidades por joins de ítems, turnos y pagos; documentar `Distinct`, subconsultas o agregaciones aisladas cuando correspondan.
- En `serie-obras/` agrupar a nivel SQL usando mes en la zona Santiago y rellenar huecos; no hacer recuentos por cada Obra en Python. En `obras-activas/` las relaciones autorizadas deben usar `select_related` + `prefetch_related` apropiados.
- Establecer presupuestos de consulta razonables con pruebas de conteo de queries, `EXPLAIN` en PostgreSQL real y dataset con varias páginas. Agregar índices solo si la medición justifica nuevas migraciones, sin editar migraciones históricas de otro dominio.
- Preservar reglas y lock ordering existentes; el módulo Dashboard **no muta** Obras, pagos ni presupuestos y no ejecuta reconciliación de alertas.
- No crear dependencia sincrónica del servicio de Dashboard en `apps.alertas` o `apps.auditoria`: el frontend consumirá esas APIs por separado.

## 6. Arquitectura de implementación recomendada

- `apps.dashboard/views.py`: autenticación, filtros, permisos, headers de caché, respuestas HTTP.
- `apps.dashboard/permissions.py`: política explícita de rol Gerencia, verificada desde Usuario persistido y sesión versionada.
- `apps.dashboard/serializers.py`: validación de query estricta y proyecciones JSON, sin permitir payloads de escritura.
- `apps.dashboard/services.py` o consultas desacopladas: selección de datos/aggregates; adaptadores hacia Comercial, Obras y Finanzas con mínima dependencia.
- `apps.dashboard/urls.py`, registradas en `backend/config/urls.py` **solo en PR de implementación**.
- `apps.dashboard/tests/`: pruebas PostgreSQL reales de cálculo, permisos, filtros, concurrencia y regresión.
- `backend/docs/SPEC-010-IMPLEMENTACION.md` y `backend/docs/openapi/SPEC-010-v1.json`: documentación y contrato versionados tras implementar.

No crear nuevas tablas, cronjobs, migraciones, réplicas MongoDB o eventos de negocio para una fachada de solo lectura, salvo justificación por rendimiento aprobada de forma expresa. No tocar el frontend.

## 7. Pruebas y criterios de aceptación

1. Las tres rutas responden exactamente el JSON tipado especificado; no hay campos de prototipo ficticio, endpoints ambiguos ni datos de ejemplo hardcodeados.
2. Rol Gerencia activo autorizado; AF, Supervisor, Técnico y Administrador TI 403, aun con flags `is_superuser`; usuario anónimo/inactivo/revocado 401; HEAD/OPTIONS y métodos escritos con status contractual.
3. Filtros y paginación: parámetros desconocidos/repetidos/vacíos → 400; fechas inválidas o invertidas y rangos superiores a 366 días → 400; fecha futura rechazada; `meses` 1 y 12, `page` fuera de rango → 400.
4. `obras_por_estado_actual` siempre tiene las cinco claves; una Obra en SUSPENDIDA cuenta en ese estado, no como EN_PROCESO; una Obra CANCELADA no figura en serie de finalizadas.
5. Periodo por defecto exactamente seis meses calendarios terminando hoy Santiago; una Obra finalizada a medianoche en los límites civiles se asigna al día/mes correcto incluso en cambios de DST.
6. Presupuesto neto con subtotales que requieran ROUND_HALF_UP por línea coincide exactamente con `Presupuesto.monto_neto` y serializers de Comercial para todos los casos, no solo precios enteros.
7. `CierreCostosObra.costo_total` se utiliza exclusivamente para rentabilidad de Obras finalizadas; costo positivo real, margen positivo/cero/negativo, cortesía SIN_COBRO conserva costo no cero; finalizar sin cierre provoca 409 y no una respuesta con cero ficticio.
8. Documento vigente, pagos parciales, pago total, anulación de pago, documento revertido y vencido: Dashboard coincide con `/api/finanzas/cobranzas/resumen/`, sin sumar abonado como documento extra, sin contar pagos anulados.
9. Ningún dato de evidencia privada, tarifas de Técnico, RUT, emails, tokens, registros de Auditoría o montos de pago individual se expone indebidamente.
10. Serie de 1–12 meses con huecos en cero, finalizado_en correcto y orden ascendente. Listado de 25 con varias páginas y orden de desempate sin N+1.
11. Pruebas de consulta concurrente mientras se registra/revierte documento, registra/anula pago o finaliza Obra: respuesta con snapshot internamente coherente sin bloquear operaciones de negocio.
12. No escrituras en GET/HEAD/OPTIONS; compatibilidad de modelos originales, migraciones sin cambios o justificadas, CI backend verde, suite Postman positiva/negativa validada por el responsable.

Antes de entregar, OpenCode debe ejecutar `manage.py check`, `makemigrations --check --dry-run`, pruebas específicas `apps.dashboard`, regresión completa y pasos de verificación en Compose, registrando resultados **reales**. Los tests deberán usar PostgreSQL real para precisión/consistencia y no depender de SQLite ni de mocks que simulen persistencia.

## 8. Fuera de alcance

No UI React, exportaciones CSV/XLSX/PDF (SPEC-011), reportes históricos de cartera, emisión DTE, procesamiento bancario, porcentajes de avance, margen proyectado, algoritmo financiero paralelo, snapshots de Auditoría, bandeja de Alertas, nuevas migraciones económicas, optimización sin medición, escritura de datos o cambios de permisos de otros módulos.

No presentar el Dashboard como indicador de utilidad contable ni construir un ratio de costos parciales frente al presupuesto neto para obras no finalizadas.

## 9. Entrega y flujo Git obligatorio

1. **SPEC formal:** revisar y aprobar esta especificación documental, y fusionarla a `main` únicamente con autorización explícita del responsable.
2. **OpenCode implementa:** iniciar desde `origin/main` ya actualizado en `feature/backend-010-dashboard`; el desarrollo es exclusivamente suyo, no de ChatGPT ni del equipo frontend.
3. **Informe previo a commits:** al terminar programación y pruebas, OpenCode entrega un informe técnico completo (arquitectura, archivos, contratos, fórmulas, seguridad, snapshot, pruebas reales, riesgos, migraciones, operación y rollback) y **se detiene** sin commit/push/PR para revisión.
4. Tras aceptación del informe, OpenCode crea commits atómicos con descripción técnica acorde a cada cambio, push y PR detallado contra `main`.
5. ChatGPT inspecciona el diff real en GitHub, permisos, precisión económica, CI y migraciones. Prepara una suite Postman importable; el responsable la ejecuta y comunica passed/failed.
6. Resolver incidencias y repetir pruebas; **merge únicamente con nueva autorización explícita**. Después, registrar el estado integrado de SPEC-010 y avisar al responsable que debe actualizar su PC.
7. No guardar prompts de OpenCode como archivos en el repositorio: ChatGPT los entrega completos y detallados en el chat.

## 10. Archivos y referencias comprobadas

- `backend/apps/dashboard/` (esqueleto actual), `backend/config/urls.py`, `backend/config/settings.py`.
- `backend/apps/obras/{models.py,serializers.py}`, `backend/apps/comercial/{models.py,calculos.py}`.
- `backend/apps/finanzas/{models.py,consultas_cobranzas.py,views_pagos.py,validaciones.py}`.
- `backend/apps/usuarios/{models.py,authentication.py}`, SPEC-006B/006C.
- `backend/apps/alertas/` (SPEC-009 integrada), `backend/apps/auditoria/` (SPEC-008 integrada).
- `frontend/src/pages/Dashboard.jsx` (prototipo sin contrato productivo), `specs/005a-frontend-autenticacion.md`, `specs/005b-frontend-comercial.md`, `specs/005c-frontend-obras.md`.
- `.github/workflows/backend-ci.yml`.

**Definición de «lista para frontend»:** tres endpoints implementados y fusionados en `main`, respuestas conforme a esta SPEC, roles y cálculos verificados, pruebas PostgreSQL/CI y Postman aprobadas, contrato OpenAPI publicado. El documento por sí solo **no** habilita la API.
