# SPEC-017 — Integración frontend FYAG: Reportes

**Estado:** borrador documental pendiente de aprobación e integración en `main`; no autoriza implementación. **Ámbito:** frontend React/Vite únicamente. **Backend:** SPEC-011 está implementada e integrada en `main` (PR #37), con OpenAPI publicado en `backend/docs/openapi/SPEC-011-v1.json`. No se cambian contratos backend.

## 1. Contexto y objetivo

- `frontend/src/app.jsx` dirige `reportes` al placeholder `PendingIntegration`. `frontend/src/pages/Reportes.jsx` es prototipo: muestra mensajes ficticios de descarga y datos de utilidad/avance derivados localmente. No montar ni reutilizar esas acciones o cálculos.
- Fuente contratual: `specs/011-reportes-backend.md` y OpenAPI de SPEC-011.
- `useAuth().request` desde AuthClient es el único transporte autenticado autorizado, incluyendo descargas Blob con Bearer y refresh existentes.

**Objetivo:** ofrecer catálogo de reportes por rol, listados JSON autorizados con filtros/paginación y descargas auténticas CSV/XLSX/PDF mediante endpoint binario autenticado.

## 2. Alcance, fases y exclusiones

**Fase 1 de esta SPEC:** catálogo y listados JSON auténticos para reportes `obras`, `rentabilidad` y `cobranzas`, respetando rol, filtros, totales, paginación y errores. **Fase 2:** exportación autenticada real de CSV/XLSX/PDF con validación Blob, límites y descarga local efímera. La fase 2 solo se activa tras pruebas específicas de binarios AuthClient y acuerdo funcional de su comportamiento.

Excluye cambios a backend/DB/infra/Compose, escrituras, emisión DTE, pagos/documentos, auditoría global de exportación, adjuntos, notificaciones, nuevos reportes, cálculo en cliente, estadísticas derivadas, datos mock, persistir archivos/PII, links públicos, URL con token, dependencias nuevas, y cualquier afirmación de exportación generada antes de respuesta HTTP exitosa.

## 3. Roles y privacidad

| Rol | Catálogo | Obras | Rentabilidad | Cobranzas | Exportación |
|---|---|---|---|---|---|
| GERENCIA | Sí | Sí | Sí | Sí | Sí según catálogo y endpoint |
| ADMINISTRATIVO_FINANZAS | Sí, solo cobranzas | No | No | Sí | Solo cobranzas |
| SUPERVISOR_OBRAS, TECNICO, ADMINISTRADOR_TI | No requests ni pantalla | No | No | No | No |

Backend decide RBAC. No usar `is_staff`, `is_superuser`, query params o claims para derivar permisos. Validar que el catálogo real recibido delimite tipos y formatos para rol; no crear opciones adicionales. AF jamás ve costo, tarifa, margen, rentabilidad, evidencia ni tipo no autorizado. No exponer RUT, teléfono, email, nombres de usuario, referencia bancaria ni campos extra. Montos se conservan como strings; folio externo como string para mantener ceros iniciales. Datos y filtros sensibles viven solo en memoria de pantalla; descargas en Blob URL efímero revocado después, sin storage persistente ni logs.

## 4. API de catálogo y JSON

Todas las requests pasan por `useAuth().request`, `/api/reportes/...`, con `no-store`, Bearer, refresh y errores existentes.

### 4.1 Catálogo

`GET /api/reportes/catalogo/`, sin query. Validar `{moneda:"CLP", zona_horaria:"America/Santiago", formatos:[...], reportes:[{tipo,titulo,filtros,formatos}]}`. GERENCIA debe ver solo sus tres tipos aprobados; AF solo `cobranzas`. Un catálogo vacío, extra o incoherente no se completa con datos hardcodeados. Mostrar solo los formatos declarados por tipo en servidor.

### 4.2 Listados

Rutas GET exactas `/api/reportes/obras/`, `/api/reportes/rentabilidad/`, `/api/reportes/cobranzas/`, permisos según §3. Envelope `{count,next,previous,results,totales,periodo,moneda,fecha_corte}`, página de 25 y totales para el conjunto completo filtrado. Validar schemas exactos por tipo desde SPEC-011/OpenAPI; no mostrar campos extra. `next/previous` deben quedar bajo mismo origen y endpoint; no navegar directamente a URL devuelta sin validar, y mantener filtros al cambiar página.

Filtros de JSON:
- `desde`/`hasta` como par, ISO civil Santiago, rango max 366 inclusive, desde<=hasta, no posterior a hoy Santiago; omitidos: mes actual desde el primer día hasta hoy.
- `cliente`: ID positivo contractual.
- `estado`: solamente para Obras o Cobranzas y enums propios correspondientes.
- `fecha_base`: solo Obras (`CREACION` o `FINALIZACION`); finalización requiere selección compatible con FINALIZADA.
- `page`: solo listados JSON, positivo, pagina fija 25.

No enviar valores vacíos, duplicados, alias ni campos no autorizados por el catálogo; consultas agregadas/totales reflejan todo el filtro y no se calculan a partir de filas visibles.

### 4.3 Exportación binaria autenticada

Endpoint `/api/reportes/{tipo}/exportar/?formato={csv|xlsx|pdf}`. Query comparte filtros aplicables del tipo; no usa `page`. Formato debe estar autorizado por catálogo para rol/tipo. El cliente debe llamar `request(path, {responseType:'blob'})` o ampliar AuthClient de forma retrocompatible y con pruebas, no usar `<a href>` contra API protegida, `window.open`, `fetch` paralelo, token en URL ni descarga anónima.

Validar respuesta OK, Content-Type esperado (CSV UTF-8, MIME XLSX o PDF), Content-Disposition de attachment con filename saneado, no usar nombre/valores de query para construir rutas. Límite backend 10.000 filas y 50 MiB; errores 413, 429 (`Retry-After`), 400, 401, 403, 404, 409, 5xx se presentan como error sin archivo descargado. Con HTTP 200, crear Blob URL temporal, nombre seguro a partir de cabeceras validadas y disparar descarga; revocar URL tras uso/unmount/logout. No persistir el Blob. El cliente no puede confirmar que navegador guardó archivo; texto de éxito solo indica que recibió respuesta de descarga.

## 5. Presentación y arquitectura

- Montar `frontend/src/pages/Reportes.jsx` solo cuando `mod==='reportes'` y G/AF. Sustituir prototipo, no replicar datos ficticios; para Af ocultar tarjetas de Obras/Rentabilidad aunque se consulte accidentalmente.
- Catálogo dirige tabs/tarjetas a endpoints JSON reales. Cada tipo puede tener filtros server-side, tabla accesible, totales del backend y paginador independiente. Mantener filtro al paginar/refrescar y anunciar base temporal/fecha de corte.
- La semántica de reportes es gestión: margen de rentabilidad no es utilidad contable ni ingreso cobrado; listado de Obras no muestra avance ni costo parcial; cobranzas muestra documentos vigentes, brutos, abonos y saldos calculados por backend. No sumar ni transformar dinero en React.
- Botón Descargar habilitado solo para formato declarado. Deshabilitar durante request, prevenir doble clic, feedback de progreso/error y resultado incierto de red; no anunciar éxito sin Blob válido.
- Reutilizar estilos Bootstrap/FYAG, pager, aislamiento `createScope` y request del contexto. Cancelar lecturas al desmontar/cambiar filtros/sesión; limpiar datos y formulario al logout. Sin dependencias nuevas.
- Validar labels, teclado, foco, tablas responsive a 320/375/768/1024 px, `aria-live`, estado vacío y error.

Archivos candidatos: `frontend/src/pages/Reportes.jsx` (reescritura), `frontend/src/reportes/api.js`, `domain.js`, `frontend/src/app.jsx`, y pruebas `frontend/tests/reportes-*.test.js`; cambios a `frontend/src/auth/client.js` solo si Blob no está soportado y se proponen retrocompatiblemente. No modificar código de ningún otro servicio.

## 6. Estados y errores

- 400: errores públicos de filtros/campos, conservar valores.
- 401: delegar a refresh de AuthClient; limpiar al terminar sesión.
- 403: acceso denegado y borrar datos, sin reintentar.
- 404: tipo/recurso no disponible; no revelar existencia ajena.
- 405: discrepancia de contrato, no variar método.
- 409: integridad de origen; no presentar cifras parciales.
- 413: dataset/archivo excede límites, sin éxito ni archivo.
- 429: mostrar Retry-After.
- Red/timeout/5xx: informar que no se confirmó lectura/descarga, ofrecer GET manual. GET no escribe; si exportación se corta no decir que el archivo quedó guardado.
- Respuestas tardías de usuario anterior, filtro anterior o página anterior se descartan. El snapshot del reporte es por request; exportación y JSON pueden diferir si datos cambian entre solicitudes.

## 7. Pruebas y aceptación

1. RBAC exacto G/AF/S/T/TI; roles no autorizados no emiten request, incluso montaje directo.
2. Catálogo exacto por rol; schema cerrado y no deriva formatos desde constantes locales.
3. Schemas estricto por cada tipo, strings monetarios, folio textual, estados, fechas, periodos, totales y envelope; rechazar floats, propiedades extra, URLs de paginación hostiles.
4. Filtros whitelisted y incompatibilidades por tipo; fechas parejas/civiles, 366 días, futuro, estados, page y ausencia de params vacíos.
5. Totales visibles provienen del envelope y corresponden al conjunto completo; no se calculan en React ni se limitan a página actual.
6. Exportación: permisos/formato/query, Blob real de Content-Type esperado, nombre seguro, Authorization/retry correctos, descarga no ejecutada en errores, URL revocada, no storage y límite 413/429.
7. 400/401/403/404/405/409/413/429/5xx/red/timeout, refresh, cambios de cuenta/filtros, doble clic y respuesta tardía.
8. No hay UI de facturar/pagar, PDF DTE, link público ni mensaje de éxito ficticio; accesibilidad/responsive.
9. Ejecutar `npm ci` si cambian dependencias/lock, `npm test`, `npm run build`. Cuentas de desarrollo/E2E solo se reportan si se ejecutan realmente.

**Aceptación:** UI consulta solo catálogo/JSON/binarios auténticos, RBAC de servidor respetado, totales y fórmulas provienen de API, exportación usa Blob autenticado y no entrega archivo ficticio, módulos ajenos permanecen intactos.

## 8. Riesgos

- Fase 2 binaria requiere confirmar MIME/cabeceras y comportamiento del AuthClient en refresh; no habilitar descarga si falla validación.
- Exportación no prueba almacenamiento por usuario; el cliente comunica «descarga recibida», no «archivo archivado».
- Reportes son snapshots individuales; tabla, totales y exportación de requests diferentes pueden variar con escrituras concurrentes.
- Cobranzas es estado vigente; no presentar cartera histórica ni pagos anulados como activos.

## 9. Aprobación e integración

1. SPEC-017 es borrador documental frontend complementario a SPEC-011; requiere aprobación explícita del texto final.
2. Después de aprobada, rama documental y PR solo de SPEC, sin código; commit/push/PR/merge requieren autorización independiente.
3. Implementar solo tras integración en `main` y encargo expreso. Crear feature desde `origin/main`, ejecutar pruebas e informe antes de publicación.
4. No cambiar backend, permisos, infra ni contratos para que la UI funcione.

## 10. Referencias

- `specs/011-reportes-backend.md`; `backend/docs/openapi/SPEC-011-v1.json`; `backend/apps/reportes/`.
- `frontend/AGENTS.md`, `frontend/src/app.jsx`, `frontend/src/data/constants.js`, `frontend/src/auth/{AuthContext.jsx,client.js}`, `frontend/src/comercial/{ui.jsx,scope.js}`.

## 11. Seguimiento de implementación local (14-11-2026)

- El worktree local contiene `frontend/src/pages/Reportes.jsx`, montado para GERENCIA y ADMINISTRATIVO_FINANZAS, con catálogo y listados JSON autorizados por el rol; se conserva la proyección mínima de AF y no se calculan importes/totales en React.
- El AuthClient local ahora tiene soporte retrocompatible para Blob y metadatos de respuesta; `frontend/tests/auth-client.test.js` lo cubre. La cobertura de Reportes en `frontend/tests/integrations-domain.test.js` verifica catálogo/listado JSON, no certifica exportación CSV/XLSX/PDF contra servidor real.
- Suite completa local: 159 pruebas aprobadas; `npm run build` aprobado. No se ejecutaron E2E ni Frontend CI. Código y nota permanecen locales, sin commit/push/PR/merge.
- El estado de SPEC-017 sigue siendo el borrador documental indicado arriba; esta nota de avance local no equivale a aprobación ni activa por sí sola la fase 2 de exportación.
