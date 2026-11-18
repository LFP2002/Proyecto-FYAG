# SPEC-014 — Integración frontend FYAG: Cobranzas

> **Estado actual (17-11-2026):** el alcance frontend de Finanzas, incluido selector elegible, estado financiero y cierre administrativo sin cobro, se publicó en la rama `feature/frontend-005c-integracion-modulos` mediante el [PR #44](https://github.com/LFP2002/Proyecto-FYAG/pull/44), pendiente de revisión y **sin merge en `main`**. Esta publicación no acredita aprobación documental histórica, despliegue ni QA integral. La autorización de merge sigue siendo independiente.

**Antecedente documental previo a la revisión del 17-11-2026:** el texto reducido describía únicamente cartera/resumen y dejaba pendientes las operaciones administrativas. Se conserva ese antecedente, pero el estado local actual se detalla a continuación. La aprobación/integración documental histórica no se acredita con este checkout.

## Alcance vigente en código

La interfaz de cartera consulta `/api/finanzas/cobranzas/` y `/api/finanzas/cobranzas/resumen/` con filtros y paginación del servidor. GERENCIA y ADMINISTRATIVO_FINANZAS pueden consultar conforme al backend; el frontend no calcula saldos, no emite DTE, no procesa pagos ni transfiere dinero.

La rama en curso agrega una interfaz administrativa de Finanzas sobre endpoints ya definidos para documento externo, pagos reales informados, historiales, reversión/anulación y adjuntos de respaldos. La autorización efectiva pertenece al backend; solo ADMINISTRATIVO_FINANZAS ve escrituras. La validación de contrato, confirmación de relecturas y pruebas de integración siguen pendientes hasta completar verificaciones reales.

## Pendiente y decisiones

- Verificar que los endpoints financieros están disponibles en el backend desplegado, confirmar esquemas completos y filtros/paginación de historiales.
- Revisar con el responsable el alcance de escritura de SPEC-014; esta actualización no acredita aprobación separada.
- Validar con entorno QA autorizado registro/replay idempotente de pagos, conflictos de saldo, pagos activos antes de revertir, errores y cargas antimalware.
- No añadir emisión de DTE, cobro en línea, transferencias, cálculos financieros de frontend, ni acceso directo a PostgreSQL.

## Contrato backend de referencia

- Cartera y resumen: `GET /api/finanzas/cobranzas/` y `/api/finanzas/cobranzas/resumen/`.
- Documento: `GET/POST /api/finanzas/documentos/`, `GET /api/finanzas/documentos/{id}/`, `POST /api/finanzas/documentos/{id}/revertir/` y `GET .../historial/`.
- Pagos: `GET/POST /api/finanzas/documentos/{id}/pagos/`, `GET .../pagos/{pago_id}/`, `POST .../pagos/{pago_id}/anular/`, historial paginado.
- Los detalles de respuestas, validaciones, RBAC y errores están en `backend/apps/finanzas/` y `specs/007-finanzas-cobranzas.md`; validar contra fuentes reales antes de ampliar schemas cliente.
- Respaldo privado documental: SPEC-012B y rutas `/api/adjuntos/`; verificación antivirus es fail closed.

## Seguridad y límites

- Reutilizar `useAuth().request`; no almacenar tokens o datos financieros en almacenamiento persistente.
- GERENCIA lectura; ADMINISTRATIVO_FINANZAS puede escribir según permiso del backend; los demás roles no deben invocar rutas financieras.
- Usar strings decimales y estados devueltos por API sin cálculos cliente. Los pagos son registros de hechos externos, no movimientos de dinero de FYAG.
- Confirmar anulaciones/reversiones con motivo y referencia externa; ante 409 no mostrar éxito ni reintentar automáticamente.
- Informar en este documento lo implementado localmente, pruebas realmente ejecutadas y pendientes; no declarar CI/E2E o aprobación sin evidencia.

## Revisión contractual local — 17-11-2026

### Objetivo, alcance y exclusiones

Completar la administración frontend de SPEC-007 usando los servicios existentes. `Cobranzas.jsx` conserva cartera/resumen; `FinanceAdmin.jsx` organiza documentos, selección elegible y consulta por ID; `FinanceDocument.jsx` presenta detalle, pagos y sus historiales. `finance.js` valida proyecciones, sin calcular montos. No cambia autenticación, backend, Obras, cortesías históricas, contabilidad, SII ni bancos. MongoDB no determina estados o saldos.

### Roles

| Operación | GERENCIA | ADMINISTRATIVO_FINANZAS | S / T / TI |
| --- | --- | --- | --- |
| Cartera, resumen, documentos, pagos, historiales, estado financiero | Lectura | Lectura | Sin acceso |
| Obras elegibles | No | Lectura | No |
| Registrar/revertir documento, registrar/anular pago, registrar sin cobro | No | Según validación Django | No |
| Respaldos y anotaciones 012B | Lectura | Lectura/escritura autorizada | No |

### APIs y contratos

Todos los endpoints son existentes, verificados en `backend/apps/finanzas/`; no son propuestas futuras. Prefijo `/api/finanzas/`:

| Método y ruta relativa | Entrada / respuesta principal |
| --- | --- |
| GET `cobranzas/`, `cobranzas/resumen/` | Filtros `estado`, `cliente`, `obra`, `fecha_vencimiento_desde/hasta`, `fecha_emision_desde/hasta`; página solo en cartera; importes y conteos calculados por backend |
| GET `obras-elegibles/?page=N` | Orígenes financieros paginados, identificados por `obra`, **sin campo id**; excluye SIN_COBRO |
| GET `obras/{id}/estado-financiero/` | `origen`, `estado_financiero`, `documento_vigente`, `cierre_sin_cobro` |
| POST `obras/{id}/registrar-sin-cobro/` | Exclusivamente `{motivo_registro: string}`; cierre con `id`, `obra`, `cortesia`, actor, fecha y estado |
| GET/POST `documentos/` | Página o registro externo con `obra` entero, tipo, folio string, fechas ISO, montos decimales string y referencia |
| GET `documentos/{id}/`, `documentos/{id}/historial/` | Documento / eventos paginados |
| POST `documentos/{id}/revertir/` | `{motivo, referencia_rectificacion_externa}` |
| GET/POST `documentos/{id}/pagos/` | Página / `{monto, fecha_pago, medio, referencia_respaldo, observacion}` y `Idempotency-Key` |
| GET `documentos/{id}/pagos/historial/` | Eventos paginados independientes |
| POST `documentos/{id}/pagos/{pago_id}/anular/` | `{motivo, referencia_reversion_externa}` |

Origen: Obra, presupuesto, cliente, moneda, monto neto aprobado, finalización y cortesía. Estados financieros: `PENDIENTE_FACTURACION`, `PENDIENTE_REGISTRO_SIN_COBRO`, `SIN_COBRO`, `DOCUMENTADO`. Documento `VIGENTE` o `REVERTIDO`; en este último `cobranza=null`, nunca saldo cero fabricado. Páginas DRF de hasta 25 filas con `count/next/previous/results`; las tres paginaciones de pagos e historiales no se mezclan ni se presentan como completas.

### UX, concurrencia y seguridad

- Selector elegible paginado conserva el ID elegido al cambiar página; consulta independiente por ID permite localizar SIN_COBRO.
- Registro sin cobro exige consulta previa, estado compatible, finalización informada, cortesía SIN_COBRO, motivo y confirmación. La proyección **no expone presupuesto.estado ni cierre histórico de costos**: no se inventan campos y Django valida definitivamente esos requisitos.
- Cada mutación invalida vistas afectadas y exige relecturas del detalle, documentos y cartera/resumen antes de confirmar éxito o limpiar formularios. Si fallan, se conserva el bloqueo y no se repite automáticamente.
- Un pago incierto conserva payload y clave en memoria, bloquea edición y requiere relectura más reintento explícito idempotente. Una intención rechazada solo se descarta mediante decisión explícita; contenido nuevo usa clave nueva.
- Contextos keyed por usuario/rol/recurso y scopes descartan respuestas tardías. `400` conserva datos, `403/404` no escalan acceso, `409` exige revisión, red/5xx no prueban fracaso. `401` usa el cliente de sesión existente.
- Adjuntos privados: FormData, límites PDF 8 MiB e imagen 5 MiB, descarga autenticada, anotaciones scoped con revisión CAS, sin edición por Gerencia. `413/422/503` no se presentan como éxito.
- Desde el detalle de un documento financiero se consultan a demanda sus respaldos (`GET /api/adjuntos/documentos-cobro/{id}/`), incluidos los documentos `REVERTIDO`. Para documentos vigentes, Finanzas puede subir respaldos según autorización Django y Gerencia solo consulta; para los revertidos la interfaz muestra listado, detalle, anotaciones y descarga en **solo lectura**, sin controles de alta ni edición. No se altera el estado financiero ni el almacenamiento privado.
- Etiquetas accesibles, estados de carga/vacío/error/bloqueo, tablas desplazables y paginación nombrada; no hay recarga completa de página ni almacenamiento persistente de datos sensibles.

### Aceptación, pruebas y publicación

1. Roles ajenos no solicitan APIs financieras; Gerencia no consulta elegibles ni escribe.
2. Selector navega páginas sin perder elección; sin cobro usa consulta independiente y un único POST contractual.
3. Cambiar documento reinicia las tres páginas y descarta lecturas del anterior.
4. Escritura y relectura fallida nunca se anuncian como éxito; pago incierto conserva clave/payload.
5. Reversión/anulación actualizan vistas afectadas con importes del servidor.

Pruebas sintéticas contractuales en `frontend/tests/integration-corrections.test.js`, incluyendo respaldos históricos, fixtures en `frontend/tests/helpers/finance-contract.js` y regresiones en `integrations-domain.test.js` y `obras-costos-ui.test.js`. Consultar resultados verificables del workflow **Frontend CI** en el PR #44; estos no equivalen a QA real. Pendientes para aceptación integral: QA aislado autorizado, concurrencia real, permisos y ClamAV. Estado documental: revisión de alcance frontend, sin atribuir aprobaciones históricas; estado del código: publicado en PR #44, **todavía no fusionado en `main`**. El merge exige autorización expresa del responsable. Un rollback autorizado debe conservar datos y trabajo ajeno.

## Aclaraciones pre-merge PR #44 — 17-11-2026

- SPEC-012B §12 formaliza ahora el rechazo autoritativo Django de PATCH sobre factura REVERTIDO (409 `documento_no_vigente`), preservando lectura histórica y CAS. La protección visual ya publicada no sustituye esa comprobación.
- Paginación: se aceptan enlaces relativos y absolutos solo del origen web o del `VITE_API_BASE_URL` explícito validado por `auth/config.js`. Se validan ruta, query sin duplicados, página entera segura y mismos filtros (sin depender del orden). El cliente extrae la página y **reconstruye rutas internas con filtros locales**, nunca sigue URLs de respuesta. `redirect: 'error'` del cliente HTTP se conserva. Lógica común en `integrations/pagination.js`/`useApi.js`, utilizada por Cobranzas, Reportes y 012A. Proxy Vite habitual conserva Host/Origin; no requiere cambio para esta corrección.
- Se preservó en el working tree la diferencia remota `e4113419…` → `efa33327…` (UI/pruebas de históricos y seguimiento documental), sin mover HEAD, commit, merge ni rebase. Al publicar posteriormente, revisar el diff **contra efa33327…**, no confundir ese contenido remoto con correcciones nuevas de esta revisión.

### Auditoría de dependencias comprobada

`npm ci`, `npm audit --json`, `npm audit --omit=dev` y `npm ls` identificaron una causa raíz, no cuatro CVE independientes:

| Paquete instalado | Tipo / severidad | Rango reportado / advisory | Corrección disponible |
| --- | --- | --- | --- |
| picomatch 4.0.7 | Transitiva dev / alta | <=4.0.7, GHSA-fc5q-39xc-vjpf, CVE-2026-112366; ReDoS por extglobs repetidos | Ninguna publicada según npm y advisory consultados el 17-11-2026 |
| fdir 6.5.0 | Transitiva dev / alta heredada | npm reporta >=5.2.1 por picomatch | Sin resolver causa raíz en árbol actual |
| tinyglobby 0.2.17 | Transitiva dev / alta heredada | npm reporta * por fdir/picomatch | Sin resolver causa raíz en árbol actual |
| vite 6.4.5 | Directa dev / alta heredada | npm reporta >=6.3.0-beta.0 por árbol glob | Vite 8.3.8 también depende de picomatch ^4.0.7; salto mayor no lo resuelve |

Advisory: https://github.com/advisories/GHSA-fc5q-39xc-vjpf (`first_patched_version=null`). Exposición: globbing Node de desarrollo/build ante patrones no confiables; el frontend no acepta globs del usuario ni incluye Vite como dependencia runtime del bundle. Esto reduce exposición, **no elimina** la vulnerabilidad ni autoriza aceptarla. Producción: `npm audit --omit=dev` reporta 0. Árbol completo: 4 altas aún pendientes.

No se aplicó `npm audit fix --force`: su sugerencia Vite 6.2.7 es un downgrade que elimina ese subárbol, no un parche de picomatch; abandona correcciones posteriores y no se considera actualización compatible y mínima. Tampoco se agregan forks/overrides no corregidos ni se deshabilita auditoría. No hay actualización publicada compatible que resuelva el hallazgo; package.json/lock se conservan. **Bloqueo abierto**, requiere parche upstream verificable o decisión de riesgo del responsable antes de merge.

QA real reproducible y recorrido manual pendiente: `backend/docs/SPEC-012B-OPERACION.md`, sección pre-merge. Resultados de esta revisión se añaden a `backend/docs/SPEC-012B-IMPLEMENTACION.md` tras la ejecución. Ningún resultado frontend simulado equivale a integración navegador/API real.

### Cierre de exposición tooling (árbol reconciliado, 17-11-2026)

`npm ci` reinstaló 71 paquetes (72 auditados), sin cambiar versiones/lock.
`npm ls` confirma Vite 6.4.5 → picomatch 4.0.7, fdir 6.5.0 y tinyglobby
0.2.17. El build normal pasó (99 módulos transformados, 1,74 s). Un segundo
build con inventario Rollup externo verificó **92 módulos runtime y cero módulos
de picomatch/fdir/tinyglobby/vite**, mismo asset `index-CIOiIAS9.js`.
Inventario: directorio externo `fyag-pr44-browser-final/bundle-inventory.json`.
Buscar únicamente texto minificado no habría bastado como prueba de exclusión.

No hay imports de esos paquetes ni `import.meta.glob` en `frontend/src`.
Los filtros/rutas API de usuario no se pasan como patrones glob a Node.
La explotación ReDoS requiere que un patrón extglob malicioso alcance el tooling;
un checkout/config/plugin no confiable en CI/desarrollo sigue siendo una vía de
riesgo. No se ha realizado una prueba de explotación ni demostrado imposibilidad.

Controles verificados: Vite no configura host público; laboratorio limitado a
127.0.0.1; workflow con `permissions: contents: read`, timeout 10 minutos y
`npm ci`/test/build/auditoría runtime, sin servir Vite. No se acredita despliegue
productivo mediante ese workflow. Controles operativos requeridos: no exponer
dev/preview a redes no confiables, revisar cambios de config/plugins/patrones,
ejecutar PR no confiables sin secretos y con límites de recursos; servir solo
artefactos estáticos en producción. Son mitigaciones, no un parche.

Resultado actual: audit completo **4 high, salida 1**; `--omit=dev` **0, salida 0**.
GHSA-fc5q-39xc-vjpf / CVE-2026-112366 sigue abierta. Riesgo residual reducido
para el navegador productivo, vigente para herramientas Node. Recomendación:
**bloquear merge** hasta parche verificado o aceptación explícita del responsable
con alcance, controles y seguimiento; esta revisión no concede esa aceptación.

### Seguimiento funcional de cierre y despliegue (17-11-2026)

El desborde de Usuarios TI se corrigió exclusivamente en `Usuarios.jsx` y
`styles/pages/usuarios.css`: las tablas de mínimos780/900px quedan dentro de
regiones con scroll horizontal, nombre accesible y tabIndex0. Grid y ajuste de
texto están acotados a `.usuarios-page`; `Table.jsx` y layout global no cambian.
Edge midió scrollWidth/clientWidth **360/360, 753/753, 1265/1265** para viewports
375/768/1280 (la diferencia es la barra vertical). Antes:929/360,933/753,1265/1265.
Regresión real versionable: `frontend/qa/usuarios-responsive.mjs`, incluye teclado,
texto largo DOM sintético y formulario, sin escritura backend.

Descargas por botones React confirmadas con `Input.dispatchMouseEvent` y eventos
`Browser.downloadWillBegin/downloadProgress` completed; CSV/XLSX/PDF y respaldo
PDF/PNG guardados y parseados. No se cambió la lógica React de descarga: la
instrumentación anterior usaba Page y no acreditaba entrega; Browser con ruta
Windows nativa e interacción real sí lo acredita. No se ha aislado una única
causa entre todas las diferencias de instrumentación, ni se atribuye un bug a React.

HTTPS probado funcionalmente entre localhost:5443 y localhost:6443, CORS con
credenciales explícito, preflight200, cookies Secure/HttpOnly/Strict, CSRF
omitido403, sesión y paginación absoluta https. **TLS no confiable por CA**:
sin excepción Edge devuelve ERR_CERT_AUTHORITY_INVALID; solo para esta prueba se
permitió la SPKI del certificado QA en perfil exclusivo. No se instaló CA ni se
acepta esa excepción como configuración productiva. Requiere repetir con cadena
de confianza autorizada antes de aprobar. Cookies Strict necesitan mismo sitio
schemeful, no necesariamente mismo origen; CORS no habilita cookies entre sitios.

Picomatch reconsultado: npm latest4.0.7 y advisory oficial con
`first_patched_version=null`; lock/dependencias sin cambios, audit completo
continúa fallando con4high. Propuesta **para decisión**, no aceptación del agente:
aceptación temporal limitada al tooling, solo tras cumplir el resto del QA;
responsable de seguridad/maintainer debe registrar nombre, decisión, fecha,
vencimiento máximo30días y revisión semanal de upstream. Condiciones: artefacto
estático sin esos módulos, tooling solo loopback/CI aislado sin secretos para
código no confiable, patrones/config/plugins revisados y límites de recursos.
Parche verificable implica actualizar mínimamente y repetir ci/test/build/audits.
Si el responsable no acepta expresamente, el riesgo sigue bloqueante.

### Registro formal de decisión autorizada — PR #44

**Estado vigente: ACEPTADO TEMPORALMENTE.** El responsable del proyecto autorizó
expresamente esta decisión en conversación el **17-11-2026**. Actualiza las
propuestas y bloqueos históricos de los apartados anteriores; no declara la
vulnerabilidad solucionada ni constituye aprobación de seguridad para producción.

| Campo | Decisión vigente y condiciones |
| --- | --- |
| Hallazgo | GHSA-fc5q-39xc-vjpf / CVE-2026-112366; severidad upstream high |
| Árbol | Vite6.4.5 → picomatch4.0.7, fdir6.5.0, tinyglobby0.2.17; dependencias dev |
| Reconsulta | npm latest4.0.7; advisory oficial sin first_patched_version; audit completo4high/salida1 |
| Alcance autorizado | **Exclusivamente desarrollo y QA**, incluido su tooling Node; no autoriza producción. ReDoS de event loop ante extglobs maliciosos; no hay imports de globbing ni entrada de usuario a patrones en frontend/src |
| Producción |92módulos runtime sin los paquetes de tooling afectados; audit omit-dev0; no certifica ausencia universal de riesgos |
| Controles exigidos | Tooling loopback, CI aislado sin secretos para código no confiable, revisión de config/plugins/patrones y límites CPU/tiempo; mantener auditoría completa visible |
| Riesgo restante | Dev/build/CI ejecutan Node vulnerable; un patrón/config/plugin/checkout no confiable puede alcanzar el tooling. El aislamiento reduce impacto, no corrige la vulnerabilidad |
| Estado | **ACEPTADO TEMPORALMENTE**; riesgo residual vigente, no corregido |
| Autoridad | Responsable del proyecto, autorizado expresamente en conversación el 17-11-2026 |
| Revisión | Semanal de disponibilidad de parches; mantener visibles las cuatro alertas npm y los controles de aislamiento/patrones confiables |
| Caducidad propuesta | 30 días: 17-12-2026, con nueva evaluación expresa del responsable; sin renovación automática |
| Condición de actualización | Cuando exista parche oficial compatible, actualizar mínimamente y repetir test/build/audits e inventario antes de cerrar el hallazgo |
| Decisión del responsable | Aceptar temporalmente el hallazgo identificado, solo en el alcance desarrollo/QA |
| Fecha de autorización | 17-11-2026, según la instrucción expresa del responsable |
| Evidencia | Autorización conversacional; no se inventan firma digital, identidad adicional ni ticket |

No downgrade de Vite, audit fix --force, override/fork ni cambio del lock para
ocultar alertas. La aceptación no cambia el resultado esperado del audit completo:
**4high/salida1** siguen visibles; `--omit=dev`0 no equivale a aprobación global.
Actualizar cuando exista una corrección oficial verificada y repetir pruebas,
build/audits e inventario. La vulnerabilidad sigue abierta hasta entonces.

**TLS: no autorizado modificar confianza.** El responsable no autoriza instalar
una CA raíz en Windows, modificar almacenes confiables ni desactivar verificaciones
TLS del sistema. La configuración queda intacta. Validar una cadena confiable y
repetir HTTPS sin excepciones es un **requisito pendiente de despliegue**, separado
del QA funcional ya realizado; SPKI/autofirmado no son confianza TLS validada.

**Publicación autorizada para auditoría:** commits y push normal únicamente a
`feature/frontend-005c-integracion-modulos`, actualizando el PR#44 existente en
Draft. Esta autorización no permite merge, push a main, force push, eliminar ramas,
crear otro PR ni convertirlo a Ready for Review. Los dictámenes históricos
NO APTO de despliegue/merge no impiden esta publicación limitada para revisión.
