# SPEC-010 — Dashboard gerencial: informe técnico y publicación para revisión

## 1. Estado, preparación y alcance

Implementación local en `feature/backend-010-dashboard`, desde **origin/main=73852fa**, que integra el PR documental #33. Al comenzar, el árbol estaba limpio, se ejecutó git fetch origin, se comprobó por API que #33 estaba fusionado y se leyó íntegramente la SPEC actualizada. Se revisaron además contratos y código de Comercial, Obras/Costos, Finanzas, Usuarios, Auditoría y Alertas, así como Docker Compose y Backend CI.

El informe inicial se entregó **sin commits, push ni PR**. Tras su revisión preliminar satisfactoria, el responsable autorizó commits y publicación para auditoría independiente. No equivale a integración en main, aprobación de CI remoto ni Postman; **el merge sigue expresamente no autorizado**. La verificación previa a publicación se documenta en la sección 10.

Se implementan exactamente:

- GET `/api/dashboard/resumen/`.
- GET `/api/dashboard/serie-obras/`.
- GET `/api/dashboard/obras-activas/`.

Fachada PostgreSQL de lectura exclusiva para Gerencia, sin nuevas tablas, migraciones, dependencias o procesos. No hay frontend, escritura de negocio, rentabilidad proyectada, porcentajes de avance, exportaciones ni llamadas a servicios de Auditoría o Alertas. Los endpoints consultan persistencia real; ejemplos y fixtures sintéticos se limitan a documentación y BD temporal de pruebas.

## 2. Arquitectura e inventario de archivos

| Archivo | Estado | Responsabilidad |
|---|---|---|
| backend/apps/dashboard/permissions.py | Modificado (esqueleto) | Rol persistido Gerencia, actividad y versión de sesión |
| backend/apps/dashboard/filtros.py | Nuevo | Query estricta, fechas civiles, meses y página |
| backend/apps/dashboard/consistencia.py | Nuevo | Transacción de lectura y snapshot PostgreSQL por respuesta |
| backend/apps/dashboard/consultas.py | Nuevo | Agregados, cálculo oficial por lotes y query de obras visibles |
| backend/apps/dashboard/services.py | Modificado (esqueleto) | Coordinación de resumen/serie y revalidación dentro del snapshot |
| backend/apps/dashboard/serializers.py | Modificado (esqueleto) | JSON público explícito y proyección reducida de serializer de Obras |
| backend/apps/dashboard/views.py | Modificado (esqueleto) | HTTP, paginación fija, headers y errores seguros |
| backend/apps/dashboard/urls.py | Modificado (esqueleto) | Tres rutas GET/HEAD/OPTIONS |
| backend/apps/dashboard/tests/base.py | Nuevo | Fixtures y operaciones reales reutilizadas de Finanzas |
| backend/apps/dashboard/tests/test_api.py | Nuevo | Contratos, cálculos, seguridad, límites y profiling PostgreSQL |
| backend/apps/dashboard/tests/test_concurrencia.py | Nuevo | Cinco intercalaciones de commits con conexiones independientes |
| backend/config/urls.py | Modificado | Único cambio de código fuera del Dashboard: registrar `/api/dashboard/` |
| backend/docs/openapi/SPEC-010-v1.json | Nuevo | Contrato OpenAPI 3.1.0, versión 1.0.0 |
| backend/docs/SPEC-010-IMPLEMENTACION.md | Nuevo | Este informe técnico y operativo |

No se cambian modelos, migraciones históricas, servicios, permisos o serializers de los dominios propietarios, configuración JWT/CSRF/CORS, frontend, Compose, workflows ni requirements. Los esqueletos models/admin/apps del Dashboard permanecen intactos.

## 3. Fuentes y fórmulas económicas

### 3.1 Operación actual

`Obra.objects.values(estado).annotate(Count(pk))`, sin filtros históricos, y ceros explícitos para PLANIFICADA, EN_PROCESO, SUSPENDIDA, FINALIZADA y CANCELADA. Presupuestos pendientes: `Presupuesto.estado=PENDIENTE_GERENCIA`, también sin filtro de periodo.

Las Obras finalizadas del periodo se seleccionan por estado actual FINALIZADA y finalizado_en dentro de las fronteras civiles solicitadas, sin incluir timestamps futuros respecto del corte de respuesta. La cantidad se obtiene al recorrer ese mismo conjunto económico: no hay una consulta alternativa con joins que pudiera duplicarlas o divergir de los cierres.

### 3.2 Presupuesto neto y redondeo

Se importan y utilizan directamente:

```text
comercial.calculos.calcular_subtotal(cantidad, precio_unitario)
comercial.calculos.sumar_monto_neto(subtotales)
```

Cada línea se calcula con Decimal, escalas oficiales y ROUND_HALF_UP al centavo; después se suman las líneas ya redondeadas. No se usa Sum(cantidad*precio_unitario), float, IVA supuesto o redondeo final como sustituto del redondeo por línea.

Ejemplo de prueba: dos líneas `0.500 × 0.01` dan `0.01 + 0.01 = 0.02`, no `0.01`. Se contrasta la proyección del Dashboard con `Presupuesto.monto_neto` y el endpoint real de Presupuestos, incluidos cantidades/precios máximos y fraccionales.

### 3.3 Costo y margen cerrados

Solo las mismas Obras FINALIZADAS del periodo contribuyen a presupuesto/costo/margen. El costo se lee de `CierreCostosObra.costo_total`, no de gastos/turnos actuales, controles parciales ni precios comerciales.

```text
presupuesto_neto = suma de líneas oficiales de esos presupuestos
costo_real_neto = suma de cierres reales de esas Obras
margen_real_neto = presupuesto_neto - costo_real_neto
```

La relación de Obra con Presupuesto y Cierre es OneToOne. Se consultan cierres y líneas por separado para evitar productos cartesianos. Las filas de Obra/cierre se recorren con iterator en lotes de hasta **500**; las líneas de los presupuestos del lote se iteran con chunk_size=500. No se materializa todo el histórico. Hay una consulta de líneas por lote, no una por Obra.

Los cálculos oficiales mantienen su precisión de 50 dígitos; el acumulador externo usa contexto Decimal **80**, suficiente para sumar cierres de 38 dígitos incluso con cardinalidad BigInt. Se prueba suma de cierres mayor a 38 dígitos y margen negativo exacto. No se impone a la rentabilidad neta el límite agregado de cartera financiera, pues son métricas distintas.

Obra FINALIZADA sin cierre en el conjunto solicitado → **409 cierre_costos_inconsistente**. No se omite ni se le inventa costo cero. El diagnóstico guarda solo código y correlación opaca, no entidades, importes o snapshots. Serie y listado no calculan rentabilidad y no fallan por un cierre ausente ajeno a su función. Un cierre faltante fuera del periodo elegido no invalida periodos íntegros.

Cortesías SIN_COBRO mantienen el costo real. El margen económico no es ingreso devengado, ingreso cobrado, utilidad contable, tributaria ni una orden de emitir/cancelar documentos.

### 3.4 Cartera actual bruta

Consulta `con_cobranza(DocumentoCobro.objects.filter(estado="VIGENTE"))`, reutilizando la subconsulta oficial de pagos activos. Las expresiones de estado/saldo no se reimplementan en Dashboard. Se construye al principio del resumen, antes del procesamiento histórico de líneas, fijando en esa expresión el día civil oficial de Finanzas al construirla.

Agregados SQL aislados: count de documentos, sum de monto_total, abonado_calculado, saldo_calculado y saldo de los clasificados VENCIDA. Un documento se cuenta una vez aunque tenga varios pagos; pagos anulados y documentos revertidos quedan excluidos. El periodo de rentabilidad **no filtra** esta cartera actual.

Se aplican los límites y finitud de `CobranzasResumenView` y se verifica exactamente `monto_documentado_bruto = abonado + saldo`. También se detecta por documento abonado negativo, abonado mayor al total o saldo negativo, para no ocultar corrupción con una sumatoria global positiva. Fallo: **409 saldo_inconsistente**. Agregado financiero fuera del límite oficial: **409 importe_fuera_rango**, sin overflow disfrazado de cero.

Importes JSON siempre strings decimales de dos posiciones, sin notación científica. Solo margen puede ser negativo. Nunca se suman montos netos de presupuesto/costo con brutos de documentos/pagos.

## 4. Snapshot, autorización y concurrencia

Cada lectura con métricas abre una transacción propia en la conexión por defecto:

1. Comprobar que no exista atomic exterior.
2. Abrir transaction.atomic.
3. Antes de cualquier SELECT dentro de ella, ejecutar `SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY`.
4. Ejecutar `SELECT pg_current_snapshot()` para fijar la fotografía SQL.
5. Tomar generado_en y releer el principal dentro de esa fotografía.
6. Ejecutar agregados, lotes, relaciones y serializers que requieran datos antes de salir. Resumen/serie devuelven estructuras ya materializadas, no querysets lazy.
7. Confirmar o revertir la transacción; los atributos de aislamiento/read-only no se conservan en la siguiente transacción.

La autenticación JWT y el primer permiso ocurren antes del snapshot; la revalidación interna impide construir métricas con un principal cambiado antes del inicio de la fotografía. Si un cambio se confirma después de establecerla, rige la identidad visible al inicio de esa lectura; la siguiente solicitud vuelve a autenticar y comprobar versión.

No hay SELECT FOR UPDATE ni advisory locks en Dashboard, ni modificaciones al aislamiento global de Django o PostgreSQL. Los SELECT toman los locks de tabla normales de lectura, compatibles con escrituras de filas. Las escrituras originales conservan su orden de locks y sus callbacks. Las características de la transacción no son escrituras de negocio.

**Prerrequisito operativo:** mantener ATOMIC_REQUESTS desactivado para esta conexión, como en la configuración actual, y no envolver estos servicios en otro atomic. No se degrada silenciosamente a READ COMMITTED ni se cambia una transacción exterior con queries previas. Una invocación incompatible se controla como 500 genérico; si en el futuro se habilita ATOMIC_REQUESTS, deberá excluirse esta fachada y revisarse su frontera transaccional.

Cinco pruebas con APIClient, conexiones PostgreSQL independientes y barreras detienen el resumen entre bloques. Mientras está detenido confirman: registro de documento, reversión de documento, pago, anulación de pago y finalización operativa real con cierre. El lector conserva el estado anterior en todos sus agregados; una nueva solicitud observa el nuevo. La escritura termina antes de liberar al lector, demostrando que no depende de que este termine. No se utilizan sleeps para simular una carrera.

Se promete coherencia SQL **por respuesta**, no entre peticiones ni páginas. generado_en es la marca de observación tomada inmediatamente después de establecer el snapshot, no un token reutilizable ni una reconstrucción histórica al microsegundo. Los filtros civiles usan ese inicio de respuesta; la clasificación de cobranza conserva el reloj oficial de Finanzas al construir su expresión al inicio. Se requiere sincronización de reloj de los servidores. No se abre una transacción persistente en el navegador.

## 5. Contrato HTTP, filtros y privacidad

### Resumen

Solo desde/hasta juntos o ausentes, formato estricto YYYY-MM-DD, desde<=hasta, máximo 366 días inclusivos y hasta no posterior a hoy Santiago. Default: primer día del mes situado cinco meses antes del actual, hasta hoy local, ambos incluidos. Ejemplo de calendario: 12-11-2026 → 01-06-2026 a 12-11-2026.

Schema exacto:

- generado_en, zona_horaria=America/Santiago, moneda=CLP y periodo.{desde,hasta}.
- operacion.{obras_por_estado_actual,presupuestos_pendientes_gerencia_actual,obras_finalizadas_periodo}.
- rentabilidad_cerrada_periodo.{obras_con_cierre,presupuesto_neto,costo_real_neto,margen_real_neto}.
- cobranza_actual.{documentos_vigentes,monto_documentado_bruto,abonado,saldo,saldo_vencido}.

### Serie mensual

Solo meses, entero sin signos/fracciones/ceros iniciales, 1–12, default6. Agrupación SQL `TruncMonth(finalizado_en,tzinfo=America/Santiago)` sobre FINALIZADA, nunca creado_en/iniciado_en. Se excluyen finalizaciones futuras. Se rellenan huecos en Python sobre el pequeño catálogo de meses solicitado, no recorriendo Obras individuales.

Respuesta exacta: metrica=OBRAS_FINALIZADAS, zona_horaria y puntos con exactamente meses objetos {mes:YYYY-MM,cantidad:entero}, en orden ascendente. El último mes es parcial.

### Obras activas

Solo page, decimal positivo sin signos ni ceros iniciales, hasta BigInt firmado. Página inválida o fuera de rango → 400 con campo page (no 404 de DRF). Tamaño fijo25, orden creado_en DESC/id DESC; solo EN_PROCESO. Sin limit/page_size u otros filtros.

Contrato DRF count/next/previous/results. Se reutiliza ObraLecturaSerializer restringiendo explícitamente sus campos a id, codigo, cliente, cliente_nombre, categoria_nombre, estado, tecnico_responsable, tecnico_nombre, fecha_programada y presupuesto_neto. Código y nombre laboral usan la implementación real de Obras. Se permiten null en técnico/nombre/fecha conforme al contrato, aunque el estado EN_PROCESO exige responsable en datos válidos.

Las relaciones autorizadas usan select_related con columnas mínimas; las líneas de los presupuestos se prefetchean únicamente al evaluar la página, no antes de paginar. Se reutiliza Presupuesto.monto_neto con ese cache de ítems; no dispara consultas por cada fila. No se exponen descripción libre, email/RUT, evidencias, tarifas, costos parciales ni margen proyectado. Next/previous son URLs del mismo endpoint/origen de la petición validada por Django; no se aceptan redirects del cliente.

### Reglas comunes

- JWT versionado existente; autorización exclusiva del rol persistido GERENCIA activo y con sesion_version vigente. AF/S/T/TI →403, también HEAD/OPTIONS; sin token, expirado/revocado/inactivo →401. Flags, grupos y claims no elevan permisos.
- GET/HEAD/OPTIONS solamente. Mutaciones de un actor autorizado →405; Dashboard no llama a servicios de escritura ni reconcilia Alertas.
- Query desconocida, repetida, vacía, fechas inválidas o incoherentes →400. Las respuestas vacías usan ceros y 0.00 donde corresponde, no null.
- Fronteras civiles: inicio de desde incluido, inicio civil del día siguiente a hasta excluido; no sumar86400 segundos. Round-trip de zona resuelve medianoche inexistente; se prueban días de23/25horas y límites de mes con UTC distinto al día local.
- Cache-Control: private, no-store y Vary: Authorization. JWT, CSRF, CORS y cookies preexistentes sin alteraciones.
- 409 código estable/detail para integridad de cierre/cartera; 500 mensaje genérico con correlacion UUID y X-Correlation-ID. Los logs propios guardan correlación/clase o código, jamás SQL, mensaje de excepción, Authorization, cookies o datos de negocio.

## 6. Pruebas y resultados reales

Todos los tests HTTP/snapshot utilizan TransactionTestCase sobre PostgreSQL real: un TestCase envuelto en atomic no serviría para demostrar el aislamiento configurado antes de cualquier consulta. Las fixtures operativas reutilizan los servicios reales de 007 y de cierre; los datos históricos adicionales son explícitos y exclusivos de la BD temporal. No se insertaron ejemplos en desarrollo/productivo.

| Comando/verificación | Resultado |
|---|---|
| docker compose exec -T backend python manage.py check | Sin problemas (0 silenced) |
| makemigrations --check --dry-run | No changes detected |
| migrate --plan | No planned migration operations |
| test apps.dashboard --noinput | **38 aprobadas, 0 fallidas, 17.884 s** |
| test --noinput | **759 aprobadas, 0 fallidas, 156.561 s** |
| docker compose up -d --build | Construcción correcta, migraciones existentes y servicios iniciados |
| git diff --check | Sin errores; advertencias LF/CRLF de Git en Windows |

Smoke HTTP real contra el servidor levantado por Compose, sin JWT: las tres rutas responden401 con Cache-Control private/no-store y Vary Authorization. No se crearon usuarios o datos demostrativos en la base de desarrollo para esta comprobación. El proceso de migraciones de Compose terminó correctamente con No migrations to apply. La revisión final detectó exactamente14 archivos de Dashboard/documentación e integración, sin archivos ajenos ni coincidencias en el escaneo de patrones sensibles.

La creación de la base de pruebas aplica las migraciones existentes desde cero. No hay nueva migración de Dashboard ni alteración de datos existentes para su instalación.

Cobertura: schemas/tipos y ceros, cinco roles y flags/claims, sesiones, métodos y cache, filtros, seis meses default, año/mes local vs UTC, 366 días, DST, cinco estados, pendiente actual no histórico, serie con huecos/canceladas/futuro, HALF_UP por línea, comparación con endpoint de presupuesto, márgenes positivo/cero/negativo, cortesía con costo, cierre faltante dentro/fuera del periodo, fuentes financieras actuales y coincidencia con resumen oficial, parciales/totales/anulados/revertidos, vencidos, importes grandes, sobrepago inconsistente, overflow financiero agregado, páginas/empates/prefetch, lectura sin writes, 500 saneado, snapshot/read-only real y restauración del aislamiento, procesamiento por lotes y cinco carreras reales.

Se corrigieron durante el desarrollo: una fixture que calculaba un importe límite con contexto Decimal insuficiente, y la clave del error de página vacía para que sea page según contrato. No se relajaron validaciones de dominio para que pasaran las pruebas. La regresión completa final no registra errores de Dashboard ni de callbacks; conserva solo los avisos preexistentes de pruebas JWT que generan deliberadamente tokens para usuarios inactivos.

### Medición PostgreSQL con dataset de varias páginas

Prueba reproducible test_perfil_sql_postgresql_con_varias_paginas: una Obra cerrada por flujo operativo y28 activas con sus presupuestos/ítems en la BD temporal. Medición local de una ejecución, **no SLA ni benchmark productivo**:

| Ruta | Consultas capturadas (incluye auth/frontera transaccional) | Tiempo HTTP local |
|---|---:|---:|
| resumen | 12 | 9.830 ms |
| serie-obras | 8 | 3.331 ms |
| obras-activas | 10 | 6.374 ms |

EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) real de la query de página activa: nodo raíz Limit,25 filas, Planning Time0.246ms y Execution Time0.092ms. El prefetch de ítems se mide por separado dentro del presupuesto de queries HTTP. No se añadieron índices porque ese dataset no justifica migraciones sobre otro dominio.

Otra prueba fuerza lotes de2 sobre7 cierres y confirma cuatro consultas de líneas, no siete consultas por Obra; los importes coinciden con el procesamiento oficial. Las sumas económicas se calculan sin join con pagos. Query budgets testeados: activas≤11 y resumen≤12 con un lote; con múltiples lotes el resumen aumenta una consulta de ítems por lote, no por fila.

OpenAPI versionado: pruebas de rutas, campos, catálogo de respuesta y resolución de referencias locales; no se declara certificación con un validador externo no ejecutado. Frontend, GitHub Actions remoto y Postman **no se ejecutaron ni se declaran aprobados** en esta entrega.

## 7. Compatibilidad, límites y riesgos residuales

- Sin cambios de negocio o migraciones nuevas; solo se registra el include fuera de Dashboard. No se modifica la SPEC contractual ni frontend.
- La cabecera histórica de SPEC-008 aún contiene un estado anterior a su implementación. Se verificó su integración real en código y se conserva la documentación ajena; Dashboard no depende de esa discrepancia ni cambia Auditoría.
- Los KPIs actuales no reconstruyen historia de estados/cobranza. Un rango pasado únicamente restringe el conjunto de finalizaciones económicas.
- Los presupuestos se leen de sus líneas oficiales actuales, inmutables funcionalmente cuando ya existe Obra; no se inventa un snapshot comercial nuevo.
- Una transacción RR larga retiene versiones MVCC hasta terminar: con volumen alto medir latencia, vacuum y planes SQL, y establecer timeouts operativos revisados antes de proponer optimización. No se promete coste constante para todo el histórico.
- La memoria del resumen está acotada por lotes de Obras y fetch de líneas. En la lista, el número de Obras es25, pero presupuestos con muchísimas líneas pueden aumentar el tamaño del prefetch; es el patrón solicitado, no una garantía de memoria independiente de la cardinalidad de ítems.
- El periodo y generated_en son civiles/temporales del inicio de la respuesta; no equivalen a una API histórica ni token de snapshot reutilizable. La comparación diaria de Finanzas se construye al inicio y no se renueva a mitad del procesamiento.
- Paginación por número puede desplazarse entre solicitudes concurrentes; el snapshot solo cubre count/resultados/contexto de una respuesta.
- Los agregados financieros conservan su límite oficial y fallan con409 al excederlo; las sumas de costos/margen no se recortan al límite de documentos.
- No hay desviaciones funcionales intencionales respecto de SPEC. Se concretó aislamiento propio también para serie/lista, política de rechazo de ceros iniciales en page y guardia explícita ante transacciones exteriores incompatibles. Son controles internos sin ampliar permisos ni cambiar los dominios.

## 8. Uso, despliegue y rollback

Uso con access Bearer del login ya existente:

```text
GET /api/dashboard/resumen/
GET /api/dashboard/resumen/?desde=2026-06-01&hasta=2026-11-12
GET /api/dashboard/serie-obras/?meses=6
GET /api/dashboard/obras-activas/?page=1
```

Ejemplo estructural **sintético**, no respuesta programada ni dato real:

```json
{
  "metrica": "OBRAS_FINALIZADAS",
  "zona_horaria": "America/Santiago",
  "puntos": [
    {"mes": "2026-09", "cantidad": 0},
    {"mes": "2026-10", "cantidad": 0},
    {"mes": "2026-11", "cantidad": 0}
  ]
}
```

El frontend recibe métricas ya calculadas y solo representa strings monetarios/nombres autorizados/puntos/paginación. No necesita calcular costos, saldos, autorización o agrupar Obras. Las APIs propias de Alertas y Auditoría se consumen por separado.

Desplegar el backend revisado con PostgreSQL y la configuración existente de JWT; no hay nueva variable, dependencia, cronjob o migración. Mantener ATOMIC_REQUESTS desactivado para estas vistas/servicios, permisos SQL de lectura apropiados y clocks sincronizados. Verificar check/migraciones y smoke de las tres rutas con Gerencia; usuarios no autorizados deben seguir401/403. Ejecutar CI y suite Postman revisada en la fase posterior; no se afirma despliegue remoto.

Rollback: retirar el include /api/dashboard/ o desplegar la versión anterior. No hay tablas, datos o migraciones económicas que revertir ni que reconstruir. No modificar cierres o pagos para forzar un KPI a cero; las inconsistencias409 deben investigarse en el dominio propietario con procedimientos aprobados.

## 9. Punto de revisión obligatorio

El informe inicial se revisó antes de cualquier commit/push/PR. La autorización posterior permite publicar para revisión independiente del código; después de publicar se detiene el trabajo. La integración y aprobación externa quedan pendientes hasta CI, Postman y autorización expresa de merge.

## 10. Verificación previa a publicación autorizada

- Se ejecutaron git status, git fetch origin, git diff --check y revisión de archivos nuevos/modificados. La rama feature/backend-010-dashboard parte exactamente de origin/main=**73852facce12ace6c2b13bf48322f92608c0d437**, merge del PR documental #33, sin avances remotos adicionales al verificarla.
- Alcance:14 archivos, únicamente backend/apps/dashboard, include en backend/config/urls.py y los dos entregables documentales. Sin cambios de frontend, contratos SPEC, settings, Compose, workflows o requirements. No hay migraciones ni dependencias nuevas.
- Revisión de artefactos y secretos: no se incluyen .env, bases/dumps, temporales, bytecode/cachés o evidencias privadas; sin coincidencias en patrones sensibles ni en comparación con credenciales locales, cuyos valores no se imprimieron. .env local sigue ignorado.
- Se separa implementación, documentación/OpenAPI y pruebas en commits coherentes. La documentación precede a las pruebas porque estas verifican el archivo OpenAPI versionado. Antes de cada commit se revisan git diff --cached --stat y git diff --cached --check.
- Nueva ejecución prepublicación: check correcto; makemigrations --check --dry-run sin cambios; **38 pruebas Dashboard aprobadas, 0 fallidas, 20.004 s**. Regresión completa nueva: **759 aprobadas, 0 fallidas, 174.596 s**, sin errores de Dashboard ni callbacks; solo avisos preexistentes de fixtures JWT para usuarios inactivos.
- Profiling de esa ejecución, sobre PostgreSQL temporal con varias páginas: resumen12 consultas/10.440ms, serie8/3.715ms, activas10/7.172ms. EXPLAIN ANALYZE de página activa: Limit25filas, planning0.254ms, execution0.135ms. Son muestras locales, no compromisos de latencia.
- Se publica el PR contra main para revisión de código; no se realiza merge. El estado de GitHub Actions se comprueba en GitHub y se comunica por separado, sin equiparar pruebas locales con CI aprobada. Postman permanece pendiente de preparación/ejecución por el responsable.
