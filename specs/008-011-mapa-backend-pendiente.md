# Mapa de contratos backend — SPEC-008 a SPEC-012

**Estado: mapa de avance actualizado tras PR #37.** SPEC-008 (Auditoría), SPEC-009 (Alertas), SPEC-010 (Dashboard) y SPEC-011 (Reportes) están implementadas e integradas en `main`; SPEC-012 (MongoDB) está **propuesta** y pendiente de aprobación e implementación. Este mapa es documental y no implementa endpoints nuevos.

## 1. Estado e inventario comprobado
- IMPLEMENTADO: autenticación y Usuarios bajo /api/auth/ y /api/usuarios/ (SPEC-002/006B/006C).
- IMPLEMENTADO: Clientes y Presupuestos bajo /api/clientes/ y /api/presupuestos/ (SPEC-003).
- IMPLEMENTADO: Obras, participantes, turnos, gastos, cierre bajo /api/obras/ y /api/categorias-servicio/ (SPEC-004/004B).
- IMPLEMENTADO: documentos externos, pagos y cobranzas bajo /api/finanzas/ (SPEC-007).
- IMPLEMENTADO: Auditoría global bajo `/api/auditoria/eventos/` (SPEC-008, PR #27) y Alertas bajo `/api/alertas/` (SPEC-009, PR #30), con sus tests y CI verificados.
- IMPLEMENTADO: Dashboard gerencial bajo `/api/dashboard/` (SPEC-010, PR #34): resumen, serie de finalizaciones y Obras en proceso; acceso solo Gerencia.
- IMPLEMENTADO: Reportes bajo `/api/reportes/` (SPEC-011, PR #37): catálogo, listados de Obras, Rentabilidad y Cobranzas, y exportaciones auténticas CSV/XLSX/PDF.
- PROPUESTA: SPEC-012A integración segura MongoDB: proyección eventual de `EvidenciaTurno` en `documentos_metadata`, reconciliación y lectura protegida. PostgreSQL sigue siendo fuente oficial; colección no integrada funcionalmente todavía.

## 2. Prioridades y contratos propuestos
1. **INTEGRADA — SPEC-008 Auditoría global:** GET `/api/auditoria/eventos/` (PR #27).
2. **INTEGRADA — SPEC-009 Alertas:** GET `/api/alertas/`, `/resumen/`, `/{id}/`, `/{id}/historial/` y POST `/{id}/atender/` (PR #30).
3. **INTEGRADA — SPEC-010 Dashboard:** GET `/api/dashboard/resumen/`, `/serie-obras/`, `/obras-activas/`; solo Gerencia; métricas consistentes, neto/bruto separado, sin margen proyectado (PR #34).
4. **INTEGRADA — SPEC-011 Reportes:** GET `/api/reportes/catalogo/`, `/obras/`, `/rentabilidad/`, `/cobranzas/`, `/{tipo}/exportar/`; PDF/XLSX/CSV reales (PR #37).
5. **PROPUESTA — SPEC-012A MongoDB:** endurecimiento de MongoDB 8.0, `pymongo` y metadatos de evidencias proyectados, reconciliación idempotente, GET `/api/documentos-metadata/?obra=<id>&page=<n>`, sin doble escritura de negocio. **No implementada.**

La numeración representa un orden sugerido, no una dependencia de ejecución obligatoria. Cada equipo puede preparar su rama desde main actualizado, sin modificar dominios ajenos salvo integraciones expresas revisadas. Alertas y Auditoría pueden renderizarse independientemente de Dashboard.

## 3. Reglas transversales
- Roles FYAG: GERENCIA, ADMINISTRATIVO_FINANZAS, SUPERVISOR_OBRAS, TECNICO, ADMINISTRADOR_TI. El backend controla RBAC; no confiar en navegador, flags Django, claims manipulados o prototipos React. TI jamás recibe negocio; Técnico nunca visualiza costos internos.
- Fuentes de verdad: PostgreSQL, presupuesto neto, CierreCostosObra inmutable y consultas de Finanzas para saldos y vencimiento. Prohibidos floats, mezclar montos netos y brutos o contar un pago como nueva facturación. MongoDB, cuando se implemente SPEC-012A aprobada, será exclusivamente una proyección documental eventual y no una fuente autorizante ni financiera.
- Versionado: rutas y JSON exactos, tipos/enum/nulabilidad, 25 filas por página salvo cursor auditoría, fechas ISO8601 civil Santiago, dinero decimal string con dos decimales, filtros estrictos. 400/401/403/404/405/409 estables; 413/429 para exportación controlada.
- Espejismo del prototipo: Obra no registra porcentaje de avance validado; queda prohibida la alerta de desviación costo-avance que mostraba React. No usar fixtures ni cálculos simulados como API.
- Seguridad: JWT/CSRF/CORS existentes, no exponer secretos, evidencia privada, fórmulas de hojas de cálculo inyectadas ni reportes con tokens en querystring.
- Verificaciones: pruebas PostgreSQL real, concurrencia, performance, regresión, migración limpia/upgrade, rol negativo y Postman completo para revisión manual. Documentar OpenAPI y ejemplos.

## 4. Definición de «backend listo para frontend»
1. SPEC revisada y congelada para rutas, inputs, outputs, errores, fechas, dinero, paginación y permisos.
2. Implementación de la API por compañeros, con tests de contrato reales y trazabilidad.
3. Backend CI en verde y regresión del sistema existente.
4. Colección Postman completa y ejecutada por el responsable, con reporte passed/failed.
5. PR de código con explicación técnica, límites, migraciones, decisiones, CI y rollback; merge autorizado.
6. Contratos publicados y versionados (OpenAPI), frontend puede consumirlos directamente sin inventar cálculos ni introducir cambios de backend.

**Las APIs de Auditoría, Alertas, Dashboard y Reportes están integradas en `main`.** MongoDB continúa sin conexión funcional desde Django hasta implementar y validar SPEC-012A. El prototipo frontend debe consumir únicamente rutas reales, no cifras simuladas, y manejar archivos binarios de Reportes con autenticación.

## 5. Responsabilidades y secuencia de colaboración

**OpenCode implementa el backend y sus pruebas**; ChatGPT redacta las SPEC, entrega en el chat un prompt técnico completo por incremento, revisa el informe de implementación, audita los commits/PR y su CI en GitHub, y prepara la suite Postman cuando sea necesario. El usuario ejecuta la suite y comunica resultados; sus compañeros desarrollan el frontend y consumen los endpoints publicados.

Orden: **SPEC → prompt completo de ChatGPT → implementación local OpenCode → informe de lo realizado → revisión → commit y push descriptivos por OpenCode → auditoría GitHub/CI → Postman si aplica → merge autorizado**. No dejar prompts como archivos de instrucciones en el repositorio; solo requisitos en `specs/`. Cuando se suba o modifique una SPEC, ChatGPT avisará que se debe actualizar la copia local, indicando el comando de Git apropiado a la rama.

## 6. Fuentes de referencia

`specs/001-backend-structure.md`, SPEC-003 a SPEC-012, `backend/config/urls.py`, `compose.yaml`, `database/*.js` y aplicaciones Django registradas.
