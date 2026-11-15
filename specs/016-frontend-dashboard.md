# SPEC-016 — Integración frontend FYAG: Dashboard gerencial

**Estado:** borrador documental pendiente de aprobación e integración en `main`; no autoriza implementación. **Ámbito:** frontend React/Vite solamente. **Backend:** SPEC-010 y sus tres endpoints están implementados e integrados en `main` (PR #34). Esta SPEC limita el Dashboard a consumir schemas existentes y no modifica el contrato backend.

## 1. Contexto y objetivo

- `frontend/src/app.jsx` dirige actualmente `dashboard` a `PendingIntegration`. El prototipo `frontend/src/pages/Dashboard.jsx` agrega montos localmente, presenta porcentajes y afirmaciones no respaldadas por contrato; no debe montarse ni reutilizar su lógica de dominio.
- Fuentes del contrato: `specs/010-dashboard-backend.md` y `backend/docs/openapi/SPEC-010-v1.json`.
- El único rol permitido es GERENCIA. Las consultas usan `useAuth().request` y el AuthClient existente; no crear cliente HTTP, sesión ni persistencia alternativos.

**Objetivo:** implementar una vista gerencial de solo lectura para resumen, serie mensual de obras finalizadas y lista paginada de obras en proceso usando exclusivamente `/api/dashboard/...`.

## 2. Alcance y exclusiones

Incluye `GET /api/dashboard/resumen/`, `GET /api/dashboard/serie-obras/`, `GET /api/dashboard/obras-activas/`; periodo documentado, selección de 1–12 meses, paginación real, actualización explícita, validación estricta de respuestas y estados de UI accesibles.

Excluye escrituras, exportaciones, detalle adicional de recursos, Alertas, Auditoría, navegación a dominios no aprobados, tendencias inventadas, filtros no contractuales, cálculos financieros cliente, porcentajes de avance, rentabilidad proyectada, mocks, cambios backend/DB/Compose/infra y nuevas dependencias.

## 3. Roles y privacidad

| Rol | Acceso Dashboard |
|---|---|
| GERENCIA | Sí, únicamente la proyección de SPEC-010. |
| ADMINISTRATIVO_FINANZAS, SUPERVISOR_OBRAS, TECNICO, ADMINISTRADOR_TI | No montar la vista ni solicitar Dashboard. |

Django controla acceso; el guard React no reemplaza autorización. No usar `is_staff`, `is_superuser`, claims ni query para elevar permisos. No mostrar email, RUT, descripción libre, pagos individuales, tarifas, costos parciales, evidencia o porcentajes de avance. Los importes son strings CLP del servidor; no convertirlos a number ni calcular totales/razones en React.

## 4. Contratos HTTP

Todas las llamadas usan `useAuth().request` a `/api/dashboard/...`, conservando Authorization/refresh. Validar schemas estrictamente y mantener datos solo mientras la pantalla está montada. Cancelar o descartar GETs al cambiar filtros/página/sesión o desmontar.

### 4.1 Resumen

`GET /api/dashboard/resumen/` admite `desde` y `hasta` conjuntamente; ambas `YYYY-MM-DD`, rango máximo 366 días inclusivos, `desde <= hasta`, y `hasta` no posterior a hoy Santiago. Si se omiten, backend aplica el periodo por defecto (primer día del mes civil ubicado cinco meses antes hasta hoy). No enviar query desconocida, repetida, vacía o solo una fecha.

Validar la respuesta exacta: `generado_en`, `zona_horaria` (`America/Santiago`), `moneda` (`CLP`), `periodo`, `operacion`, `rentabilidad_cerrada_periodo`, `cobranza_actual`. `obras_por_estado_actual` debe contener los cinco estados con enteros no negativos. Los montos son strings decimales con dos decimales; mostrar separados presupuesto neto, costo real neto, margen real neto y cobranza bruta. Cifras de operación/cobranza son actuales sin filtro temporal; periodo solo aplica a finalizaciones y rentabilidad según contrato. Margen no equivale a ingreso cobrado, utilidad contable o ganancia tributaria.

### 4.2 Serie mensual

`GET /api/dashboard/serie-obras/?meses=N`; `meses` entero decimal 1–12, omisión equivale a seis. Query whitelist, no vacío/duplicado. Validar `metrica="OBRAS_FINALIZADAS"`, zona Santiago y exactamente N puntos cronológicos `{mes:"YYYY-MM", cantidad: entero no negativo}`. Representar exclusivamente finalizaciones según `finalizado_en`; no etiquetar como inicios ni actividad genérica.

### 4.3 Obras en proceso

`GET /api/dashboard/obras-activas/?page=N`, solo `page`, entero positivo. El backend devuelve `{count,next,previous,results}`, página fija de 25, solo estado `EN_PROCESO`, orden oficial y la proyección exacta `id`, `codigo`, `cliente`, `cliente_nombre`, `categoria_nombre`, `estado`, `tecnico_responsable`, `tecnico_nombre`, `fecha_programada`, `presupuesto_neto`. `next/previous` se validan contra mismo origen y endpoint; la UI deriva la página permitida y no sigue URLs arbitrarias. No filtrar cliente-side como si fuera búsqueda global.

## 5. UX y arquitectura

- Montar la página desde `frontend/src/app.jsx` únicamente con `mod === 'dashboard'` y rol GERENCIA; conservar las otras rutas y placeholders restantes.
- Presentar KPIs exactamente según payload, gráfica accesible de serie finalizada, estado de cinco categorías, rentabilidad cerrada y cartera actual, más tabla paginada de Obras EN_PROCESO. Etiquetas y leyendas explican periodo y diferencias neto/bruto.
- Ningún botón ficticio de exportación, reportes o navegación a acciones no incluidas. No reutilizar arreglos mock del prototipo.
- Reutilizar Bootstrap/CSS FYAG y patrones de fetch aislado/cancelable; sin dependencia nueva. Loading, vacío, errores, 400/401/403/409/5xx/red y vista desactualizada diferenciados. Reintento de lectura solo por acción explícita. Mostrar fallo de rentabilidad inconsistente 409 sin rellenar con cero.
- Labels, tabla navegable, aria-live para estados, contraste/teclado y responsive 320/375/768/1024 px.

Archivos candidatos posteriores: `frontend/src/pages/Dashboard.jsx` (reescritura del prototipo), servicio/domain mínimo bajo `frontend/src/dashboard/`, montaje acotado `frontend/src/app.jsx` y pruebas `frontend/tests/dashboard-*.test.js`. No tocar `frontend/src/auth/client.js` salvo incompatibilidad probada.

## 6. Errores y consistencia

- 400: conservar periodo y filtros y señalar entrada inválida.
- 401: flujo AuthClient; si sesión termina limpiar panel.
- 403: limpiar datos y mostrar permiso denegado sin reintento.
- 405: incompatibilidad contractual; no cambiar método.
- 409: integridad de origen; no presentar rentabilidad parcial ni cifras cero ficticias.
- 5xx/red/timeout: mostrar que no se actualizó, permitir GET manual y no dar cifras previas como actuales sin aviso.
- Una respuesta Dashboard es snapshot coherente por request, no entre endpoints ni solicitudes separadas. No inferir que paneles de llamadas distintas reflejan el mismo instante.

## 7. Pruebas y aceptación

1. Solo Gerencia efectúa las tres rutas; AF/S/T/TI no hacen requests incluso si la página se monta directamente.
2. Resumen, cinco estados, strings monetarios, fechas, serie con N puntos, y página estrictamente tipados; schemas rechazan campos/estados/tipos desconocidos.
3. Periodo default ausente, par de fechas, fechas inválidas/futuras/rango y parámetros repetidos/desconocidos; meses 1, 6, 12 y valores inválidos; page 1/varias y URL next externa.
4. No recalcular dinero, estado, conteos, porcentajes ni totales a partir de tabla; presenta solo los datos contractuales.
5. Rentabilidad inconsistente 409 no se transforma en cero/éxito; 401/403/400/5xx/red y expiración de sesión limpian o conservan estados apropiados.
6. Cambio de usuario/logout/filtro/page descarta respuestas tardías y no persiste respuestas.
7. A11y/responsive y ausencia de mocks; `npm test`, `npm run build`; E2E reportado solo si realmente se ejecuta.

**Aceptación:** dashboard muestra cifras recibidas de API oficial, sin datos simulados ni cálculo financiero en cliente; solo Gerencia consulta; los tres endpoints, filtros/paginación, errores y logout quedan probados; otros módulos siguen intactos.

## 8. Riesgos

- Algunas métricas de resumen no respetan el rango por definición; el diseño debe rotularlo, sin hacer creer que toda tarjeta es histórica.
- Rentabilidad usa obras finalizadas y cierres reales; no denominar ingreso, utilidad o margen proyectado.
- Un snapshot aplica a una respuesta, no a todas las tarjetas cargadas por llamadas separadas.

## 9. Aprobación y secuencia

1. El presente documento es un contrato frontend borrador complementario a SPEC-010; aprobarlo requiere revisión específica del texto.
2. Tras aprobación explícita, publicar exclusivamente documentación en rama `docs/spec-016-frontend-dashboard`, sin código; PR/merge requieren autorización independiente.
3. Después de integrar el documento en `main`, actualizar la copia local; implementar solo con SPEC integrada y encargo expreso, en rama frontend desde `origin/main`.
4. No publicar código ni tocar backend/infra automáticamente; presentar diff, pruebas reales e informe para revisión antes de cualquier commit/push.

## 10. Referencias

- `specs/010-dashboard-backend.md`; `backend/docs/openapi/SPEC-010-v1.json`; `backend/apps/dashboard/`.
- `frontend/AGENTS.md`, `frontend/src/app.jsx`, `frontend/src/data/constants.js`, `frontend/src/auth/{AuthContext.jsx,client.js}`, `frontend/src/comercial/{ui.jsx,scope.js}`.

## 11. Seguimiento de implementación local (14-11-2026)

- El worktree local contiene `frontend/src/pages/Dashboard.jsx`, montado solo para GERENCIA; consulta `/api/dashboard/resumen/`, `/api/dashboard/serie-obras/` y `/api/dashboard/obras-activas/`, sin mocks ni agregación financiera en React.
- `frontend/tests/integrations-domain.test.js` cubre las consultas Dashboard. La suite local completa aprobó 159 pruebas y el build aprobó; E2E autenticado y Frontend CI no se ejecutaron.
- El código permanece local, sin commit/push/PR/merge. Esta anotación registra implementación presente, pero no cambia el estado de aprobación documental borrador descrito arriba.
