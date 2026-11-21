# SPEC-022 — Integración frontend FYAG Beta: Bodega y egresos

> **Estado: contrato de integración revisado para implementación en incrementos independientes.** 21-11-2026.
> **Base verificada:** `main` `daf4ce55687c61a4304e8fe985dc2977fe875f1f`. Backend SPEC-019A/019B/020A/020B/021 integrado. Sin PR abiertos al preparar este contrato.
> **Ámbito:** `frontend/` React/Vite y sus pruebas. No modificar modelos, migraciones, permisos ni contratos del backend; cualquier incompatibilidad material se reporta, no se subsana improvisando API.
> **División:** 022A = acceso BODEGUERO e interfaz de Bodega (019A/019B); 022B = interfaz de egresos y flujo registrado (021). PR y CI independientes. El frontend React es un trabajo coordinable con colaboradores; comprobar ramas/cambios ajenos antes de comenzar.

## 1. Razón y prioridad

El backend ya resuelve los movimientos de inventario y flujo de dinero pero la interfaz actual todavía no los expone. La identidad `BODEGUERO` no está incorporada en `frontend/src/auth/client.js` (`USER_ROLES`) ni en `frontend/src/data/constants.js` (`ROLES/NAV/DEFMOD/MODS`): la sesión del bodeguero es rechazada por la validación de perfil. No debe presentarse FYAG Beta como operativamente integrada mientras esto ocurra. La app tampoco tiene páginas para registrar egresos 021 ni el resumen neto; no confundir los reportes antiguos de cobranza con flujo de dinero.

Objetivo: interfaz operable con los roles y contratos existentes, sin frontend ficticio, sin procesamiento financiero en cliente y sin nuevas funciones fuera de las SPEC.

## 2. Incremento 022A — Bodega de material y movimientos

### Acceso y rutas
- Añadir `BODEGUERO` a validación de identidad, etiquetas, navegación y módulo inicial. Mantener la sesión versionada, la CSRF existente, refresh HttpOnly, separación de datos por usuario/rol, cierre de sesión y restauración segura.
- Módulo `bodega` para Bodeguero, Supervisor, Gerencia y Administrativo/Finanzas, con opciones y acciones condicionadas a permiso real del backend. Técnico y TI no lo ven. Gerencia solo consulta.
- No generar rutas de negocio ficticias ni mostrar cifras económicas al Bodeguero. El backend es autoridad para permisos; ocultar botones no reemplaza 403/401.

### Experiencia mínima por rol
- Bodeguero: consultar/buscar catálogo, crear/editar artículos (con invariantes de 019A), ver existencias, registrar ingreso físico, consultar movimientos de inventario, revisar autorizaciones de entrega, confirmar despachos parciales y recepciones de devoluciones previamente autorizadas. Consultar `estados-valorizacion/` sin precios y explicar que no se despacha si hay cantidades sin valorizar.
- Supervisor: consultar catálogo/existencias, autorizar entregas para Obras operativas, revisar despachos, autorizar devoluciones por entrega específica y consultar costos históricos de despachos/devoluciones en vistas donde corresponda. No confirmar movimientos físicos ni valorar artículos.
- Administrativo/Finanzas: consultar existencias y estado, listar valorizaciones/regularizaciones y registrar precio neto respaldado por ingreso, incluyendo regularización de stock histórico cuando procede. Nunca simular un pago real ni crear `Egreso`.
- Gerencia: consultar datos autorizados; lectura de costo/valorización donde backend lo permita, sin operaciones de escritura.

### Contrato y seguridad
- Fuente de verdad: `/api/inventario/` de SPEC-019A/019B. Leer código y OpenAPI `backend/docs/openapi/SPEC-019B-v1.json` y la documentación de 019A; no inventar rutas. Las consultas paginadas solo admiten filtros documentados. Si la lista de Obras del Supervisor se usa para una autorización, obtenerla por su endpoint ya autorizado. El Bodeguero selecciona autorizaciones sin acceder a detalles no autorizados de Obras.
- Escrituras 019B: `clave_idempotencia` UUID **en JSON body**, único por intención de usuario. Conservar la misma UUID y el mismo cuerpo al resolver una escritura ambigua; jamás regenerarla automáticamente para hacer un segundo POST. Mostrar 200 replay y 201 alta como el mismo acto, no crear duplicados; 409 obliga a releer y reconciliar antes de decidir.
- Entrada 019A: identidad idempotente en body; movimientos físicos y saldos proceden exclusivamente del servidor. Cantidades son strings decimales hasta tres posiciones, sin floats. Valor unitario neto/precio de Bodega: strings con dos decimales, solo AF/G y dentro de las vistas autorizadas.
- Mostrar el promedio y costo original retornados por el servidor solo a roles autorizados. Nunca calcular ni actualizar manualmente saldos, costo de Obra, promedio, costo histórico o subtotal oficial en React.
- No exponer errores SQL, secretos, URLs arbitrarias, datos de terceros ajenos ni costos en mensajes accesibles a Bodega. Separar proyecciones de lectura, vistas y validadores por rol; prevenir fugas en DOM, estado compartido, navegación y caches.
- Formularios con controles claros y confirmación en acciones que cambian stock/costos; accesibilidad con etiquetas, estados loading/error/empty, teclado y navegación móvil. No convertir una denegación de permisos en pantalla blanca.

## 3. Incremento 022B — Egresos y flujo registrado

- Módulo `egresos` accesible a `ADMINISTRATIVO_FINANZAS` y `GERENCIA`. No agregarlo a Bodega, Supervisor, Técnico o TI.
- AF: listado paginado/filtros, alta de egreso real (fecha civil Santiago, total CLP string decimal, categoría, medio, beneficiario, concepto, respaldo, observación, Obra opcional como referencia), detalle, historial y anulación motivada con referencia de corrección. No editar egresos existentes.
- Gerencia: listados, detalles, historial y resumen solo lectura, sin botones operativos.
- Resumen de período: `GET /api/finanzas/flujo-dinero/resumen/`; usar exactamente `ingresos_recibidos`, `egresos_pagados` y `flujo_neto_registrado` del backend, incluso negativo. Etiquetar como **flujo de dinero registrado, no conciliado**, jamás utilidad, caja disponible o saldo bancario.
- `POST /api/finanzas/egresos/` usa header `Idempotency-Key` UUID y mismo cuerpo en reintentos; 201 primera alta, 200 replay incluso tras anulación. Un 409 requiere conciliación de estado. `POST .../{id}/anular/` exige `motivo` y `referencia_correccion`; no equiparar a devolución bancaria.
- Usar `backend/docs/openapi/SPEC-021-v1.json` y `backend/docs/SPEC-021-IMPLEMENTACION.md`. Fechas civiles y filtros según API; paginación validada. Sin calcular en frontend pagos/costos a partir de otros dominios ni emitir DTE. Sin Banco/IVA/DTE/conciliación automática.

## 4. Patrones comunes

1. Reutilizar `AuthContext`, `authClient.request`, `useApi`, scope de cancelación/operación, `PageHead`, `Pager`, Shell responsive y diseño existente. Mejorar adaptadores de paginación donde la API real exija nuevos filtros; validar los enlaces sin permitir hosts ajenos. Evitar duplicar un cliente HTTP.
2. No usar datos `seed.js` para módulos reales, ni persistir JWT, CSRF, formularios financieros, precios ni secretos en localStorage/sessionStorage. Respuesta 401 limpia sesión; 403 informa sin mostrar datos; 400 valida campos; 409 fuerza reconciliación. Ante corte de red o respuesta 502 después de POST, bloquear reenvío inadvertido y conservar la clave mientras se consulta/reconcilia.
3. Mantener los nombres y reglas exactos de roles/campos/estados respaldados por backend. No reutilizar etiquetas antiguas que atribuyan a Gerencia aprobación de presupuestos o creación de gastos si contradicen SPEC-020; actualizar solo lo necesario dentro de los incrementos.
4. Cambios del contrato deben reflejarse en pruebas permanentes sin modificar las pruebas para ocultar un defecto. Sin ampliar alcance a autenticación inicial SPEC-018, chat, 019C, alertas nuevas o despliegue. Las pendientes de credenciales iniciales/TLS/picomatch siguen siendo puertas separadas para producción.
5. Comprobar siempre rama, árbol y trabajo de colaboradores; cambios exclusivamente en `frontend/` y pruebas/estilos directamente necesarios. No tocar `backend/`, SPEC antiguas ni archivos del equipo React ajenos al alcance.

## 5. Aceptación 022A

- Login/restore de BODEGUERO permitido y navegación correcta; acceso de roles viejos sin regresiones.
- Flujo completo: catálogo → ingreso → valoración AF → autorización Supervisor → despacho Bodeguero → autorización de devolución Supervisor → recepción Bodeguero → consultas y estado.
- Ninguna operación genera dinero; Bodeguero no puede ver precios ni costos; 403/401/409 tratados; idempotencia de reintentos y cambios de usuario sin datos residuales.
- Respuesta de servidor manda sobre existencias, unidades y costos. Lista/paginación y filtros estables con datos extra; no asumir que página 1 es única.
- Tests unitarios/contratos React, `npm test`, `npm run build`, `npm audit --omit=dev`, y QA de navegador contra backend permitido cuando exista; no reportar pruebas no ejecutadas.

## 6. Aceptación 022B

- AF crea, consulta y anula egresos; Gerencia lee, otros roles sin acceso.
- Idempotency-Key sostenida ante reconexión/reintento; no doble POST involuntario.
- Filtros/periodos y resumen exactos de API; no sumas monetarias ni valores financieros inventados.
- Pruebas unitarias/contratos, errores, permisos, regresión frontend y CI.

## 7. Git y entrega

- 022A: `feature/frontend-022a-bodega`; 022B: `feature/frontend-022b-egresos`; derivar cada rama de `main` actualizado tras merge de la anterior. Ningún merge directo ni force-push por OpenCode.
- OpenCode hace pruebas, `git diff --check`, revisión de untracked, limpieza, commit y push en cada rama. ChatGPT revisa los cambios en GitHub, abre PR y fusiona **solo con CI y revisión técnica aprobados**, por autorización general del responsable.
- No subir capturas, fixtures falsos, secrets, dumps, scripts desechables, .patch, .diff, caches, node_modules, builds ni documentación duplicada. Conservar SPEC y pruebas permanentes.
- Las colecciones Postman de informe están delegadas a compañeros; no bloquear la implementación por resultados manuales pendientes. El QA automático de cada PR sigue siendo obligatorio.
